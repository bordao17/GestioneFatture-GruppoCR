"""Gestione del registro persistente (OK.json / CHECK.json) in /fatture_lette."""

import os
import json
import shutil

CARTELLA_REGISTRO = "/fatture_lette"


def leggi_registro(stato):
    """
    Legge il file del registro per uno specifico stato (OK, CHECK, KO).
    Restituisce una lista vuota se il file non esiste.
    """
    percorso_registro = os.path.join(CARTELLA_REGISTRO, f"{stato}.json")
    
    if not os.path.exists(percorso_registro):
        return []
    
    try:
        with open(percorso_registro, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def aggiorna_documento_registro(stato, indice, documento):
    """
    Aggiorna un documento specifico nel registro per uno dato stato.
    """
    registro = leggi_registro(stato)
    
    if 0 <= indice < len(registro):
        registro[indice] = documento
        salva_registro(stato, registro)
        return True
    
    return False


def rimuovi_dal_registro(stato, indice):
    """
    Rimuove un documento dal registro per indice.
    """
    registro = leggi_registro(stato)
    
    if 0 <= indice < len(registro):
        registro.pop(indice)
        salva_registro(stato, registro)
        return True
    
    return False


def salva_registro(stato, registro):
    """
    Salva il registro su file.
    """
    percorso_registro = os.path.join(CARTELLA_REGISTRO, f"{stato}.json")
    os.makedirs(os.path.dirname(percorso_registro), exist_ok=True)
    
    with open(percorso_registro, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)


def aggiorna_registro(stato, nuovi_dati):
    """
    Legge il file OK.json o CHECK.json (se esiste), aggiunge il nuovo dato
    e lo salva. I file vengono creati nella root della cartella fatture_lette.
    """
    registro = leggi_registro(stato)
    registro.append(nuovi_dati)
    salva_registro(stato, registro)