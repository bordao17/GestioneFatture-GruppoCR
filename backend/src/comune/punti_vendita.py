"""I punti vendita: chi sono, e cosa scrivono sul D.D.T. che arriva da loro.

Sta a archivio_punti_vendita.py come memory_manager.py sta ad
archivio_fornitori.py: li' c'e' il magazziniere (schema e query), qui le
decisioni. La regola vale anche per la seconda anagrafica — la stessa scritta
in due posti ne lascerebbe vera una sola.

L'IDEA. Ogni scansione e' la posta di UN punto vendita: chi mette i fogli nello
scanner sa gia' dove quella merce e' stata consegnata, e non c'e' ragione di
chiederlo a un modello che guarda una fotografia. Dichiarandolo prima di
premere Analizza, ragione_sociale_consegna e indirizzo_consegna smettono di
essere una lettura e diventano un dato certo.

IL DICHIARATO BATTE IL LETTO, e non e' un'eccezione ma la regola di sempre di
questo progetto: se una cosa e' esatta si fa in Python, non si spera che il
modello la indovini. E' lo stesso principio di applica_nome_canonico() (il nome
del fornitore lo mette l'anagrafica) e dei divieti su indirizzo e fornitore —
qui pero' non si SVUOTA un campo sbagliato, si SCRIVE quello giusto. Cio' che
il modello aveva letto resta accanto in consegna_letta, perche' il giorno in
cui qualcuno sceglie il punto vendita sbagliato la traccia di quel che c'era
scritto sul foglio e' l'unico modo di accorgersene.

FACOLTATIVO PER COSTRUZIONE. Senza punto vendita dichiarato non succede niente
e il documento resta quello di prima: la scansione notturna del pianificatore
non ha nessuno a cui chiederlo, e una pila mista si analizza scegliendo "non
specificato". Un campo in piu' non deve poter impedire un lavoro che prima
funzionava.
"""

import os
import re

from src.comune import archivio_punti_vendita, database
from src.comune.normalizzatore import (
    normalizza_azienda, normalizza_indirizzo, normalizza_partita_iva,
)

# Il CSV di partenza: sta in data/ e non alla radice del repo perche' e' l'unica
# cartella montata nel container insieme ai tre alberi dei documenti. Un file
# che il backend non puo' aprire non e' una sorgente.
FILE_CSV = os.path.join("data", "punti_vendita.csv")

# Le due chiavi con cui il punto vendita dichiarato viaggia dentro i dati del
# documento. Stanno in "dati" e non accanto all'id per la stessa ragione di
# fornitore_critico: e' li' che unisci_dati_pagina() le porta avanti da sola
# quando due pagine diventano un documento solo.
CAMPO_CODICE = "punto_vendita"
CAMPO_NOME = "punto_vendita_nome"

# Dove finisce cio' che il modello aveva letto, quando il dichiarato lo
# sostituisce. Stessa convenzione di indirizzo_scartato e fornitore_scartato.
CAMPO_LETTO = "consegna_letta"

# Il sospetto che alla scansione sia stato scelto il negozio sbagliato: ci
# finisce il punto vendita di cui il documento sembra parlare, quando NON e'
# quello dichiarato. Sta in "dati" come fornitore_critico e per le stesse
# ragioni — lo legge determina_stato() senza sapere da dove viene, e
# unisci_dati_pagina() se lo porta avanti da sola.
CAMPO_DISCORDE = "consegna_discorde"

# Un CAP: cinque cifre di fila. E' il solo pezzo di un indirizzo che identifica
# un comune da solo e si confronta per uguaglianza esatta, senza nessuna
# soglia — la stessa ragione per cui il cedente di una fattura si riconosce
# per P.IVA e non per somiglianza di nome.
_CAP = re.compile(r"(?<![0-9])[0-9]{5}(?![0-9])")

# Sotto le quattro lettere un nome non identifica niente: "RM", "TOR", "SAN"
# compaiono su mezza anagrafica, e un riconoscimento su quelle manderebbe in
# CHECK documenti giusti.
_LUNGHEZZA_MINIMA_NOME = 4


def elenco():
    """I punti vendita in anagrafica, o [] se il database non risponde.

    Ripiega in silenzio come carica_memoria() lato fornitori: qui non c'e'
    nemmeno una copia su file da rileggere, ma un'anagrafica assente deve
    costare la comodita' del menu a tendina, non l'analisi delle bolle.
    """
    if not database.configurato():
        return []
    try:
        return archivio_punti_vendita.leggi()
    except Exception as e:
        print(f"⚠️ Anagrafica punti vendita non leggibile ({e}): menu a tendina vuoto.")
        return []


def trova(codice):
    """Il punto vendita con quel codice, o None.

    Il confronto e' esatto sul codice gestionale, mai per somiglianza di nome:
    qui si sta per SCRIVERE due campi obbligatori su ogni bolla del batch, e
    una soglia che sbaglia non darebbe un campo brutto da guardare ma una
    consegna attribuita al negozio sbagliato.
    """
    codice = str(codice or "").strip()
    if not codice:
        return None

    for voce in elenco():
        if voce["codice"] == codice:
            return voce
    return None


def indirizzo_consegna(voce):
    """L'indirizzo del NEGOZIO (DIP_*), nella forma dell'archivio.

    Passa da normalizza_indirizzo come tutto il resto: un indirizzo dichiarato
    e uno letto devono risultare uguali quando lo sono, altrimenti
    l'accorpatore vedrebbe due magazzini diversi sulle pagine dello stesso
    documento. Non e' la sede della societa' (IND_*), che sul D.D.T. non
    c'entra: quella e' dove arriva la fattura.
    """
    if not voce:
        return ""

    pezzi = [voce.get("via", ""), voce.get("cap", ""), voce.get("citta", "")]
    testo = " ".join(p.strip() for p in pezzi if p and p.strip())
    provincia = (voce.get("provincia", "") or "").strip()
    if provincia:
        testo = f"{testo} {provincia}"

    return normalizza_indirizzo(testo)


def ragione_sociale_consegna(voce):
    """La societa' a cui il punto vendita appartiene, in forma compatta.

    E' RAG_SOC e non DIPENDENZA: sulla bolla il destinatario e' la societa'
    ("C.R. MARKET SPA"), mentre "TORTRETESTE" e' il nome con cui la chiamiamo
    noi e non comparirebbe mai su un documento di un fornitore. Il nome visivo
    resta comunque sul documento, in punto_vendita_nome.
    """
    if not voce:
        return ""
    return normalizza_azienda(voce.get("ragione_sociale", ""))


def descrizione(voce):
    """Come il punto vendita si scrive in un log o in una mail."""
    if not voce:
        return ""
    return f"{voce['dipendenza']} ({voce['codice']})"


def _parole(testo):
    """Le parole di un testo, in maiuscolo, senza punteggiatura."""
    return set(re.findall(r"[A-Z0-9]+", (testo or "").upper()))


def _nome_riconoscibile(nome, parole_lette):
    """Vero se tutte le parti significative del nome compaiono in cio' che si e'
    letto: "CITTADUCALE" dentro "CONAD CITTADUCALE" si', "RM" da nessuna parte.

    Il confronto e' per PAROLA INTERA e non per sottostringa, per la stessa
    ragione per cui lo e' quello delle sigle dei corrieri: cercare "TOR" dentro
    un indirizzo prenderebbe mezza anagrafica. Serve solo a RICONOSCERE il
    negozio dichiarato e quindi a tacere — perche' un nome sia una prova a
    carico non basta (vedi punto_vendita_discorde).
    """
    parti = [p for p in _parole(nome) if len(p) >= _LUNGHEZZA_MINIMA_NOME]
    return bool(parti) and all(p in parole_lette for p in parti)


def punto_vendita_discorde(dati, voce, anagrafica=None):
    """Il punto vendita di cui il documento parla, quando NON e' quello dichiarato.

    L'errore che cerca e' quello di distrazione: la pila di fogli e' di un
    negozio e nel menu a tendina ne e' stato scelto un altro. E' il caso piu'
    silenzioso che ci sia, proprio perche' il dichiarato BATTE il letto — i due
    campi sbagliati vengono scritti sulla bolla al posto di quelli giusti, e il
    documento finisce in OK con tutti e quattro i campi pieni. Ed e' un errore
    che non capita mai da solo: si sceglie una volta per tutto il batch.

    SI GUARDA SOLO IL CAP, e per uguaglianza esatta: nessuna soglia, come per la
    deduplica delle pagine e per il cedente di una fattura. E' l'unico pezzo di
    un indirizzo che identifica un luogo da solo, e sui nostri documenti c'e'
    quasi sempre perche' il normalizzatore lo tiene.

    IL NOME DEL NEGOZIO NON SI USA, ed e' una misura, non un'impressione (2026-09-15,
    sui 31 punti vendita reali): i nomi delle dipendenze SONO nomi di localita'
    e di societa' — GUIDONIA, MONTEROSI, CITTADUCALE, RIETI, CASSIA, COOKERY LAB —
    e compaiono negli indirizzi e nelle ragioni sociali di ALTRI negozi, 38 volte
    su 31 voci. Cercarli darebbe un "hai scelto il negozio sbagliato" ogni volta
    che una bolla di TIBURTINO CC nomina Guidonia, che e' la citta' in cui
    TIBURTINO CC si trova.

    Non si segnala un indirizzo che non e' di nessun nostro negozio: e' il
    rumore quotidiano del modello (tipicamente la sede del fornitore letta al
    posto della consegna), e rimanderebbe in CHECK proprio le bolle che la
    consegna dichiarata ha appena sistemato. Si segnala solo il caso in cui si
    puo' anche DIRE quale negozio era — che e' l'unica forma in cui l'avviso
    serve a qualcosa.

    MISURATO sui 31 punti vendita reali (2026-09-15): 0 segnalazioni sulle 31
    dichiarazioni giuste e 0 sull'indirizzo di sede letto al posto della
    consegna; 810 riconosciute sulle 930 dichiarazioni sbagliate possibili. Le
    120 che sfuggono sono negozi che condividono il CAP con quello dichiarato,
    cioe' gli stessi che spesso condividono anche il portone: li' l'indirizzo
    scritto sulla bolla sarebbe comunque quello giusto.

    anagrafica e' l'elenco dei punti vendita, letto UNA VOLTA PER BATCH dal
    chiamante: senza, sarebbe una query a Postgres per ogni pagina.
    """
    if not isinstance(dati, dict) or not voce:
        return None

    letto = " ".join((
        dati.get("indirizzo_consegna") or "",
        dati.get("ragione_sociale_consegna") or "",
    )).strip()
    if not letto:
        return None

    cap_letti = set(_CAP.findall(letto))
    if not cap_letti:
        return None

    # 1. Il CAP del negozio dichiarato, o quello della sede della sua societa'.
    #    Il secondo e' l'indirizzo di fatturazione stampato accanto a quello di
    #    consegna, cioe' l'errore di lettura piu' comune del modello: un fatto
    #    suo, non una distrazione di chi ha scelto nel menu a tendina.
    #    Va guardato PER PRIMO, ed e' anche cio' che tiene fuori i negozi
    #    che stanno allo stesso indirizzo (nel CSV sono parecchi: BAR
    #    CITTADUCALE e CITTADUCALE hanno lo stesso portone) — condividendo il
    #    CAP col dichiarato, la risposta e' gia' "coerente".
    for campo in ("cap", "sede_cap"):
        if (voce.get(campo) or "").strip() in cap_letti:
            return None

    # 2. Il foglio nomina comunque il negozio dichiarato: allora il CAP che non
    #    torna e' una cifra letta male, non un negozio sbagliato. E' l'unico
    #    uso che si fa del nome, e serve solo a TACERE.
    if _nome_riconoscibile(voce.get("dipendenza"), _parole(letto)):
        return None

    # 3. Quel CAP e' di un altro nostro negozio: questa e' la distrazione.
    for altro in (elenco() if anagrafica is None else anagrafica):
        cap = (altro.get("cap") or "").strip()
        if altro["codice"] != voce["codice"] and cap and cap in cap_letti:
            return {"codice": altro["codice"], "nome": altro["dipendenza"],
                    "motivo": f"il CAP {cap} letto sul documento e' di {altro['dipendenza']}"}

    return None


def applica_consegna(dati, voce, anagrafica=None):
    """Scrive sul documento la consegna dichiarata, tenendo traccia della letta.

    Va chiamata DOPO l'estrazione e PRIMA di determina_stato(): sono due dei
    quattro campi obbligatori, e applicarla dopo lascerebbe in CHECK proprio i
    documenti a cui abbiamo appena dato il dato che mancava.

    Senza voce non tocca niente e restituisce i dati com'erano: e' la strada di
    ogni scansione che non ha dichiarato un punto vendita.
    """
    if not isinstance(dati, dict) or not voce:
        return dati

    ragione = ragione_sociale_consegna(voce)
    indirizzo = indirizzo_consegna(voce)

    # PRIMA di sovrascrivere: il sospetto si cerca su cio' che il modello aveva
    # letto, che fra due righe non ci sara' piu'.
    discorde = punto_vendita_discorde(dati, voce, anagrafica)
    if discorde:
        dati[CAMPO_DISCORDE] = discorde
        print(f"⚠️ Consegna discorde: dichiarato {descrizione(voce)}, ma "
              f"{discorde['motivo']}. Il documento va in CHECK.")

    # Cio' che il modello aveva letto si tiene solo se diceva qualcosa e se
    # diceva qualcosa di DIVERSO: una traccia identica al valore buono e'
    # rumore che fa cercare una discordanza che non c'e'.
    letti = {}
    letta_ragione = (dati.get("ragione_sociale_consegna") or "").strip()
    letto_indirizzo = (dati.get("indirizzo_consegna") or "").strip()
    if letta_ragione and letta_ragione != ragione:
        letti["ragione_sociale_consegna"] = letta_ragione
    if letto_indirizzo and letto_indirizzo != indirizzo:
        letti["indirizzo_consegna"] = letto_indirizzo
    if letti:
        dati[CAMPO_LETTO] = letti

    if ragione:
        dati["ragione_sociale_consegna"] = ragione
    if indirizzo:
        dati["indirizzo_consegna"] = indirizzo

    dati[CAMPO_CODICE] = voce["codice"]
    dati[CAMPO_NOME] = voce["dipendenza"]

    return dati


def importa_da_csv():
    """Porta nel database il CSV del gestionale, una volta sola.

    La chiama il lifespan di main.py, ed e' la gemella di
    migra_da_file_a_database() lato fornitori: importa SOLO se la tabella e'
    ancora vuota, altrimenti una modifica fatta sul database si ritroverebbe
    sovrascritta dal file a ogni riavvio.

    Restituisce quante voci ha importato (0 = non c'era niente da fare).
    """
    if not archivio_punti_vendita.vuota():
        return 0

    grezze = archivio_punti_vendita.leggi_csv(FILE_CSV)
    if not grezze:
        return 0

    return archivio_punti_vendita.scrivi([_normalizza(voce) for voce in grezze])


def _normalizza(voce):
    """Ripulisce una voce appena letta dal CSV.

    Le stesse normalizzazioni del resto del progetto, per la stessa ragione:
    la ragione sociale di qui finira' a confronto con quella letta su una bolla
    ("C.R. MARKET S.P.A." e "C.R.MARKET S.P.A." sono nel file tutte e due), e
    la P.IVA e' una chiave — nel CSV ce n'e' una scritta "0" con dieci spazi in
    coda, che e' un campo vuoto travestito da numero.
    """
    pulita = dict(voce)
    pulita["ragione_sociale"] = normalizza_azienda(voce.get("ragione_sociale", ""))

    piva = normalizza_partita_iva(voce.get("partita_iva", ""))
    pulita["partita_iva"] = piva if len(piva) == 11 else ""

    for chiave in ("dipendenza", "via", "citta", "provincia",
                   "sede_via", "sede_citta", "sede_provincia"):
        pulita[chiave] = (voce.get(chiave, "") or "").strip().upper()

    return pulita
