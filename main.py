import os
import json
import shutil
from src.pdf_processor import converti_pdf_in_immagini
from src.llm_engine import estrai_dati_da_immagine
from src.document_builder import elabora_pagine_in_documenti
from src.memory_manager import aggiorna_fornitore

# Inserisci un PDF multi-pagina o un singolo JPG
FILE_INPUT = 'documento.pdf' 

def main():
    print(f"🚀 Avvio elaborazione su: {FILE_INPUT}")
    
    # 1. GENERAZIONE IMMAGINI
    immagini = []
    if FILE_INPUT.lower().endswith('.pdf'):
        immagini = converti_pdf_in_immagini(FILE_INPUT)
    else:
        immagini = [FILE_INPUT]
    
    print(f"📸 Trovate {len(immagini)} pagine da analizzare.")

    # 2. ESTRAZIONE DATI
    dati_pagine_grezze = []
    for i, img_path in enumerate(immagini):
        print(f"🤖 Scansione AI pagina {i+1} in corso...")
        dati = estrai_dati_da_immagine(img_path)
        if dati:
            dati_pagine_grezze.append(dati)
    
    # 3. MACCHINA A STATI (Raggruppamento)
    print("⚙️ Analisi semantica: Raggruppamento dei documenti...")
    documenti_finali = elabora_pagine_in_documenti(dati_pagine_grezze)

    # 4. SALVATAGGIO IN MEMORIA
    for doc in documenti_finali:
        aggiorna_fornitore(doc.get("fornitore"))

    # 5. OUTPUT FINALE (Lista Array JSON)
    print("\n✅ RISULTATO FINALE:")
    print(json.dumps(documenti_finali, indent=4, ensure_ascii=False))

    # 6. PULIZIA CARTELLE TEMPORANEE
    if FILE_INPUT.lower().endswith('.pdf') and os.path.exists("temp_images"):
        shutil.rmtree("temp_images")

if __name__ == "__main__":
    main()