# ==========================================
# 1. IMPORTS & SETUP APP
# ==========================================
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
from src.memory_manager import carica_memoria, salva_memoria, aggiorna_fornitore

app = FastAPI(
    title="GestioneFatture - GruppoCR API",
    description="Microservizio AI per l'estrazione dati da DDT e Fatture",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. CONFIGURAZIONI & COSTANTI
# ==========================================
TZ = zoneinfo.ZoneInfo(os.getenv("GENERIC_TIMEZONE", "Europe/Rome"))
CARTELLA_FATTURE = "/fatture_lette"

def timestamp_locale():
    return datetime.now(TZ).isoformat()

# ==========================================
# 3. ROUTING: MEMORIA AI (FORNITORI)
# ==========================================
@app.get("/api/fornitori")
async def get_fornitori():
    try:
        return carica_memoria()
    except Exception as e:
        print(f"Errore lettura fornitori: {e}")
        return {}

@app.put("/api/fornitori")
async def update_fornitori(data: dict):
    try:
        salva_memoria(data)
        return {"message": "Memoria AI aggiornata con successo"}
    except Exception as e:
        print(f"Errore salvataggio fornitori: {e}")
        raise HTTPException(status_code=500, detail="Impossibile salvare la memoria fornitori.")

# ==========================================
# 4. ROUTING: GESTIONE DOCUMENTI (CRUD)
# ==========================================
@app.get("/api/documents")
async def get_all_documents():
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
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for i, doc in enumerate(registro):
                if doc.get('id') == doc_id:
                    doc['extracted_data'] = updated_data.get('extracted_data', doc.get('dati', {}))
                    if 'dati' in doc:
                        doc['dati'] = updated_data.get('extracted_data', doc['dati'])
                    aggiorna_documento_registro(stato, i, doc)
                    return {"message": "Documento aggiornato con successo", "document": doc}
    raise HTTPException(status_code=404, detail="Documento non trovato")

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    for stato in ["OK", "CHECK", "KO"]:
        registro = leggi_registro(stato)
        if registro:
            for i, doc in enumerate(registro):
                if doc.get('id') == doc_id:
                    rimuovi_dal_registro(stato, i)
                    pdf_path = os.path.join(CARTELLA_FATTURE, stato, f"{doc_id}.pdf")
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                    return {"message": "Documento eliminato con successo"}
    raise HTTPException(status_code=404, detail="Documento non trovato")

# ==========================================
# 5. ROUTING: VISUALIZZAZIONE PDF
# ==========================================
@app.get("/api/pdf/{doc_id}.pdf")
async def get_pdf(doc_id: str):
    print(f"🔍 Cerco PDF per ID: {doc_id}")
    file_path = None
    
    for stato in ["OK", "CHECK", "KO"]:
        path = os.path.join(CARTELLA_FATTURE, stato, f"{doc_id}.pdf")
        if os.path.exists(path):
            file_path = path
            break
            
    if not file_path:
        root_path = os.path.join(CARTELLA_FATTURE, f"{doc_id}.pdf")
        if os.path.exists(root_path):
             file_path = root_path
    
    if not file_path:
        raise HTTPException(status_code=404, detail=f"PDF non trovato per ID: {doc_id}")
    
    return FileResponse(
        path=file_path, 
        media_type="application/pdf", 
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache, no-store, must-revalidate"
        }
    )

# ==========================================
# 6. ROUTING: RIEPILOGO STATISTICHE
# ==========================================
@app.get("/riepilogo")
async def riepilogo_endpoint(
    da: str = Query(..., description="Timestamp ISO 8601 es. 2026-08-09T10:30:00+02:00")
):
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

# ==========================================
# 7. ROUTING CORE: ESTRAZIONE IBRIDA (OCR + LLM)
# ==========================================
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

        for i, img_path in enumerate(immagini):
            id_generico = str(uuid.uuid4())
            print(f"🤖 Analisi pagina {i + 1}/{len(immagini)} (id={id_generico}) in corso...")

            t0 = time.time()
            dati_estratti = estrai_dati_da_immagine(img_path)
            t_modello = time.time() - t0
            print(f"⏱️ [3/4] Pagina {i + 1}: completata in: {t_modello:.2f} secondi")

            if not dati_estratti:
                dati_estratti = {}

            # SALVATAGGIO AUTOMATICO NUOVO FORNITORE IN MEMORIA
            fornitore_estratto = dati_estratti.get("fornitore")
            if fornitore_estratto and str(fornitore_estratto).strip().lower() not in ["", "dato mancante", "nessuno"]:
                try:
                    aggiorna_fornitore(str(fornitore_estratto).strip(), "")
                except Exception as e:
                    print(f"⚠️ Errore durante l'aggiornamento della memoria fornitori: {e}")

            stato, campi_trovati = determina_stato(dati_estratti, CAMPI_OBBLIGATORI)

            cartella_dest = os.path.join(CARTELLA_FATTURE, stato)
            os.makedirs(cartella_dest, exist_ok=True)

            t0 = time.time()
            path_pdf_dest = os.path.join(cartella_dest, f"{id_generico}.pdf")
            salva_pdf_multipagina(path_pdf_dest, [img_path])
            print(f"⏱️ [4/4] Pagina {i + 1}: salvataggio PDF su disco: {time.time() - t0:.2f} secondi")

            anagrafica = {
                "id": id_generico,
                "file_origine": file.filename,
                "timestamp": timestamp_locale(),
            }
            if stato in ["OK", "CHECK"]:
                anagrafica["dati"] = dati_estratti
                
            aggiorna_registro(stato, anagrafica)

            risultati_pagine.append({
                "id": id_generico,
                "stato": stato,
                "campi_trovati": campi_trovati
            })

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
    print("Avvio del server GestioneFatture - GruppoCR (Author: Lo Staff di Pa.Rea S.n.C.)...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)