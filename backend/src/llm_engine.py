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

MODEL_NAME = 'qwythos'

def carica_surya():
    """Carica i modelli in RAM/VRAM solo alla primissima fattura inviata, non all'avvio del server"""
    global det_processor, det_model, rec_model, rec_processor, surya_loaded

    if surya_loaded:
        return # Se sono già stati caricati, non fa nulla

    print("\n⏳ Inizializzazione modelli Surya OCR per la prima volta (sfruttando la RTX 3080)...")
    try:
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
    carica_surya()
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
    print(f"  -> Avvio lettura ottica (OCR) locale con Surya per {image_path}...")
    testo_grezzo = estrai_testo_surya(image_path)

    if not testo_grezzo.strip():
        return {
            "fornitore": "",
            "numero_ddt": "",
            "data_ddt": "",
            "ragione_sociale_consegna": "",
            "indirizzo_consegna": "",
            "leggibilita_bassa": True
        }

    regole_memoria = ottieni_regole_formattate()
    sezione_memoria = ""

    if regole_memoria:
        sezione_memoria = f"\n\nMEMORIA STORICA DEI FORNITORI:\nApplica queste regole al testo estratto se riconosci il fornitore:\n{regole_memoria}
    
    prompt = f"""
        Estrai i dati da questa pagina di un D.D.T. italiano. Se un campo non è presente o leggibile con certezza, lascia stringa vuota "" (mai "dato mancante"/"non trovato"). Non duplicare dati tra campi. Distingui bene caratteri simili (3/9, O/0).
        TESTO ESTRATTO DAL DOCUMENTO:
        --------------------------------------------------
        {testo_grezzo}
        --------------------------------------------------
        CONSEGNA — è l'indirizzo dove viene fisicamente recapitata la merce. Segui questa procedura in ordine, fermati al primo passo che si applica. Usa SEMPRE UN SOLO indirizzo: non concatenare mai due indirizzi diversi nello stesso campo, anche se ne vedi più di uno candidato.

        1. Cerca PRIMA le etichette più specifiche: "Consegna a", "Luogo di Consegna", "Luogo di Destinazione", "Destinazione Merce", "Luogo Dest. Merci", "Destinatario merce"/"Luogo di scarico", "Spedizione a". Se una di queste è presente, usa SEMPRE quell'indirizzo — anche se sulla stessa pagina c'è ANCHE un campo generico "Destinatario" con un indirizzo diverso. In quel caso "Destinatario" da solo indica quasi sempre il cliente fatturato/proprietario dell'ordine, NON il luogo fisico di consegna: ignoralo a favore dell'etichetta più specifica.
        2. Solo se NON è presente NESSUNA delle etichette specifiche sopra, allora usa il campo "Destinatario" (se presente) come consegna.
        3. NON usare MAI l'indirizzo sotto "Intestatario", "Fatturazione", "Cliente Fatturazione", "Sede di fatturazione" o "Cessionario/Cliente" — quello è sempre l'indirizzo di chi paga, mai il luogo fisico di consegna, a prescindere da quale indirizzo specifico contenga.
        4. In assenza di etichette, cerca un secondo blocco indirizzo nella pagina, diverso da quello di intestazione/fatturazione: quello è la consegna.
        5. Se nel documento c'è un solo indirizzo in tutto e non è chiaramente etichettato come fatturazione/intestatario, usalo come consegna.

        - ragione_sociale_consegna: nome del punto vendita/destinatario finale (es. "CONAD", "PAC 2000A", "C.R. MARKET SRL", "CR SUPERMERCATI SRL"), senza indirizzo. Cercalo attivamente vicino all'indirizzo di consegna scelto: quasi sempre un nome azienda/insegna è scritto proprio sopra o accanto all'indirizzo. Non lasciarlo vuoto se un nome è visibile. Se il documento riporta "Ragione Sociale" e "Indirizzo" già separati nella sezione destinazione, usali direttamente per i due campi rispettivamente.
        - indirizzo_consegna: solo l'indirizzo, formato esatto "VIA NUMERO, CAP CITTÀ (PROV)" — es. "VIA MARIO VISINTINI 51, 00012 GUIDONIA MONTECELIO (RM)". Niente codici cliente, partite IVA o sigle interne.

        ALTRI CAMPI:
        - fornitore: azienda emittente (in alto, es. srl/spa/snc).
        - numero_ddt: numero documento (cerca "D.D.T. N." o "Doc. N."), copiato esattamente come appare, incluso qualsiasi prefisso alfanumerico o codice (es. "SGE/0705580" deve restare "SGE/0705580" INTERO, non tagliare mai il prefisso). Rimuovi gli zeri iniziali SOLO se il numero è composto esclusivamente da cifre, senza lettere né simboli davanti (es. "00127" → "127"; ma "SGE/0705580" resta invariato).
        - data_ddt: data emissione, formato "GG-MM-AAAA", senza orario.{sezione_memoria}

        Se il documento è sfocato oppure ha dati incerti → leggibilita_bassa: true.

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

    print(f"  -> Interrogazione LLM locale ({MODEL_NAME})...")
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}],
            format='json',
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
        if numero and str(numero) != "dato mancante" and str(numero).isdigit():
            dati["numero_ddt"] = str(numero).lstrip('0') or "0"

        return dati
    except Exception as e:
        print(f"❌ Errore durante l'analisi testuale: {e}")
        return None