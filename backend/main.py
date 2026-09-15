"""L'avvio dell'applicazione, e nient'altro.

Fino al 2026-09-11 qui dentro c'erano anche trentasei route, gli aiutanti che
si passavano fra loro e i due corpi di elaborazione: 1726 righe in cui trovare
una route voleva dire cercarla, e in cui due cose scritte a mille righe di
distanza sembravano indipendenti anche quando non lo erano. Le route sono
passate in src/api/, un modulo per entita' del dominio (vedi il suo
__init__.py). Qui restano le quattro cose che riguardano l'applicazione intera:
il filtro sui log, la preparazione delle anagrafiche, il ciclo di vita e il
montaggio dei router.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.api import (
    documenti, fatture, fornitori, impostazioni, ingresso, punti_vendita,
)
from src.comune import (
    archivio_fornitori, archivio_punti_vendita, database, pianificatore,
)
from src.comune.memory_manager import migra_da_file_a_database
from src.comune.punti_vendita import importa_da_csv


# La dashboard interroga /api/elaborazione ogni 2 secondi per tenere viva la
# barra di avanzamento: e' una lettura di un dizionario in memoria, non pesa
# nulla, ma la sua riga di access log si ripete 30 volte al minuto e sommerge i
# print pagina-per-pagina dell'estrazione. Qui si tace solo quella riga.
class FiltroPollingBarra(logging.Filter):
    def filter(self, record):
        return "/api/elaborazione" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(FiltroPollingBarra())


def _prepara_anagrafiche():
    """Crea le tabelle delle anagrafiche e, la prima volta, ci porta dentro il JSON.

    Non solleva MAI. Un database che non risponde deve poter costare
    l'anagrafica sul database, non l'avvio del backend: senza, un container
    Postgres che tarda a salire terrebbe giu' anche le estrazioni e la
    dashboard, che con la copia su file funzionano lo stesso.
    """
    if not database.configurato():
        print("ℹ️ DATABASE_URL non impostata: le anagrafiche restano sul file JSON.")
        return

    try:
        archivio_fornitori.prepara()
        importate = migra_da_file_a_database()
        if importate:
            print(f"📥 Anagrafica fornitori importata nel database: {importate} voci.")
        else:
            print("✅ Anagrafica fornitori sul database.")
    except Exception as e:
        print(f"⚠️ Anagrafiche su database non disponibili ({e}): "
              f"si continua con la copia su file.")

    # I punti vendita hanno il loro try: sono la seconda anagrafica e una non
    # deve poter costare l'altra. Qui pero' non c'e' nessuna copia su file su
    # cui ripiegare — senza database il menu a tendina resta vuoto e le
    # scansioni tornano a essere quelle di prima, senza consegna dichiarata.
    try:
        archivio_punti_vendita.prepara()
        importati = importa_da_csv()
        if importati:
            print(f"📥 Anagrafica punti vendita importata dal CSV: {importati} voci.")
        else:
            print("✅ Anagrafica punti vendita sul database.")
    except Exception as e:
        print(f"⚠️ Anagrafica punti vendita non disponibile ({e}): "
              f"le scansioni resteranno senza punto vendita dichiarato.")


@asynccontextmanager
async def ciclo_di_vita(app):
    """All'avvio prepara le anagrafiche e mette in moto il pianificatore.

    Le tre azioni le passa main.py invece di essere importate dentro il
    pianificatore: quello sa QUANDO, non COSA. Se gli orari sono vuoti (ed e'
    il valore di partenza) il thread gira a vuoto e non succede niente: il
    sistema resta quello di prima, tutto a pulsanti.
    """
    _prepara_anagrafiche()
    pianificatore.avvia({
        "scansione_ddt": ingresso.lavoro_scansione_ddt,
        "scansione_fatture": ingresso.lavoro_scansione_fatture,
        "sollecito": ingresso.lavoro_sollecito,
    })
    yield


app = FastAPI(
    title="GestioneFatture - GruppoCR API",
    description="Microservizio AI per l'estrazione dati da DDT e Fatture",
    version="1.0.0",
    lifespan=ciclo_di_vita,
)

# Abilita CORS per il frontend React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Senza expose_headers il browser nasconde al JavaScript ogni header non
    # standard: X-Fascicolo-Anteprima esiste proprio perche' la dashboard possa
    # dire che il fascicolo mostrato e' provvisorio, e da cross-origin non
    # sarebbe leggibile.
    expose_headers=["X-Fascicolo-Anteprima"],
)

# L'ORDINE CONTA: FastAPI prova le route nell'ordine in cui sono registrate, e
# i router sono registrati nell'ordine in cui le route stavano prima.
# Un caso su tutti: ingresso porta /api/fatture/carica e /api/fatture/scansiona,
# fatture porta /api/fatture/{id_fattura} — invertendo i due include, "carica"
# e "scansiona" diventerebbero l'id di una fattura che non esiste.
app.include_router(fornitori.router)
app.include_router(punti_vendita.router)
app.include_router(documenti.router)
app.include_router(ingresso.router)
app.include_router(fatture.router)
app.include_router(impostazioni.router)


if __name__ == "__main__":
    print("Avvio del server GestioneFatture - GruppoCR (Author: Lo Staff di Pa.Rea S.n.C.)...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
