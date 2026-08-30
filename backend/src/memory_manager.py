import os
import json
import re
from difflib import SequenceMatcher

from src.normalizzatore import normalizza_azienda

# Ora il file vive dentro la cartella data/
FILE_MEMORIA = os.path.join('data', 'fornitori_memoria.json')

# Forme giuridiche e qualificatori generici: irrilevanti per capire SE due voci
# parlano dello stesso fornitore ("Cerealdolci S.r.l." e "CEREALDOLCI SRL").
_RUMORE_RAGIONE_SOCIALE = re.compile(
    r"\b(?:SRLS|SRL|SPA|SNC|SAS|SS|SOCIETA'?\s+AGRICOLA|SOCIETA'?|COOPERATIVA|COOP)\b"
)

# Sopra questa soglia due nomi sono considerati lo stesso fornitore.
# Misurata sulle 37 voci realmente presenti in memoria: i duplicati veri stanno
# a 0.80-1.00, mentre fornitori diversi non superano 0.59 ("VITAKRAFT ITALIA"
# vs "NUTRITION & SANTÈ ITALIA", che condividono solo "ITALIA"). 0.85 tiene il
# margine largo dal lato pericoloso: fondere due fornitori distinti farebbe
# perdere una regola già confermata.
SOGLIA_SIMILARITA = 0.85
# Il nome più corto deve coprire almeno questa frazione delle PAROLE di quello
# più lungo. Il confronto è per parole e non per caratteri perché "ITALIA SRL"
# è contenuto in "ABC ITALIA SRL" come stringa, ma non ne è un'abbreviazione:
# a livello di parole copre 1 token su 2 e viene correttamente scartato, mentre
# "MARIANANTONI SILVIO" ne copre 2 su 3 di "PANIFICIO MARIANANTONI SILVIO".
COPERTURA_MINIMA_TOKEN = 0.6


def chiave_confronto(nome):
    """Riduce un nome fornitore alla sua parte identificante, per i confronti.

    Maiuscolo, senza forma giuridica e senza punteggiatura: "PERFETTI van Melle
    S.p.A." e "PERFETTI VAN MELLE SPA" collassano entrambi su "perfettivanmelle".
    """
    testo = _RUMORE_RAGIONE_SOCIALE.sub(" ", normalizza_azienda(nome))
    return re.sub(r"[^A-Z0-9]", "", testo).lower()


def token_confronto(nome):
    """Le parole identificanti del nome, senza forma giuridica né iniziali sciolte."""
    testo = _RUMORE_RAGIONE_SOCIALE.sub(" ", normalizza_azienda(nome))
    return {t for t in re.findall(r"[A-Z0-9]+", testo) if len(t) > 1}


def stesso_fornitore(nome_a, nome_b):
    """True se i due nomi indicano — con ogni probabilità — lo stesso fornitore."""
    a, b = chiave_confronto(nome_a), chiave_confronto(nome_b)
    if not a or not b:
        return False
    if a == b:
        return True

    # Nome abbreviato: "MARIANANTONI SILVIO SRLS" al posto di "Panificio
    # Marianantoni Silvio srls" (il modello a volte perde l'insegna iniziale).
    token_a, token_b = token_confronto(nome_a), token_confronto(nome_b)
    if token_a and token_b:
        corti, lunghi = sorted((token_a, token_b), key=len)
        if corti <= lunghi and len(corti) / len(lunghi) >= COPERTURA_MINIMA_TOKEN:
            return True

    # Piccole differenze di lettura tra un documento e l'altro
    # ("SANTÈ"/"SANITÀ"): confronto tollerante sui caratteri.
    return SequenceMatcher(None, a, b).ratio() >= SOGLIA_SIMILARITA


def trova_fornitore_simile(nome, memoria):
    """Restituisce la chiave già presente in memoria che indica lo stesso
    fornitore, oppure None se è davvero un fornitore nuovo."""
    for chiave_esistente in memoria:
        if stesso_fornitore(nome, chiave_esistente):
            return chiave_esistente
    return None


def unifica_memoria(memoria):
    """Porta tutte le chiavi in maiuscolo e fonde le voci dello stesso fornitore.

    Nella fusione non si perde nulla: la voce risultante è confermata se lo era
    almeno una delle originali, e tiene la nota più dettagliata tra quelle
    disponibili. Come chiave si conserva il nome più lungo, cioè il più
    informativo ("PANIFICIO MARIANANTONI SILVIO SRLS" batte "MARIANANTONI SILVIO SRLS").
    """
    if not isinstance(memoria, dict):
        return {}

    unificata = {}

    for nome, dati in memoria.items():
        if not isinstance(dati, dict):
            dati = {"confermato": "no", "note_specifiche": ""}

        chiave = normalizza_azienda(nome) or str(nome).strip().upper()
        if not chiave:
            continue

        esistente = trova_fornitore_simile(chiave, unificata)

        if esistente is None:
            unificata[chiave] = {
                "confermato": str(dati.get("confermato", "no")).lower(),
                "note_specifiche": dati.get("note_specifiche", "") or "",
            }
            continue

        voce = unificata[esistente]
        nota_nuova = dati.get("note_specifiche", "") or ""
        if len(nota_nuova) > len(voce["note_specifiche"]):
            voce["note_specifiche"] = nota_nuova
        if str(dati.get("confermato", "no")).lower() in ("yes", "si"):
            voce["confermato"] = "yes"

        # Il nome più lungo è quello che conserva più informazione.
        if len(chiave) > len(esistente):
            unificata[chiave] = unificata.pop(esistente)

    return unificata

def carica_memoria():
    if os.path.exists(FILE_MEMORIA):
        try:
            with open(FILE_MEMORIA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            # File vuoto (0 byte) o corrotto: senza questa rete l'errore risale
            # fino a /estrai-ddt tramite ottieni_regole_formattate e fa fallire
            # l'intera estrazione con un 500.
            print(f"⚠️ Memoria fornitori illeggibile ({e}): riparto da memoria vuota.")
            return {}
    return {}

def salva_memoria(memoria):
    # Unico punto di scrittura del file: normalizzando qui, sia il censimento
    # automatico sia il PUT dalla dashboard non possono reintrodurre duplicati.
    with open(FILE_MEMORIA, 'w', encoding='utf-8') as f:
        json.dump(unifica_memoria(memoria), f, indent=4, ensure_ascii=False)

def aggiorna_fornitore(fornitore, note_proposte):
    if not fornitore or fornitore.lower() == "dato mancante":
        return
    memoria = carica_memoria()

    # Il confronto è per somiglianza, non per uguaglianza: il modello scrive lo
    # stesso fornitore in modi diversi da un documento all'altro ("PERFETTI van
    # Melle S.p.A." / "PERFETTI VAN MELLE SPA"), e censirli separatamente
    # riempirebbe la dashboard di doppioni da confermare uno per uno.
    chiave = normalizza_azienda(fornitore)
    gia_noto = trova_fornitore_simile(chiave, memoria)

    if gia_noto:
        print(f"[MEMORIA] '{fornitore}' riconosciuto come '{gia_noto}': nessuna nuova voce.")
        return

    # Lo inserisce SOLO la prima volta che lo incontra
    memoria[chiave] = {
        "confermato": "no",
        "note_specifiche": note_proposte
    }
    salva_memoria(memoria)
    print(f"[MEMORIA] Nuovo fornitore censito: {chiave}. Note auto-generate in attesa di conferma ('yes').")

def ottieni_regole_formattate():
    """Legge il JSON e prende le regole SOLO se 'confermato' è impostato su 'yes'."""
    memoria = carica_memoria()
    regole = []
    
    for fornitore, dati in memoria.items():
        nota = dati.get("note_specifiche", "").strip()
        confermato = dati.get("confermato", "no").lower()
        
        # Inietta la regola solo se hai approvato cambiando in 'yes'
        if nota and confermato in ["yes", "si"]:
            regole.append(f"- Se il fornitore è '{fornitore}': {nota}")
    
    if regole:
        return "\n".join(regole)
    return ""