"""Le route dell'anagrafica punti vendita.

Una sola, e in sola lettura: i punti vendita li possiede il gestionale, che li
esporta in CSV. Farli modificare anche da qui creerebbe la seconda fonte di
verita' che tutto il resto del progetto evita — e il giorno in cui il
gestionale riesporta, una delle due sarebbe sbagliata senza che nessuno se ne
accorga. Si aggiornano riscrivendo data/punti_vendita.csv su un database
vuoto, oppure con un UPDATE.

La consuma il menu a tendina della barra di ingresso dei D.D.T.: e' li' che si
dichiara per quale punto vendita e' la pila di fogli appena messa nello
scanner.
"""

from fastapi import APIRouter

from src.comune import punti_vendita

router = APIRouter()


@router.get("/api/punti-vendita")
async def elenco_punti_vendita():
    """I punti vendita in anagrafica, in ordine di nome visivo.

    Non fallisce mai: senza database (o con Postgres giu') torna un elenco
    vuoto e la dashboard mostra il menu a tendina disattivato invece di un
    errore rosso. La scansione senza punto vendita e' una strada prevista, non
    un guasto — e' quella che ha sempre fatto il pianificatore notturno.
    """
    voci = punti_vendita.elenco()
    return {"punti_vendita": voci, "totale": len(voci)}
