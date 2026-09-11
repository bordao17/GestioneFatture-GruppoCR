"""L'identita' di una pagina scansionata, per riconoscerla se ritorna.

Sui D.D.T. non e' mai esistita nessuna deduplica, ed era una scelta: due bolle
diverse possono legittimamente portare lo stesso numero, quindi *sui dati
estratti* non c'e' nessuna regola che distingua un duplicato da un documento
vero. Resta pero' il caso che capita davvero — la stessa pila passata due volte
nello scanner, lo stesso PDF trascinato due volte in DDT/da_leggere/, il
pulsante Analizza premuto due volte — e finora quel caso non dava nessun
segnale: la pagina ripetuta prendeva un id nuovo, veniva letta dal modello
(sei secondi di GPU), archiviata, e infine **assorbita in silenzio**
dall'accorpamento dentro il documento gia' presente, che si ritrovava una
pagina in piu' e il suo doppione dentro il fascicolo.

**La chiave e' l'immagine della pagina, non i dati.** E' l'unico dato che
distingue due bolle identiche nel contenuto da una bolla contata due volte, ed
e' una regola ESATTA: sha256 dei byte dell'immagine renderizzata, nessuna
soglia, nessuna somiglianza. Vale il principio gia' scritto per i formati e per
gli indirizzi vietati — se e' una regola esatta va in Python, e se non lo e'
non si inventa una soglia senza averla misurata.

Si firma l'immagine RENDERIZZATA e non il file caricato, per due motivi: un PDF
di quattro pagine ricaricato va riconosciuto pagina per pagina (magari due sono
nuove), e la stessa pagina puo' arrivare dentro due PDF diversi. In cambio la
firma dipende da PDF_RENDER_ZOOM: cambiando lo zoom le firme vecchie non
corrispondono piu'. E' il verso giusto in cui sbagliare — si perde un
riconoscimento, non si scarta un documento buono.

**Limite noto, da non coprire con una soglia:** un foglio passato due volte
nello scanner produce due immagini diverse (allineamento, rumore, polvere) e
non viene riconosciuto. Riconoscerlo vorrebbe dire un hash percettivo con una
distanza massima, cioe' un numero da misurare su un batch reale prima di
scriverlo — e un falso positivo qui non e' un campo brutto da guardare, e' una
bolla buttata via.
"""

import hashlib
import os

from src.comune.registro import leggi_registro

# Il nome del campo sta qui una volta sola: lo scrivono l'estrazione e
# l'inserimento manuale, lo rileggono l'accorpamento e l'unione manuale.
CAMPO_FIRME = "firme_pagine"

STATI_DDT = ["OK", "CHECK", "KO"]


def firma_pagina(percorso_immagine):
    """sha256 dei byte dell'immagine di una pagina, o "" se non e' leggibile.

    Restituisce la stringa vuota invece di sollevare: una firma che non si puo'
    calcolare deve costare il riconoscimento del duplicato, non l'estrazione.
    """
    try:
        digest = hashlib.sha256()
        with open(percorso_immagine, "rb") as f:
            for blocco in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(blocco)
        return digest.hexdigest()
    except OSError as e:
        print(f"⚠️ Impronta non calcolabile per {os.path.basename(percorso_immagine)}: {e}")
        return ""


def firme_di(voce):
    """Le firme di una voce di registro, sempre come lista (anche vuota)."""
    firme = (voce or {}).get(CAMPO_FIRME)
    if isinstance(firme, list):
        return [f for f in firme if f]
    return []


def firme_archiviate():
    """Tutte le firme gia' presenti nei tre registri, per id del documento.

    KO compreso: una pagina illeggibile archiviata e' comunque una pagina gia'
    vista, e rileggerla darebbe un secondo KO identico al primo.

    Le voci archiviate prima del 2026-09-11 non hanno firme e semplicemente non
    compaiono qui: non c'e' niente da migrare, i documenti vecchi restano fuori
    dal confronto e il sistema si comporta con loro come ha sempre fatto.
    """
    archivio = {}
    for stato in STATI_DDT:
        for voce in leggi_registro(stato):
            for firma in firme_di(voce):
                archivio.setdefault(firma, {"id": voce.get("id", ""), "stato": stato})
    return archivio
