"""
Raggruppa le pagine analizzate singolarmente in "documenti logici" (DDT multi-pagina).

Il raggruppamento avviene A POSTERIORI, confrontando i dati già estratti dal
modello (numero_ddt + fornitore) — non richiede modifiche al prompt né campi
aggiuntivi, quindi non ha alcun impatto sulla velocità di analisi delle immagini.
"""

import re
import time
import uuid
from difflib import SequenceMatcher

from src.llm_engine import estrai_dati_da_immagine

SOGLIA_SIMILARITA_FORNITORE = 0.5

# Campi che vengono "uniti" tra le pagine di uno stesso documento: se una pagina
# ha il campo vuoto ma un'altra pagina dello stesso gruppo lo ha valorizzato,
# il valore viene riportato nel dato finale del gruppo.
CAMPI_DA_UNIRE = ["fornitore", "numero_ddt", "data_ddt", "indirizzo_consegna", "ragione_sociale_consegna"]


def normalizza_numero_ddt(numero):
    """Confronto esatto ma tollerante a spazi/maiuscole diverse tra pagine dello stesso documento."""
    return (numero or "").strip().upper()


def normalizza_fornitore(nome):
    """Riduce il nome fornitore a soli caratteri alfanumerici minuscoli, per confronti tolleranti a piccoli errori OCR."""
    return re.sub(r'[^a-z0-9]', '', (nome or "").lower())


def stesso_documento(dati_pagina, dati_gruppo):
    """
    Decide se una pagina appartiene allo stesso documento del gruppo corrente,
    confrontando numero_ddt (match esatto, obbligatorio) e fornitore (match
    tollerante, per gestire piccole variazioni OCR tra una pagina e l'altra
    dello stesso DDT multi-pagina).
    """
    numero_pagina = normalizza_numero_ddt(dati_pagina.get("numero_ddt"))
    numero_gruppo = normalizza_numero_ddt(dati_gruppo.get("numero_ddt"))

    # Senza un numero_ddt uguale su entrambe le pagine, non uniamo mai:
    # troppo rischioso decidere di accorpare due documenti diversi.
    if not numero_pagina or not numero_gruppo or numero_pagina != numero_gruppo:
        return False

    fornitore_pagina = normalizza_fornitore(dati_pagina.get("fornitore"))
    fornitore_gruppo = normalizza_fornitore(dati_gruppo.get("fornitore"))

    # Se manca il fornitore su una delle due pagine, ci basiamo solo sul numero_ddt
    # (che comunque è già un identificativo abbastanza specifico).
    if not fornitore_pagina or not fornitore_gruppo:
        return True

    similarita = SequenceMatcher(None, fornitore_pagina, fornitore_gruppo).ratio()
    return similarita >= SOGLIA_SIMILARITA_FORNITORE


def unisci_dati_pagina(dati_gruppo, dati_nuova_pagina, campi_da_unire=CAMPI_DA_UNIRE):
    """
    Riempie nel dato del gruppo solo i campi ancora vuoti, usando i valori
    della nuova pagina. Non sovrascrive MAI un campo già valorizzato da una
    pagina precedente dello stesso gruppo.
    """
    for campo in campi_da_unire:
        if not dati_gruppo.get(campo) and dati_nuova_pagina.get(campo):
            dati_gruppo[campo] = dati_nuova_pagina[campo]

    if dati_nuova_pagina.get("leggibilita_bassa"):
        dati_gruppo["leggibilita_bassa"] = True

    return dati_gruppo


def raggruppa_pagine_in_documenti(immagini):
    """
    Analizza ogni pagina con il modello (nessuna modifica al prompt/velocità)
    e RAGGRUPPA A POSTERIORI le pagine consecutive che risultano appartenere
    allo stesso documento, confrontando numero_ddt e fornitore già estratti.

    Il confronto avviene SOLO con l'ultimo gruppo aperto: si assume che le
    pagine dello stesso DDT multi-pagina siano consecutive nel file originale.

    Ritorna una lista di gruppi:
      { "id": ..., "dati": {...unito...}, "immagini": [path_pagina_1, path_pagina_2, ...] }
    """
    gruppi = []

    for img_path in immagini:
        inizio = time.time()
        dati_estratti = estrai_dati_da_immagine(img_path) or {}
        print(f"⏱️ Pagina {img_path} elaborata in {time.time() - inizio:.1f} secondi")

        if gruppi and stesso_documento(dati_estratti, gruppi[-1]["dati"]):
            gruppo = gruppi[-1]
            gruppo["immagini"].append(img_path)
            gruppo["dati"] = unisci_dati_pagina(gruppo["dati"], dati_estratti)
            print(f"🔗 Pagina unita al documento precedente (id={gruppo['id']}, numero_ddt={dati_estratti.get('numero_ddt')})")
        else:
            gruppi.append({
                "id": str(uuid.uuid4()),
                "dati": dati_estratti,
                "immagini": [img_path]
            })

    return gruppi