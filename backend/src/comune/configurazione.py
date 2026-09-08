"""
Le impostazioni che si cambiano senza ricostruire il container.

Fino a ieri OLLAMA_HOST, MODELLO_VISION e compagnia stavano solo in
docker-compose.yml: cambiarne una voleva dire aprire un file YAML sul server e
rifare `docker compose up -d`. Sono pero' esattamente le leve che si provano
piu' spesso (si cambia modello, si sposta la macchina Ollama, si allunga la
soglia del sollecito), quindi adesso vivono anche in data/configurazione.json,
che sta su un volume montato e sopravvive alle ricostruzioni dell'immagine.

TRE LIVELLI, in quest'ordine di precedenza:
    1. data/configurazione.json   scritto dalla dashboard
    2. la variabile d'ambiente    docker-compose.yml
    3. il default qui sotto

Il file vince sull'ambiente di proposito: e' l'unico dei tre che una persona
puo' cambiare mentre il sistema gira, e se non vincesse la dashboard mentirebbe.
Cancellare una voce dal file (o il file intero) fa tornare il valore del
compose: e' la via di fuga se una modifica dalla dashboard rompe qualcosa.

REGOLA IMPORTANTE PER CHI USA QUESTO MODULO: i valori vanno letti con valore()
*al momento in cui servono*, mai messi in una costante di modulo all'import.
Una costante letta all'avvio congelerebbe il valore fino al riavvio, ed e'
precisamente il problema che questo file esiste per togliere.
"""

import json
import os
import threading

# Il file sta accanto a fornitori_memoria.json, sullo stesso volume: le due
# cose che l'utente amministra dalla dashboard stanno nello stesso posto.
PERCORSO = os.getenv("FILE_CONFIGURAZIONE", "data/configurazione.json")

TESTO = "testo"
INTERO = "intero"
DECIMALE = "decimale"

# Le sole chiavi ammesse. Una chiave non elencata qui viene ignorata sia in
# lettura sia in scrittura: la dashboard non deve poter inventare impostazioni
# che nessuno legge, ne' sovrascrivere variabili d'ambiente di sistema.
IMPOSTAZIONI = (
    {
        "chiave": "OLLAMA_HOST",
        "etichetta": "Server Ollama",
        "tipo": TESTO,
        "default": "http://10.1.20.25:11434",
        "gruppo": "Motore AI",
        "aiuto": "Indirizzo della macchina che esegue il modello vision. "
                 "E' una GPU condivisa in LAN: se e' occupata da un altro "
                 "modello, l'estrazione aspetta.",
    },
    {
        "chiave": "MODELLO_VISION",
        "etichetta": "Modello vision",
        "tipo": TESTO,
        "default": "qwen2.5vl:7b",
        "gruppo": "Motore AI",
        "aiuto": "Il modello che legge le scansioni. Deve essere gia' scaricato "
                 "sul server Ollama. Attenzione ai modelli 'thinking': "
                 "consumano la finestra di contesto prima di rispondere.",
    },
    {
        "chiave": "MODELLO_NUM_CTX",
        "etichetta": "Finestra di contesto (num_ctx)",
        "tipo": INTERO,
        "default": 8192,
        "minimo": 2048,
        "massimo": 131072,
        "gruppo": "Motore AI",
        "aiuto": "Token disponibili al modello. L'immagine di una pagina a zoom "
                 "2.5 ne occupa gia' circa 4500: se le risposte tornano vuote, "
                 "e' questo il primo numero da alzare.",
    },
    {
        "chiave": "PDF_RENDER_ZOOM",
        "etichetta": "Risoluzione di rendering",
        "tipo": DECIMALE,
        "default": 2.5,
        "minimo": 1.0,
        "massimo": 6.0,
        "gruppo": "Motore AI",
        "aiuto": "Fattore di ingrandimento della pagina prima di darla al "
                 "modello (2.5 = circa 180 DPI). Alzarlo NON e' gratis: "
                 "provato a 3.5, il modello ha sbagliato piu' campi, non meno.",
    },
    {
        "chiave": "GIORNI_ATTESA_SOLLECITO",
        "etichetta": "Giorni prima di sollecitare una bolla mancante",
        "tipo": INTERO,
        "default": 30,
        "minimo": 1,
        "massimo": 365,
        "gruppo": "Solleciti",
        "aiuto": "Dopo quanti giorni una fattura che aspetta un D.D.T. (e un "
                 "D.D.T. che aspetta la sua fattura) finisce nella mail del "
                 "mattino. E' un numero organizzativo, non tecnico.",
    },
    {
        "chiave": "GIORNI_ATTESA_ACCOPPIAMENTO",
        "etichetta": "Giorni prima di sollecitare un accoppiamento non firmato",
        "tipo": INTERO,
        "default": 7,
        "minimo": 1,
        "massimo": 365,
        "gruppo": "Solleciti",
        "aiuto": "Una pratica con tutti i D.D.T. trovati ma senza la conferma "
                 "dell'operatore non aspetta un documento: aspetta un click. "
                 "La soglia e' piu' corta apposta.",
    },
)

_PER_CHIAVE = {i["chiave"]: i for i in IMPOSTAZIONI}

# Il file viene riletto solo quando cambia sul disco: valore() e' chiamata
# dentro il ciclo delle pagine, e una lettura per pagina sarebbe uno spreco
# silenzioso. La mtime basta: a scriverlo e' solo salva_configurazione().
_LUCCHETTO = threading.Lock()
_CACHE = {"mtime": None, "dati": {}}


def _converti(impostazione, grezzo):
    """Il valore nel tipo dichiarato, oppure None se non e' convertibile.

    None significa "questa sorgente non ha un valore usabile" e fa passare la
    palla alla sorgente successiva: un file con dentro una stringa vuota o
    'qwen2.5vl:7b' scritto nel campo del num_ctx non deve rompere l'estrazione,
    deve solo essere ignorato.
    """
    if grezzo is None:
        return None

    tipo = impostazione["tipo"]

    if tipo == TESTO:
        testo = str(grezzo).strip()
        return testo or None

    try:
        numero = int(grezzo) if tipo == INTERO else float(grezzo)
    except (TypeError, ValueError):
        return None

    minimo, massimo = impostazione.get("minimo"), impostazione.get("massimo")
    if minimo is not None and numero < minimo:
        return None
    if massimo is not None and numero > massimo:
        return None

    return numero


def _dal_file():
    """Il contenuto di configurazione.json, riletto solo se e' cambiato."""
    try:
        mtime = os.path.getmtime(PERCORSO)
    except OSError:
        with _LUCCHETTO:
            _CACHE["mtime"], _CACHE["dati"] = None, {}
        return {}

    with _LUCCHETTO:
        if _CACHE["mtime"] == mtime:
            return _CACHE["dati"]

    try:
        with open(PERCORSO, "r", encoding="utf-8") as f:
            dati = json.load(f)
        if not isinstance(dati, dict):
            dati = {}
    except (json.JSONDecodeError, OSError) as e:
        # Stessa scelta di carica_memoria(): un file corrotto fa tornare ai
        # valori del compose, non fa fallire l'estrazione in corso.
        print(f"⚠️ configurazione.json non leggibile ({e}): valgono le variabili d'ambiente.")
        dati = {}

    with _LUCCHETTO:
        _CACHE["mtime"], _CACHE["dati"] = mtime, dati

    return dati


def valore(chiave):
    """Il valore attuale di un'impostazione: file → ambiente → default.

    Da chiamare ogni volta che serve, non una volta all'import.
    """
    impostazione = _PER_CHIAVE.get(chiave)
    if impostazione is None:
        raise KeyError(f"Impostazione sconosciuta: {chiave}")

    dal_file = _converti(impostazione, _dal_file().get(chiave))
    if dal_file is not None:
        return dal_file

    dall_ambiente = _converti(impostazione, os.getenv(chiave))
    if dall_ambiente is not None:
        return dall_ambiente

    return impostazione["default"]


def origine(chiave):
    """Da dove viene il valore attuale: 'dashboard', 'ambiente' o 'default'.

    Serve alla dashboard per dire all'utente se sta guardando una sua modifica
    o il valore del docker-compose: senza, un campo pieno non distingue le due
    cose e non si capisce cosa succede svuotandolo.
    """
    impostazione = _PER_CHIAVE[chiave]
    if _converti(impostazione, _dal_file().get(chiave)) is not None:
        return "dashboard"
    if _converti(impostazione, os.getenv(chiave)) is not None:
        return "ambiente"
    return "default"


def configurazione_completa():
    """Tutte le impostazioni con valore, origine e metadati, per la dashboard."""
    return [
        {**impostazione, "valore": valore(impostazione["chiave"]),
         "origine": origine(impostazione["chiave"])}
        for impostazione in IMPOSTAZIONI
    ]


def salva_configurazione(dati):
    """Scrive le impostazioni modificate, scartando chiavi e valori non validi.

    Una chiave assente (o svuotata) non viene scritta: e' il modo di dire
    "torna al valore del docker-compose". Restituisce (salvate, scartate) cosi'
    la dashboard puo' dire quali campi non sono stati accettati invece di
    fingere di averli presi.
    """
    if not isinstance(dati, dict):
        raise ValueError("La configurazione dev'essere un oggetto.")

    da_scrivere, scartate = {}, []

    for chiave, grezzo in dati.items():
        impostazione = _PER_CHIAVE.get(chiave)
        if impostazione is None:
            scartate.append(chiave)
            continue

        # Il campo svuotato non e' un errore: significa "usa il default".
        if grezzo is None or (isinstance(grezzo, str) and not grezzo.strip()):
            continue

        convertito = _converti(impostazione, grezzo)
        if convertito is None:
            scartate.append(chiave)
            continue

        da_scrivere[chiave] = convertito

    cartella = os.path.dirname(PERCORSO)
    if cartella:
        os.makedirs(cartella, exist_ok=True)

    with open(PERCORSO, "w", encoding="utf-8") as f:
        json.dump(da_scrivere, f, indent=4, ensure_ascii=False, sort_keys=True)

    with _LUCCHETTO:
        _CACHE["mtime"] = None  # forza la rilettura al prossimo valore()

    return da_scrivere, scartate
