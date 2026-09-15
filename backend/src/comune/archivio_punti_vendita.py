"""L'anagrafica dei punti vendita su Postgres: schema, lettura e scrittura.

E' la seconda anagrafica a vivere sul database (2026-09-14), e si e' portata il
proprio modulo come vuole la regola: database.py non conosce nessuna tabella, e
aggiungerne una non deve costringere a toccarlo. Qui dentro c'e' SOLO il
mestiere del magazziniere — come una voce sta scritta su disco e come si
rilegge. Le decisioni (quale ragione sociale e quale indirizzo finiscono sul
D.D.T., come si normalizzano) stanno in punti_vendita.py.

PERCHE' SERVE. Ogni scansione di bolle e' la posta di UN punto vendita: chi
mette i fogli nello scanner sa gia' dove sono state consegnate. Due dei quattro
campi obbligatori — ragione_sociale_consegna e indirizzo_consegna — smettono
cosi' di essere una lettura da una fotografia e diventano un dato dichiarato, e
sono proprio i due su cui il modello sbaglia di piu' (il destinatario di
fatturazione stampato accanto al luogo di consegna e' il caso che ha fatto
nascere gli indirizzi_vietati).

DUE INDIRIZZI PER VOCE, e non e' una ripetizione: DIP_* e' il negozio, dove la
merce arriva davvero; IND_* e' la sede della societa' che lo possiede, dove
arriva la fattura. Sul D.D.T. serve il primo — e sono diversi per davvero
(CITTADUCALE consegna a Cittaducale ma la sua societa' ha sede a Roma).

LA CHIAVE E' COD_AZI, il codice gestionale del punto vendita: e' quello che gli
resta uguale anche se l'insegna cambia nome. DIPENDENZA e' il nome con cui lo
chiamano le persone, ed e' cio' che si legge nel menu a tendina.
"""

import csv
import io
import os

from src.comune.database import connessione

# Le dodici colonne della voce, nell'ordine del CSV di origine.
CHIAVI_VOCE = (
    "codice", "dipendenza", "via", "cap", "citta", "provincia",
    "ragione_sociale", "sede_via", "sede_cap", "sede_citta", "sede_provincia",
    "partita_iva",
)

# Le intestazioni del CSV gestionale, nell'ordine in cui le esporta. Stanno qui
# e non in punti_vendita.py perche' sono un fatto del FILE, come lo schema e'
# un fatto della tabella: chi legge questo modulo deve poter capire da dove
# viene ogni colonna senza aprire un secondo file.
COLONNE_CSV = {
    "codice": "COD_AZI",
    "dipendenza": "DIPENDENZA",
    "via": "DIP_VIA",
    "cap": "DIP_CAP",
    "citta": "DIP_CIT",
    "provincia": "DIP_PRO",
    "ragione_sociale": "RAG_SOC",
    "sede_via": "IND_VIA",
    "sede_cap": "IND_CAP",
    "sede_citta": "IND_CIT",
    "sede_provincia": "IND_PRO",
    "partita_iva": "PAR_IVA",
}

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS punti_vendita (
        -- COD_AZI. TEXT e non INTEGER: e' un codice gestionale, non un numero
        -- su cui si fanno conti, e uno zero davanti non deve poter sparire.
        codice          TEXT PRIMARY KEY,
        -- Il nome con cui lo chiamano le persone: e' cio' che si sceglie nel
        -- menu a tendina prima di premere Analizza.
        dipendenza      TEXT NOT NULL,
        -- DIP_*: il negozio, cioe' dove la merce viene consegnata davvero.
        via             TEXT NOT NULL DEFAULT '',
        cap             TEXT NOT NULL DEFAULT '',
        citta           TEXT NOT NULL DEFAULT '',
        provincia       TEXT NOT NULL DEFAULT '',
        -- IND_*: la sede della societa' che possiede il negozio. Non finisce
        -- sul D.D.T. (li' conta il luogo di consegna) ma e' l'unico posto in
        -- cui e' scritta, e senza non si saprebbe a chi appartiene il punto.
        ragione_sociale TEXT NOT NULL DEFAULT '',
        sede_via        TEXT NOT NULL DEFAULT '',
        sede_cap        TEXT NOT NULL DEFAULT '',
        sede_citta      TEXT NOT NULL DEFAULT '',
        sede_provincia  TEXT NOT NULL DEFAULT '',
        partita_iva     TEXT NOT NULL DEFAULT '',
        creato_il       TIMESTAMPTZ NOT NULL DEFAULT now(),
        aggiornato_il   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Il nome visivo e' unico nel gestionale e deve restarlo: due punti vendita
    # con la stessa etichetta nel menu a tendina renderebbero impossibile
    # sceglierne uno.
    "CREATE UNIQUE INDEX IF NOT EXISTS punti_vendita_dipendenza_idx "
    "ON punti_vendita (dipendenza)",
)


def prepara():
    """Crea la tabella se non c'e'. La chiama il lifespan di main.py."""
    with connessione() as conn:
        for istruzione in SCHEMA:
            conn.execute(istruzione)


def vuota():
    """Vero se non c'e' ancora nessun punto vendita: e' cio' che autorizza
    l'importazione dal CSV, che altrimenti si ripeterebbe a ogni avvio."""
    with connessione() as conn:
        riga = conn.execute("SELECT COUNT(*) AS n FROM punti_vendita").fetchone()
    return (riga["n"] if riga else 0) == 0


def leggi():
    """Tutti i punti vendita, in ordine di nome visivo.

    L'ordine e' quello del menu a tendina e dell'elenco in dashboard: qui si
    cerca una voce per nome, come nell'anagrafica fornitori. L'ordinamento e'
    del database e non di Python perche' la lista si legge e non si rimescola.
    """
    with connessione() as conn:
        return [
            {chiave: riga[chiave] for chiave in CHIAVI_VOCE}
            for riga in conn.execute(
                "SELECT " + ", ".join(CHIAVI_VOCE) + " FROM punti_vendita "
                "ORDER BY dipendenza"
            )
        ]


def scrivi(voci):
    """Upsert su un elenco di punti vendita, in una transazione sola.

    NON e' la sostituzione integrale che fa scrivi() sui fornitori, ed e'
    voluto: li' il chiamante e' una PUT che manda l'anagrafica intera, qui e'
    un'importazione da CSV. Un export parziale del gestionale non deve poter
    cancellare i punti vendita che non contiene — soprattutto perche' i D.D.T.
    gia' archiviati ne portano il codice.
    """
    with connessione() as conn:
        for voce in voci:
            conn.execute(
                """
                INSERT INTO punti_vendita (codice, dipendenza, via, cap, citta,
                                           provincia, ragione_sociale, sede_via,
                                           sede_cap, sede_citta, sede_provincia,
                                           partita_iva)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codice) DO UPDATE SET
                    dipendenza = EXCLUDED.dipendenza,
                    via = EXCLUDED.via,
                    cap = EXCLUDED.cap,
                    citta = EXCLUDED.citta,
                    provincia = EXCLUDED.provincia,
                    ragione_sociale = EXCLUDED.ragione_sociale,
                    sede_via = EXCLUDED.sede_via,
                    sede_cap = EXCLUDED.sede_cap,
                    sede_citta = EXCLUDED.sede_citta,
                    sede_provincia = EXCLUDED.sede_provincia,
                    partita_iva = EXCLUDED.partita_iva,
                    aggiornato_il = now()
                """,
                tuple(voce.get(chiave, "") or "" for chiave in CHIAVI_VOCE),
            )

    return len(voci)


def leggi_csv(percorso):
    """Le voci contenute in un export del gestionale, senza toccare il database.

    Il file e' quello che il gestionale sputa fuori: intestazioni maiuscole,
    virgolette solo dove servono, campi vuoti dove il dato non c'e'. Qui si
    traduce nelle chiavi della tabella e si toglie lo spazio di contorno, e
    basta: le normalizzazioni (maiuscolo, forma giuridica, P.IVA) sono
    decisioni e stanno in punti_vendita.py.

    Una riga senza codice o senza nome visivo viene saltata: sono le due cose
    con cui il punto vendita si sceglie, e una voce che non si puo' scegliere
    non serve a nessuno.
    """
    if not os.path.isfile(percorso):
        return []

    # utf-8-sig: l'export passa spesso da Excel, che ci mette il BOM davanti e
    # trasformerebbe "COD_AZI" in "﻿COD_AZI", cioe' in una colonna che non
    # si trova piu' per nome.
    with io.open(percorso, encoding="utf-8-sig", newline="") as f:
        righe = list(csv.DictReader(f))

    voci = []
    for riga in righe:
        voce = {
            chiave: str(riga.get(colonna, "") or "").strip()
            for chiave, colonna in COLONNE_CSV.items()
        }
        if not voce["codice"] or not voce["dipendenza"]:
            continue
        voci.append(voce)

    return voci
