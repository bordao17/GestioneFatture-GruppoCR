"""I due corpi di elaborazione, tirati fuori dalle route che li usano.

elabora_ddt() e elabora_fattura() hanno due chiamanti ciascuno — l'upload
singolo e la scansione della cartella in ingresso — e la ragione per cui stanno
in un modulo loro e' sempre quella: il file caricato a mano e quello depositato
in da_leggere/ devono percorrere la STESSA pipeline, non due copie che
divergono al primo ritocco.

Sono sincrone di proposito, e per lo stesso motivo vanno chiamate solo da route
sincrone: il corpo e' tutto bloccante (rendering, chiamata al modello,
scrittura su disco) e dentro una route async terrebbe fermo l'event loop,
rendendo irraggiungibile /api/elaborazione, cioe' proprio la barra che quel
lavoro dovrebbe raccontarlo.
"""

import os
import shutil
import tempfile
import time
import uuid

from fastapi import HTTPException

from src.api.supporto import ricontrolla_fatture_in_attesa
from src.comune import stato_elaborazione
from src.comune.memory_manager import (
    aggiorna_fornitore, registra_fornitore_fattura, verifica_fornitore_fattura,
)
from src.comune.pdf_writer import salva_pdf_multipagina
from src.comune.percorsi import CARTELLA_DDT
from src.comune.registro import aggiorna_registro
from src.comune.tempo import timestamp_locale
from src.ddt.accorpatore import accorpa_documenti
from src.ddt.classificatore import determina_stato, CAMPI_OBBLIGATORI
from src.ddt.impronte import CAMPO_FIRME, firma_pagina, firme_archiviate
from src.ddt.llm_engine import estrai_dati_da_immagine
from src.ddt.pdf_processor import converti_pdf_in_immagini
from src.fatture.abbinatore import carica_documenti, classifica_fattura, DA_ABBINARE
from src.fatture.coda import registra_senza_abbinare, trova_fattura_registrata
from src.fatture.lettore_xml import leggi_fattura


def elabora_ddt(file_path, nome_file):
    """Estrae, classifica e archivia un PDF/immagine di D.D.T. già su disco.

    È il corpo di /estrai-ddt, tirato fuori dalla route perché lo usa anche la
    scansione della cartella in ingresso (POST /api/ddt/scansiona): il file
    caricato da n8n e quello depositato in DDT/da_leggere devono percorrere la
    stessa identica pipeline, non due copie che divergono.

    Sincrona di proposito, e per lo stesso motivo va chiamata solo da route
    sincrone: il corpo è tutto bloccante (rendering, chiamata al modello,
    scrittura su disco) e dentro una route async terrebbe fermo l'event loop,
    rendendo irraggiungibile qualsiasi altra chiamata — compresa
    /api/elaborazione, cioè proprio la barra di avanzamento.
    """
    t_totale_inizio = time.time()
    print(f"🚀 Apertura file: {nome_file}")

    temp_dir = tempfile.mkdtemp()
    id_lavoro = stato_elaborazione.inizia(nome_file, tipo="estrazione")

    try:
        # 1. SPLIT: Divido il PDF in immagini, una per pagina
        t0 = time.time()
        immagini = []
        if nome_file.lower().endswith('.pdf'):
            immagini = converti_pdf_in_immagini(file_path, cartella_output=os.path.join(temp_dir, "pages"))
        elif nome_file.lower().endswith(('.jpg', '.jpeg', '.png')):
            immagini = [file_path]
        else:
            raise HTTPException(status_code=400, detail="Formato non supportato.")
        print(f"⏱️ [2/4] Conversione PDF → {len(immagini)} immagini: {time.time() - t0:.2f} secondi")
        stato_elaborazione.imposta_totale(id_lavoro, len(immagini))

        risultati_pagine = []
        duplicati = []

        # Le pagine gia' archiviate, lette una volta sola per batch. Il
        # dizionario cresce strada facendo, cosi' il confronto copre anche le
        # pagine appena lette in QUESTO file: un PDF che contiene due volte la
        # stessa scansione si riconosce da solo, senza essere gia' in archivio.
        archivio_firme = firme_archiviate()

        # 2. ELABORAZIONE SINGOLO DDT (una pagina = un documento)
        for i, img_path in enumerate(immagini):
            id_generico = str(uuid.uuid4())
            stato_elaborazione.aggiorna_pagina(id_lavoro, i + 1)

            # DUPLICATO: si controlla PRIMA di chiamare il modello. Costa un
            # hash (millisecondi) e ne risparmia sei secondi di GPU condivisa,
            # ma soprattutto evita di archiviare una seconda voce che
            # l'accorpamento poi assorbirebbe in silenzio come pagina in piu'
            # del documento gia' presente. Qui non si archivia niente e non si
            # scrive nessun PDF: la pagina buona e' gia' sotto DDT/lette/.
            firma = firma_pagina(img_path)
            if firma and firma in archivio_firme:
                gia_visto = archivio_firme[firma]
                print(f"↩️ Pagina {i + 1}/{len(immagini)}: gia' archiviata "
                      f"(id={gia_visto['id']}, {gia_visto['stato']}), saltata.")
                duplicati.append({
                    "file_origine": nome_file,
                    "pagina": i + 1,
                    "id_originale": gia_visto["id"],
                    "stato_originale": gia_visto["stato"],
                })
                continue

            print(f"🤖 Analisi pagina {i + 1}/{len(immagini)} (id={id_generico}) in corso...")

            t0 = time.time()
            dati_estratti = estrai_dati_da_immagine(img_path)
            t_modello = time.time() - t0
            print(f"⏱️ [3/4] Pagina {i + 1}: chiamata al modello Ollama: {t_modello:.2f} secondi")

            if not dati_estratti:
                dati_estratti = {}

            # =======================================================
            # SALVATAGGIO AUTOMATICO NUOVO FORNITORE IN MEMORIA
            # =======================================================
            fornitore_estratto = dati_estratti.get("fornitore")
            if fornitore_estratto and str(fornitore_estratto).strip().lower() not in ["", "dato mancante", "nessuno"]:
                try:
                    # Inserisce il fornitore se non esiste già
                    aggiorna_fornitore(str(fornitore_estratto).strip(), "",
                                       dati_estratti.get("partita_iva"))
                except Exception as e:
                    print(f"⚠️ Errore durante l'aggiornamento della memoria fornitori: {e}")
            # =======================================================

            stato, campi_trovati = determina_stato(dati_estratti, CAMPI_OBBLIGATORI)

            if dati_estratti.get("leggibilita_bassa"):
                print(f"⚠️  Pagina {i + 1} segnalata come poco leggibile dal modello.")

            cartella_dest = os.path.join(CARTELLA_DDT, stato)
            os.makedirs(cartella_dest, exist_ok=True)

            t0 = time.time()
            path_pdf_dest = os.path.join(cartella_dest, f"{id_generico}.pdf")
            salva_pdf_multipagina(path_pdf_dest, [img_path])
            print(f"⏱️ [4/4] Pagina {i + 1}: salvataggio PDF su disco: {time.time() - t0:.2f} secondi")

            # La firma segue la voce, in tutti e tre gli stati: e' l'identita'
            # della pagina, non un dato estratto, quindi vale anche per un KO —
            # rileggere una pagina illeggibile darebbe un secondo KO identico.
            firme = [firma] if firma else []

            if stato in ["OK", "CHECK"]:
                anagrafica = {
                    "id": id_generico,
                    "file_origine": nome_file,
                    "timestamp": timestamp_locale(),
                    CAMPO_FIRME: firme,
                    "dati": dati_estratti
                }
                aggiorna_registro(stato, anagrafica)
            else:  # KO: nessun dato utile estratto, salviamo solo un riferimento minimo
                anagrafica_ko = {
                    "id": id_generico,
                    "file_origine": nome_file,
                    "timestamp": timestamp_locale(),
                    CAMPO_FIRME: firme,
                }
                aggiorna_registro(stato, anagrafica_ko)

            if firma:
                archivio_firme[firma] = {"id": id_generico, "stato": stato}

            risultati_pagine.append({
                "id": id_generico,
                "stato": stato,
                "campi_trovati": campi_trovati
            })

        # 3. ACCORPAMENTO A POSTERIORI: unisce le pagine di questo PDF che
        #    risultano appartenere allo stesso DDT multi-pagina (stesso
        #    numero_ddt + fornitore), fondendo PDF e voci JSON già scritte.
        t0 = time.time()
        report_accorpamento = accorpa_documenti()
        print(f"🔗 Accorpamento completato in {time.time() - t0:.2f} secondi: {report_accorpamento}")

        # 4. RICONTROLLO DELLE FATTURE IN CODA: stesso principio "a posteriori"
        #    dell'accorpamento, e stesso posto. I DDT appena archiviati possono
        #    completare fatture arrivate giorni fa e rimaste in attesa.
        report_fatture = ricontrolla_fatture_in_attesa("estrazione")

        print(f"✅ Elaborazione completata per {nome_file} in {time.time() - t_totale_inizio:.2f} secondi totali")
        return {
            "status": "success",
            "filename": nome_file,
            "pagine_elaborate": risultati_pagine,
            # Va detto, non lasciato succedere: un file scartato per intero
            # perche' gia' letto e una risposta con zero pagine si assomigliano
            # troppo, e la seconda sembra un errore.
            "duplicati": duplicati,
            "accorpamento": report_accorpamento,
            "fatture_sbloccate": report_fatture["sbloccate"],
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Errore critico: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Anche in caso di errore: senza questa riga la barra resterebbe accesa
        # per sempre in dashboard.
        stato_elaborazione.termina(id_lavoro)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


def elabora_fattura(nome_file, contenuto):
    """Legge, controlla e archivia una fattura elettronica già in memoria.

    Corpo di /abbina-fattura, condiviso con la scansione della cartella in
    ingresso (POST /api/fatture/scansiona) per la stessa ragione di
    elabora_ddt(): due strade per lo stesso file devono restare una strada sola.
    """
    estensione = os.path.splitext(nome_file)[1].lower()
    if estensione not in [".xml", ".p7m"]:
        raise HTTPException(status_code=400, detail="Formato non supportato: carica un file .xml o .xml.p7m.")

    print(f"🧾 Lettura fattura: {nome_file}")
    t_totale_inizio = time.time()

    try:
        fatture = leggi_fattura(contenuto)
    except ValueError as e:
        print(f"❌ Fattura {nome_file} non leggibile: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"❌ Errore lettura fattura {nome_file}: {e}")
        raise HTTPException(status_code=500, detail=f"Impossibile leggere la fattura: {e}")

    # I DDT archiviati si leggono una volta sola: con la fattura a lotti sarebbe
    # una rilettura dei tre registri per ogni corpo fattura.
    documenti = carica_documenti()
    risultati = []

    for fattura in fatture:
        numero_fattura = fattura.get("numero_fattura", "")
        fornitore = fattura.get("fornitore", "")
        partita_iva = fattura.get("partita_iva", "")
        intestazione = {
            "numero_fattura": numero_fattura,
            "data_fattura": fattura.get("data_fattura", ""),
            "fornitore": fornitore,
            "partita_iva": partita_iva,
        }

        # 1. CONTROLLO DEL CEDENTE. Non è più un filtro: dal 2026-09-08 le
        #    fatture si caricano a mano dalla dashboard, quindi il fatto che
        #    qualcuno l'abbia scelta è già l'autorizzazione, e scartarla la
        #    farebbe solo sparire. Restano le segnalazioni sulla P.IVA — la
        #    sola chiave esatta fra i due lati del sistema: se manca, o se
        #    contraddice una P.IVA già confermata per quel fornitore, la
        #    fattura si archivia lo stesso ma se lo porta scritto addosso.
        try:
            segnalazioni, _chiave = verifica_fornitore_fattura(fornitore, partita_iva)
            registra_fornitore_fattura(fornitore, partita_iva)
        except Exception as e:
            print(f"⚠️ Anagrafica fornitori non aggiornabile ({e}): la fattura {numero_fattura} viene archiviata comunque.")
            segnalazioni = []

        for segnalazione in segnalazioni:
            print(f"⚠️ Fattura {numero_fattura} di '{fornitore}': {segnalazione['messaggio']}")

        # 2. DEDUPLICA.
        registro_esistente, voce_esistente = trova_fattura_registrata(fattura)
        if voce_esistente:
            print(f"↩️ Fattura {numero_fattura} già registrata "
                  f"({voce_esistente.get('stato')}, id={voce_esistente.get('id')}): ignorata.")
            risultati.append({
                **intestazione,
                "id": voce_esistente.get("id", ""),
                "stato": "DUPLICATA",
                "motivo": f"già registrata come {voce_esistente.get('stato')}",
                "ddt_totali": len(voce_esistente.get("ddt", [])),
                "ddt_abbinati": sum(1 for r in voce_esistente.get("ddt", []) if r.get("esito") == "abbinato"),
                "ddt": [],
            })
            continue

        # 3. ARCHIVIAZIONE, SENZA ABBINARE.
        #    Leggere una fattura e cercarle i DDT sono due gesti diversi, e da
        #    oggi lo sono anche nel codice: qui la fattura entra in coda come
        #    DA_ABBINARE, con i suoi riferimenti già estratti ma nessun
        #    confronto fatto. L'abbinamento lo chiede l'operatore, sulla
        #    singola fattura (ABBINA) o su tutta la coda (Abbina tutte).
        #    Il tipo (differita / accompagnatoria / senza_ddt) si decide invece
        #    subito: dipende solo dalla struttura dell'XML, non dai DDT, ed è
        #    ciò che dirà COSA cercare quando l'abbinamento verrà chiesto.
        tipo = classifica_fattura(fattura)
        try:
            voce = registra_senza_abbinare(fattura, tipo, nome_file, contenuto, estensione,
                                           segnalazioni)
        except Exception as e:
            print(f"❌ Errore archiviazione della fattura {numero_fattura}: {e}")
            raise HTTPException(status_code=500, detail=f"Impossibile archiviare la fattura: {e}")

        righe = voce.get("ddt", [])
        print(f"📥 Fattura {numero_fattura} ({tipo}) archiviata: "
              f"{len(righe)} riferimenti DDT, da abbinare. id={voce['id']}")

        risultati.append({
            **intestazione,
            "id": voce["id"],
            "stato": DA_ABBINARE,
            "tipo": tipo,
            "motivo": "",
            "segnalazioni": segnalazioni,
            "ddt_totali": len(righe),
            "ddt_abbinati": 0,
            "attesa": voce.get("attesa", {}),
            # Solo l'essenziale per riga: serve alla mail di n8n per dire QUALI
            # DDT non sono stati trovati, non a ricostruire l'abbinamento (per
            # quello c'è GET /api/fatture/{id}).
            "ddt": [
                {chiave: riga[chiave] for chiave in ("numero_ddt", "data_ddt", "esito", "motivo")}
                for riga in righe
            ],
        })

    print(f"✅ Fattura {nome_file} elaborata in {time.time() - t_totale_inizio:.2f} secondi")
    return {"status": "success", "filename": nome_file, "fatture": risultati}
