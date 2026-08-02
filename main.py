import os
import shutil
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List
import uvicorn

from src.pdf_processor import converti_pdf_in_immagini
from src.llm_engine import estrai_dati_da_immagine
from src.document_builder import elabora_pagine_in_documenti
from src.memory_manager import aggiorna_fornitore

# --- MODELLI PYDANTIC (Il Contratto dei Dati) ---
class DocumentoDDT(BaseModel):
    fornitore: str
    numero_ddt: str
    data_ddt: str
    consegna: str

class RispostaEstrazione(BaseModel):
    status: str
    filename: str
    documenti_estratti: List[DocumentoDDT]
# ------------------------------------------------

app = FastAPI(
    title="GestioneFatture - GruppoCR API",
    description="Microservizio AI per l'estrazione dati da DDT e Fatture",
    version="1.0.0"
)

@app.post("/estrai-ddt", summary="Analizza un documento (PDF o Immagine) ed estrae i dati dei DDT")
async def analizza_documento(file: UploadFile = File(...)):
    print(f"🚀 [GestioneFatture-GruppoCR] Ricevuto file da elaborare: {file.filename}")
    
    # 1. SALVATAGGIO TEMPORANEO DEL FILE IN INGRESSO
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. GENERAZIONE IMMAGINI
        immagini = []
        if file.filename.lower().endswith('.pdf'):
            immagini = converti_pdf_in_immagini(file_path, cartella_output=os.path.join(temp_dir, "pages"))
        elif file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            immagini = [file_path]
        else:
            raise HTTPException(status_code=400, detail="Formato file non supportato. Invia PDF, JPG o PNG.")
        
        print(f"📸 Trovate {len(immagini)} pagine da analizzare.")

        # 3. ESTRAZIONE DATI
        dati_pagine_grezze = []
        for i, img_path in enumerate(immagini):
            print(f"🤖 Scansione AI pagina {i+1} in corso...")
            dati = estrai_dati_da_immagine(img_path)
            if dati:
                dati_pagine_grezze.append(dati)
        
        # 4. MACCHINA A STATI (Raggruppamento)
        print("⚙️ Analisi semantica: Raggruppamento dei documenti...")
        documenti_finali = elabora_pagine_in_documenti(dati_pagine_grezze)

        # 5. SALVATAGGIO IN MEMORIA (e pulizia JSON finale)
        for doc in documenti_finali:
            note_proposte = doc.get("note_layout", "")
            aggiorna_fornitore(doc.get("fornitore"), note_proposte)
            
            if "note_layout" in doc:
                del doc["note_layout"]

        print(f"✅ Elaborazione completata per {file.filename}")
        
        # 6. OUTPUT VERSO n8n
        return {
            "status": "success",
            "filename": file.filename,
            "documenti_estratti": documenti_finali
        }

    except Exception as e:
        print(f"❌ Errore critico durante l'elaborazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # 7. PULIZIA GARANTITA DELL'HARD DISK
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    # Avvia il server locale sulla porta 8000
    print("Avvio del server GestioneFatture - GruppoCR...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)