import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
import requests
import ollama
from src.memory_manager import ottieni_regole_formattate

# Configurazioni lette da variabili d'ambiente con fallback sul server AI
OLLAMA_HOST = os.getenv("OLLAMA_BASE_URL", "http://10.1.20.25:11434")
SURYA_OCR_URL = os.getenv("SURYA_OCR_URL", "http://10.1.20.25:8000/v1/ocr")
MODEL_NAME = os.getenv("LLM_MODEL", "llama3.1")

# Inizializzazione del client Ollama puntando all'host specificato
ollama_client = ollama.Client(host=OLLAMA_HOST)


def estrai_testo_surya_remoto(image_path: str) -> str:
    """Invia il documento al microservizio FastAPI Surya OCR remoto per estrarre il testo."""
    file_path = Path(image_path)
    if not file_path.exists():
        print(f"❌ File non trovato: {image_path}")
        return ""

    mime_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/png"

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, mime_type)}
            response = requests.post(SURYA_OCR_URL, files=files, timeout=120)

        if response.status_code == 200:
            data = response.json()
            # Concatena il testo di tutte le pagine restituite dal microservizio
            testo_pagine = [page.get("full_text", "") for page in data.get("results", [])]
            return "\n".join(testo_pagine).strip()
        else:
            print(f"❌ Errore Surya OCR API ({response.status_code}): {response.text}")
            return ""
    except Exception as e:
        print(f"❌ Errore di connessione a Surya OCR remoto ({SURYA_OCR_URL}): {e}")
        return ""


def estrai_dati_da_immagine(image_path: str) -> Optional[Dict[str, Any]]:
    print(f"  -> Avvio lettura ottica (OCR) remota per {image_path}...")
    testo_grezzo = estrai_testo_surya_remoto(image_path)

    if not testo_grezzo or not testo_grezzo.strip():
        print("⚠️ Testo estratto vuoto o illeggibile.")
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

    print(f"  -> Interrogazione Ollama remota ({MODEL_NAME} su {OLLAMA_HOST})...")
    try:
        response = ollama_client.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}],
            format='json',
            options={'num_ctx': 8192, 'temperature': 0.0},
            keep_alive='30m'
        )

        risultato_testo = response['message']['content'].strip()

        # Pulizia blocchi markdown se presenti nonostante format='json'
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
        print(f"❌ Errore durante l'analisi testuale con Ollama: {e}")
        return None