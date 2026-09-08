"""Stato condiviso delle elaborazioni in corso, per la barra di avanzamento in dashboard.

Le estrazioni "classiche" (un PDF intero, spesso lanciato da n8n sulla cartella
monitorata) durano minuti: senza questo registro la dashboard non ha modo di
sapere che sta succedendo qualcosa e sembra semplicemente ferma.

È volutamente uno stato in memoria e non un file: serve solo a raccontare cosa
sta accadendo *adesso* nel processo, e se il backend si riavvia non c'è nulla da
ricostruire (i documenti già elaborati stanno nei registri, quelli in corso sono
persi comunque). Il lock serve perché le route sincrone di FastAPI girano nel
threadpool: due estrazioni possono aggiornare il dizionario insieme.
"""

import threading
import time
import uuid

_lock = threading.Lock()
_lavori = {}
_ultimo_completato = None


def inizia(nome_file, tipo="estrazione", pagine_totali=0):
    """Registra un nuovo lavoro e ne restituisce l'id.

    `pagine_totali` è 0 finché il PDF non è stato diviso in pagine: in quella
    fase il frontend mostra una barra indeterminata invece di una percentuale
    finta.
    """
    id_lavoro = str(uuid.uuid4())
    with _lock:
        _lavori[id_lavoro] = {
            "id": id_lavoro,
            "file": nome_file,
            "tipo": tipo,
            "pagine_totali": pagine_totali,
            "pagina_corrente": 0,
            "inizio": time.time(),
        }
    return id_lavoro


def imposta_totale(id_lavoro, pagine_totali):
    """Numero di pagine, noto solo dopo la conversione PDF → immagini."""
    with _lock:
        if id_lavoro in _lavori:
            _lavori[id_lavoro]["pagine_totali"] = pagine_totali


def aggiorna_pagina(id_lavoro, pagina_corrente):
    with _lock:
        if id_lavoro in _lavori:
            _lavori[id_lavoro]["pagina_corrente"] = pagina_corrente


def termina(id_lavoro, esito="completato"):
    """Chiude il lavoro. Va chiamata anche in caso di errore, altrimenti la
    barra resta accesa per sempre: per questo nel chiamante sta in un finally."""
    global _ultimo_completato
    with _lock:
        lavoro = _lavori.pop(id_lavoro, None)
        if lavoro:
            lavoro["esito"] = esito
            lavoro["secondi"] = round(time.time() - lavoro["inizio"], 1)
            _ultimo_completato = lavoro


def stato():
    """Fotografia per il frontend: lavori attivi + l'ultimo concluso."""
    adesso = time.time()
    with _lock:
        in_corso = [
            {**lavoro, "secondi": round(adesso - lavoro["inizio"], 1)}
            for lavoro in _lavori.values()
        ]
        ultimo = dict(_ultimo_completato) if _ultimo_completato else None

    in_corso.sort(key=lambda lavoro: lavoro["inizio"])
    return {"in_corso": in_corso, "ultimo_completato": ultimo}
