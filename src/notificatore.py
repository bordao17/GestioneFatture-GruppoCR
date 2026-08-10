"""
Calcola il riepilogo numerico dei DDT elaborati (OK / CHECK / KO).

L'invio della mail di notifica NON avviene qui: questo modulo restituisce
solo i dati, poi è n8n (nodo "Send Email") a comporre e spedire il messaggio,
usando le credenziali SMTP configurate direttamente nell'interfaccia di n8n.
"""

import os
import json
from datetime import datetime

CARTELLA_BASE = "/fatture_lette"


def _carica_registro(stato):
    percorso = os.path.join(CARTELLA_BASE, f"{stato}.json")
    if not os.path.exists(percorso):
        return []
    try:
        with open(percorso, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _filtra_per_timestamp(voci, da_timestamp):
    """
    Mantiene solo le voci con 'timestamp' >= da_timestamp. Le voci senza
    campo timestamp (non dovrebbe succedere, ma per sicurezza) vengono escluse:
    meglio un falso negativo che contare per errore documenti di run precedenti.
    """
    if da_timestamp is None:
        return voci

    risultato = []
    for voce in voci:
        ts_raw = voce.get("timestamp")
        if not ts_raw:
            continue
        try:
            ts = datetime.fromisoformat(ts_raw)
        except ValueError:
            continue
        if ts >= da_timestamp:
            risultato.append(voce)
    return risultato


def calcola_riepilogo(da_timestamp=None):
    """
    Ritorna un dizionario con i conteggi OK/CHECK/KO, il totale, e la lista
    delle voci CHECK — limitati alla sola elaborazione corrente, cioè alle
    voci con timestamp >= da_timestamp (se fornito).

    da_timestamp: datetime oppure None (None = nessun filtro, conta tutto lo storico).
    """
    ok = _filtra_per_timestamp(_carica_registro("OK"), da_timestamp)
    check = _filtra_per_timestamp(_carica_registro("CHECK"), da_timestamp)
    ko = _filtra_per_timestamp(_carica_registro("KO"), da_timestamp)

    return {
        "ok": len(ok),
        "check": len(check),
        "ko": len(ko),
        "totale": len(ok) + len(check) + len(ko),
        "voci_check": check,
    }