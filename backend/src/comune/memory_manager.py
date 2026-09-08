import os
import json
import re
from difflib import SequenceMatcher

from src.comune.normalizzatore import normalizza_azienda, partita_iva_valida

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

# Indirizzi che per un dato fornitore NON sono mai la consegna (tipicamente la
# sede legale/cessionario ristampata su ogni bolla). È una regola esatta, quindi
# vive in Python e non nel prompt: un 7B ignora sistematicamente i "MAI usare X",
# un confronto di stringhe no. A differenza delle note, questa lista la scrive
# solo l'utente (non viene mai auto-generata), quindi vale sempre, anche senza
# "confermato": "yes".
CHIAVE_INDIRIZZI_VIETATI = "indirizzi_vietati"

# Regole della forma "il campo X sta sotto l'etichetta Y". A differenza delle
# note in prosa NON finiscono nel prompt: diventano una domanda mirata al
# modello a estrazione avvenuta (llm_engine.applica_regole_campo).
# Misurato il 2026-09-07 su SA.BA FISH, VITAKRAFT, CEREALDOLCI e NUOVO SRL: la
# stessa identica regola scritta dentro il prompt di estrazione sbaglia 6
# documenti su 6, posta come domanda singola ne azzecca 16 su 16 in ~1 secondo.
# Non e' una questione di lunghezza del prompt (togliere tutte le regole non
# cambia una virgola dell'output): un 7B a cui si chiedono sei campi insieme
# non applica una condizione "se il fornitore e' questo, allora guarda li'".
# Come indirizzi_vietati, queste regole le scrive solo l'utente e quindi valgono
# sempre, anche senza "confermato": "yes".
CHIAVE_REGOLE_CAMPO = "regole_campo"

# I campi che una regola mirata puo' indirizzare: sono quelli che il modello
# estrae, perche' e' li' che la risposta va a finire. "leggibilita_bassa" non
# c'e' apposta, non e' un dato scritto sul documento.
CAMPI_REGOLABILI = (
    "fornitore",
    "partita_iva",
    "numero_ddt",
    "data_ddt",
    "ragione_sociale_consegna",
    "indirizzo_consegna",
)

# Il confronto tra indirizzi è già tollerante a punteggiatura e maiuscole, la
# soglia serve solo per le differenze di lettura del modello (una cifra del CAP).
SOGLIA_SIMILARITA_INDIRIZZO = 0.9

# Sotto questa lunghezza un indirizzo vietato non può essere usato come
# sottostringa: "VIA 2" comparirebbe dentro mezzo archivio.
LUNGHEZZA_MINIMA_CONTENIMENTO = 8

# P.IVA del fornitore (IdFiscaleIVA del cedente nelle fatture elettroniche) e
# flag di autorizzazione. Servono al filtro in ingresso del flusso fatture:
# l'archivio da cui arrivano gli XML contiene anche fatture che non ci
# riguardano, e vanno riconosciute PRIMA di entrare nella coda.
# La P.IVA e' l'unico dato di fornitore che sia esatto: nella fattura c'e'
# sempre, e "CRIK CROK S.R.L." vs "CRIK CROK SRL" non deve dipendere da una
# soglia. Dal 2026-09-08 si legge anche sul DDT scansionato, ma li' e' una
# lettura del modello: entra come proposta e vale come chiave solo dopo la
# conferma umana (CHIAVE_PIVA_CONFERMATA).
CHIAVE_PARTITA_IVA = "partita_iva"
CHIAVE_AUTORIZZATO = "autorizzato"

# Da dove viene la P.IVA scritta nella voce. Vera = dato certo (letto da un XML
# firmato, oppure confermato a mano da chi aveva il documento sotto gli occhi);
# Falsa = proposta letta dal modello su una scansione, ancora da verificare.
# La distinzione serve perche' la P.IVA e' una CHIAVE: una cifra sbagliata non
# e' un campo brutto da guardare, e' un fornitore diverso.
CHIAVE_PIVA_CONFERMATA = "partita_iva_confermata"

# Altri nomi sotto cui lo STESSO fornitore compare sui documenti. Serve quando
# la ragione sociale per esteso e la forma corta non si somigliano abbastanza:
# "SA.BA FISH" copre 3 parole su 8 di "SA.BA DI SABATINI EUGENIO FISH VENDITA
# SURGELATI", cioe' 0.375 contro COPERTURA_MINIMA_TOKEN di 0.60, e a seconda di
# quanto nome il modello legge sulla singola scansione le regole del fornitore
# scattano o no. Abbassare la soglia non e' la risposta: e' la stessa che
# decide gli abbinamenti fattura<->DDT, e allargarla li' fonde fornitori
# diversi. Un alias e' invece un dato esatto, scritto a mano dall'utente, che
# non sposta nessun confronto automatico.
CHIAVE_ALIAS = "nomi_alternativi"


def normalizza_piva(valore):
    """Solo cifre: "IT 16834201002", "IT16834201002" e "16834201002" sono la
    stessa partita IVA scritta in tre modi che girano tutti nei tracciati."""
    return re.sub(r"[^0-9]", "", str(valore or ""))


def piva_confermata_da_valore(valore, default=True):
    """Legge il flag "partita_iva_confermata", con la stessa convenzione di
    autorizzato_da_valore: la chiave ASSENTE vale confermata.

    Le P.IVA gia' presenti in anagrafica ci sono arrivate da un XML di fattura
    (dato fiscale esatto) e non hanno il campo: trattarle come da verificare
    riempirebbe la dashboard di conferme inutili. Chi nasce invece da una
    lettura del modello su una scansione scrive False ESPLICITAMENTE, ed e'
    l'unica cosa che finisce nella coda delle conferme.
    """
    if valore is None:
        return default
    if isinstance(valore, bool):
        return valore
    return str(valore).strip().lower() in ("yes", "si", "sì", "true", "1")


def autorizzato_da_valore(valore, default=True):
    """Legge il flag "autorizzato" accettando bool, "si"/"no", "true"/"false".

    Quando la chiave manca il fornitore è considerato AUTORIZZATO: le voci già
    in memoria sono state censite dai DDT realmente ricevuti, quindi sono per
    definizione fornitori con cui lavoriamo, e trattarle come non autorizzate
    bloccherebbe di colpo ogni fattura al primo avvio del filtro. Le voci nate
    da una fattura di un cedente sconosciuto lo scrivono invece esplicitamente
    a False: quelle sono il caso per cui il filtro esiste.
    """
    if valore is None:
        return default
    if isinstance(valore, bool):
        return valore
    return str(valore).strip().lower() in ("yes", "si", "sì", "true", "1")


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


def chiave_indirizzo(indirizzo):
    """Riduce un indirizzo alla forma confrontabile: maiuscolo, solo lettere e
    cifre separate da spazi singoli, senza la coda "ITALIA" che alcuni fornitori
    stampano e altri no ("Via del Rame, 2 - 06134 Perugia (PG) ITALIA" e
    "VIA DEL RAME 2, 06134 PERUGIA (PG)" collassano sulla stessa chiave)."""
    testo = re.sub(r"[^A-Z0-9]+", " ", (indirizzo or "").upper())
    testo = re.sub(r"\s+", " ", testo).strip()
    return re.sub(r"\s+ITALIA$", "", testo).strip()


def stesso_indirizzo(indirizzo_a, indirizzo_b):
    """True se i due indirizzi sono lo stesso posto.

    Il contenimento serve perché l'utente in dashboard scrive spesso solo la
    parte stabile ("VIA DEL RAME 2") mentre il modello estrae la riga completa
    di CAP e città.
    """
    a, b = chiave_indirizzo(indirizzo_a), chiave_indirizzo(indirizzo_b)
    if not a or not b:
        return False
    if a == b:
        return True

    corto, lungo = sorted((a, b), key=len)
    if len(corto) >= LUNGHEZZA_MINIMA_CONTENIMENTO and corto in lungo:
        return True

    return SequenceMatcher(None, a, b).ratio() >= SOGLIA_SIMILARITA_INDIRIZZO


def lista_indirizzi(valore):
    """Normalizza il campo indirizzi_vietati: accetta stringa singola o lista,
    scarta le righe vuote (la textarea della dashboard ne produce sempre)."""
    if not valore:
        return []
    if isinstance(valore, str):
        valore = [valore]
    if not isinstance(valore, list):
        return []
    return [str(v).strip() for v in valore if str(v).strip()]


def lista_regole_campo(valore):
    """Normalizza il campo regole_campo: tiene solo le voci con ENTRAMBI campo
    ed etichetta valorizzati.

    Una regola senza etichetta non e' una regola ma un desiderio: la domanda
    mirata si costruisce attorno a un testo stampato sul documento, e senza
    quello non c'e' niente da cercare. Il campo dev'essere uno di quelli che il
    modello estrae davvero, altrimenti la risposta non avrebbe dove finire.
    """
    if not isinstance(valore, list):
        return []

    regole = []
    for voce in valore:
        if not isinstance(voce, dict):
            continue
        campo = str(voce.get("campo", "")).strip()
        etichetta = str(voce.get("etichetta", "")).strip()
        if campo in CAMPI_REGOLABILI and etichetta:
            regole.append({"campo": campo, "etichetta": etichetta})
    return regole


def regole_campo_per(fornitore, memoria=None):
    """Le regole "campo sotto etichetta" definite per questo fornitore.

    Il fornitore si cerca per somiglianza come ovunque nel modulo: il nome
    arriva da una lettura del modello e cambia da un documento all'altro.
    """
    memoria = carica_memoria() if memoria is None else memoria
    chiave = trova_fornitore_simile(normalizza_azienda(fornitore), memoria)
    if not chiave:
        return []

    voce = memoria.get(chiave)
    if not isinstance(voce, dict):
        return []

    return lista_regole_campo(voce.get(CHIAVE_REGOLE_CAMPO))


def lista_alias(valore):
    """Normalizza il campo nomi_alternativi: stringa singola o lista, righe
    vuote scartate (la textarea della dashboard ne produce sempre)."""
    return lista_indirizzi(valore)


def trova_fornitore_simile(nome, memoria):
    """Restituisce la chiave già presente in memoria che indica lo stesso
    fornitore, oppure None se è davvero un fornitore nuovo.

    Il confronto è per somiglianza sulla chiave e sui nomi alternativi: gli
    alias esistono proprio per i casi in cui la somiglianza non basta (nome per
    esteso contro forma corta), e vanno quindi provati tutti prima di
    concludere che il fornitore è nuovo.
    """
    for chiave_esistente, dati in memoria.items():
        if stesso_fornitore(nome, chiave_esistente):
            return chiave_esistente

        if not isinstance(dati, dict):
            continue
        for alias in lista_alias(dati.get(CHIAVE_ALIAS)):
            if stesso_fornitore(nome, alias):
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
                CHIAVE_INDIRIZZI_VIETATI: lista_indirizzi(dati.get(CHIAVE_INDIRIZZI_VIETATI)),
                CHIAVE_REGOLE_CAMPO: lista_regole_campo(dati.get(CHIAVE_REGOLE_CAMPO)),
                CHIAVE_ALIAS: lista_alias(dati.get(CHIAVE_ALIAS)),
                CHIAVE_PARTITA_IVA: normalizza_piva(dati.get(CHIAVE_PARTITA_IVA)),
                CHIAVE_PIVA_CONFERMATA: piva_confermata_da_valore(dati.get(CHIAVE_PIVA_CONFERMATA)),
                CHIAVE_AUTORIZZATO: autorizzato_da_valore(dati.get(CHIAVE_AUTORIZZATO)),
            }
            continue

        voce = unificata[esistente]
        nota_nuova = dati.get("note_specifiche", "") or ""
        if len(nota_nuova) > len(voce["note_specifiche"]):
            voce["note_specifiche"] = nota_nuova
        if str(dati.get("confermato", "no")).lower() in ("yes", "si"):
            voce["confermato"] = "yes"

        # P.IVA: vince quella confermata, poi quella che c'è. Una proposta
        # letta dal modello non deve mai coprire un dato certo, ma se la voce
        # non ne ha nessuna la proposta si tiene (con il suo flag), altrimenti
        # sparirebbe proprio la conferma che stiamo chiedendo all'operatore.
        piva_nuova = normalizza_piva(dati.get(CHIAVE_PARTITA_IVA))
        confermata_nuova = piva_confermata_da_valore(dati.get(CHIAVE_PIVA_CONFERMATA))
        if piva_nuova and (not voce[CHIAVE_PARTITA_IVA]
                           or (confermata_nuova and not voce[CHIAVE_PIVA_CONFERMATA])):
            voce[CHIAVE_PARTITA_IVA] = piva_nuova
            voce[CHIAVE_PIVA_CONFERMATA] = confermata_nuova
        if autorizzato_da_valore(dati.get(CHIAVE_AUTORIZZATO), default=False):
            voce[CHIAVE_AUTORIZZATO] = True

        # Gli indirizzi vietati si sommano (senza ridoppiarli): sono divieti,
        # tenerne uno solo riaprirebbe la porta all'errore che l'altro chiudeva.
        for indirizzo in lista_indirizzi(dati.get(CHIAVE_INDIRIZZI_VIETATI)):
            if not any(stesso_indirizzo(indirizzo, noto) for noto in voce[CHIAVE_INDIRIZZI_VIETATI]):
                voce[CHIAVE_INDIRIZZI_VIETATI].append(indirizzo)

        # Gli alias si sommano: sono i nomi sotto cui il fornitore e' stato
        # davvero visto, e scartarne uno rimetterebbe in gioco il caso che
        # quell'alias era stato aggiunto per chiudere.
        for alias in lista_alias(dati.get(CHIAVE_ALIAS)):
            if not any(stesso_fornitore(alias, noto) for noto in voce[CHIAVE_ALIAS]):
                voce[CHIAVE_ALIAS].append(alias)

        # Stessa logica per le regole mirate: si sommano. Due voci duplicate
        # possono portare regole su campi diversi (una sul numero, una
        # sull'indirizzo) e tenerne una sola ne perderebbe metà.
        for regola in lista_regole_campo(dati.get(CHIAVE_REGOLE_CAMPO)):
            gia_nota = any(
                nota["campo"] == regola["campo"]
                and nota["etichetta"].casefold() == regola["etichetta"].casefold()
                for nota in voce[CHIAVE_REGOLE_CAMPO]
            )
            if not gia_nota:
                voce[CHIAVE_REGOLE_CAMPO].append(regola)

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
        # sort_keys: il file lo si apre anche a mano per controllare una voce,
        # e l'ordine di inserimento (chi e' passato prima in scansione) non
        # aiuta a trovarla. Stesso ordine della dashboard.
        json.dump(unifica_memoria(memoria), f, indent=4, ensure_ascii=False, sort_keys=True)

def aggiorna_fornitore(fornitore, note_proposte, partita_iva=""):
    """Censisce il fornitore letto su un DDT e, se serve, gli propone la P.IVA.

    La P.IVA arriva qui solo quando e' stata letta davvero (fornitore nuovo o
    voce ancora senza chiave, vedi completa_partita_iva): entra come PROPOSTA,
    cioe' con partita_iva_confermata a False, perche' una chiave letta da una
    scansione vale finche' un umano non la guarda.
    """
    if not fornitore or fornitore.lower() == "dato mancante":
        return
    memoria = carica_memoria()

    # Il confronto è per somiglianza, non per uguaglianza: il modello scrive lo
    # stesso fornitore in modi diversi da un documento all'altro ("PERFETTI van
    # Melle S.p.A." / "PERFETTI VAN MELLE SPA"), e censirli separatamente
    # riempirebbe la dashboard di doppioni da confermare uno per uno.
    chiave = normalizza_azienda(fornitore)
    gia_noto = trova_fornitore_simile(chiave, memoria)

    piva_letta = normalizza_piva(partita_iva) if partita_iva_valida(partita_iva) else ""

    if gia_noto:
        # Un fornitore gia' noto ma senza P.IVA e' il caso normale delle voci
        # nate dai DDT prima che la leggessimo: la proposta gli si attacca ora,
        # senza toccare nient'altro della voce.
        voce = memoria.get(gia_noto)
        if piva_letta and isinstance(voce, dict) and not normalizza_piva(voce.get(CHIAVE_PARTITA_IVA)):
            voce[CHIAVE_PARTITA_IVA] = piva_letta
            voce[CHIAVE_PIVA_CONFERMATA] = False
            salva_memoria(memoria)
            print(f"[MEMORIA] P.IVA {piva_letta} proposta per '{gia_noto}': da confermare in dashboard.")
        else:
            print(f"[MEMORIA] '{fornitore}' riconosciuto come '{gia_noto}': nessuna nuova voce.")
        return

    # Lo inserisce SOLO la prima volta che lo incontra
    memoria[chiave] = {
        "confermato": "no",
        "note_specifiche": note_proposte,
        CHIAVE_INDIRIZZI_VIETATI: [],
        CHIAVE_REGOLE_CAMPO: [],
        CHIAVE_ALIAS: [],
        CHIAVE_PARTITA_IVA: piva_letta,
        # Letta da una scansione: e' una proposta, la conferma la da' l'umano
        # dalla dashboard. Se non l'abbiamo letta il flag resta comunque False,
        # cosi' la voce compare tra quelle da completare invece di sembrare a
        # posto con la chiave vuota.
        CHIAVE_PIVA_CONFERMATA: False,
        # Chi ci manda merce ci riguarda: un fornitore censito da un DDT
        # realmente ricevuto nasce autorizzato. Il filtro delle fatture serve a
        # fermare i cedenti che non abbiamo mai visto, non questi.
        CHIAVE_AUTORIZZATO: True,
    }
    salva_memoria(memoria)
    print(f"[MEMORIA] Nuovo fornitore censito: {chiave} (P.IVA letta: {piva_letta or 'nessuna'}, da confermare).")


def partita_iva_per(fornitore, memoria=None):
    """(partita_iva, confermata) del fornitore in anagrafica, ("", False) se ignoto.

    Il fornitore si cerca per somiglianza come ovunque nel modulo: qui si parte
    da un nome LETTO da una scansione, che e' esattamente il dato inesatto per
    cui esistono le soglie. La P.IVA che ne esce e' invece esatta, ed e' quella
    che il documento si portera' dietro.
    """
    memoria = carica_memoria() if memoria is None else memoria
    chiave = trova_fornitore_simile(normalizza_azienda(fornitore), memoria)
    if not chiave:
        return "", False

    voce = memoria.get(chiave)
    if not isinstance(voce, dict):
        return "", False

    piva = normalizza_piva(voce.get(CHIAVE_PARTITA_IVA))
    return piva, (piva != "" and piva_confermata_da_valore(voce.get(CHIAVE_PIVA_CONFERMATA)))


def conferma_partita_iva(fornitore, partita_iva, confermata=True):
    """Scrive (e conferma) la P.IVA di un fornitore: e' la conferma dell'umano.

    Restituisce (chiave_anagrafica, partita_iva) oppure (None, "") se il valore
    non e' una partita IVA italiana valida — il carattere di controllo e' una
    regola esatta, quindi si verifica qui e non nel frontend.
    """
    piva = normalizza_piva(partita_iva)
    if not partita_iva_valida(piva):
        return None, ""

    memoria = carica_memoria()
    chiave = trova_fornitore_simile(normalizza_azienda(fornitore), memoria)

    if not chiave:
        chiave = normalizza_azienda(fornitore)
        if not chiave:
            return None, ""
        memoria[chiave] = {
            "confermato": "no",
            "note_specifiche": "",
            CHIAVE_INDIRIZZI_VIETATI: [],
            CHIAVE_REGOLE_CAMPO: [],
            CHIAVE_ALIAS: [],
            CHIAVE_PARTITA_IVA: "",
            CHIAVE_PIVA_CONFERMATA: False,
            CHIAVE_AUTORIZZATO: True,
        }

    voce = memoria[chiave]
    voce[CHIAVE_PARTITA_IVA] = piva
    voce[CHIAVE_PIVA_CONFERMATA] = bool(confermata)
    salva_memoria(memoria)
    print(f"[MEMORIA] P.IVA {piva} confermata a mano per '{chiave}'.")

    return chiave, piva

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


def indirizzi_vietati_per(fornitore, memoria=None):
    """Gli indirizzi che l'utente ha marcato come 'mai la consegna' per questo
    fornitore. Il fornitore si cerca per somiglianza, come ovunque nel modulo:
    il modello scrive lo stesso nome in modi diversi da un documento all'altro."""
    memoria = carica_memoria() if memoria is None else memoria
    chiave = trova_fornitore_simile(normalizza_azienda(fornitore), memoria)
    if not chiave:
        return []

    voce = memoria.get(chiave)
    if not isinstance(voce, dict):
        return []

    return lista_indirizzi(voce.get(CHIAVE_INDIRIZZI_VIETATI))


def filtra_indirizzo_vietato(dati):
    """Svuota indirizzo_consegna se il modello ha estratto un indirizzo che per
    quel fornitore non è mai la destinazione (di solito il cessionario/sede
    legale stampato su ogni bolla).

    È l'unico caso in cui azzeriamo deliberatamente un campo estratto — altrove
    vale la regola opposta (meglio un dato sporco che nessun dato). Qui però il
    dato è noto per essere SBAGLIATO, e lasciarlo manda in OK un documento che
    andrebbe controllato: senza indirizzo il classificatore lo porta in CHECK,
    dove l'utente lo corregge guardando il PDF.
    """
    if not isinstance(dati, dict):
        return dati

    indirizzo = dati.get("indirizzo_consegna")
    fornitore = dati.get("fornitore")
    if not indirizzo or not fornitore:
        return dati

    for vietato in indirizzi_vietati_per(fornitore):
        if stesso_indirizzo(indirizzo, vietato):
            print(f"🚫 [{fornitore}] '{indirizzo}' è un indirizzo vietato "
                  f"(regola: '{vietato}'): campo svuotato, documento da verificare.")
            dati["indirizzo_consegna"] = ""
            # Tenuto come traccia per chi rivede il documento in dashboard:
            # spiega perché il campo è vuoto invece che semplicemente non letto.
            dati["indirizzo_scartato"] = indirizzo
            return dati

    return dati


# ---------------------------------------------------------------------------
# Anagrafica per il flusso fatture: chi siamo autorizzati a lavorare
# ---------------------------------------------------------------------------

def trova_fornitore_per_piva(partita_iva, memoria):
    """La chiave in memoria con questa P.IVA, oppure None.

    Confronto esatto (a parte il prefisso "IT" e gli spazi): è il punto del
    sistema in cui NON si usano soglie di somiglianza.
    """
    piva = normalizza_piva(partita_iva)
    if not piva:
        return None

    for chiave, dati in memoria.items():
        if isinstance(dati, dict) and normalizza_piva(dati.get(CHIAVE_PARTITA_IVA)) == piva:
            return chiave
    return None


def trova_voce_fornitore(nome, partita_iva, memoria):
    """La voce di anagrafica che corrisponde a un cedente di fattura.

    Prima la P.IVA (esatta), poi il nome (per somiglianza) — ma il ripiego sul
    nome vale solo se la voce trovata non ha già una P.IVA DIVERSA: due società
    dello stesso gruppo hanno spesso nomi quasi uguali e partite IVA distinte,
    e autorizzarne una perché si chiama come l'altra è esattamente l'errore che
    il filtro dovrebbe evitare.
    """
    per_piva = trova_fornitore_per_piva(partita_iva, memoria)
    if per_piva:
        return per_piva

    per_nome = trova_fornitore_simile(normalizza_azienda(nome), memoria)
    if not per_nome:
        return None

    voce = memoria.get(per_nome)
    piva_voce = normalizza_piva(voce.get(CHIAVE_PARTITA_IVA)) if isinstance(voce, dict) else ""
    # Il veto vale solo se la P.IVA della voce e' CONFERMATA: una proposta
    # letta da una scansione puo' avere una cifra sbagliata, e usarla per
    # negare il nome bloccherebbe le fatture del fornitore giusto. Se la
    # proposta e' sbagliata, registra_fornitore_fattura la corregge qui sotto
    # con quella dell'XML, che e' un dato fiscale.
    if piva_voce and normalizza_piva(partita_iva) and piva_voce != normalizza_piva(partita_iva):
        if isinstance(voce, dict) and piva_confermata_da_valore(voce.get(CHIAVE_PIVA_CONFERMATA)):
            return None

    return per_nome


def fornitore_autorizzato(nome, partita_iva, memoria=None):
    """(autorizzato, chiave_anagrafica) per un cedente di fattura.

    Un fornitore sconosciuto NON è autorizzato: è il caso per cui il filtro
    esiste. Chi lo censisce (registra_fornitore_fattura) lo rende però visibile
    in dashboard, così autorizzarlo è un click e non una caccia al file.
    """
    memoria = carica_memoria() if memoria is None else memoria
    chiave = trova_voce_fornitore(nome, partita_iva, memoria)
    if not chiave:
        return False, None

    voce = memoria.get(chiave)
    if not isinstance(voce, dict):
        return False, chiave

    return autorizzato_da_valore(voce.get(CHIAVE_AUTORIZZATO)), chiave


# Codici delle anomalie che una fattura si porta dietro. Non bloccano niente:
# da quando i file si caricano a mano (2026-09-08) l'anagrafica non e' piu' un
# elenco di ammessi, e scartare una fattura che una persona ha appena scelto di
# caricare sarebbe solo un modo di farla sparire. Restano pero' tre cose che
# vale la pena dire ad alta voce, tutte e tre sulla P.IVA, che e' l'unica chiave
# esatta che lega i due lati del sistema.
SEGNALAZIONE_PIVA_ASSENTE = "piva_assente"
SEGNALAZIONE_PIVA_DIVERSA = "piva_diversa"
SEGNALAZIONE_FORNITORE_NUOVO = "fornitore_nuovo"


def verifica_fornitore_fattura(nome, partita_iva, memoria=None):
    """Le anomalie del cedente di una fattura, senza giudicarlo.

    Sostituisce il vecchio filtro "fornitore autorizzato": quello rispondeva
    si'/no e buttava via il resto, questa descrive cosa non torna e lascia
    decidere a chi guarda. Restituisce (segnalazioni, chiave_anagrafica).
    """
    memoria = carica_memoria() if memoria is None else memoria
    piva = normalizza_piva(partita_iva)
    segnalazioni = []

    if not piva:
        segnalazioni.append({
            "codice": SEGNALAZIONE_PIVA_ASSENTE,
            "messaggio": "La fattura non riporta la partita IVA del cedente.",
        })

    per_piva = trova_fornitore_per_piva(piva, memoria) if piva else None
    per_nome = trova_fornitore_simile(normalizza_azienda(nome), memoria)

    # Stesso nome ma P.IVA diversa da una gia' CONFERMATA: o e' un'altra
    # societa' dello stesso gruppo, o e' la voce sbagliata. In entrambi i casi
    # non e' il sistema a poterlo decidere. Su una proposta non confermata si
    # tace: quella la corregge da sola registra_fornitore_fattura con il dato
    # dell'XML, che e' fiscale.
    if piva and per_nome and not per_piva:
        voce = memoria.get(per_nome)
        if isinstance(voce, dict):
            piva_voce = normalizza_piva(voce.get(CHIAVE_PARTITA_IVA))
            if (piva_voce and piva_voce != piva
                    and piva_confermata_da_valore(voce.get(CHIAVE_PIVA_CONFERMATA))):
                segnalazioni.append({
                    "codice": SEGNALAZIONE_PIVA_DIVERSA,
                    "messaggio": f"In anagrafica '{per_nome}' ha la P.IVA confermata "
                                 f"{piva_voce}, la fattura porta {piva}.",
                    "partita_iva_anagrafica": piva_voce,
                    "partita_iva_fattura": piva,
                    "fornitore_anagrafica": per_nome,
                })

    if not per_piva and not per_nome:
        segnalazioni.append({
            "codice": SEGNALAZIONE_FORNITORE_NUOVO,
            "messaggio": f"'{nome}' non era in anagrafica: e' stato aggiunto adesso.",
        })

    return segnalazioni, (per_piva or per_nome)


def registra_fornitore_fattura(nome, partita_iva):
    """Censisce (o completa) il cedente di una fattura. Restituisce la chiave.

    Due effetti:
      - se il fornitore è già noto ma senza P.IVA — cioè censito da un DDT, dove
        la P.IVA è solo una proposta — gliela scrive: è il modo in cui
        l'anagrafica acquisisce la chiave esatta senza che nessuno la digiti;
      - se è sconosciuto lo aggiunge, perché una fattura caricata a mano è
        già la prova che quel fornitore ci riguarda.
    """
    memoria = carica_memoria()
    chiave = trova_voce_fornitore(nome, partita_iva, memoria)
    piva = normalizza_piva(partita_iva)

    if chiave:
        voce = memoria.get(chiave)
        if not isinstance(voce, dict):
            return chiave

        # La P.IVA dell'XML e' un dato fiscale: riempie la voce che non ce
        # l'ha e SOSTITUISCE una proposta letta da una scansione (che poteva
        # avere una cifra sbagliata). Una P.IVA gia' confermata non si tocca:
        # se fosse diversa, trova_voce_fornitore non avrebbe restituito questa
        # voce.
        piva_voce = normalizza_piva(voce.get(CHIAVE_PARTITA_IVA))
        if piva and (not piva_voce or (piva != piva_voce
                                       and not piva_confermata_da_valore(voce.get(CHIAVE_PIVA_CONFERMATA)))):
            voce[CHIAVE_PARTITA_IVA] = piva
            voce[CHIAVE_PIVA_CONFERMATA] = True
            salva_memoria(memoria)
            print(f"[MEMORIA] P.IVA {piva} associata (da fattura) al fornitore '{chiave}'.")

        return chiave

    chiave_nuova = normalizza_azienda(nome) or (piva and f"P.IVA {piva}")
    if not chiave_nuova:
        return None

    memoria[chiave_nuova] = {
        "confermato": "no",
        "note_specifiche": "",
        CHIAVE_INDIRIZZI_VIETATI: [],
        CHIAVE_REGOLE_CAMPO: [],
        CHIAVE_ALIAS: [],
        CHIAVE_PARTITA_IVA: piva,
        # Viene da un XML: e' gia' certa, non c'e' niente da confermare.
        CHIAVE_PIVA_CONFERMATA: True,
        CHIAVE_AUTORIZZATO: True,
    }
    salva_memoria(memoria)
    print(f"[MEMORIA] Nuovo cedente censito dalla fattura: {chiave_nuova} (P.IVA {piva or 'assente'}).")

    return chiave_nuova
