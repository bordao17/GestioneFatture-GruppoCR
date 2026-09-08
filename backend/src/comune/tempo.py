"""Orologio del backend: un solo fuso e un solo formato di timestamp.

I timestamp finiscono nei registri e vengono riletti da chi filtra per data
(/riepilogo, l'anzianita' delle fatture in coda): scriverli in due formati
diversi da due moduli diversi significherebbe romperne uno alla prima lettura.
"""

import os
import zoneinfo
from datetime import datetime

FUSO = zoneinfo.ZoneInfo(os.getenv("GENERIC_TIMEZONE", "Europe/Rome"))


def timestamp_locale():
    """Adesso, in ISO 8601 con fuso: e' il formato scritto in tutti i registri."""
    return datetime.now(FUSO).isoformat()


def leggi_timestamp(valore):
    """Rilegge un timestamp di registro, None se assente o illeggibile.

    Le voci vecchie possono averlo scritto senza fuso: in quel caso viene
    assunto quello locale, altrimenti il confronto con adesso() esploderebbe
    ("can't compare offset-naive and offset-aware datetimes").
    """
    if not valore:
        return None
    try:
        istante = datetime.fromisoformat(str(valore))
    except (TypeError, ValueError):
        return None

    if istante.tzinfo is None:
        return istante.replace(tzinfo=FUSO)
    return istante


def adesso():
    return datetime.now(FUSO)
