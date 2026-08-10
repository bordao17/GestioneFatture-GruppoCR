import os
import json

# Ora il file vive dentro la cartella data/
FILE_MEMORIA = os.path.join('data', 'fornitori_memoria.json')

def carica_memoria():
    if os.path.exists(FILE_MEMORIA):
        with open(FILE_MEMORIA, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salva_memoria(memoria):
    with open(FILE_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

def aggiorna_fornitore(fornitore, note_proposte):
    if not fornitore or fornitore.lower() == "dato mancante":
        return
    memoria = carica_memoria()
    
    # Lo inserisce SOLO la prima volta che lo incontra
    if fornitore not in memoria:
        memoria[fornitore] = {
            "confermato": "no",
            "note_specifiche": note_proposte
        }
        salva_memoria(memoria)
        print(f"[MEMORIA] Nuovo fornitore censito: {fornitore}. Note auto-generate in attesa di conferma ('yes').")

def ottieni_regole_formattate():
    """Legge il JSON e prende le regole SOLO se 'confermato' è impostato su 'yes'."""
    memoria = carica_memoria()
    regole = []
    
    for fornitore, dati in memoria.items():
        nota = dati.get("note_specifiche", "").strip()
        confermato = dati.get("confermato", "no").lower()
        
        # Inietta la regola solo se hai approvato cambiando in 'yes'
        if nota and confermato in ["yes", "si"]:
            regole.append(f"- Se il fornitore è '{fornitore}': {nota}")
    
    if regole:
        return "\n".join(regole)
    return ""