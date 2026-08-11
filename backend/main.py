import os
import shutil
import tempfile
import uuid
import time
from datetime import datetime, timezone
import zoneinfo
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from src.pdf_processor import converti_pdf_in_immagini
from src.llm_engine import estrai_dati_da_immagine
from src.classificatore import determina_stato, CAMPI_OBBLIGATORI
from src.registro import aggiorna_registro, leggi_registro, rimuovi_dal_registro, aggiorna_documento_registro
from src.pdf_writer import salva_pdf_multipagina
from src.accorpatore import accorpa_documenti
from src.notificatore import calcola_riepilogo

app = FastAPI(
    title="GestioneFatture - GruppoCR API",
    description="Microservizio AI per l'estrazione dati da DDT e Fatture",
    version="1.0.0"
)

# Abilita CORS per il frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In produzione, specifica gli origin consentiti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TZ = zoneinfo.ZoneInfo(os.getenv("GENERIC_TIMEZONE", "Europe/Rome"))
CARTELLA_FATTURE = "/fatture_lette"

def timestamp_locale():
    return datetime.now(TZ).isoformat()

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
    
    return tutti_documenti

@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: str):
    """Restituisce un documento specifico per ID"""
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for doc in registro:
                if doc.get('id') == doc_id:
                    doc['status'] = stato
                    return doc
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@app.put("/api/documents/{doc_id}")
async def update_document(doc_id: str, updated_data: dict):
    """Aggiorna i dati estratti di un documento"""
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for i, doc in enumerate(registro):
                if doc.get('id') == doc_id:
                    # Aggiorna solo i dati estratti, mantieni metadata
                    doc['extracted_data'] = updated_data.get('extracted_data', doc.get('dati', {}))
                    if 'dati' in doc:
                        doc['dati'] = updated_data.get('extracted_data', doc['dati'])
                    
                    # Salva nel registro
                    aggiorna_documento_registro(stato, i, doc)
                    return {"message": "Documento aggiornato con successo", "document": doc}
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

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
                    pdf_path = os.path.join(CARTELLA_FATTURE, stato, f"{doc_id}.pdf")
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                    
                    return {"message": "Documento eliminato con successo"}
    
    raise HTTPException(status_code=404, detail="Documento non trovato")

@app.get("/api/pdf/{doc_id}.pdf")
async def get_pdf(doc_id: str):
    print(f"🔍 Cerco PDF per ID: {doc_id}")
    
    # Lista dei possibili percorsi dove potrebbe trovarsi il file
    possible_paths = [
        f"fatture_da_leggere/{doc_id}.pdf",
        f"fatture_lette/OK/{doc_id}.pdf",
        f"fatture_lette/CHECK/{doc_id}.pdf",
        f"fatture_lette/KO/{doc_id}.pdf",
        f"fatture_lette/{doc_id}.pdf"
    ]
    
    file_path = None
    for path in possible_paths:
        print(f"  Controllo: {path}")
        if os.path.exists(path):
            file_path = path
            print(f"✅ Trovato: {path}")
            break
    
    if not file_path:
        print(f"💥 PDF non trovato per ID: {doc_id}")
        raise HTTPException(status_code=404, detail=f"PDF non trovato per ID: {doc_id}")
    
    # Leggi il file in memoria
    with open(file_path, "rb") as f:
        pdf_content = f.read()
    
    # Restituisci il PDF con gli header corretti per la visualizzazione inline
    from fastapi.responses import Response
    
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=documento.pdf",
            "Content-Type": "application/pdf",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Content-Type-Options": "nosniff"
        }
    )


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
        return riepilogo
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/estrai-ddt")
async def analizza_documento(file: UploadFile = File(...)):
    t_totale_inizio = time.time()
    print(f"🚀 Apertura file: {file.filename}")

    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, file.filename)

    try:
        t0 = time.time()
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"⏱️ [1/4] Salvataggio file caricato: {time.time() - t0:.2f} secondi")

        # 1. SPLIT: Divido il PDF in immagini, una per pagina
        t0 = time.time()
        immagini = []
        if file.filename.lower().endswith('.pdf'):
            immagini = converti_pdf_in_immagini(file_path, cartella_output=os.path.join(temp_dir, "pages"))
        elif file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            immagini = [file_path]
        else:
            raise HTTPException(status_code=400, detail="Formato non supportato.")
        print(f"⏱️ [2/4] Conversione PDF → {len(immagini)} immagini: {time.time() - t0:.2f} secondi")

        risultati_pagine = []

        # 2. ELABORAZIONE SINGOLO DDT (una pagina = un documento, NESSUN raggruppamento)
        for i, img_path in enumerate(immagini):
            id_generico = str(uuid.uuid4())
            print(f"🤖 Analisi pagina {i + 1}/{len(immagini)} (id={id_generico}) in corso...")

            t0 = time.time()
            dati_estratti = estrai_dati_da_immagine(img_path)
            t_modello = time.time() - t0
            print(f"⏱️ [3/4] Pagina {i + 1}: chiamata al modello Ollama: {t_modello:.2f} secondi")

            if not dati_estratti:
                dati_estratti = {}

            stato, campi_trovati = determina_stato(dati_estratti, CAMPI_OBBLIGATORI)

            if dati_estratti.get("leggibilita_bassa"):
                print(f"⚠️  Pagina {i + 1} segnalata come poco leggibile dal modello.")

            cartella_dest = f"/fatture_lette/{stato}"
            os.makedirs(cartella_dest, exist_ok=True)

            t0 = time.time()
            path_pdf_dest = os.path.join(cartella_dest, f"{id_generico}.pdf")
            salva_pdf_multipagina(path_pdf_dest, [img_path])
            print(f"⏱️ [4/4] Pagina {i + 1}: salvataggio PDF su disco: {time.time() - t0:.2f} secondi")

            if stato in ["OK", "CHECK"]:
                anagrafica = {
                    "id": id_generico,
                    "file_origine": file.filename,
                    "timestamp": timestamp_locale(),
                    "dati": dati_estratti
                }
                aggiorna_registro(stato, anagrafica)
            else:  # KO: nessun dato utile estratto, salviamo solo un riferimento minimo
                anagrafica_ko = {
                    "id": id_generico,
                    "file_origine": file.filename,
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

        print(f"✅ Elaborazione completata per {file.filename} in {time.time() - t_totale_inizio:.2f} secondi totali")
        return {
            "status": "success",
            "filename": file.filename,
            "pagine_elaborate": risultati_pagine,
            "accorpamento": report_accorpamento
        }

    except Exception as e:
        print(f"❌ Errore critico: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    print("Avvio del server GestioneFatture - GruppoCR (Author: Lorenzo Bordi)...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)