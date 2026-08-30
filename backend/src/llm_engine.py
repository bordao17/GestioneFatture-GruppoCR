import json
import ollama
from src.memory_manager import ottieni_regole_formattate
from src.normalizzatore import normalizza_dati

def estrai_dati_da_immagine(image_path):
    regole_memoria = ottieni_regole_formattate()
    sezione_memoria = ""
    
    if regole_memoria:
        sezione_memoria = f"\n\nMEMORIA STORICA DEI FORNITORI (Applica queste regole se riconosci il fornitore):\n{regole_memoria}"

    prompt = f"""
        Estrai i dati da questa pagina di un D.D.T. italiano. Se un campo non è presente o leggibile con certezza, lascia stringa vuota "" (mai "dato mancante"/"non trovato"). Non duplicare dati tra campi. Distingui bene caratteri simili (3/9, O/0).

        CONSEGNA — è l'indirizzo dove viene fisicamente recapitata la merce. Segui questa procedura in ordine, fermati al primo passo che si applica. Usa SEMPRE UN SOLO indirizzo: non concatenare mai due indirizzi diversi nello stesso campo, anche se ne vedi più di uno candidato.

        1. Cerca PRIMA le etichette più specifiche: "Consegna a", "Luogo di Consegna", "Luogo di Destinazione", "Destinazione Merce", "Luogo Dest. Merci", "Destinatario merce"/"Luogo di scarico", "Spedizione a". Se una di queste è presente, usa SEMPRE quell'indirizzo — anche se sulla stessa pagina c'è ANCHE un campo generico "Destinatario" con un indirizzo diverso. In quel caso "Destinatario" da solo indica quasi sempre il cliente fatturato/proprietario dell'ordine, NON il luogo fisico di consegna: ignoralo a favore dell'etichetta più specifica.
        2. Solo se NON è presente NESSUNA delle etichette specifiche sopra, allora usa il campo "Destinatario" (se presente) come consegna.
        3. NON usare MAI l'indirizzo sotto "Intestatario", "Fatturazione", "Cliente Fatturazione", "Sede di fatturazione" o "Cessionario/Cliente" — quello è sempre l'indirizzo di chi paga, mai il luogo fisico di consegna, a prescindere da quale indirizzo specifico contenga.
        4. In assenza di etichette, cerca un secondo blocco indirizzo nella pagina, diverso da quello di intestazione/fatturazione: quello è la consegna.
        5. Se nel documento c'è un solo indirizzo in tutto e non è chiaramente etichettato come fatturazione/intestatario, usalo come consegna.

        - ragione_sociale_consegna: nome del punto vendita/destinatario finale (es. "CONAD", "PAC 2000A", "C.R. MARKET SRL", "CR SUPERMERCATI SRL"), senza indirizzo. Cercalo attivamente vicino all'indirizzo di consegna scelto: quasi sempre un nome azienda/insegna è scritto proprio sopra o accanto all'indirizzo. Non lasciarlo vuoto se un nome è visibile. Se il documento riporta "Ragione Sociale" e "Indirizzo" già separati nella sezione destinazione, usali direttamente per i due campi rispettivamente.
        - indirizzo_consegna: solo l'indirizzo, formato esatto "VIA NUMERO, CAP CITTÀ (PROV)" — es. "VIA MARIO VISINTINI 51, 00012 GUIDONIA MONTECELIO (RM)". Niente codici cliente, partite IVA o sigle interne.

        ALTRI CAMPI:
        - fornitore: azienda emittente (in alto, es. srl/spa/snc). Riporta la ragione sociale COMPLETA come stampata, mai un'abbreviazione o una sola iniziale: se leggi solo una lettera isolata stai guardando un logo tagliato, cerca il nome per esteso altrove nella pagina (intestazione, piè di pagina, timbro).
        - numero_ddt: SOLO il codice del documento (cerca "D.D.T. N." o "Doc. N."), copiato esattamente come appare, incluso qualsiasi prefisso alfanumerico (es. "SGE/0705580" deve restare "SGE/0705580" INTERO, non tagliare mai il prefisso e non perdere cifre). Rimuovi gli zeri iniziali SOLO se il numero è composto esclusivamente da cifre (es. "00127" → "127"; ma "SGE/0705580" resta invariato).
          NON includere MAI nel campo l'etichetta che precede il numero: "DOC. DI TRASPORTO 7071" → "7071", non "DOC.DI TRASPORTO 7071".
          NON includere MAI la data: sui moduli numero e data sono spesso affiancati nella stessa riga, ma "374764 del 01/07/2026" → numero_ddt "374764" e data_ddt "01-07-2026", mai "374764/01/07/2026".
        - data_ddt: data di emissione, SEMPRE nel formato "GG-MM-AAAA" con il trattino e l'anno a 4 cifre, senza orario. Converti sempre qualunque formato tu veda sul documento: "4/6/26" → "04-06-2026", "01.07.2026" → "01-07-2026", "2026-07-08" → "08-07-2026". Non usare mai "/" o "." come separatore.{sezione_memoria}

        Se il documento è sfocato, tagliato, storto o di qualità incerta → leggibilita_bassa: true.

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

    try:
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }],
            options={'num_ctx': 8192, 'temperature': 0.0},
            keep_alive='30m'
        )

        risultato_testo = response['message']['content'].strip()
        
        if risultato_testo.startswith("```json"):
            risultato_testo = risultato_testo[7:-3].strip()
        elif risultato_testo.startswith("```"):
            risultato_testo = risultato_testo[3:-3].strip()

        dati = json.loads(risultato_testo)

        # Il prompt chiede formati precisi ma il modello non li rispetta in modo
        # affidabile: la normalizzazione deterministica avviene a valle.
        return normalizza_dati(dati)
    except Exception as e:
        print(f"❌ Errore sull'immagine {image_path}: {e}")
        return None