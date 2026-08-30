"""Normalizzazione deterministica dei campi restituiti dal modello vision.

Il prompt chiede formati precisi (data "GG-MM-AAAA", numero_ddt senza etichette,
indirizzo "VIA NUMERO, CAP CITTA (PROV)"), ma un 7B non li rispetta in modo
affidabile: sui 17 documenti OK gia' elaborati solo 3 date su 17 erano nel
formato richiesto. Tutto cio' che e' esprimibile come regola esatta viene quindi
ripulito qui a valle, invece di affidarsi solo al prompt.

Principio guida: in caso di dubbio si restituisce il dato grezzo ripulito, mai
una stringa vuota. Perdere un dato e' peggio che tenerlo in un formato strano.
"""

import re
from datetime import date

# Valori che il modello usa come "non ho trovato niente": vanno azzerati,
# altrimenti il classificatore li conta come campi validi.
PLACEHOLDER = {"dato mancante", "non trovato", "nessuno", "n/a", "na", "-", "--"}

_SEP_DATA = r"[/.\-\s]"

_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

# Etichette che il modello a volte trascina dentro numero_ddt
# (visto sul campo: "DOC.DI TRASPORTO 2 7071").
_ETICHETTA_DDT = re.compile(
    r"^\s*(?:doc(?:umento)?\.?\s*(?:di\s*)?trasp(?:orto)?"
    r"|d\.?\s*d\.?\s*t\.?"
    r"|ddt"
    r"|bolla(?:\s*di\s*accompagnamento)?"
    r"|documento)[\s.:\-°º/]*",
    re.IGNORECASE,
)
_PREFISSO_NUMERO = re.compile(r"^(?:nr|num(?:ero)?|n)[\s.:°º]*", re.IGNORECASE)
# Data appiccicata in coda al numero (visto sul campo: "374764/01/07/2026").
_DATA_IN_CODA = re.compile(r"[\s/\-]\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\s*$")

_FORME_GIURIDICHE = [
    (re.compile(r"(?<![A-Z0-9])S\.?\s?R\.?\s?L\.?(?![A-Z])"), "SRL"),
    (re.compile(r"(?<![A-Z0-9])S\.?\s?P\.?\s?A\.?(?![A-Z])"), "SPA"),
    (re.compile(r"(?<![A-Z0-9])S\.?\s?N\.?\s?C\.?(?![A-Z])"), "SNC"),
    (re.compile(r"(?<![A-Z0-9])S\.?\s?A\.?\s?S\.?(?![A-Z])"), "SAS"),
]


def _pulisci(valore):
    """Stringa collassata negli spazi, con i placeholder ridotti a ''."""
    if valore is None:
        return ""
    testo = re.sub(r"\s+", " ", str(valore)).strip()
    if testo.lower().strip(".") in PLACEHOLDER:
        return ""
    return testo


def normalizza_data(valore):
    """Riporta qualsiasi data riconoscibile al formato GG-MM-AAAA.

    Gestisce i separatori visti in produzione ('-', '/', '.', spazio), l'anno a
    due cifre e la forma ISO. Se non riconosce nulla restituisce il dato grezzo.
    """
    testo = _pulisci(valore)
    if not testo:
        return ""

    # Il modello a volte allega l'orario: teniamo solo la parte di data.
    testo = re.sub(r"[\s,]+\d{1,2}[:.]\d{2}(?::\d{2})?$", "", testo)

    giorno = mese = anno = None

    m = re.match(rf"^(\d{{1,2}}){_SEP_DATA}(\d{{1,2}}){_SEP_DATA}(\d{{2,4}})$", testo)
    if m:
        giorno, mese, anno = (int(g) for g in m.groups())
    else:
        m = re.match(rf"^(\d{{4}}){_SEP_DATA}(\d{{1,2}}){_SEP_DATA}(\d{{1,2}})$", testo)
        if m:
            anno, mese, giorno = (int(g) for g in m.groups())
        else:
            m = re.match(r"^(\d{1,2})[\s\-]+([a-zà-ü]+)\.?[\s\-]+(\d{2,4})$", testo, re.IGNORECASE)
            if m and m.group(2).lower() in _MESI:
                giorno, mese, anno = int(m.group(1)), _MESI[m.group(2).lower()], int(m.group(3))

    if giorno is None:
        return testo

    if anno < 100:
        anno += 2000

    try:
        date(anno, mese, giorno)
    except ValueError:
        return testo

    return f"{giorno:02d}-{mese:02d}-{anno:04d}"


def normalizza_numero_ddt(valore):
    """Toglie etichetta e data appiccicate al numero, poi gli zeri iniziali.

    Gli zeri vengono rimossi SOLO se il numero e' interamente numerico: un
    prefisso alfanumerico (es. "SGE/0705580") resta intatto.
    """
    testo = _pulisci(valore)
    if not testo:
        return ""

    precedente = None
    while precedente != testo:  # l'etichetta puo' comparire raddoppiata
        precedente = testo
        testo = _ETICHETTA_DDT.sub("", testo).strip()

    testo = _PREFISSO_NUMERO.sub("", testo).strip()
    testo = _DATA_IN_CODA.sub("", testo).strip(" -/.,")

    if testo.isdigit():
        testo = testo.lstrip("0") or "0"

    return testo


def normalizza_indirizzo(valore):
    """Uniforma l'indirizzo di consegna a "VIA NUMERO, CAP CITTA (PROV)".

    Serve anche all'accorpatore e ai confronti: lo stesso magazzino tornava
    scritto in quattro modi diversi ("... FONTANA 01030 MONTEROSI VT",
    "...-PRATO DELLA FONTANA 01030 MONTEROSI, VT", ...).
    """
    testo = _pulisci(valore)
    if not testo:
        return ""

    testo = testo.upper()
    testo = re.sub(r"\bIT?\s*-\s*(?=\d{5}\b)", "", testo)      # "I-00189" -> "00189"
    testo = re.sub(r"\s*-\s*(?=\d{5}\b)", ", ", testo)          # "... - 06061" -> "..., 06061"
    testo = re.sub(r"(?<!,)\s+(?=\d{5}\b)", ", ", testo)        # virgola davanti al CAP
    testo = re.sub(r"[\s,\-]+([A-Z]{2})\s*$", r" (\1)", testo)  # provincia finale tra parentesi
    testo = re.sub(r"\s+", " ", testo).strip(" ,-")

    return testo


def normalizza_azienda(valore):
    """Uniforma fornitore e ragione sociale: maiuscolo + forma giuridica compatta.

    Evita che lo stesso soggetto finisca in memoria fornitori con piu' chiavi
    ("PERFETTI van Melle S.p.A." vs "PERFETTI VAN MELLE S.p.A.").
    """
    testo = _pulisci(valore)
    if not testo:
        return ""

    testo = testo.upper()
    for pattern, forma in _FORME_GIURIDICHE:
        testo = pattern.sub(forma, testo)

    return re.sub(r"\s+", " ", testo).strip(" ,-")


def normalizza_dati(dati):
    """Applica tutte le normalizzazioni al dizionario estratto dal modello."""
    if not isinstance(dati, dict):
        return dati

    dati["fornitore"] = normalizza_azienda(dati.get("fornitore"))
    dati["ragione_sociale_consegna"] = normalizza_azienda(dati.get("ragione_sociale_consegna"))
    dati["numero_ddt"] = normalizza_numero_ddt(dati.get("numero_ddt"))
    dati["data_ddt"] = normalizza_data(dati.get("data_ddt"))
    dati["indirizzo_consegna"] = normalizza_indirizzo(dati.get("indirizzo_consegna"))
    dati["leggibilita_bassa"] = bool(dati.get("leggibilita_bassa"))

    return dati
