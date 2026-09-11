"""Le route del pannello Configurazione: i lavori automatici e le impostazioni.

Due gruppi che stanno insieme perche' si guardano insieme: gli orari dei tre
lavori SONO impostazioni come le altre (vuoto = non pianificare), e il pannello
che mostra prossima esecuzione ed esito dell'ultima serve a sapere se quegli
orari stanno funzionando davvero. Un lavoro notturno che non parte non lo
scoprirebbe nessuno fino al mattino dopo: da qui "Esegui adesso" e la mail di
prova.
"""

from fastapi import APIRouter, HTTPException

from src.comune import pianificatore
from src.comune.configurazione import configurazione_completa, salva_configurazione
from src.notifiche import mailer
from src.notifiche.impaginazione import pagina as pagina_mail

router = APIRouter()


@router.get("/api/pianificazione")
async def stato_pianificazione():
    """I tre lavori automatici (orario, prossima esecuzione, ultimo esito) e lo
    stato delle notifiche. La password SMTP non esce mai di qui."""
    return {**pianificatore.stato(), "notifiche": mailer.descrizione()}


@router.post("/api/pianificazione/{lavoro}/esegui")
def esegui_lavoro(lavoro: str):
    """Fa partire adesso un lavoro pianificato, senza aspettare la sua ora.

    Stessa strada dell'esecuzione notturna, di proposito: se la si prova a mano
    e funziona, di notte funzionerà per le stesse ragioni. Sincrona perché una
    scansione D.D.T. è bloccante.
    """
    if lavoro not in {chiave for chiave, _, _ in pianificatore.LAVORI}:
        raise HTTPException(status_code=404, detail=f"Lavoro sconosciuto: {lavoro}")

    esito = pianificatore.esegui(lavoro, motivo="richiesto dalla dashboard")
    if esito.get("errore"):
        raise HTTPException(status_code=500, detail=esito["errore"])
    return esito


@router.post("/api/notifiche/prova")
def prova_notifiche():
    """Manda una mail di prova ai destinatari configurati.

    È l'unico modo di sapere se SMTP è a posto senza aspettare la notte: qui
    l'errore serve, quindi si usa invia() e non invia_silenzioso().
    """
    if not mailer.configurata():
        raise HTTPException(
            status_code=400,
            detail="Notifiche non configurate: servono almeno il server SMTP e un destinatario.",
        )

    corpo = pagina_mail(
        "Prova di invio",
        "Se leggi questo messaggio, le notifiche funzionano.",
        '<tr><td style="padding:0 32px 14px 32px;" class="padding-laterale">'
        '<div style="font-size:13px; color:#374151;">Da qui in poi arriveranno il riepilogo '
        'delle scansioni automatiche e la mail di sollecito di ciò che è fermo da troppi '
        'giorni, agli orari impostati nella sezione Configurazione.</div></td></tr>',
    )

    try:
        return mailer.invia("Prova di invio - GestioneFatture GruppoCR", corpo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/configurazione")
async def get_configurazione():
    """Le impostazioni modificabili, con valore attuale e provenienza.

    L'origine ('dashboard' / 'ambiente' / 'default') non è un dettaglio: senza,
    un campo pieno non direbbe se si sta guardando una modifica fatta di qui o
    il valore del docker-compose, e non si capirebbe cosa succede svuotandolo.
    """
    return {"impostazioni": configurazione_completa()}


@router.put("/api/configurazione")
async def put_configurazione(payload: dict):
    """Salva le impostazioni cambiate dalla dashboard.

    Un campo svuotato non è un errore: significa "torna al valore del
    docker-compose". I valori fuori intervallo vengono scartati e restituiti in
    'scartate', invece di essere accettati in silenzio.

    Hanno effetto subito, senza riavviare: chi le usa le rilegge a ogni
    chiamata (vedi src/comune/configurazione.py).
    """
    try:
        salvate, scartate = salva_configurazione(payload or {})
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"Configurazione non salvata: {e}")

    if scartate:
        print(f"⚠️ Configurazione: valori scartati {scartate}")

    return {
        "message": "Configurazione salvata",
        "salvate": sorted(salvate),
        "scartate": scartate,
        "impostazioni": configurazione_completa(),
    }
