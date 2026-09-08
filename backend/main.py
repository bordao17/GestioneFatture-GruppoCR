# ==========================================
# 1. IMPORTS & SETUP APP
# ==========================================
import os
import logging
import shutil
import tempfile
import uuid
import time
from datetime import datetime, timezone
import json
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import uvicorn

from src.ddt.pdf_processor import converti_pdf_in_immagini
from src.ddt.llm_engine import estrai_dati_da_immagine
from src.ddt.classificatore import determina_stato, CAMPI_OBBLIGATORI
from src.comune.registro import (
    aggiorna_registro, leggi_registro, rimuovi_dal_registro,
    aggiorna_documento_registro, salva_registro, percorso_pdf_documento,
)
from src.comune.pdf_writer import salva_pdf_multipagina
from src.ddt.accorpatore import accorpa_documenti, unisci_documenti_manuale
from src.ddt.raggruppatore import unisci_dati_pagina
from src.ddt.notificatore import calcola_riepilogo
from src.comune.memory_manager import (
    carica_memoria, salva_memoria, aggiorna_fornitore, registra_fornitore_fattura,
    conferma_partita_iva, partita_iva_per, verifica_fornitore_fattura,
)
from src.comune.normalizzatore import normalizza_partita_iva
from src.comune import stato_elaborazione
from src.comune.percorsi import (
    CARTELLA_ACCOPPIATE, CARTELLA_DDT, CARTELLA_DDT_INGRESSO, CARTELLA_FATTURE,
    CARTELLA_FATTURE_INGRESSO, REGISTRO_FATTURE, REGISTRO_ATTESA,
)
from src.comune.configurazione import configurazione_completa, salva_configurazione
from src.comune.tempo import timestamp_locale
from src.fatture.lettore_xml import leggi_fattura
from src.fatture.abbinatore import (
    carica_documenti, dimentica_fattura, classifica_fattura,
    ABBINATA, DA_ABBINARE, IN_ATTESA,
)
from src.fatture.coda import (
    abbina_tutte, anteprima_fascicolo, completate_da, fatture_da_accoppiare,
    fatture_in_attesa, conferma_accoppiamento, ddt_senza_fattura,
    giorni_accoppiamento, giorni_in_attesa, giorni_sollecito, percorso_fascicolo,
    proponi_accoppiamento, registra_senza_abbinare, ricontrolla_attese,
    trova_fattura, trova_fattura_registrata,
)

# La dashboard interroga /api/elaborazione ogni 2 secondi per tenere viva la
# barra di avanzamento: e' una lettura di un dizionario in memoria, non pesa
# nulla, ma la sua riga di access log si ripete 30 volte al minuto e sommerge i
# print pagina-per-pagina dell'estrazione. Qui si tace solo quella riga.
class FiltroPollingBarra(logging.Filter):
    def filter(self, record):
        return "/api/elaborazione" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(FiltroPollingBarra())

app = FastAPI(
    title="GestioneFatture - GruppoCR API",
    description="Microservizio AI per l'estrazione dati da DDT e Fatture",
    version="1.0.0"
)

# Abilita CORS per il frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Senza expose_headers il browser nasconde al JavaScript ogni header non
    # standard: X-Fascicolo-Anteprima esiste proprio perche' la dashboard possa
    # dire che il fascicolo mostrato e' provvisorio, e da cross-origin non
    # sarebbe leggibile.
    expose_headers=["X-Fascicolo-Anteprima"],
)

# ==========================================
# 2. CONFIGURAZIONI & COSTANTI
# ==========================================
# timestamp_locale() vive in src/comune/tempo.py: lo scrivono anche i registri
# delle fatture, e due formati diversi romperebbero chi li rilegge per data.


def ricontrolla_fatture_in_attesa(motivo):
    """Riprova l'abbinamento delle fatture in coda dopo un evento sui DDT.

    Chiamata da TUTTI i punti in cui un DDT prima invisibile diventa
    abbinabile: fine estrazione, inserimento manuale, unione manuale, rianalisi
    e correzione a mano dei dati (quest'ultima è proprio il caso che sblocca gli
    abbinamenti "probabili", cioè le cifre lette male dal modello).

    Non deve mai far fallire l'operazione sui DDT che l'ha innescata: il
    documento è già stato archiviato, e una coda che esplode è un problema del
    flusso fatture, non di chi stava salvando una bolla.
    """
    try:
        report = ricontrolla_attese()
    except Exception as e:
        print(f"⚠️ Ricontrollo delle fatture in attesa fallito ({motivo}): {e}")
        return {"in_coda": 0, "sbloccate": [], "restano": 0}

    if report["sbloccate"]:
        print(f"🔓 {len(report['sbloccate'])} fatture completate dopo {motivo}")
    return report


def trova_documento(doc_id):
    """Cerca un D.D.T. nei tre registri: (stato, indice, documento), altrimenti None."""
    for stato in ["OK", "CHECK", "KO"]:
        for indice, doc in enumerate(leggi_registro(stato)):
            if doc.get('id') == doc_id:
                return stato, indice, doc

    return None, None, None


def sposta_documento(doc_id, stato_origine, indice, documento, stato_finale, path_pdf=None):
    """Riscrive la voce nel registro dello stato finale, portandosi dietro il PDF.

    Se lo stato non cambia si limita ad aggiornare la voce dov'è. Il file deve
    seguire il registro: GET /api/pdf/{id}.pdf lo ritroverebbe comunque
    scorrendo gli stati, ma i due archivi resterebbero disallineati e il
    fallback esiste per i documenti vecchi, non per coprire uno spostamento
    fatto a metà.
    """
    if stato_finale == stato_origine:
        aggiorna_documento_registro(stato_origine, indice, documento)
        return

    origine = path_pdf or percorso_pdf_documento(stato_origine, doc_id)

    rimuovi_dal_registro(stato_origine, indice)
    aggiorna_registro(stato_finale, documento)

    if not origine:
        return

    destinazione = os.path.join(CARTELLA_DDT, stato_finale, f"{doc_id}.pdf")
    if os.path.abspath(origine) != os.path.abspath(destinazione):
        os.makedirs(os.path.dirname(destinazione), exist_ok=True)
        shutil.move(origine, destinazione)

# ==========================================
# 3. ROUTING: MEMORIA AI (FORNITORI)
# ==========================================
@app.get("/api/fornitori")
async def get_fornitori():
    """Legge la memoria attuale dell'AI sui fornitori"""
    try:
        return carica_memoria()
    except Exception as e:
        print(f"Errore lettura fornitori: {e}")
        return {}

@app.put("/api/fornitori")
async def update_fornitori(data: dict):
    """Sovrascrive il file JSON con le nuove istruzioni dell'utente"""
    try:
        salva_memoria(data)
        return {"message": "Memoria AI aggiornata con successo"}
    except Exception as e:
        print(f"Errore salvataggio fornitori: {e}")
        raise HTTPException(status_code=500, detail="Impossibile salvare la memoria fornitori.")

@app.put("/api/fornitori/partita-iva")
def conferma_piva_fornitore(payload: dict):
    """Conferma (o corregge) la partita IVA di un fornitore.

    E' il passaggio umano che rende la P.IVA una chiave utilizzabile: quella
    letta da una scansione entra in anagrafica come proposta, e finche' nessuno
    la guarda vale solo come promemoria. Si conferma dall'anagrafica oppure,
    con il PDF davanti, dal modale di revisione del D.D.T. — in quel caso il
    payload porta anche l'id del documento, che viene riallineato al valore
    confermato.
    """
    fornitore = str(payload.get("fornitore") or "").strip()
    partita_iva = str(payload.get("partita_iva") or "").strip()

    if not fornitore:
        raise HTTPException(status_code=400, detail="Manca il fornitore a cui associare la partita IVA.")

    chiave, piva_salvata = conferma_partita_iva(fornitore, partita_iva)
    if not chiave:
        raise HTTPException(
            status_code=400,
            detail="Partita IVA non valida: servono 11 cifre con carattere di controllo corretto.",
        )

    documento_aggiornato = None
    doc_id = str(payload.get("id") or "").strip()
    if doc_id:
        stato, indice, documento = trova_documento(doc_id)
        if documento:
            dati = documento.get("dati") or {}
            dati["partita_iva"] = piva_salvata
            dati.pop("partita_iva_scartata", None)
            documento["dati"] = dati
            aggiorna_documento_registro(stato, indice, documento)
            documento_aggiornato = dict(documento)
            documento_aggiornato["status"] = stato
            documento_aggiornato["partita_iva_anagrafica"] = piva_salvata
            documento_aggiornato["partita_iva_confermata"] = True

    return {
        "message": "Partita IVA confermata",
        "fornitore": chiave,
        "partita_iva": piva_salvata,
        "document": documento_aggiornato,
    }


# ==========================================
# 4. ROUTING: GESTIONE DOCUMENTI (CRUD)
# ==========================================
def annota_stato_piva(documenti):
    """Aggiunge a ogni documento lo stato della P.IVA del suo fornitore.

    Non e' un dato del documento e non viene mai scritto nei registri: la
    verita' sta in anagrafica, e una copia sul registro invecchierebbe alla
    prima conferma fatta da un'altra bolla dello stesso fornitore. Sta
    accanto a 'status', calcolato in lettura come lui.

    Serve al modale di revisione per decidere se la P.IVA e' ancora da
    confermare (campo editabile + pulsante) o e' gia' una chiave (campo in
    sola lettura: da li' in poi si corregge dall'anagrafica).

    La cache tiene la ricerca per somiglianza a una volta per nome distinto,
    non a una per documento.
    """
    memoria = carica_memoria()
    cache = {}
    for doc in documenti:
        nome = ((doc.get('dati') or {}).get('fornitore') or "").strip()
        if nome not in cache:
            cache[nome] = partita_iva_per(nome, memoria) if nome else ("", False)
        piva, confermata = cache[nome]
        doc['partita_iva_anagrafica'] = piva
        doc['partita_iva_confermata'] = bool(piva) and confermata
    return documenti


@app.get("/api/documents")
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

@app.get("/api/documents/{doc_id}")
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

@app.post("/api/documents/manuale")
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

@app.put("/api/documents/{doc_id}")
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

                    return {
                        "message": "Documento aggiornato con successo",
                        "document": doc,
                        "fatture_sbloccate": report_fatture["sbloccate"],
                    }
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@app.put("/api/documents/{doc_id}/stato")
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

@app.delete("/api/documents/{doc_id}")
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

@app.post("/api/documents/unisci")
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

@app.post("/api/documents/{doc_id}/rianalizza")
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
@app.get("/api/pdf/{doc_id}.pdf")
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

@app.get("/api/elaborazione")
async def stato_elaborazione_endpoint():
    """Cosa sta elaborando il backend in questo momento (barra di avanzamento).

    Deve restare velocissima e non bloccante: la dashboard la interroga a
    intervalli regolari mentre un'estrazione è in corso.
    """
    return stato_elaborazione.stato()

# ==========================================
# 6. ROUTING: RIEPILOGO STATISTICHE
# ==========================================
@app.get("/riepilogo")
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

# ==========================================
# 7. ROUTING CORE: ESTRAZIONE AI OLLAMA
# ==========================================
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

        # 2. ELABORAZIONE SINGOLO DDT (una pagina = un documento)
        for i, img_path in enumerate(immagini):
            id_generico = str(uuid.uuid4())
            stato_elaborazione.aggiorna_pagina(id_lavoro, i + 1)
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

            if stato in ["OK", "CHECK"]:
                anagrafica = {
                    "id": id_generico,
                    "file_origine": nome_file,
                    "timestamp": timestamp_locale(),
                    "dati": dati_estratti
                }
                aggiorna_registro(stato, anagrafica)
            else:  # KO: nessun dato utile estratto, salviamo solo un riferimento minimo
                anagrafica_ko = {
                    "id": id_generico,
                    "file_origine": nome_file,
                    "timestamp": timestamp_locale()
                }
                aggiorna_registro(stato, anagrafica_ko)

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


@app.post("/estrai-ddt")
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


# ==========================================
# 8. ROUTING: FATTURE XML (ABBINAMENTO AI DDT)
# ==========================================
@app.post("/abbina-fattura")
def abbina_fattura_endpoint(file: UploadFile = File(...)):
    """Legge una fattura elettronica (.xml o .xml.p7m) e la aggancia ai DDT archiviati.

    Qui il modello NON entra mai: i riferimenti ai DDT sono già strutturati
    dentro <DatiDDT>, quindi tutto il lavoro è parsing e confronto di stringhe.
    Un file può contenere più fatture (fattura a lotti): ognuna viene valutata
    per conto suo.

    Tre filtri prima dell'abbinamento vero e proprio:
      1. il cedente dev'essere un fornitore AUTORIZZATO in anagrafica — la
         cartella da cui arrivano gli XML contiene anche fatture che non ci
         riguardano. Il riconoscimento è per P.IVA, che è esatta, non per nome;
      2. la fattura non dev'essere già passata di qui (P.IVA + numero + data):
         il ramo n8n non svuota la cartella, quindi rilanciarlo ripassa gli
         stessi file;
      3. senza <DatiDDT> non c'è niente da aspettare e la pratica nasce chiusa
         come NON_ABBINATA.
    Ciò che resta incompleto NON è un esito ma una coda (IN_ATTESA): viene
    ricontrollato a ogni nuovo DDT finché si chiude.

    Sincrona come /estrai-ddt: il corpo scrive su disco e assembla PDF.
    """
    nome_file = file.filename or "fattura.xml"
    contenuto = file.file.read()
    return elabora_fattura(nome_file, contenuto)


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


# ==========================================
# 8-bis. LE DUE CARTELLE IN INGRESSO
# ==========================================
# Fino a ieri ci scriveva e ci passava sopra solo n8n. Da oggi la dashboard fa
# le stesse due cose (deposita i file, poi li elabora) senza dipendere da un
# workflow: n8n resta l'automatismo, questi sono i pulsanti per quando serve
# adesso. Sono le STESSE cartelle e la STESSA pipeline, non un secondo canale.

ESTENSIONI_DDT = (".pdf", ".jpg", ".jpeg", ".png")
ESTENSIONI_FATTURA = (".xml", ".p7m")


def _file_in_ingresso(cartella, estensioni):
    """I file lavorabili di una cartella, in ordine alfabetico."""
    if not os.path.isdir(cartella):
        return []
    return sorted(
        nome for nome in os.listdir(cartella)
        if nome.lower().endswith(estensioni)
        and os.path.isfile(os.path.join(cartella, nome))
    )


def _deposita(cartella, files, estensioni, etichetta):
    """Scrive gli upload nella cartella in ingresso, senza mai sovrascrivere.

    Un nome già presente prende un suffisso numerico: due bolle scansionate lo
    stesso giorno si chiamano spesso "scan.pdf", e una sovrascritta in silenzio
    è un documento perso — lo stesso motivo per cui il file unico in ACCOPPIATE
    porta in coda le cifre dell'id.
    """
    os.makedirs(cartella, exist_ok=True)
    caricati, scartati = [], []

    for file in files:
        nome = os.path.basename(file.filename or "")
        if not nome.lower().endswith(estensioni):
            scartati.append({"file": nome, "motivo": f"non è un file {etichetta}"})
            continue

        radice, estensione = os.path.splitext(nome)
        destinazione = os.path.join(cartella, nome)
        contatore = 2
        while os.path.exists(destinazione):
            destinazione = os.path.join(cartella, f"{radice}_{contatore}{estensione}")
            contatore += 1

        with open(destinazione, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        caricati.append(os.path.basename(destinazione))
        print(f"📂 {etichetta}: '{nome}' depositato come '{os.path.basename(destinazione)}'.")

    return caricati, scartati


@app.post("/api/ddt/carica")
def carica_ddt(files: List[UploadFile] = File(...)):
    """Deposita una o più scansioni in DDT/da_leggere, senza analizzarle.

    Caricare e analizzare restano due gesti: si possono mettere in coda dieci
    bolle in pochi secondi e far partire l'analisi (minuti, sulla GPU condivisa)
    una volta sola.
    """
    caricati, scartati = _deposita(CARTELLA_DDT_INGRESSO, files, ESTENSIONI_DDT, "D.D.T.")
    return {
        "caricati": caricati,
        "scartati": scartati,
        "in_attesa": len(_file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT)),
    }


@app.post("/api/fatture/carica")
def carica_fatture(files: List[UploadFile] = File(...)):
    """Deposita una o più fatture elettroniche in FATTURE/da_leggere."""
    caricati, scartati = _deposita(CARTELLA_FATTURE_INGRESSO, files, ESTENSIONI_FATTURA, "fattura")
    return {
        "caricati": caricati,
        "scartati": scartati,
        "in_attesa": len(_file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA)),
    }


@app.get("/api/ingresso")
async def stato_ingresso():
    """Quanti file aspettano nelle due cartelle: è il numero sul pulsante Analizza."""
    return {
        "ddt": _file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT),
        "fatture": _file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA),
    }


@app.post("/api/ddt/scansiona")
def scansiona_ddt():
    """Analizza tutte le scansioni ferme in DDT/da_leggere.

    Il file elaborato viene RIMOSSO dalla cartella. Non è una pulizia
    facoltativa: sui D.D.T. non esiste nessuna deduplica (due bolle possono
    legittimamente avere lo stesso numero, e la stessa pagina riletta produce un
    id nuovo), quindi lasciare il file lì significherebbe archiviare un
    duplicato a ogni click su Analizza. La scansione resta comunque nell'archivio
    come PDF sotto DDT/lette/<stato>/, che è la copia buona.
    Un file che fallisce resta dov'è: sarà riprovabile dopo aver capito perché.

    Sincrona: chiama elabora_ddt(), che è bloccante.
    """
    nomi = _file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT)
    print(f"📥 Scansione manuale di DDT/da_leggere: {len(nomi)} file da elaborare.")

    elaborati, falliti, sbloccate = [], [], []

    for nome in nomi:
        percorso = os.path.join(CARTELLA_DDT_INGRESSO, nome)
        try:
            esito = elabora_ddt(percorso, nome)
        except HTTPException as e:
            print(f"❌ '{nome}' non elaborato: {e.detail}")
            falliti.append({"file": nome, "motivo": str(e.detail)})
            continue
        except Exception as e:
            print(f"❌ '{nome}' non elaborato: {e}")
            falliti.append({"file": nome, "motivo": str(e)})
            continue

        elaborati.append({"file": nome, "pagine": len(esito["pagine_elaborate"])})
        sbloccate.extend(esito.get("fatture_sbloccate", []))
        try:
            os.remove(percorso)
        except OSError as e:
            print(f"⚠️ '{nome}' elaborato ma non rimosso dalla cartella ({e}): rimuovilo a mano, "
                  f"altrimenti la prossima analisi lo archivierà una seconda volta.")

    return {
        "elaborati": elaborati,
        "falliti": falliti,
        "pagine_totali": sum(e["pagine"] for e in elaborati),
        "fatture_sbloccate": sbloccate,
    }


@app.post("/api/fatture/scansiona")
def scansiona_fatture():
    """Legge e archivia tutte le fatture ferme in FATTURE/da_leggere.

    NON le abbina: dal 2026-09-08 leggere una fattura e cercarle i D.D.T. sono
    due gesti distinti, e il secondo lo chiede l'operatore (ABBINA su una riga,
    "Abbina tutte" sulla coda).

    Il file viene rimosso quando è stato archiviato o riconosciuto come
    duplicato — in entrambi i casi la fattura è già nei registri, e l'XML
    originale è conservato accanto alla voce, che è la copia che conta.
    """
    nomi = _file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA)
    print(f"📥 Scansione manuale di FATTURE/da_leggere: {len(nomi)} file da leggere.")

    lette, falliti = [], []

    for nome in nomi:
        percorso = os.path.join(CARTELLA_FATTURE_INGRESSO, nome)
        try:
            with open(percorso, "rb") as f:
                contenuto = f.read()
            esito = elabora_fattura(nome, contenuto)
        except HTTPException as e:
            print(f"❌ '{nome}' non letto: {e.detail}")
            falliti.append({"file": nome, "motivo": str(e.detail)})
            continue
        except Exception as e:
            print(f"❌ '{nome}' non letto: {e}")
            falliti.append({"file": nome, "motivo": str(e)})
            continue

        lette.extend(esito["fatture"])
        try:
            os.remove(percorso)
        except OSError as e:
            print(f"⚠️ '{nome}' letto ma non rimosso dalla cartella ({e}).")

    # Le anomalie sul cedente si tirano fuori appiattite: la barra di ingresso
    # deve poter dire "2 fatture con anomalie" senza aprire ogni voce. Restano
    # comunque scritte sulla pratica, perché chi le guarda spesso non è chi ha
    # premuto il pulsante.
    segnalate = [
        {
            "numero_fattura": f.get("numero_fattura", ""),
            "fornitore": f.get("fornitore", ""),
            "messaggi": [s["messaggio"] for s in f.get("segnalazioni", [])],
        }
        for f in lette if f.get("segnalazioni")
    ]

    return {
        "fatture": lette,
        "falliti": falliti,
        "totale": len(lette),
        "duplicate": sum(1 for f in lette if f.get("stato") == "DUPLICATA"),
        "segnalate": segnalate,
    }


# ==========================================
# 8-ter. CONFIGURAZIONE
# ==========================================
@app.get("/api/configurazione")
async def get_configurazione():
    """Le impostazioni modificabili, con valore attuale e provenienza.

    L'origine ('dashboard' / 'ambiente' / 'default') non è un dettaglio: senza,
    un campo pieno non direbbe se si sta guardando una modifica fatta di qui o
    il valore del docker-compose, e non si capirebbe cosa succede svuotandolo.
    """
    return {"impostazioni": configurazione_completa()}


@app.put("/api/configurazione")
async def put_configurazione(payload: dict):
    """Salva le impostazioni cambiate dalla dashboard.

    Un campo svuotato non è un errore: significa "torna al valore del
    docker-compose". I valori fuori intervallo vengono scartati e restituiti in
    'scartate', invece di essere accettati in silenzio.

    Hanno effetto subito, senza riavviare: chi le usa le rilegge a ogni
    chiamata (vedi src/comune/configurazione.py).
    """
    try:
        salvate, scartate = salva_configurazione(payload or {})
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Configurazione non salvata: {e}")

    if scartate:
        print(f"⚠️ Configurazione: valori scartati {scartate}")

    return {
        "message": "Configurazione salvata",
        "salvate": sorted(salvate),
        "scartate": scartate,
        "impostazioni": configurazione_completa(),
    }

@app.get("/api/fatture")
async def get_fatture():
    """Tutte le fatture, chiuse e in coda, con lo stato di ognuna.

    I due registri sono file separati (FATTURE.json e ATTESA.json) ma per la
    dashboard sono un elenco solo: lo stato è già dentro la voce, come per i DDT.
    """
    fatture = []

    # "in_coda" dice in quale registro sta la voce, e va detto esplicitamente:
    # da quando la chiusura e' manuale lo stato non basta piu' a distinguere una
    # pratica pronta (ABBINATA, ancora in coda: aspetta il pulsante ACCOPPIA) da
    # una gia' confermata (ABBINATA, in FATTURE.json: il file unico esiste).
    for voce in leggi_registro(REGISTRO_ATTESA):
        fatture.append({**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)})

    for voce in leggi_registro(REGISTRO_FATTURE):
        fatture.append({**voce, "in_coda": False})

    return fatture

@app.get("/api/fatture/attese")
async def get_fatture_attese(
    giorni: int = Query(None, ge=0, description="Solo le ferme da almeno N giorni (default: la soglia configurata)")
):
    """La coda: fatture i cui DDT non sono ancora tutti arrivati.

    È l'endpoint che alimenta la mail di sollecito di n8n. Senza parametro
    applica GIORNI_ATTESA_SOLLECITO (30 giorni, dalla sezione Configurazione o
    dal docker-compose): la soglia resta così un solo numero, qui, e il nodo n8n
    non ne conserva una copia che prima o poi divergerebbe. La dashboard passa esplicitamente ?giorni=0 per
    avere la coda intera.

    Le fatture sono divise per motivo, perché non si risolvono nello stesso
    modo: "attende_ddt" si sblocca da sola quando il documento viene scansionato,
    "da_confermare" no — il DDT probabilmente c'è già ma con un numero letto
    male, e finché nessuno lo corregge il ricontrollo darà sempre lo stesso
    risultato.
    """
    soglia = giorni_sollecito() if giorni is None else giorni
    voci = fatture_in_attesa(soglia)

    # Terza lista, e aspetta una cosa diversa dalle altre due: qui il documento
    # c'è (o non è ancora stato nemmeno cercato), manca un click in dashboard.
    # Ha una soglia sua, più corta, perché una pratica pronta non deve restare
    # ferma quanto una bolla che qualcuno deve andare a cercare in magazzino.
    soglia_accoppiamento = giorni_accoppiamento() if giorni is None else giorni
    da_accoppiare = fatture_da_accoppiare(soglia_accoppiamento)

    return {
        "soglia_giorni": soglia,
        "soglia_predefinita": giorni_sollecito(),
        "soglia_accoppiamento": soglia_accoppiamento,
        "totale": len(voci),
        "da_confermare": [v for v in voci if v.get("attesa", {}).get("da_confermare")],
        "attende_ddt": [v for v in voci if not v.get("attesa", {}).get("da_confermare")],
        "fatture": voci,
        "da_accoppiare": da_accoppiare,
        "totale_da_accoppiare": len(da_accoppiare),
    }

@app.get("/api/ddt/senza-fattura")
async def get_ddt_senza_fattura(
    giorni: int = Query(None, ge=0, description="Solo i DDT fermi da almeno N giorni (default: la soglia configurata)")
):
    """I DDT archiviati che nessuna fattura ha ancora agganciato.

    È il lato speculare di /api/fatture/attese: là le fatture a cui manca una
    bolla, qui le bolle a cui manca una fattura. Serve allo stesso sollecito
    mensile — con la differenza che da questo lato non c'è niente da
    ricontrollare: ogni fattura nuova viene confrontata con tutti i DDT
    archiviati, quindi un DDT che aspetta si aggancia da solo quando l'XML
    arriva. Se dopo un mese non è successo, o la fattura non è mai arrivata o è
    stata scartata dal filtro fornitori.
    """
    soglia = giorni_sollecito() if giorni is None else giorni
    voci = ddt_senza_fattura(soglia)

    return {
        "soglia_giorni": soglia,
        "soglia_predefinita": giorni_sollecito(),
        "totale": len(voci),
        "ddt": voci,
    }

@app.post("/api/fatture/ricontrolla")
def ricontrolla_fatture():
    """Riprova a mano l'abbinamento di tutte le fatture in coda.

    Normalmente non serve: il ricontrollo scatta da solo dopo ogni evento sui
    DDT (estrazione, inserimento manuale, unione, rianalisi, correzione dei
    dati). Resta utile dopo aver modificato l'anagrafica fornitori, che cambia
    il riconoscimento del fornitore e quindi gli abbinamenti possibili.
    """
    report = ricontrolla_fatture_in_attesa("richiesta manuale")
    return {"message": "Ricontrollo completato", **report}

@app.post("/api/fatture/abbina-tutte")
def abbina_tutte_le_fatture():
    """Cerca i D.D.T. di tutte le fatture in coda, comprese quelle mai abbinate.

    È il pulsante globale: /api/fatture/ricontrolla riguarda solo le pratiche
    che un abbinamento ce l'hanno già (e che possono essersi sbloccate da sole),
    questo prende anche le DA_ABBINARE, cioè quelle appena archiviate su cui
    nessuno ha ancora chiesto niente. Nessuna pratica si chiude: restano tutte
    in coda in attesa della firma sul singolo accoppiamento.
    """
    try:
        report = abbina_tutte()
    except Exception as e:
        print(f"❌ Abbinamento di tutta la coda fallito: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    print(f"🔗 Abbina tutte: {report['in_coda']} pratiche esaminate, "
          f"{len(report['sbloccate'])} pronte da accoppiare.")
    return {"message": "Abbinamento completato", **report}


@app.post("/api/fatture/{id_fattura}/accoppia")
def accoppia_fattura(id_fattura: str):
    """Primo tempo del pulsante ACCOPPIA: cerca i DDT di QUESTA fattura.

    Rifa' il confronto fra i riferimenti della fattura e tutti i DDT archiviati
    e restituisce la voce aggiornata, che l'interfaccia mostra nel modale.
    Non produce nessun file e non annota nessun DDT: e' una proposta, e a
    firmarla e' /conferma con l'operatore che ha appena visto cosa e' stato
    agganciato.

    Sincrona: rilegge i tre registri DDT da disco.
    """
    voce, errore = proponi_accoppiamento(id_fattura)

    if errore == "non trovata":
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if errore == "gia confermata":
        # Non e' un errore da mostrare come rosso: la pratica e' semplicemente
        # gia' chiusa, e l'interfaccia mostrera' il file unico.
        return {"message": "Accoppiamento gia' confermato", "confermata": True, "fattura": voce}

    riepilogo = voce.get("attesa") or {}
    return {
        "message": "Abbinamento ricalcolato",
        "confermata": False,
        "pronta": voce.get("stato") == ABBINATA,
        "abbinati": len([r for r in voce.get("ddt", []) if r.get("documento_id")]),
        "attesa": riepilogo,
        "fattura": {**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)},
    }

@app.post("/api/fatture/{id_fattura}/conferma-accoppiamento")
def conferma_accoppiamento_fattura(id_fattura: str):
    """Secondo tempo: l'operatore firma e nasce il file unico in ACCOPPIATE.

    E' l'unico modo in cui una pratica si chiude. Da qui i DDT ricevono
    l'annotazione della loro fattura e la voce passa in FATTURE.json.
    """
    voce, errore = conferma_accoppiamento(id_fattura)

    if errore == "non trovata":
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if errore == "gia confermata":
        raise HTTPException(status_code=409, detail="Questa fattura e' gia' stata accoppiata")

    return {
        "message": "Accoppiamento confermato",
        "fascicolo": voce.get("fascicolo", ""),
        "ddt": len(voce.get("ddt", [])),
        "fattura": {**voce, "in_coda": False},
    }

@app.get("/api/fatture/{id_fattura}")
async def get_fattura(id_fattura: str):
    registro, voce = trova_fattura(id_fattura)
    if not voce:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    if registro == REGISTRO_ATTESA:
        return {**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)}
    return {**voce, "in_coda": False}

@app.get("/api/pdf-fattura/{id_fattura}.pdf")
def get_pdf_fattura(id_fattura: str):
    """Serve il fascicolo PDF (fattura + DDT).

    Per le pratiche confermate è il file unico archiviato in ACCOPPIATE. Per una
    fattura ancora in coda quel file NON esiste — sarebbe già vecchio al
    prossimo DDT, e soprattutto nessuno l'ha ancora firmato — quindi viene
    costruito qui su richiesta in un file temporaneo, cancellato subito
    dopo l'invio. L'header X-Fascicolo-Anteprima distingue i due casi, così
    l'interfaccia può dire che quello che si sta guardando è provvisorio.

    Sincrona: costruire il fascicolo è lavoro bloccante (PyMuPDF).
    """
    registro, voce = trova_fattura(id_fattura)
    if not voce:
        raise HTTPException(status_code=404, detail=f"Fascicolo non trovato per ID: {id_fattura}")

    # Il file confermato non si chiama piu' come l'id (in ACCOPPIATE i nomi sono
    # leggibili da una persona): il percorso lo sa la voce, non questa route.
    percorso = percorso_fascicolo(voce)
    if percorso:
        return FileResponse(
            path=percorso,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )

    try:
        percorso_temporaneo = anteprima_fascicolo(voce)
    except Exception as e:
        print(f"❌ Anteprima del fascicolo {id_fattura} non costruibile: {e}")
        raise HTTPException(status_code=500, detail=f"Impossibile costruire l'anteprima: {e}")

    return FileResponse(
        path=percorso_temporaneo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Fascicolo-Anteprima": "1",
        },
        background=BackgroundTask(shutil.rmtree, os.path.dirname(percorso_temporaneo), True),
    )

@app.delete("/api/fatture/{id_fattura}")
async def delete_fattura(id_fattura: str):
    """Elimina una fattura (chiusa o in coda), col file unico e l'XML archiviato.

    I DDT restano dove sono — un DDT non smette di esistere perché la sua
    fattura è stata cancellata — ma PERDONO l'annotazione: cancellare la pratica
    è il modo in cui si disfa un accoppiamento sbagliato, e `ddt_senza_fattura()`
    riconosce le bolle libere proprio dall'assenza di quel campo. Lasciarlo
    terrebbe quei DDT agganciati a una fattura che non c'è più, quindi fuori dal
    sollecito per sempre."""
    for nome_registro in (REGISTRO_ATTESA, REGISTRO_FATTURE):
        registro = leggi_registro(nome_registro)

        for i, voce in enumerate(registro):
            if voce.get("id") != id_fattura:
                continue

            rimuovi_dal_registro(nome_registro, i)

            # L'XML originale e (per le pratiche vecchie) il fascicolo stanno
            # in FATTURE/lette col nome dell'id; il file unico confermato sta in
            # ACCOPPIATE con un nome leggibile, che solo la voce conosce.
            for nome in os.listdir(CARTELLA_FATTURE) if os.path.isdir(CARTELLA_FATTURE) else []:
                if nome.startswith(id_fattura):
                    os.remove(os.path.join(CARTELLA_FATTURE, nome))

            unico = voce.get("fascicolo")
            if unico:
                percorso_unico = os.path.join(CARTELLA_ACCOPPIATE, unico)
                if os.path.exists(percorso_unico):
                    os.remove(percorso_unico)

            liberati = dimentica_fattura(id_fattura)

            return {
                "message": "Fattura eliminata con successo",
                "ddt_liberati": liberati,
            }

    raise HTTPException(status_code=404, detail="Fattura non trovata")


if __name__ == "__main__":
    print("Avvio del server GestioneFatture - GruppoCR (Author: Lo Staff di Pa.Rea S.n.C.)...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)