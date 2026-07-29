import os
import json

FILE_MEMORIA = 'fornitori_memoria.json'

def carica_memoria():
    if os.path.exists(FILE_MEMORIA):
        with open(FILE_MEMORIA, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salva_memoria(memoria):
    with open(FILE_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

def aggiorna_fornitore(fornitore):
    if not fornitore or fornitore.lower() == "dato mancante":
        return
    memoria = carica_memoria()
    # Se il fornitore non esiste, lo crea con un campo note vuoto da poter riempire a mano
    if fornitore not in memoria:
        memoria[fornitore] = {
            "note_specifiche": ""
        }
        salva_memoria(memoria)
        print(f"[MEMORIA] Nuovo fornitore censito a sistema: {fornitore}")

def ottieni_regole_formattate():
    """Legge il file JSON e crea un blocco di testo con tutte le eccezioni note."""
    memoria = carica_memoria()
    regole = []
    
    for fornitore, dati in memoria.items():
        nota = dati.get("note_specifiche", "").strip()
        if nota:
            regole.append(f"- Se il fornitore è '{fornitore}': {nota}")
    
    if regole:
        return "\n".join(regole)
    return ""