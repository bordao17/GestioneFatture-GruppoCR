"""Gestione dei registri persistenti (OK/CHECK/KO in DDT/lette, FATTURE in FATTURE/lette)."""

import os
import json
import shutil

from src.comune.percorsi import cartella_registro


def percorso_pdf_documento(stato, doc_id):
    """Percorso su disco del PDF di un documento, con il fallback sulla root
    dell'archivio usato per i documenti salvati prima delle sottocartelle."""
    cartella = cartella_registro(stato)

    percorso = os.path.join(cartella, stato, f"{doc_id}.pdf")
    if os.path.exists(percorso):
        return percorso

    percorso_root = os.path.join(cartella, f"{doc_id}.pdf")
    if os.path.exists(percorso_root):
        return percorso_root

    return None


def leggi_registro(stato):
    """
    Legge il file del registro per uno specifico stato (OK, CHECK, KO, FATTURE).
    Restituisce una lista vuota se il file non esiste.
    """
    percorso_registro = os.path.join(cartella_registro(stato), f"{stato}.json")
    
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
    percorso_registro = os.path.join(cartella_registro(stato), f"{stato}.json")
    os.makedirs(os.path.dirname(percorso_registro), exist_ok=True)
    
    with open(percorso_registro, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)


def aggiorna_registro(stato, nuovi_dati):
    """
    Legge il registro dello stato (se esiste), aggiunge il nuovo dato e lo
    salva. I file stanno nella root dell'archivio del flusso.
    """
    registro = leggi_registro(stato)
    registro.append(nuovi_dati)
    salva_registro(stato, registro)