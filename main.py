import os
import json
import ollama
from PIL import Image

# 1. Percorso dell'immagine originale
percorso_immagine = 'documento.jpg'

def ottimizza_immagine(image_path):
    """
    Ridimensiona l'immagine mantenendo una risoluzione alta (1800px) 
    per preservare la nitidezza delle etichette e dei testi piccoli.
    """
    percorso_temp = 'documento_ottimizzato.jpg'
    with Image.open(image_path) as img:
        img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        img.save(percorso_temp, format="JPEG", quality=95)
    return percorso_temp

def estrai_dati_ddt(image_path):
    if not os.path.exists(image_path):
        print(f"Errore: Il file non è stato trovato: {image_path}")
        return

    print("Ottimizzazione dell'immagine in corso...")
    immagine_leggera = ottimizza_immagine(image_path)

    print("Scansione con l'Intelligenza Artificiale...")
    prompt = (
        """
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
        - numero_ddt: Il numero identificativo o progressivo del documento.
        - data_ddt: La data di emissione.
         
        Se un campo non è presente o non è leggibile con certezza, restituisci una stringa vuota "".
         
        Rispondi ESCLUSIVAMENTE con un oggetto JSON valido, senza aggiungere testo prima o dopo, senza markdown.
        Usa esattamente questa struttura:
        {
            "fornitore": "",
            "numero_ddt": "",
            "data_ddt": "",
            "consegna": ""
        }
        """
    )

    try:
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [immagine_leggera]
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

        dati_json = json.loads(risultato_testo)
        
        print("\n✅ Dati estratti con successo:")
        print(json.dumps(dati_json, indent=4, ensure_ascii=False))

    except json.JSONDecodeError:
        print("\n❌ Errore: Il modello non ha restituito un JSON valido. Risposta grezza:")
        print(risultato_testo)
    except Exception as e:
        print(f"\n❌ Si è verificato un errore con Ollama: {e}")
    finally:
        if os.path.exists(immagine_leggera):
            os.remove(immagine_leggera)

if __name__ == "__main__":
    estrai_dati_ddt(percorso_immagine)