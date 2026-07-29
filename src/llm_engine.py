import json
import ollama
from src.memory_manager import ottieni_regole_formattate

def estrai_dati_da_immagine(image_path):
    # 1. Recupera le regole dalla memoria storica
    regole_memoria = ottieni_regole_formattate()
    sezione_memoria = ""
    
    if regole_memoria:
        sezione_memoria = f"\n\nMEMORIA STORICA DEI FORNITORI (Applica queste regole se riconosci il fornitore):\n{regole_memoria}"

    # 2. Costruisce il prompt (il tuo prompt originale + le regole dinamiche)
    prompt = f"""
    Sei un sistema esperto nell'estrazione di dati da Documenti di Trasporto (D.D.T.) italiani.
    Ti viene fornita l'immagine di un documento.
     
    REGOLE RIGIDE DI ESTRAZIONE:
    1. NON duplicare i dati tra i campi.
    2. Distingui con precisione i caratteri simili (es. 3 e 9, O e 0).
    
    GUIDA CRITICA PER IL CAMPO "consegna":
    - IGNORA ASSOLUTAMENTE la sede legale se riporta l'indirizzo: "VIA G. ANDREASSI 30 00123 ROMA (RM)" (o variazioni simili della sede amministrativa/Spett.le). Quella non è la destinazione della merce!
    - Cerca esplicitamente etichette come **"Destinazione"**, **"Luogo di consegna"**, **"Spedizione a"**, **"Consegnare a"** o il box del punto vendita effettivo.
    - Estrai solo il vero indirizzo in cui viene recapitata la merce.
    
    Altri campi:
    - fornitore: L'azienda emittente (in alto, es. srl, spa, snc).
    - numero_ddt: Il numero identificativo o progressivo del documento. Se il numero inizia con uno o più zeri (es. "00127"), rimuovili e restituisci solo le cifre (es. "127").
    - data_ddt: La data di emissione del documento, escludi l'orario e formatta la data come segue "GG-MM-AAAA".{sezione_memoria}
     
    Se un campo non è presente o non è leggibile con certezza, restituisci una stringa "dato mancante".
     
    Rispondi ESCLUSIVAMENTE con un oggetto JSON valido, senza aggiungere testo prima o dopo, senza markdown.
    Usa esattamente questa struttura:
    {{
        "fornitore": "",
        "numero_ddt": "",
        "data_ddt": "",
        "consegna": ""
    }}
    """

    try:
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }],
            options={
                'num_ctx': 4096,
                'temperature': 0.0
            }
        )

        risultato_testo = response['message']['content'].strip()
        
        if risultato_testo.startswith("```json"):
            risultato_testo = risultato_testo[7:-3].strip()
        elif risultato_testo.startswith("```"):
            risultato_testo = risultato_testo[3:-3].strip()

        dati = json.loads(risultato_testo)
        
        # 3. RETE DI SICUREZZA PYTHON: Rimuove forzatamente gli zeri iniziali
        numero = dati.get("numero_ddt", "")
        if numero and numero != "dato mancante":
            dati["numero_ddt"] = numero.lstrip('0')
            # Se era tutto composto da zeri (es "000"), rimarrà vuoto. In quel caso rimettiamo "0".
            if dati["numero_ddt"] == "":
                dati["numero_ddt"] = "0"
        
        return dati

    except json.JSONDecodeError:
        print(f"❌ Il modello non ha restituito JSON valido per {image_path}. Risposta: {risultato_testo}")
        return None
    except Exception as e:
        print(f"❌ Errore LLM sull'immagine {image_path}: {e}")
        return None