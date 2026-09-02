"""
Accorpa A POSTERIORI i documenti multi-pagina già elaborati e salvati su disco.

A differenza dell'approccio precedente (raggruppamento durante l'analisi),
qui si parte dai file già scritti da main.py:
- OK.json / CHECK.json  → contengono i dati estratti pagina per pagina
- /fatture_lette/{stato}/{id}.pdf → il PDF di ogni singola pagina

Questo modulo:
1. Legge tutte le voci OK e CHECK
2. Raggruppa quelle che risultano appartenere allo stesso documento
   (stesso numero_ddt + fornitore simile, riusando la stessa logica
   di confronto già usata altrove — vedi src/raggruppatore.py)
3. Unisce i PDF delle pagine in un unico file multi-pagina
4. Riscrive i registri con UNA sola voce per documento reale

Va invocato come step separato (endpoint dedicato), non durante l'analisi
di ogni singola pagina — così l'analisi resta leggera e questo passaggio
gira una sola volta a fine batch.
"""

import os
import json
import fitz  # PyMuPDF, già usato in pdf_processor.py

from src.raggruppatore import stesso_documento, unisci_dati_pagina
from src.classificatore import determina_stato, CAMPI_OBBLIGATORI

CARTELLA_BASE = "/fatture_lette"
STATI_DA_ACCORPARE = ["OK", "CHECK"]
# L'unione manuale può pescare da qualsiasi tab della dashboard, KO compreso
# (una pagina illeggibile appartiene comunque a un documento reale).
STATI_TUTTI = ["OK", "CHECK", "KO"]


def _percorso_registro(stato):
    return os.path.join(CARTELLA_BASE, f"{stato}.json")


def _percorso_pdf(stato, id_documento):
    return os.path.join(CARTELLA_BASE, stato, f"{id_documento}.pdf")


def _carica_registro(stato):
    percorso = _percorso_registro(stato)
    if not os.path.exists(percorso):
        return []
    try:
        with open(percorso, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _salva_registro(stato, voci):
    percorso = _percorso_registro(stato)
    os.makedirs(os.path.dirname(percorso), exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(voci, f, indent=2, ensure_ascii=False)


def _unisci_pdf(percorsi_pdf, percorso_dest):
    """Concatena più PDF (anche provenienti da cartelle/stati diversi) in un unico file multi-pagina."""
    doc_finale = fitz.open()
    for percorso in percorsi_pdf:
        with fitz.open(percorso) as doc:
            doc_finale.insert_pdf(doc)
    doc_finale.save(percorso_dest)
    doc_finale.close()


def _pulisci_voce(voce):
    voce = dict(voce)
    voce.pop("_stato_origine", None)
    return voce


def accorpa_documenti():
    """
    Punto di ingresso principale: legge tutte le voci OK/CHECK già salvate,
    le raggruppa per documento reale, unisce PDF e dati, e riscrive i registri.

    Ritorna un piccolo report con quanti documenti sono stati accorpati.
    """
    # 1. Carica tutte le voci di OK e CHECK insieme, ricordando da quale stato provengono
    voci = []
    for stato in STATI_DA_ACCORPARE:
        for voce in _carica_registro(stato):
            voce["_stato_origine"] = stato
            voci.append(voce)

    if not voci:
        return {"documenti_totali": 0, "gruppi_creati": 0, "pagine_accorpate": 0}

    # 2. Raggruppa le voci che appartengono allo stesso documento (confronto su TUTTE le voci,
    #    non solo consecutive, dato che qui lavoriamo su registri già consolidati)
    gruppi = []
    for voce in voci:
        gruppo_trovato = None
        for gruppo in gruppi:
            if stesso_documento(voce["dati"], gruppo["dati"]):
                gruppo_trovato = gruppo
                break

        if gruppo_trovato:
            gruppo_trovato["voci"].append(voce)
            gruppo_trovato["dati"] = unisci_dati_pagina(gruppo_trovato["dati"], voce["dati"])
        else:
            gruppi.append({"dati": dict(voce["dati"]), "voci": [voce]})

    # 3. Per ogni gruppo con più di una pagina, unisci PDF e riscrivi come documento unico
    nuovi_registri = {stato: [] for stato in STATI_DA_ACCORPARE}
    pagine_accorpate = 0

    for gruppo in gruppi:
        voci_gruppo = gruppo["voci"]
        dati_uniti = gruppo["dati"]

        if len(voci_gruppo) == 1:
            # Nessun accorpamento necessario: la voce resta dov'era, invariata
            nuovi_registri[voci_gruppo[0]["_stato_origine"]].append(_pulisci_voce(voci_gruppo[0]))
            continue

        # Ricalcola lo stato sui dati UNITI: può anche migliorare
        # (es. due pagine CHECK che insieme coprono tutti i campi diventano OK)
        stato_finale, _ = determina_stato(dati_uniti, CAMPI_OBBLIGATORI)

        id_finale = voci_gruppo[0]["id"]
        percorsi_pdf_origine = [_percorso_pdf(v["_stato_origine"], v["id"]) for v in voci_gruppo]
        percorso_pdf_finale = _percorso_pdf(stato_finale, id_finale)

        os.makedirs(os.path.dirname(percorso_pdf_finale), exist_ok=True)
        _unisci_pdf(percorsi_pdf_origine, percorso_pdf_finale)

        # Rimuove i PDF originali di pagina singola (tranne quello che ora coincide con la destinazione finale)
        for percorso in percorsi_pdf_origine:
            if percorso != percorso_pdf_finale and os.path.exists(percorso):
                os.remove(percorso)

        nuovi_registri[stato_finale].append({
            "id": id_finale,
            "file_origine": voci_gruppo[0].get("file_origine"),
            "numero_pagine": len(voci_gruppo),
            "timestamp": voci_gruppo[0].get("timestamp"),
            "dati": dati_uniti
        })
        pagine_accorpate += len(voci_gruppo)

    # 4. Riscrivi i registri aggiornati
    for stato in STATI_DA_ACCORPARE:
        _salva_registro(stato, nuovi_registri[stato])

    return {
        "documenti_totali": len(voci),
        "gruppi_creati": len(gruppi),
        "pagine_accorpate": pagine_accorpate
    }

def _trova_pdf(stato, id_documento):
    """Percorso del PDF di un documento, con lo stesso fallback sulla root usato
    da GET /api/pdf/{id} per i documenti archiviati prima delle sottocartelle."""
    percorso = _percorso_pdf(stato, id_documento)
    if os.path.exists(percorso):
        return percorso

    percorso_root = os.path.join(CARTELLA_BASE, f"{id_documento}.pdf")
    if os.path.exists(percorso_root):
        return percorso_root

    return None


def unisci_documenti_manuale(ids):
    """
    Unisce a mano i documenti indicati in un unico documento multi-pagina,
    anche se stanno in stati diversi (OK/CHECK/KO).

    Serve quando l'accorpamento automatico non è scattato: `stesso_documento()`
    pretende un numero_ddt identico, quindi basta una cifra letta male su una
    pagina perché le pagine dello stesso DDT restino separate.

    L'ordine di `ids` conta: il primo è il documento PRINCIPALE — i suoi dati
    vincono, gli altri riempiono solo i campi ancora vuoti (stessa regola di
    `unisci_dati_pagina` usata dall'accorpamento automatico), e le pagine dei
    PDF vengono concatenate nell'ordine ricevuto.
    """
    # Dedup mantenendo l'ordine: il frontend manda l'ordine di selezione.
    ids_unici = list(dict.fromkeys(ids or []))
    if len(ids_unici) < 2:
        raise ValueError("Servono almeno due documenti diversi da unire.")

    # 1. Localizza ogni voce nel registro del suo stato, nell'ordine richiesto
    registri = {stato: _carica_registro(stato) for stato in STATI_TUTTI}
    voci_ordinate = []
    for doc_id in ids_unici:
        trovata = None
        for stato in STATI_TUTTI:
            for voce in registri[stato]:
                if voce.get("id") == doc_id:
                    trovata = (stato, voce)
                    break
            if trovata:
                break
        if not trovata:
            raise ValueError(f"Documento non trovato: {doc_id}")
        voci_ordinate.append(trovata)

    # 2. Unisci i dati: il primo documento fa da base, gli altri completano i buchi
    voce_master = voci_ordinate[0][1]
    dati_uniti = dict(voce_master.get("dati") or {})
    for _, voce in voci_ordinate[1:]:
        dati_uniti = unisci_dati_pagina(dati_uniti, voce.get("dati") or {})

    # Lo stato finale si ricalcola sui dati uniti, come nell'accorpamento automatico:
    # due pagine CHECK che insieme coprono tutti i campi diventano OK.
    stato_finale, _ = determina_stato(dati_uniti, CAMPI_OBBLIGATORI)

    # 3. Concatena i PDF nell'ordine di selezione
    id_finale = voce_master["id"]
    percorsi_origine = [_trova_pdf(stato, voce["id"]) for stato, voce in voci_ordinate]
    percorsi_esistenti = [p for p in percorsi_origine if p]
    percorso_finale = _percorso_pdf(stato_finale, id_finale)

    if percorsi_esistenti:
        os.makedirs(os.path.dirname(percorso_finale), exist_ok=True)
        _unisci_pdf(percorsi_esistenti, percorso_finale)
        for percorso in percorsi_esistenti:
            if percorso != percorso_finale and os.path.exists(percorso):
                os.remove(percorso)

    # 4. Riscrivi i registri: via le voci di partenza, dentro quella unita.
    #    Partiamo dalla voce master per non perdere eventuali metadati suoi
    #    (es. "inserimento": "manuale").
    file_origini = []
    for _, voce in voci_ordinate:
        origine = voce.get("file_origine")
        if origine and origine not in file_origini:
            file_origini.append(origine)

    voce_finale = _pulisci_voce(voce_master)
    voce_finale["dati"] = dati_uniti
    voce_finale["numero_pagine"] = sum(v.get("numero_pagine", 1) for _, v in voci_ordinate)
    voce_finale["file_origine"] = " + ".join(file_origini)
    voce_finale["unione"] = "manuale"

    ids_da_rimuovere = set(ids_unici)
    for stato in STATI_TUTTI:
        registri[stato] = [v for v in registri[stato] if v.get("id") not in ids_da_rimuovere]
    registri[stato_finale].append(voce_finale)

    for stato in STATI_TUTTI:
        _salva_registro(stato, registri[stato])

    return {
        "id": id_finale,
        "stato": stato_finale,
        "numero_pagine": voce_finale["numero_pagine"],
        "documenti_uniti": len(voci_ordinate),
        "stati_origine": [stato for stato, _ in voci_ordinate],
        "pdf_mancanti": len(percorsi_origine) - len(percorsi_esistenti),
    }
