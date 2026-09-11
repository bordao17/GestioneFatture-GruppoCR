"""
L'anagrafica fornitori su Postgres: schema, lettura e scrittura.

E' la prima delle anagrafiche a lasciare il JSON (2026-09-11). Qui c'e' SOLO il
mestiere del magazziniere — come una voce sta scritta su disco e come si
rilegge. Tutte le decisioni (chi somiglia a chi, quale P.IVA vince in una
fusione, quando una regola e' valida) restano dove sono sempre state, in
memory_manager.py: questo modulo non deve saperne niente, altrimenti la stessa
regola finirebbe scritta in due posti e ne resterebbe vera una sola.

IL CONTRATTO E' IL DIZIONARIO. leggi() restituisce e scrivi() accetta
esattamente la struttura che stava nel JSON:

    {"NOME FORNITORE": {"confermato": "yes", "note_specifiche": "...",
                        "indirizzi_vietati": [...], "regole_campo": [...],
                        "nomi_alternativi": [...], "partita_iva": "...",
                        "partita_iva_confermata": True, "autorizzato": True,
                        "mai_fornitore": False}}

Nove chiavi, sempre tutte presenti: e' cio' che unifica_memoria() produce, e
salva_memoria() la applica a ogni scrittura. Per questo il giro
dizionario -> tabelle -> dizionario non perde niente e nessun altro modulo si
accorge del cambio.

PERCHE' TRE TABELLE FIGLIE e non tre colonne JSONB: indirizzi vietati, nomi
alternativi e regole mirate sono elenchi che si consultano uno per uno, e sono
la parte dell'anagrafica che cresce. In colonne vere si possono interrogare
("quali fornitori hanno una regola sul numero DDT?") senza rileggere in memoria
l'intera anagrafica, che e' meta' della ragione per cui si e' passati a un
database.
"""

from src.comune.database import connessione

# Le nove chiavi della voce, nell'ordine in cui unifica_memoria() le scrive.
CHIAVI_VOCE = (
    "confermato", "note_specifiche", "indirizzi_vietati", "regole_campo",
    "nomi_alternativi", "partita_iva", "partita_iva_confermata",
    "autorizzato", "mai_fornitore",
)

# Lo schema. Ogni istruzione e' IF NOT EXISTS: prepara() gira a ogni avvio, e
# un avvio che ricrea tutto da zero e' anche il modo in cui l'anagrafica si
# rialza su una macchina nuova senza nessun passaggio a mano.
SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS fornitori (
        chiave                  TEXT PRIMARY KEY,
        confermato              TEXT    NOT NULL DEFAULT 'no',
        note_specifiche         TEXT    NOT NULL DEFAULT '',
        partita_iva             TEXT    NOT NULL DEFAULT '',
        -- La chiave assente nel JSON valeva "confermata" (le voci storiche
        -- vengono da XML firmati): qui il default tiene la stessa convenzione.
        partita_iva_confermata  BOOLEAN NOT NULL DEFAULT TRUE,
        autorizzato             BOOLEAN NOT NULL DEFAULT TRUE,
        -- Il divieto e' l'eccezione e va scritto: default permissivo.
        mai_fornitore           BOOLEAN NOT NULL DEFAULT FALSE,
        creato_il               TIMESTAMPTZ NOT NULL DEFAULT now(),
        aggiornato_il           TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # La P.IVA e' la chiave esatta fra i due lati del sistema (il cedente di una
    # fattura si riconosce di li'): merita un indice suo. Non e' UNIQUE perche'
    # l'anagrafica contiene anche le proposte lette dal modello, che possono
    # legittimamente duplicarsi finche' nessuno le ha guardate.
    "CREATE INDEX IF NOT EXISTS fornitori_partita_iva_idx "
    "ON fornitori (partita_iva) WHERE partita_iva <> ''",
    # posizione: l'ordine degli elenchi e' quello in cui l'utente li ha scritti
    # e va restituito uguale, altrimenti la textarea della dashboard si
    # rimescola sotto gli occhi di chi la sta compilando.
    """
    CREATE TABLE IF NOT EXISTS fornitori_indirizzi_vietati (
        chiave      TEXT NOT NULL REFERENCES fornitori (chiave) ON DELETE CASCADE,
        posizione   INTEGER NOT NULL,
        indirizzo   TEXT NOT NULL,
        PRIMARY KEY (chiave, posizione)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fornitori_nomi_alternativi (
        chiave      TEXT NOT NULL REFERENCES fornitori (chiave) ON DELETE CASCADE,
        posizione   INTEGER NOT NULL,
        nome        TEXT NOT NULL,
        PRIMARY KEY (chiave, posizione)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fornitori_regole_campo (
        chiave      TEXT NOT NULL REFERENCES fornitori (chiave) ON DELETE CASCADE,
        posizione   INTEGER NOT NULL,
        campo       TEXT NOT NULL,
        etichetta   TEXT NOT NULL,
        PRIMARY KEY (chiave, posizione)
    )
    """,
)


def prepara():
    """Crea le tabelle se non ci sono. La chiama il lifespan di main.py."""
    with connessione() as conn:
        for istruzione in SCHEMA:
            conn.execute(istruzione)


def leggi():
    """L'anagrafica intera, nella stessa forma che aveva nel JSON.

    Quattro interrogazioni e non una join: gli elenchi figli sono tre e una
    join li moltiplicherebbe fra loro (tre indirizzi e due regole darebbero sei
    righe da sbrogliare a mano). Su un'anagrafica da qualche decina di voci
    quattro letture sono comunque una manciata di millisecondi.
    """
    memoria = {}

    with connessione() as conn:
        for riga in conn.execute(
            "SELECT chiave, confermato, note_specifiche, partita_iva, "
            "       partita_iva_confermata, autorizzato, mai_fornitore "
            "FROM fornitori"
        ):
            memoria[riga["chiave"]] = {
                "confermato": riga["confermato"],
                "note_specifiche": riga["note_specifiche"],
                "indirizzi_vietati": [],
                "regole_campo": [],
                "nomi_alternativi": [],
                "partita_iva": riga["partita_iva"],
                "partita_iva_confermata": riga["partita_iva_confermata"],
                "autorizzato": riga["autorizzato"],
                "mai_fornitore": riga["mai_fornitore"],
            }

        for riga in conn.execute(
            "SELECT chiave, indirizzo FROM fornitori_indirizzi_vietati "
            "ORDER BY chiave, posizione"
        ):
            memoria[riga["chiave"]]["indirizzi_vietati"].append(riga["indirizzo"])

        for riga in conn.execute(
            "SELECT chiave, nome FROM fornitori_nomi_alternativi "
            "ORDER BY chiave, posizione"
        ):
            memoria[riga["chiave"]]["nomi_alternativi"].append(riga["nome"])

        for riga in conn.execute(
            "SELECT chiave, campo, etichetta FROM fornitori_regole_campo "
            "ORDER BY chiave, posizione"
        ):
            memoria[riga["chiave"]]["regole_campo"].append(
                {"campo": riga["campo"], "etichetta": riga["etichetta"]}
            )

    return memoria


def scrivi(memoria):
    """Riscrive l'anagrafica intera, in una transazione sola.

    E' una sostituzione e non un merge, esattamente come lo era la PUT sul
    file: una chiave che non c'e' piu' nel dizionario e' una voce cancellata.
    Il chiamante (salva_memoria) passa sempre l'anagrafica gia' unificata, cioe'
    tutto cio' che deve esistere dopo questa scrittura.

    Il giro e' upsert sui fornitori + svuota-e-riscrivi sugli elenchi: sui figli
    non c'e' niente da conservare (sono liste ordinate, riscriverle e' piu'
    semplice che capire quale riga e' cambiata), mentre sul padre l'upsert tiene
    creato_il, che e' l'unico dato che una cancellazione perderebbe.
    """
    chiavi = list(memoria)

    with connessione() as conn:
        # Tutto dentro una transazione (la apre e la chiude il with sulla
        # connessione): un'anagrafica a meta', con i padri nuovi e i figli
        # vecchi, e' peggio di un salvataggio fallito, perche' nessuno se ne
        # accorge finche' non manca una regola.
        if chiavi:
            conn.execute("DELETE FROM fornitori WHERE chiave <> ALL(%s)", (chiavi,))
        else:
            conn.execute("DELETE FROM fornitori")

        for chiave, voce in memoria.items():
            conn.execute(
                """
                INSERT INTO fornitori (chiave, confermato, note_specifiche,
                                       partita_iva, partita_iva_confermata,
                                       autorizzato, mai_fornitore)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chiave) DO UPDATE SET
                    confermato = EXCLUDED.confermato,
                    note_specifiche = EXCLUDED.note_specifiche,
                    partita_iva = EXCLUDED.partita_iva,
                    partita_iva_confermata = EXCLUDED.partita_iva_confermata,
                    autorizzato = EXCLUDED.autorizzato,
                    mai_fornitore = EXCLUDED.mai_fornitore,
                    aggiornato_il = now()
                """,
                (
                    chiave,
                    voce.get("confermato", "no"),
                    voce.get("note_specifiche", "") or "",
                    voce.get("partita_iva", "") or "",
                    bool(voce.get("partita_iva_confermata", True)),
                    bool(voce.get("autorizzato", True)),
                    bool(voce.get("mai_fornitore", False)),
                ),
            )

            conn.execute("DELETE FROM fornitori_indirizzi_vietati WHERE chiave = %s", (chiave,))
            for posizione, indirizzo in enumerate(voce.get("indirizzi_vietati") or []):
                conn.execute(
                    "INSERT INTO fornitori_indirizzi_vietati (chiave, posizione, indirizzo) "
                    "VALUES (%s, %s, %s)",
                    (chiave, posizione, indirizzo),
                )

            conn.execute("DELETE FROM fornitori_nomi_alternativi WHERE chiave = %s", (chiave,))
            for posizione, nome in enumerate(voce.get("nomi_alternativi") or []):
                conn.execute(
                    "INSERT INTO fornitori_nomi_alternativi (chiave, posizione, nome) "
                    "VALUES (%s, %s, %s)",
                    (chiave, posizione, nome),
                )

            conn.execute("DELETE FROM fornitori_regole_campo WHERE chiave = %s", (chiave,))
            for posizione, regola in enumerate(voce.get("regole_campo") or []):
                conn.execute(
                    "INSERT INTO fornitori_regole_campo (chiave, posizione, campo, etichetta) "
                    "VALUES (%s, %s, %s, %s)",
                    (chiave, posizione, regola.get("campo", ""), regola.get("etichetta", "")),
                )


def vuota():
    """Vero se in anagrafica non c'e' ancora nessun fornitore.

    Serve solo alla migrazione dal JSON: si importa una volta, e solo su un
    database appena nato. Un'anagrafica svuotata a mano dalla dashboard svuota
    anche la copia di scorta, quindi non c'e' modo che una cancellazione voluta
    si ritrovi reimportata al riavvio successivo.
    """
    with connessione() as conn:
        riga = conn.execute("SELECT COUNT(*) AS n FROM fornitori").fetchone()
    return riga["n"] == 0
