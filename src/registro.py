"""Gestione del registro persistente (OK.json / CHECK.json) in /fatture_lette."""

import os
import json

CARTELLA_REGISTRO = "/fatture_lette"


def aggiorna_registro(stato, nuovi_dati):
    """
    Legge il file OK.json o CHECK.json (se esiste), aggiunge il nuovo dato
    e lo salva. I file vengono creati nella root della cartella fatture_lette.
    """
    percorso_registro = os.path.join(CARTELLA_REGISTRO, f"{stato}.json")
    registro = []

    os.makedirs(os.path.dirname(percorso_registro), exist_ok=True)

    if os.path.exists(percorso_registro):
        try:
            with open(percorso_registro, "r", encoding="utf-8") as f:
                registro = json.load(f)
        except json.JSONDecodeError:
            pass

    registro.append(nuovi_dati)

    with open(percorso_registro, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)