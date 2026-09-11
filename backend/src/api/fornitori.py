"""Le route dell'anagrafica fornitori: la memoria dell'AI e le partite IVA.

Tre sole route, ma sono il punto in cui una lettura del modello diventa un
dato: la conferma della P.IVA e' il passaggio umano che trasforma una proposta
in una chiave, ed e' la stessa chiave con cui una fattura ritrova il suo
cedente.
"""

from fastapi import APIRouter, HTTPException

from src.api.supporto import trova_documento
from src.comune.memory_manager import carica_memoria, salva_memoria, conferma_partita_iva
from src.comune.registro import aggiorna_documento_registro

router = APIRouter()


@router.get("/api/fornitori")
async def get_fornitori():
    """Legge la memoria attuale dell'AI sui fornitori"""
    try:
        return carica_memoria()
    except Exception as e:
        print(f"Errore lettura fornitori: {e}")
        return {}

@router.put("/api/fornitori")
async def update_fornitori(data: dict):
    """Sovrascrive il file JSON con le nuove istruzioni dell'utente"""
    try:
        salva_memoria(data)
        return {"message": "Memoria AI aggiornata con successo"}
    except Exception as e:
        print(f"Errore salvataggio fornitori: {e}")
        raise HTTPException(status_code=500, detail="Impossibile salvare la memoria fornitori.")

@router.put("/api/fornitori/partita-iva")
def conferma_piva_fornitore(payload: dict):
    """Conferma (o corregge) la partita IVA di un fornitore.

    E' il passaggio umano che rende la P.IVA una chiave utilizzabile: quella
    letta da una scansione entra in anagrafica come proposta, e finche' nessuno
    la guarda vale solo come promemoria. Si conferma dall'anagrafica oppure,
    con il PDF davanti, dal modale di revisione del D.D.T. — in quel caso il
    payload porta anche l'id del documento, che viene riallineato al valore
    confermato.
    """
    fornitore = str(payload.get("fornitore") or "").strip()
    partita_iva = str(payload.get("partita_iva") or "").strip()

    if not fornitore:
        raise HTTPException(status_code=400, detail="Manca il fornitore a cui associare la partita IVA.")

    chiave, piva_salvata = conferma_partita_iva(fornitore, partita_iva)
    if not chiave:
        raise HTTPException(
            status_code=400,
            detail="Partita IVA non valida: servono 11 cifre con carattere di controllo corretto.",
        )

    documento_aggiornato = None
    doc_id = str(payload.get("id") or "").strip()
    if doc_id:
        stato, indice, documento = trova_documento(doc_id)
        if documento:
            dati = documento.get("dati") or {}
            dati["partita_iva"] = piva_salvata
            dati.pop("partita_iva_scartata", None)
            documento["dati"] = dati
            aggiorna_documento_registro(stato, indice, documento)
            documento_aggiornato = dict(documento)
            documento_aggiornato["status"] = stato
            documento_aggiornato["partita_iva_anagrafica"] = piva_salvata
            documento_aggiornato["partita_iva_confermata"] = True

    return {
        "message": "Partita IVA confermata",
        "fornitore": chiave,
        "partita_iva": piva_salvata,
        "document": documento_aggiornato,
    }
