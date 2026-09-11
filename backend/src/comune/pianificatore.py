"""L'orologio del sistema: i lavori che partono da soli a un'ora fissa.

Era n8n (tre nodi Schedule). n8n faceva pero' solo due cose — guardare l'ora e
spedire una mail — mentre tutto cio' che decideva stava gia' qui: dal 2026-09-09
l'orologio e il postino stanno dove sta lo stato.

TRE LAVORI, e sono i tre che ha senso far partire da soli:
    scansione_ddt       analizza cio' che e' fermo in DDT/da_leggere
    scansione_fatture   legge cio' che e' fermo in FATTURE/da_leggere
    sollecito           manda la mail di cio' che e' fermo da troppi giorni

Gli orari stanno in configurazione.py (ORARIO_SCANSIONE_DDT e compagni) e si
rileggono a ogni giro: cambiarne uno dalla dashboard ha effetto senza riavviare
niente. **Il campo vuoto significa "non pianificare"**, ed e' il valore di
partenza: chi non compila nulla continua ad avere il sistema di prima, tutto a
pulsanti.

COME DECIDE SE E' ORA. Non tiene "l'ultima volta che ha girato" ma l'istante
dell'ultimo controllo, e fa partire un lavoro quando l'orario previsto cade
nella finestra (ultimo_controllo, adesso]. Due conseguenze volute:
  - un backend spento a quell'ora semplicemente salta il giro, invece di
    lanciare una scansione a sorpresa all'avvio del mattino dopo;
  - una scansione D.D.T. che dura quaranta minuti tiene fermo il ciclo, e al
    giro successivo la finestra copre tutto il tempo passato: se nel frattempo
    e' scattata l'ora delle fatture, parte subito dopo. Che e' esattamente
    l'ordine che si vuole (prima le bolle, poi le fatture che le cercano).

I lavori girano **uno alla volta** in un thread solo, il suo: sono tutti
bloccanti e due estrazioni in parallelo si contenderebbero la stessa GPU.
"""

import threading
import time
from datetime import timedelta

from src.comune.configurazione import valore
from src.comune.tempo import adesso

# Ogni mezzo minuto: la precisione al minuto e' piu' che sufficiente per un
# lavoro notturno, e il giro costa una lettura di dizionario.
INTERVALLO = 30

# I lavori, con l'impostazione che ne decide l'ora. L'ORDINE CONTA: quando due
# orari cadono nella stessa finestra, i D.D.T. vanno estratti prima che le
# fatture li cerchino.
LAVORI = (
    ("scansione_ddt", "ORARIO_SCANSIONE_DDT", "Scansione D.D.T."),
    ("scansione_fatture", "ORARIO_SCANSIONE_FATTURE", "Scansione fatture"),
    ("sollecito", "ORARIO_SOLLECITO", "Mail di sollecito"),
)

_LUCCHETTO = threading.Lock()      # protegge _STATO, come in stato_elaborazione.py
_ESECUZIONE = threading.Lock()     # un lavoro alla volta, anche se lanciato a mano
_AZIONI = {}
_STATO = {chiave: {"in_corso": False, "ultima": None, "esito": None, "durata": 0.0}
          for chiave, _, _ in LAVORI}
_ultimo_controllo = None
_thread = None


def _orario_di(chiave_configurazione):
    """L'ora pianificata come (ore, minuti), oppure None se il lavoro e' spento."""
    grezzo = str(valore(chiave_configurazione) or "").strip()
    if not grezzo:
        return None
    ore, minuti = grezzo.split(":")[:2]
    return int(ore), int(minuti)


def prossima_esecuzione(chiave_configurazione, da=None):
    """Quando tocchera' a questo lavoro: oggi se l'ora deve ancora arrivare, domani se e' passata."""
    orario = _orario_di(chiave_configurazione)
    if orario is None:
        return None

    ora = da or adesso()
    prevista = ora.replace(hour=orario[0], minute=orario[1], second=0, microsecond=0)
    if prevista <= ora:
        prevista += timedelta(days=1)
    return prevista


def esegui(chiave, motivo="pianificato"):
    """Esegue un lavoro adesso, registrandone l'esito. Non solleva mai.

    Usata sia dal ciclo sia dai pulsanti della dashboard: un lavoro fatto a
    mano e uno notturno devono percorrere la stessa strada, o divergono.
    """
    azione = _AZIONI.get(chiave)
    if azione is None:
        return {"eseguito": False, "motivo": f"lavoro sconosciuto: {chiave}"}

    with _ESECUZIONE:
        with _LUCCHETTO:
            _STATO[chiave]["in_corso"] = True
        inizio = time.time()
        print(f"⏰ {chiave}: avvio ({motivo}).")

        try:
            esito = azione() or {}
            riassunto = esito.get("riassunto", "completato")
            errore = None
        except Exception as e:
            riassunto = f"non riuscito: {e}"
            errore = str(e)
            print(f"❌ {chiave}: {e}")

        durata = time.time() - inizio
        with _LUCCHETTO:
            _STATO[chiave].update({
                "in_corso": False,
                "ultima": adesso().isoformat(),
                "esito": riassunto,
                "durata": round(durata, 1),
                "errore": errore,
            })

        print(f"⏰ {chiave}: {riassunto} ({durata:.1f}s).")
        return {"eseguito": True, "esito": riassunto, "errore": errore}


def _giro():
    """Un controllo: fa partire i lavori il cui orario e' caduto dall'ultimo giro."""
    global _ultimo_controllo

    ora = adesso()
    precedente = _ultimo_controllo or ora

    for chiave, chiave_configurazione, _ in LAVORI:
        orario = _orario_di(chiave_configurazione)
        if orario is None:
            continue

        prevista = ora.replace(hour=orario[0], minute=orario[1], second=0, microsecond=0)
        # La finestra e' aperta a sinistra: un lavoro non riparte due volte per
        # lo stesso orario, e non recupera quelli persi mentre il backend era spento.
        if precedente < prevista <= ora:
            esegui(chiave)

    _ultimo_controllo = ora


def _ciclo():
    while True:
        try:
            _giro()
        except Exception as e:
            # Il pianificatore non deve morire per un giro andato storto:
            # domani a quell'ora deve esserci ancora.
            print(f"⚠️ Giro del pianificatore fallito: {e}")
        time.sleep(INTERVALLO)


def avvia(azioni):
    """Registra le azioni e mette in moto il ciclo (una volta sola).

    Le azioni arrivano da main.py invece di essere importate qui: il
    pianificatore sa QUANDO, non COSA, e importare le pipeline dentro un modulo
    di src/comune/ significherebbe legarlo a tutti e due i flussi.
    """
    global _thread, _ultimo_controllo

    _AZIONI.update(azioni)

    if _thread is not None and _thread.is_alive():
        return

    # La base di partenza e' adesso: un backend riavviato alle 23:10 non deve
    # eseguire la scansione delle 23:00 di stasera.
    _ultimo_controllo = adesso()
    _thread = threading.Thread(target=_ciclo, name="pianificatore", daemon=True)
    _thread.start()

    pianificati = [f"{etichetta} {valore(cfg)}" for _, cfg, etichetta in LAVORI if valore(cfg)]
    print("⏰ Pianificatore avviato: "
          + (", ".join(pianificati) if pianificati else "nessun lavoro pianificato "
             "(orari vuoti nella sezione Configurazione)."))


def stato():
    """Per la dashboard: i tre lavori con orario, prossima esecuzione e ultimo esito."""
    ora = adesso()
    with _LUCCHETTO:
        istantanea = {chiave: dict(dati) for chiave, dati in _STATO.items()}

    lavori = []
    for chiave, chiave_configurazione, etichetta in LAVORI:
        prossima = prossima_esecuzione(chiave_configurazione, ora)
        lavori.append({
            "chiave": chiave,
            "etichetta": etichetta,
            "impostazione": chiave_configurazione,
            "orario": str(valore(chiave_configurazione) or ""),
            "prossima": prossima.isoformat() if prossima else None,
            **istantanea[chiave],
        })

    return {"attivo": _thread is not None and _thread.is_alive(), "lavori": lavori}
