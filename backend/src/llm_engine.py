import json
import ollama
from PIL import Image
from src.memory_manager import ottieni_regole_formattate

# Variabili globali "vuote" che riempiremo solo quando serve
det_processor = None
det_model = None
rec_model = None
rec_processor = None
surya_loaded = False

MODEL_NAME = 'llama3.2'

def carica_surya():
    """Carica i modelli in RAM solo alla primissima fattura inviata, non all'avvio del server"""
    global det_processor, det_model, rec_model, rec_processor, surya_loaded
    
    if surya_loaded:
        return # Se sono già stati caricati, non fa nulla
        
    print("\n⏳ Inizializzazione modelli Surya OCR per la prima volta (richiederà RAM e tempo)...")
    try:
        # ---> CORREZIONE QUI: usiamo 'segformer' invece di 'model' per la detection
        from surya.model.detection.segformer import load_model as load_det_model, load_processor as load_det_processor
        from surya.model.recognition.model import load_model as load_rec_model
        from surya.model.recognition.processor import load_processor as load_rec_processor

        print("   - Caricamento modello di Rilevamento Testo...")
        det_processor, det_model = load_det_processor(), load_det_model()
        
        print("   - Caricamento modello di Riconoscimento Caratteri...")
        rec_model, rec_processor = load_rec_model(), load_rec_processor()
        
        surya_loaded = True
        print("✅ Modelli Surya OCR caricati con successo in memoria!\n")
    except Exception as e:
        print(f"\n❌ ERRORE CRITICO DURANTE IL CARICAMENTO DI SURYA: {e}")
        raise e

    
def estrai_testo_surya(image_path: str) -> str:
    """Usa Surya OCR per estrarre il testo grezzo dalla pagina"""
    # Si assicura che Surya sia in memoria
    carica_surya()
    
    # Importa la funzione di run solo quando serve
    from surya.ocr import run_ocr
    
    try:
        image = Image.open(image_path)
        langs = ["it", "en"] 
        
        predictions = run_ocr([image], [langs], det_model, det_processor, rec_model, rec_processor)
        
        testo_estratto = []
        for pred in predictions:
            for riga in pred.text_lines:
                testo_estratto.append(riga.text)
                
        return "\n".join(testo_estratto)
    except Exception as e:
        print(f"❌ Errore Surya OCR: {e}")
        return ""

def estrai_dati_da_immagine(image_path):
    print(f"  -> Avvio lettura ottica (OCR) con Surya per {image_path}...")
    testo_grezzo = estrai_testo_surya(image_path)
    
    if not testo_grezzo.strip():
        return {"leggibilita_bassa": True}

    regole_memoria = ottieni_regole_formattate()
    sezione_memoria = ""
    
    if regole_memoria:
        sezione_memoria = f"\n\nMEMORIA STORICA DEI FORNITORI:\nApplica queste regole al testo estratto se riconosci il fornitore:\n{regole_memoria}"

    prompt = f"""
    Sei un assistente esperto in contabilità italiana.
    Ho letto un Documento di Trasporto (D.D.T.) o Fattura usando un software OCR. 
    Il testo estratto (in ordine di lettura) è qui sotto.

    TESTO ESTRATTO DAL DOCUMENTO:
    --------------------------------------------------
    {testo_grezzo}
    --------------------------------------------------

    Estrai i dati da questo testo. Se un campo non è presente o leggibile con certezza, lascia stringa vuota "" (mai "dato mancante"/"non trovato"). Non duplicare dati tra campi. Distingui bene caratteri simili (3/9, O/0).

    CONSEGNA — è l'indirizzo dove viene fisicamente recapitata la merce. Segui questa procedura in ordine, fermati al primo passo che si applica. Usa SEMPRE UN SOLO indirizzo.
    1. Cerca PRIMA le etichette testuali più specifiche: "Consegna a", "Luogo di Consegna", "Destinazione Merce".
    2. NON usare MAI l'indirizzo vicino a "Intestatario", "Fatturazione" o "Cliente Fatturazione".
    3. Se nel testo c'è un solo indirizzo in tutto, usalo come consegna.

    - ragione_sociale_consegna: nome del punto vendita/destinatario finale (es. "CONAD", "PAC 2000A"). Cercalo attivamente vicino all'indirizzo di consegna.
    - indirizzo_consegna: solo l'indirizzo, formato esatto "VIA NUMERO, CAP CITTÀ (PROV)".

    ALTRI CAMPI:
    - fornitore: azienda emittente (in alto, es. srl/spa/snc).
    - numero_ddt: numero documento. Copialo esattamente come appare, incluso qualsiasi prefisso. Rimuovi zeri iniziali SOLO se interamente numerico.
    - data_ddt: data emissione, formato "GG-MM-AAAA".{sezione_memoria}

    Rispondi SOLO con questo JSON, nessun testo/markdown attorno:
    {{
        "fornitore": "",
        "numero_ddt": "",
        "data_ddt": "",
        "ragione_sociale_consegna": "",
        "indirizzo_consegna": "",
        "leggibilita_bassa": false
    }}
    """

    print(f"  -> Interrogazione LLM ({MODEL_NAME}) in corso...")
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}],
            options={'num_ctx': 8192, 'temperature': 0.0},
            keep_alive='30m'
        )

        risultato_testo = response['message']['content'].strip()
        
        if risultato_testo.startswith("```json"):
            risultato_testo = risultato_testo[7:-3].strip()
        elif risultato_testo.startswith("```"):
            risultato_testo = risultato_testo[3:-3].strip()

        dati = json.loads(risultato_testo)
        
        numero = dati.get("numero_ddt", "")
        if numero and numero != "dato mancante" and numero.isdigit():
            dati["numero_ddt"] = numero.lstrip('0') or "0"
        
        return dati
    except Exception as e:
        print(f"❌ Errore durante l'analisi testuale: {e}")
        return None