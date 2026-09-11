"""
Il database delle anagrafiche: unico punto del backend che apre una connessione.

Fino al 2026-09-11 le anagrafiche vivevano in un JSON su volume
(data/fornitori_memoria.json). Ha retto finche' l'unica era quella dei
fornitori e la si riscriveva tutta a ogni salvataggio, ma e' la prima di
diverse: un file per anagrafica significa riscrivere ogni volta l'intero
contenuto per cambiare un campo, nessun vincolo che impedisca due voci con la
stessa chiave, e nessun modo di chiedere "chi ha questa partita IVA" senza
rileggere tutto in memoria. Da qui Postgres, in un container accanto agli
altri due.

REGOLA: qui dentro non c'e' nessuna tabella. Questo modulo sa APRIRE una
connessione e basta; ogni anagrafica si porta il proprio schema e le proprie
query (la prima e' src/comune/archivio_fornitori.py). Cosi' aggiungerne una
seconda non costringe a toccare questo file.

CONFIGURAZIONE: DATABASE_URL sta nelle variabili d'ambiente e NON in
configurazione.py, per la stessa ragione dei percorsi. Le impostazioni della
dashboard si possono sbagliare e si correggono dalla dashboard; una stringa di
connessione sbagliata scritta di li' toglierebbe di mezzo proprio l'anagrafica
che serve a correggerla.

DATABASE_URL VUOTO = nessun database. Il backend parte lo stesso e le
anagrafiche tornano al JSON di prima: e' la via d'uscita se il container
Postgres non si alza, ed e' anche cio' che tiene funzionante un checkout del
progetto su una macchina dove gira solo il backend.
"""

import os
from contextlib import contextmanager

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    # Il backend deve poter partire anche senza il driver installato: senza
    # database le anagrafiche usano il JSON, esattamente come prima.
    psycopg = None
    dict_row = None


# postgresql://utente:password@host:porta/database — la scrive docker-compose.
URL = os.getenv("DATABASE_URL", "")

# Secondi di attesa prima di dire che il database non risponde. Corto di
# proposito: questa connessione sta sulla strada di un'estrazione, e un
# database irraggiungibile deve fallire subito per lasciarla proseguire con il
# JSON, non tenerla ferma trenta secondi per pagina.
TIMEOUT = int(os.getenv("DATABASE_TIMEOUT", "5"))


class DatabaseNonDisponibile(RuntimeError):
    """Il database non e' configurato, o non risponde."""


def configurato():
    """Vero se c'e' un database a cui parlare. Chi legge un'anagrafica lo
    chiede prima di provarci, per non trasformare una scelta (nessun database)
    in un errore da registrare a ogni pagina."""
    return bool(URL.strip()) and psycopg is not None


@contextmanager
def connessione(autocommit=False):
    """Una connessione per operazione, chiusa dal with.

    Niente pool: le anagrafiche si leggono una volta per pagina e si scrivono
    di rado, quindi l'handshake (millisecondi) non si nota accanto ai secondi
    del modello, e un pool andrebbe aperto, sorvegliato e chiuso — tre cose in
    piu' che possono rompersi all'avvio.

    Le righe tornano come dizionari (dict_row): le anagrafiche si rileggono per
    nome di colonna, e una tupla posizionale si sposta in silenzio il giorno in
    cui si aggiunge un campo.
    """
    if not configurato():
        raise DatabaseNonDisponibile(
            "DATABASE_URL non impostata (o driver psycopg assente)."
        )

    try:
        conn = psycopg.connect(URL, connect_timeout=TIMEOUT, row_factory=dict_row,
                               autocommit=autocommit)
    except psycopg.Error as e:
        raise DatabaseNonDisponibile(f"connessione a Postgres fallita: {e}") from e

    try:
        with conn:
            yield conn
    finally:
        conn.close()


def raggiungibile():
    """Una domanda sola al database, per la diagnostica dell'avvio."""
    if not configurato():
        return False
    try:
        with connessione() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
