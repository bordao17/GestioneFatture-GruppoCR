"""Le route dei D.D.T.: CRUD sui registri, PDF, riepilogo ed estrazione.

Tutto cio' che si fa a una bolla: leggerla, correggerla, forzarne lo stato,
unirla a un'altra, rianalizzarla, cancellarla, vederne il PDF. C'e' anche
POST /estrai-ddt, che di questo flusso e' l'ingresso vero e proprio.

Le route con un corpo bloccante restano `def` e non `async def` — sta scritto
accanto a ognuna: dentro una route async terrebbero fermo l'event loop e
nessun'altra richiesta verrebbe servita durante un'estrazione, compresa
/api/elaborazione.
"""

import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import FileResponse

from src.api.lavorazione import elabora_ddt
from src.api.supporto import (
    annota_stato_piva, ricontrolla_fatture_in_attesa, sposta_documento, trova_documento,
)
from src.comune import stato_elaborazione
from src.comune.memory_manager import aggiorna_fornitore, conferma_partita_iva
from src.comune.normalizzatore import normalizza_partita_iva
from src.comune.pdf_writer import salva_pdf_multipagina
from src.comune.percorsi import CARTELLA_DDT
from src.comune.registro import (
    aggiorna_registro, leggi_registro, rimuovi_dal_registro,
    aggiorna_documento_registro, percorso_pdf_documento,
)
from src.comune.tempo import timestamp_locale
from src.ddt.accorpatore import unisci_documenti_manuale
from src.ddt.classificatore import determina_stato, CAMPI_OBBLIGATORI
from src.ddt.llm_engine import estrai_dati_da_immagine
from src.ddt.notificatore import calcola_riepilogo
from src.ddt.pdf_processor import converti_pdf_in_immagini
from src.ddt.raggruppatore import unisci_dati_pagina
from src.fatture.coda import completate_da

router = APIRouter()


@router.get("/api/documents")
async def get_all_documents():
    """Restituisce tutti i documenti dai registri OK, CHECK e KO"""
    tutti_documenti = []
    
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for doc in registro:
                doc['status'] = stato
                tutti_documenti.append(doc)
    
    return annota_stato_piva(tutti_documenti)

@router.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """Restituisce un documento specifico per ID"""
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for doc in registro:
                if doc.get('id') == doc_id:
                    doc['status'] = stato
                    return annota_stato_piva([doc])[0]
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@router.post("/api/documents/manuale")
def crea_documento_manuale(
    file: UploadFile = File(...),
    fornitore: str = Form(""),
    numero_ddt: str = Form(""),
    data_ddt: str = Form(""),
    ragione_sociale_consegna: str = Form(""),
    indirizzo_consegna: str = Form(""),
    partita_iva: str = Form(""),
):
    """Inserisce un D.D.T. compilato a mano, senza passare dal modello AI.

    Serve per i documenti che l'utente ha già davanti e preferisce trascrivere:
    il file viene archiviato come tutti gli altri, ma i dati sono quelli digitati
    e NON vengono normalizzati — vale la stessa regola delle correzioni fatte da
    dashboard, quello che l'utente scrive a mano resta com'è.
    """
    estensione = os.path.splitext(file.filename or "")[1].lower()
    if estensione not in [".pdf", ".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Formato non supportato: carica un PDF o un'immagine.")

    dati = {
        "fornitore": fornitore.strip(),
        "numero_ddt": numero_ddt.strip(),
        "data_ddt": data_ddt.strip(),
        "ragione_sociale_consegna": ragione_sociale_consegna.strip(),
        "indirizzo_consegna": indirizzo_consegna.strip(),
        # Unica eccezione alla regola "quello che l'utente scrive a mano resta
        # com'e'": la P.IVA non e' un testo da leggere ma una CHIAVE, e "IT
        # 00159560366" e "00159560366" devono essere lo stesso valore ovunque.
        "partita_iva": normalizza_partita_iva(partita_iva),
        "leggibilita_bassa": False,
    }

    if not any(dati[campo] for campo in CAMPI_OBBLIGATORI):
        raise HTTPException(status_code=400, detail="Compila almeno un campo del documento.")

    # Stessa regola degli altri documenti: se manca qualcosa finisce in CHECK,
    # così un inserimento incompleto resta visibile tra quelli da verificare.
    stato, campi_trovati = determina_stato(dati, CAMPI_OBBLIGATORI)
    id_documento = str(uuid.uuid4())

    cartella_dest = os.path.join(CARTELLA_DDT, stato)
    os.makedirs(cartella_dest, exist_ok=True)
    path_pdf_dest = os.path.join(cartella_dest, f"{id_documento}.pdf")

    temp_dir = tempfile.mkdtemp()
    try:
        path_origine = os.path.join(temp_dir, f"upload{estensione}")
        with open(path_origine, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if estensione == ".pdf":
            # Già un PDF: archiviato com'è. Passare da immagine come fa
            # l'estrazione AI ne peggiorerebbe soltanto la qualità.
            shutil.copyfile(path_origine, path_pdf_dest)
        else:
            salva_pdf_multipagina(path_pdf_dest, [path_origine])
    except Exception as e:
        print(f"❌ Errore salvataggio documento manuale: {e}")
        raise HTTPException(status_code=500, detail=f"Impossibile salvare il file: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    anagrafica = {
        "id": id_documento,
        "file_origine": file.filename,
        "timestamp": timestamp_locale(),
        "inserimento": "manuale",
        "dati": dati,
    }
    aggiorna_registro(stato, anagrafica)

    # Anche i fornitori scritti a mano entrano nella memoria AI: sono anzi i più
    # affidabili, perché non passano da una lettura del modello.
    if dati["fornitore"]:
        try:
            aggiorna_fornitore(dati["fornitore"], "", dati["partita_iva"])
            # Una P.IVA digitata da chi ha il documento in mano non e' una
            # proposta da rivedere: e' gia' la conferma.
            if dati["partita_iva"]:
                chiave_piva, _ = conferma_partita_iva(dati["fornitore"], dati["partita_iva"])
                if not chiave_piva:
                    print(f"⚠️ Partita IVA '{dati['partita_iva']}' non valida: "
                          f"resta sul documento ma non entra in anagrafica.")
        except Exception as e:
            print(f"⚠️ Errore durante l'aggiornamento della memoria fornitori: {e}")

    print(f"✍️ Documento manuale registrato: id={id_documento}, stato={stato}")

    # Un DDT trascritto a mano è un DDT che prima non esisteva per il flusso
    # fatture: può completare una fattura ferma in coda.
    report_fatture = ricontrolla_fatture_in_attesa("inserimento manuale")

    return {
        "message": "Documento inserito manualmente",
        "id": id_documento,
        "stato": stato,
        "campi_trovati": campi_trovati,
        "fatture_sbloccate": report_fatture["sbloccate"],
    }

@router.put("/api/documents/{doc_id}")
def update_document(doc_id: str, updated_data: dict):
    """Aggiorna i dati estratti di un documento"""
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for i, doc in enumerate(registro):
                if doc.get('id') == doc_id:
                    # Aggiorna solo i dati estratti, mantieni metadata.
                    # Il registro usa la chiave 'dati' (come il frontend in lettura):
                    # scrivere anche 'extracted_data' duplicava il campo nel JSON.
                    doc['dati'] = updated_data.get('extracted_data', doc.get('dati', {}))


                    # Salva nel registro
                    aggiorna_documento_registro(stato, i, doc)

                    # La correzione a mano di un numero DDT letto male è il caso
                    # che sblocca gli abbinamenti "probabili": la fattura è
                    # esatta, era il documento a essere sbagliato.
                    report_fatture = ricontrolla_fatture_in_attesa("correzione manuale")

                    # Come nella rianalisi: la voce torna al modale senza
                    # passare da una GET, quindi lo stato della chiave va
                    # calcolato qui.
                    doc['status'] = stato
                    annota_stato_piva([doc])

                    return {
                        "message": "Documento aggiornato con successo",
                        "document": doc,
                        "fatture_sbloccate": report_fatture["sbloccate"],
                    }
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@router.put("/api/documents/{doc_id}/stato")
def cambia_stato_documento(doc_id: str, payload: dict):
    """Sposta un D.D.T. in un altro stato perché lo ha deciso chi lo sta rivedendo.

    determina_stato() sa contare i campi letti, non giudicare il documento: una
    bolla con tutti e quattro i campi pieni ma sbagliati resta OK, e una pagina
    inservibile (scansione doppia, foglio di un altro fornitore, retro bianco)
    non ha nessun modo di finire tra gli errori. Qui la classificazione la fa
    una persona con il PDF davanti, quindi lo stato scritto a mano vince su
    quello calcolato.

    I dati estratti non vengono toccati: per correggerli c'è
    PUT /api/documents/{doc_id}. Una rianalisi successiva ricalcola lo stato e
    sovrascrive questa scelta, ed è corretto così — è di nuovo l'utente a
    chiederla, sapendo che i dati vengono rifatti da capo.

    Body: {"stato": "OK" | "CHECK" | "KO"}.
    """
    stato_finale = str(payload.get("stato") or "").strip().upper()
    if stato_finale not in ["OK", "CHECK", "KO"]:
        raise HTTPException(status_code=400, detail="Stato non valido: usa OK, CHECK o KO.")

    stato_origine, indice, documento = trova_documento(doc_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    documento_aggiornato = dict(documento)

    if stato_finale != stato_origine:
        # Traccia la forzatura come si fa già per "inserimento", "unione" e
        # "rianalisi": a posteriori serve sapere che quello stato non l'ha
        # deciso il classificatore.
        documento_aggiornato['stato_manuale'] = timestamp_locale()

        try:
            sposta_documento(doc_id, stato_origine, indice, documento_aggiornato, stato_finale)
        except Exception as e:
            print(f"❌ Errore durante lo spostamento di {doc_id} in {stato_finale}: {e}")
            raise HTTPException(status_code=500, detail="Impossibile spostare il documento.")

        print(f"🔀 Stato forzato a mano per id={doc_id}: {stato_origine} → {stato_finale}")

    documento_aggiornato['status'] = stato_finale
    # Come nella rianalisi: la voce torna al modale, che da li' decide se la
    # P.IVA e' ancora da confermare.
    annota_stato_piva([documento_aggiornato])

    # Nessun ricontrollo delle fatture in coda, a differenza degli altri
    # interventi sui D.D.T.: l'abbinamento legge tutti e tre i registri
    # (STATI_DDT in abbinatore.py), quindi spostare una voce non la rende né
    # più né meno agganciabile. A contare sono i dati, che qui non cambiano.
    return {
        "message": "Stato del documento aggiornato",
        "id": doc_id,
        "stato": stato_finale,
        "stato_precedente": stato_origine,
        "document": documento_aggiornato,
    }

@router.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Elimina un documento dal registro e il file PDF associato"""
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for i, doc in enumerate(registro):
                if doc.get('id') == doc_id:
                    # Rimuovi dal registro
                    rimuovi_dal_registro(stato, i)
                    
                    # Elimina il file PDF associato se esiste
                    pdf_path = os.path.join(CARTELLA_DDT, stato, f"{doc_id}.pdf")
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                    
                    return {"message": "Documento eliminato con successo"}
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@router.post("/api/documents/unisci")
def unisci_documenti(payload: dict):
    """Unisce manualmente più documenti in un unico DDT multi-pagina.

    Serve quando l'accorpamento automatico non è scattato (tipicamente perché il
    modello ha letto un numero_ddt diverso su una pagina) e le pagine dello stesso
    documento sono finite separate, anche in tab diversi della dashboard.

    Body: {"ids": [...]} — l'ordine conta, il primo id è il documento principale.
    """
    ids = payload.get("ids") or []
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="Il campo 'ids' deve essere una lista.")

    try:
        risultato = unisci_documenti_manuale(ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"❌ Errore durante l'unione manuale: {e}")
        raise HTTPException(status_code=500, detail="Impossibile unire i documenti.")

    print(f"🧩 Unione manuale di {risultato['documenti_uniti']} documenti "
          f"({', '.join(risultato['stati_origine'])}) → {risultato['stato']} id={risultato['id']}")

    # L'unione cambia il documento che porta il numero DDT buono: quello che
    # prima non si abbinava adesso può farlo.
    report_fatture = ricontrolla_fatture_in_attesa("unione manuale")

    return {
        "message": "Documenti uniti con successo",
        **risultato,
        "fatture_sbloccate": report_fatture["sbloccate"],
    }

@router.post("/api/documents/{doc_id}/rianalizza")
def rianalizza_documento(doc_id: str):
    """Rimanda al modello un documento GIÀ archiviato, riscrivendone i dati estratti.

    Serve tipicamente dopo aver confermato una regola in memoria fornitori o
    dopo aver alzato PDF_RENDER_ZOOM: il PDF resta quello che è, cambia solo
    la lettura. La pipeline è la stessa di POST /estrai-ddt (rendering pagine →
    modello → normalizzazione → classificazione), applicata al PDF sul disco.

    I dati precedenti vengono sostituiti da quelli della nuova lettura, comprese
    eventuali correzioni manuali: è una scelta esplicita dell'utente dal modale.
    Se lo stato cambia, la voce e il PDF vengono spostati nel registro/cartella
    del nuovo stato mantenendo id e metadati (es. "inserimento": "manuale").
    """
    # 1. Localizza la voce nel registro del suo stato
    stato_origine, indice, documento = None, None, None
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        for i, doc in enumerate(registro):
            if doc.get('id') == doc_id:
                stato_origine, indice, documento = stato, i, doc
                break
        if documento:
            break

    if not documento:
        raise HTTPException(status_code=404, detail="Documento non trovato")

    path_pdf = percorso_pdf_documento(stato_origine, doc_id)
    if not path_pdf:
        raise HTTPException(status_code=404, detail=f"PDF non trovato per ID: {doc_id}")

    print(f"🔁 Rianalisi documento id={doc_id} (stato attuale: {stato_origine})")
    t_totale_inizio = time.time()
    id_lavoro = stato_elaborazione.inizia(documento.get("file_origine") or doc_id, tipo="rianalisi")

    temp_dir = tempfile.mkdtemp()
    try:
        immagini = converti_pdf_in_immagini(path_pdf, cartella_output=os.path.join(temp_dir, "pages"))
        if not immagini:
            raise HTTPException(status_code=400, detail="Il PDF non contiene pagine leggibili.")
        stato_elaborazione.imposta_totale(id_lavoro, len(immagini))

        # 2. Una lettura per pagina, poi fusione: il documento è già accorpato,
        #    quindi le pagine appartengono per definizione allo stesso DDT e non
        #    va rifatto il confronto numero_ddt/fornitore. Vale la stessa regola
        #    dell'accorpamento: la prima pagina vince, le altre riempiono i vuoti.
        dati_finali = {}
        for i, img_path in enumerate(immagini):
            t0 = time.time()
            stato_elaborazione.aggiorna_pagina(id_lavoro, i + 1)
            dati_pagina = estrai_dati_da_immagine(img_path) or {}
            print(f"⏱️ Rianalisi pagina {i + 1}/{len(immagini)}: {time.time() - t0:.2f} secondi")

            if i == 0:
                dati_finali = dict(dati_pagina)
            else:
                dati_finali = unisci_dati_pagina(dati_finali, dati_pagina)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Errore durante la rianalisi di {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Rianalisi fallita: {e}")
    finally:
        stato_elaborazione.termina(id_lavoro)
        shutil.rmtree(temp_dir, ignore_errors=True)

    # 3. Memoria fornitori: come nell'estrazione normale, il fornitore letto
    #    viene censito (o ritrovato) anche qui.
    fornitore_estratto = dati_finali.get("fornitore")
    if fornitore_estratto and str(fornitore_estratto).strip().lower() not in ["", "dato mancante", "nessuno"]:
        try:
            aggiorna_fornitore(str(fornitore_estratto).strip(), "", dati_finali.get("partita_iva"))
        except Exception as e:
            print(f"⚠️ Errore durante l'aggiornamento della memoria fornitori: {e}")

    stato_finale, campi_trovati = determina_stato(dati_finali, CAMPI_OBBLIGATORI)

    documento_aggiornato = dict(documento)
    documento_aggiornato['dati'] = dati_finali
    documento_aggiornato['rianalisi'] = timestamp_locale()

    # 4. Aggiorna i registri: in place se lo stato non cambia, altrimenti
    #    sposta la voce (e il PDF) nel registro/cartella del nuovo stato.
    sposta_documento(doc_id, stato_origine, indice, documento_aggiornato, stato_finale, path_pdf)

    documento_aggiornato['status'] = stato_finale
    # Lo stato della P.IVA va ricalcolato PRIMA di restituire la voce, come in
    # lettura: la rianalisi riscrive 'dati' ma la chiave sta in anagrafica, e
    # documento_aggiornato nasce da una copia del registro, dove
    # partita_iva_confermata non e' mai scritto. Senza questa riga il modale
    # riceve un documento senza il campo e rimette il pulsante "Conferma" su
    # una P.IVA gia' confermata da un'altra bolla dello stesso fornitore.
    annota_stato_piva([documento_aggiornato])
    print(f"✅ Rianalisi completata per id={doc_id}: {stato_origine} → {stato_finale} "
          f"({campi_trovati}/{len(CAMPI_OBBLIGATORI)} campi) in {time.time() - t_totale_inizio:.2f} secondi")

    # La rianalisi riscrive i dati estratti: se ha corretto il numero DDT, una
    # fattura in coda può chiudersi adesso.
    report_fatture = ricontrolla_fatture_in_attesa("rianalisi")

    return {
        "message": "Documento rianalizzato",
        "id": doc_id,
        "stato": stato_finale,
        "stato_precedente": stato_origine,
        "campi_trovati": campi_trovati,
        "pagine_analizzate": len(immagini),
        "document": documento_aggiornato,
        "fatture_sbloccate": report_fatture["sbloccate"],
    }

# ==========================================
# 5. ROUTING: VISUALIZZAZIONE PDF
# ==========================================
@router.get("/api/pdf/{doc_id}.pdf")
async def get_pdf(doc_id: str):
    """Restituisce fisicamente il file PDF forzandone la visualizzazione a schermo"""
    print(f"🔍 Cerco PDF per ID: {doc_id}")
    file_path = None
    
    # Usa os.path.join con la costante CARTELLA_DDT e gli stati
    for stato in ["OK", "CHECK", "KO"]:
        path = os.path.join(CARTELLA_DDT, stato, f"{doc_id}.pdf")
        print(f"  Controllo: {path}")
        
        if os.path.exists(path):
            file_path = path
            print(f"✅ Trovato: {path}")
            break
            
    # Ricerca di fallback nella root di CARTELLA_DDT (vecchi documenti)
    if not file_path:
        root_path = os.path.join(CARTELLA_DDT, f"{doc_id}.pdf")
        if os.path.exists(root_path):
             file_path = root_path
             print(f"✅ Trovato (root): {root_path}")
    
    if not file_path:
        print(f"💥 PDF non trovato per ID: {doc_id}")
        raise HTTPException(status_code=404, detail=f"PDF non trovato per ID: {doc_id}")
    
    return FileResponse(
        path=file_path, 
        media_type="application/pdf", 
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )

@router.get("/api/elaborazione")
async def stato_elaborazione_endpoint():
    """Cosa sta elaborando il backend in questo momento (barra di avanzamento).

    Deve restare velocissima e non bloccante: la dashboard la interroga a
    intervalli regolari mentre un'estrazione è in corso.
    """
    return stato_elaborazione.stato()

@router.get("/riepilogo")
async def riepilogo_endpoint(
    da: str = Query(..., description="Timestamp ISO 8601 es. 2026-08-09T10:30:00+02:00")
):
    # PATCH URL ENCODING: Ripristina il '+' che viene convertito in spazio dall'URL
    da_corretto = da.replace(" ", "+")
    
    try:
        da_timestamp = datetime.fromisoformat(da_corretto)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Timestamp non valido: '{da_corretto}'")

    try:
        riepilogo = calcola_riepilogo(da_timestamp)
        # Le fatture chiuse dai DDT di questa elaborazione: è l'unico posto in
        # cui l'informazione può comparire nella mail di riepilogo, perché i
        # registri DDT non la contengono.
        riepilogo["fatture_completate"] = completate_da(da_timestamp)
        return riepilogo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/estrai-ddt")
def analizza_documento(file: UploadFile = File(...)):
    """Upload di una scansione e sua elaborazione immediata (è quel che fa n8n).

    Sincrona di proposito: vedi elabora_ddt(). Non riconvertirla in async def.
    """
    temp_dir = tempfile.mkdtemp()
    nome_file = file.filename or "documento.pdf"
    file_path = os.path.join(temp_dir, os.path.basename(nome_file))

    try:
        t0 = time.time()
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"⏱️ Salvataggio file caricato: {time.time() - t0:.2f} secondi")

        return elabora_ddt(file_path, nome_file)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
