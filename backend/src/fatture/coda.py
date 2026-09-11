"""
Coda delle fatture in attesa dei loro DDT (registro ATTESA) e archivio delle
pratiche chiuse (registro FATTURE).

Il punto di tutto il modulo: l'abbinamento fattura->DDT NON e' un'operazione
one-shot. Una fattura che cita 3 DDT di cui uno solo gia' scansionato non e'
"parziale e amen": e' una pratica aperta, che va rimessa in discussione ogni
volta che un DDT nuovo diventa abbinabile — cioe' a fine estrazione, dopo un
inserimento manuale, dopo un'unione, dopo una rianalisi e dopo la correzione a
mano di un numero DDT dalla dashboard. Sono tutti modi in cui un documento
prima invisibile compare, e l'ultimo (la cifra corretta a mano) e' proprio
quello che sblocca gli abbinamenti "probabili".

Chi riprova e' quindi Python, non n8n: meta' di quegli eventi non muove un file
e n8n non avrebbe modo di accorgersene. A n8n resta cio' che e' davvero
temporale — il sollecito delle fatture ferme da troppo — perche' nessun evento
del backend scatta al trentesimo giorno.

Il fascicolo PDF viene scritto su disco SOLO per le pratiche chiuse: finche' la
fattura e' in coda ogni nuovo DDT lo renderebbe obsoleto. L'anteprima di una
fattura in attesa si genera a richiesta, in un file temporaneo.

CHI CHIUDE UNA PRATICA (2026-09-08): l'operatore, non l'automatismo. Il
ricontrollo calcola l'abbinamento e si ferma li'. Una fattura i cui DDT sono
stati tutti trovati resta in coda con stato ABBINATA, cioe' "pronta, aspetta un
occhio"; la chiusura vera — file unico in ACCOPPIATE, DDT annotati, voce
spostata in FATTURE.json — la fa solo conferma_accoppiamento(), cioe' il
pulsante in dashboard.

E' la stessa regola gia' valida per la P.IVA letta da una scansione: un
abbinamento e' il confronto fra un XML esatto e dei numeri LETTI da una
fotografia, quindi e' una proposta, e a convalidare una proposta e' una
persona. Prima la pratica si chiudeva da sola e l'operatore non aveva nessun
momento in cui vedere cosa fosse stato agganciato; adesso l'automatismo prepara
e l'uomo firma. Il corollario e' che ATTESA.json contiene due cose diverse —
chi aspetta una bolla (IN_ATTESA) e chi aspetta un click (ABBINATA) — e chi
legge la coda deve dire quale delle due sta guardando: fatture_in_attesa()
tiene solo IN_ATTESA perche' alimenta il sollecito, e mandare a cercare in
magazzino una bolla gia' archiviata farebbe smettere di leggere la mail.
"""

import os
import shutil
import tempfile
import threading
import uuid

from src.comune.configurazione import valore
from src.comune.percorsi import (
    CARTELLA_ACCOPPIATE, CARTELLA_FATTURE, REGISTRO_FATTURE, REGISTRO_ATTESA,
)
from src.comune.registro import leggi_registro, salva_registro, aggiorna_registro
from src.comune.tempo import timestamp_locale, leggi_timestamp, adesso
from src.fatture.abbinatore import (
    abbina_fattura, annota_ddt_abbinati, carica_documenti, riepilogo_attesa,
    righe_da_abbinare, ABBINATA, DA_ABBINARE, IN_ATTESA,
)
from src.fatture.fascicolatore import costruisci_fascicolo
from src.fatture.lettore_xml import leggi_fattura

# Dopo quanti giorni una pratica ferma finisce nella mail di sollecito. Sono
# numeri ORGANIZZATIVI, non tecnici, e stanno in configurazione.py: si cambiano
# dalla dashboard, quindi si leggono a ogni chiamata e non all'import.
#
# Sono TRE perche' le attese sono tre e non si assomigliano:
#
#   - una FATTURA senza le sue bolle aspetta che qualcuno vada a cercarle in
#     magazzino, e quanto sia ragionevole aspettare dipende da come lavora quel
#     fornitore;
#   - un D.D.T. che nessuna fattura ha agganciato aspetta il giro di
#     fatturazione (spesso di fine mese), che e' un'altra cosa e puo' meritare
#     un'altra pazienza: la bolla c'e' gia' e non manca a nessuno, e' la
#     fattura che non e' arrivata;
#   - una pratica gia' completa non aspetta nessun documento, aspetta un CLICK.
#
# Le prime due avevano un numero solo fino al 2026-09-10, ed era lo stesso
# numero per comodita', non perche' fossero la stessa attesa: allungare la
# pazienza sulle bolle mancanti faceva tacere anche sulle fatture che non
# arrivavano piu'. Adesso si regolano una per una.


def giorni_attesa_fattura():
    """Soglia per una FATTURA ferma: i suoi D.D.T. non sono ancora arrivati."""
    return valore("GIORNI_ATTESA_FATTURA")


def giorni_attesa_ddt():
    """Soglia per un D.D.T. fermo: nessuna fattura lo ha ancora agganciato."""
    return valore("GIORNI_ATTESA_DDT")


def giorni_accoppiamento():
    """Soglia per chi aspetta una FIRMA: i D.D.T. ci sono tutti, manca il click."""
    return valore("GIORNI_ATTESA_ACCOPPIAMENTO")

# Le route sincrone girano nel threadpool di FastAPI e n8n manda piu' file in
# parallelo: due ricontrolli simultanei riscriverebbero la coda a vicenda,
# duplicando in FATTURE.json le fatture sbloccate. Stesso motivo del lock in
# stato_elaborazione.py.
_LUCCHETTO = threading.RLock()

CAMPI_RIFERIMENTO_DDT = ("numero_ddt", "data_ddt", "numero_ddt_xml", "origine")

# I registri DDT in cui ha senso cercare una bolla non ancora fatturata. KO e'
# escluso di proposito: li' il numero non e' stato letto affatto, quindi nessuna
# fattura potrebbe agganciarlo — e' un problema di rilettura, gia' visibile nel
# suo tab in dashboard, non una fattura che tarda.
STATI_DDT_DA_FATTURARE = ("OK", "CHECK")


# ---------------------------------------------------------------------------
# Identita' di una fattura (deduplica)
# ---------------------------------------------------------------------------

def chiave_fattura(dati):
    """Identita' fiscale di una fattura: P.IVA del cedente + numero + data.

    Serve perche' il ramo n8n NON svuota /FATTURE/da_leggere: rilanciarlo
    ripassa gli stessi file, e con una coda che si rilegge in continuo la
    stessa fattura comparirebbe piu' volte tra le attese (e verrebbe
    sollecitata piu' volte). Con questa chiave la cartella diventa idempotente,
    il che e' anche cio' che permette di lasciarci ferme le fatture scartate.
    """
    return (
        str(dati.get("partita_iva", "") or "").strip(),
        str(dati.get("numero_fattura", "") or "").strip().upper(),
        str(dati.get("data_fattura", "") or "").strip(),
    )


def trova_fattura_registrata(dati):
    """(registro, voce) se questa fattura e' gia' passata di qui, altrimenti (None, None)."""
    chiave = chiave_fattura(dati)
    if not any(chiave):
        return None, None

    for registro in (REGISTRO_ATTESA, REGISTRO_FATTURE):
        for voce in leggi_registro(registro):
            if chiave_fattura(voce.get("dati", {})) == chiave:
                return registro, voce

    return None, None


# ---------------------------------------------------------------------------
# File su disco
# ---------------------------------------------------------------------------

def archivia_originale(id_fattura, contenuto, estensione):
    """L'XML (firmato compreso) accanto al fascicolo: il PDF e' un prodotto
    derivato, il documento fiscale e' l'XML. Viene salvato subito, anche per le
    fatture che restano in coda: e' da li' che si rileggono gli allegati quando
    piu' avanti si costruira' il fascicolo."""
    os.makedirs(CARTELLA_FATTURE, exist_ok=True)
    percorso = os.path.join(CARTELLA_FATTURE, f"{id_fattura}{estensione}")
    with open(percorso, "wb") as f:
        f.write(contenuto)
    return percorso


def percorso_originale(id_fattura):
    if not id_fattura or not os.path.isdir(CARTELLA_FATTURE):
        return None

    for estensione in (".xml", ".p7m", ".xml.p7m"):
        percorso = os.path.join(CARTELLA_FATTURE, f"{id_fattura}{estensione}")
        if os.path.exists(percorso):
            return percorso
    return None


def fattura_per_fascicolo(voce):
    """La fattura ricostruita per costruire il fascicolo.

    Si rilegge l'XML archiviato perche' e' l'unico posto in cui vive la copia di
    cortesia in PDF (gli allegati sono byte: nel registro non ci vanno). Se il
    file non c'e' piu' si ripiega sui dati di testata gia' salvati: un fascicolo
    senza copia di cortesia vale comunque piu' di un errore.
    """
    percorso = percorso_originale(voce.get("id", ""))
    if percorso:
        try:
            with open(percorso, "rb") as f:
                fatture = leggi_fattura(f.read())
            numero = voce.get("dati", {}).get("numero_fattura", "")
            for fattura in fatture:
                if fattura.get("numero_fattura", "") == numero:
                    return fattura
            if fatture:
                return fatture[0]
        except Exception as errore:
            print(f"⚠️ XML archiviato di {voce.get('id')} non rileggibile ({errore}): "
                  f"fascicolo senza copia di cortesia.")

    return {**voce.get("dati", {}), "ddt": [], "allegati": []}


def riferimenti_da_voce(voce):
    """La fattura ridotta a cio' che serve per riabbinare: fornitore piu'
    riferimenti DDT. I riferimenti originali restano dentro le righe di esito,
    quindi non serve rileggere l'XML a ogni ricontrollo."""
    dati = voce.get("dati", {})
    return {
        "fornitore": dati.get("fornitore", ""),
        "numero_fattura": dati.get("numero_fattura", ""),
        "data_fattura": dati.get("data_fattura", ""),
        "ddt": [
            {campo: riga.get(campo, "") for campo in CAMPI_RIFERIMENTO_DDT}
            for riga in voce.get("ddt", [])
        ],
    }


# ---------------------------------------------------------------------------
# Registrazione e completamento
# ---------------------------------------------------------------------------

def nome_fascicolo(voce):
    """Nome del file unico dentro ACCOPPIATE.

    Quella cartella la apre una persona da Esplora Risorse, quindi il nome dice
    fornitore, numero e data della fattura invece dell'UUID che usano gli
    archivi di lavoro. In coda le prime otto cifre dell'id: due fornitori
    diversi possono emettere la fattura "47" nello stesso giorno, e un file
    sovrascritto in silenzio sarebbe una pratica persa.
    """
    dati = voce.get("dati", {})
    pezzi = (dati.get("fornitore", ""), dati.get("numero_fattura", ""), dati.get("data_fattura", ""))

    puliti = []
    for pezzo in pezzi:
        # I numeri di fattura contengono spesso "/" e le ragioni sociali "&":
        # qui diventano un nome di file, e su Windows meta' di quei caratteri
        # non sono ammessi.
        testo = "".join(c if (c.isalnum() or c in " -_") else "_" for c in str(pezzo))
        testo = "_".join(testo.split())
        if testo:
            puliti.append(testo[:60])

    radice = "_".join(puliti) if puliti else "FATTURA"
    return f"{radice}_{str(voce.get('id', ''))[:8]}.pdf"


def _scrivi_fascicolo(voce, fattura=None):
    """Costruisce il file unico fattura+DDT dentro ACCOPPIATE.

    Il nome finisce in voce["fascicolo"] perche' non e' piu' derivabile
    dall'id: chi serve il PDF (GET /api/pdf-fattura) e chi lo cancella (DELETE)
    lo leggono di li' invece di ricostruirlo.
    """
    fattura = fattura or fattura_per_fascicolo(voce)
    os.makedirs(CARTELLA_ACCOPPIATE, exist_ok=True)

    nome = nome_fascicolo(voce)
    percorso = os.path.join(CARTELLA_ACCOPPIATE, nome)
    numero_pagine, ddt_allegati = costruisci_fascicolo(fattura, voce["ddt"], percorso)

    voce["numero_pagine"] = numero_pagine
    voce["ddt_allegati"] = ddt_allegati
    voce["fascicolo"] = nome
    return voce


def percorso_fascicolo(voce):
    """Il file unico gia' su disco, o None se la pratica non e' confermata.

    Senza conferma non esiste nessun file: quella fattura si guarda in
    anteprima (anteprima_fascicolo), perche' i suoi DDT possono ancora cambiare.
    """
    nome = voce.get("fascicolo")
    if nome:
        percorso = os.path.join(CARTELLA_ACCOPPIATE, nome)
        if os.path.exists(percorso):
            return percorso

    # Pratiche chiuse prima del 2026-09-08, quando chiudeva l'automatismo e il
    # fascicolo si chiamava come l'id dentro FATTURE/lette.
    vecchio = os.path.join(CARTELLA_FATTURE, f"{voce.get('id', '')}.pdf")
    return vecchio if os.path.exists(vecchio) else None


def _chiudi(voce, fattura=None):
    """Sposta una pratica tra le chiuse: file unico in ACCOPPIATE, DDT annotati,
    voce in FATTURE.json. Da chiamare gia' dentro il lucchetto.

    Unico chiamante rimasto: conferma_accoppiamento(). Non richiamarla da un
    automatismo — il perche' e' in cima al modulo."""
    voce.pop("attesa", None)
    voce["completata"] = timestamp_locale()

    _scrivi_fascicolo(voce, fattura)

    # I DDT vengono annotati solo adesso: durante l'attesa l'abbinamento e'
    # ancora provvisorio, e scrivere sul DDT il numero di una fattura che
    # potrebbe agganciarsi altrove confonderebbe chi rivede la dashboard.
    annota_ddt_abbinati(voce["ddt"], {
        "id_fattura": voce["id"],
        "numero_fattura": voce.get("dati", {}).get("numero_fattura", ""),
        "data_fattura": voce.get("dati", {}).get("data_fattura", ""),
    })

    aggiorna_registro(REGISTRO_FATTURE, voce)
    return voce


def registra_fattura(fattura, stato, righe, tipo, nome_file, contenuto, estensione,
                     segnalazioni=None):
    """Prima archiviazione di una fattura: in coda se IN_ATTESA, chiusa altrimenti."""
    id_fattura = str(uuid.uuid4())
    voce = {
        "id": id_fattura,
        "file_origine": nome_file,
        "timestamp": timestamp_locale(),
        "stato": stato,
        # differita / accompagnatoria / senza_ddt: va conservato perche' al
        # ricontrollo i riferimenti sono gia' costruiti e non direbbero piu' da
        # dove venivano.
        "tipo_abbinamento": tipo,
        "dati": {c: v for c, v in fattura.items() if c not in ("ddt", "allegati")},
        "ddt": righe,
        "ddt_allegati": [],
        "numero_pagine": 0,
    }

    # Le anomalie sul cedente (P.IVA assente, o diversa da quella confermata in
    # anagrafica) restano ATTACCATE alla pratica, non solo nella risposta della
    # chiamata che l'ha caricata: chi apre la fattura tre giorni dopo deve poter
    # vedere perche' non torna, e chi la carica non e' detto stia guardando.
    # Assente = niente da segnalare, come tutte le chiavi opzionali dei registri.
    if segnalazioni:
        voce["segnalazioni"] = segnalazioni

    archivia_originale(id_fattura, contenuto, estensione)

    with _LUCCHETTO:
        # Nessuna pratica si chiude da sola, nemmeno quando tutti i DDT sono
        # gia' stati trovati: l'abbinamento e' una proposta e la firma la mette
        # l'operatore col pulsante ACCOPPIA. Qui si prepara soltanto.
        voce["controlli"] = 0
        if stato == IN_ATTESA:
            voce["attesa"] = riepilogo_attesa(righe)
        aggiorna_registro(REGISTRO_ATTESA, voce)

    return voce


def registra_senza_abbinare(fattura, tipo, nome_file, contenuto, estensione,
                            segnalazioni=None):
    """Archivia una fattura letta, SENZA cercarle i DDT.

    E' la porta d'ingresso dal 2026-09-08: caricare una fattura e abbinarla sono
    due gesti distinti, perche' l'abbinamento e' un confronto fra un XML esatto
    e numeri letti da una fotografia — quindi una proposta, che si guarda prima
    di accettarla. Il confronto lo fa poi "Abbina tutte" oppure il pulsante
    sulla singola riga.

    I numeri citati vengono comunque conservati (righe_da_abbinare): senza, il
    modale non avrebbe niente da mostrare e il ricontrollo non saprebbe piu'
    cosa cercare.
    """
    return registra_fattura(
        fattura, DA_ABBINARE, righe_da_abbinare(fattura, tipo), tipo,
        nome_file, contenuto, estensione, segnalazioni,
    )


# ---------------------------------------------------------------------------
# Il ricontrollo (il cuore ri-entrante)
# ---------------------------------------------------------------------------

def ricontrolla_attese(documenti=None, includi_da_abbinare=False):
    """Riprova l'abbinamento delle fatture in coda.

    Va chiamata dopo ogni evento che rende abbinabile un DDT che prima non lo
    era. E' volutamente senza parametri di selezione delle voci: la coda e'
    corta (contiene solo pratiche aperte) e ragionare su "quali fatture potrebbe
    sbloccare questo DDT" costerebbe piu' errori che secondi.

    `includi_da_abbinare` distingue i due modi in cui si arriva qui:
      - False (i cinque agganci sui DDT): si aggiornano solo le pratiche che
        l'operatore aveva gia' abbinato. Una fattura mai confrontata resta
        intatta, perche' nessuno ha chiesto quel confronto;
      - True (il pulsante "Abbina tutte"): il confronto lo sta chiedendo
        adesso una persona, su tutta la coda.
    """
    with _LUCCHETTO:
        coda = leggi_registro(REGISTRO_ATTESA)
        if not coda:
            return {"in_coda": 0, "sbloccate": [], "restano": 0}

        documenti = carica_documenti() if documenti is None else documenti
        restano, sbloccate = [], []

        for voce in coda:
            # Una voce mai abbinata resta com'e': il confronto non e' stato
            # chiesto, e farlo di nascosto perche' e' arrivato un DDT sarebbe
            # esattamente l'automatismo che si e' voluto togliere. Si sblocca
            # da sola solo una pratica che l'operatore aveva gia' abbinato.
            if voce.get("stato") == DA_ABBINARE and not includi_da_abbinare:
                restano.append(voce)
                continue

            try:
                stato, righe, _tipo = abbina_fattura(
                    riferimenti_da_voce(voce), documenti, voce.get("tipo_abbinamento"))
            except Exception as errore:
                # Una fattura che esplode non deve svuotare la coda delle altre.
                print(f"⚠️ Ricontrollo fallito per la fattura {voce.get('id')}: {errore}")
                restano.append(voce)
                continue

            precedente = voce.get("stato")
            voce["ddt"] = righe
            voce["stato"] = stato
            voce["ultimo_controllo"] = timestamp_locale()
            voce["controlli"] = voce.get("controlli", 0) + 1

            # "Sbloccata" non vuol piu' dire "chiusa" ma "diventata pronta da
            # accoppiare": la pratica resta in coda ad aspettare la conferma.
            # Va detto lo stesso, anzi soprattutto: e' l'effetto della
            # correzione che l'utente ha appena fatto in un'altra sezione.
            voce.pop("attesa", None)

            if stato == ABBINATA:
                if precedente != ABBINATA:
                    sbloccate.append({
                        "id": voce["id"],
                        "numero_fattura": voce.get("dati", {}).get("numero_fattura", ""),
                        "fornitore": voce.get("dati", {}).get("fornitore", ""),
                        "ddt": len(righe),
                    })
            else:
                voce["attesa"] = riepilogo_attesa(righe)

            restano.append(voce)

        salva_registro(REGISTRO_ATTESA, restano)

    if sbloccate:
        elenco = ", ".join(f"{s['numero_fattura']} ({s['fornitore']})" for s in sbloccate)
        print(f"🔓 Fatture pronte da accoppiare grazie ai nuovi DDT: {elenco}")

    return {"in_coda": len(coda), "sbloccate": sbloccate, "restano": len(restano)}


# ---------------------------------------------------------------------------
# Anzianita' della coda (input della mail di sollecito)
# ---------------------------------------------------------------------------

def abbina_tutte(documenti=None):
    """Il pulsante "Abbina tutte": cerca i DDT di ogni fattura ancora in coda.

    E' ricontrolla_attese() con il confronto esteso anche alle fatture mai
    abbinate — che sono la maggioranza subito dopo una scansione della cartella
    in ingresso. Non chiude niente: al massimo porta delle pratiche a
    "pronte da accoppiare", e la firma resta un gesto separato.
    """
    return ricontrolla_attese(documenti, includi_da_abbinare=True)


def giorni_in_attesa(voce):
    """Da quanti giorni la voce e' ferma (vale per una fattura in coda come per
    un DDT non ancora fatturato). Si conta dal primo ingresso in archivio, non
    dall'ultimo ricontrollo: e' l'attesa reale del documento."""
    istante = leggi_timestamp(voce.get("timestamp"))
    if istante is None:
        return 0
    return max(0, (adesso() - istante).days)


def fatture_in_attesa(giorni_minimi=0):
    """Le fatture che aspettano un DOCUMENTO, dalla piu' vecchia.

    Da quando la chiusura e' manuale, ATTESA.json contiene anche le pratiche
    gia' pronte che aspettano solo la conferma: quelle restano fuori di
    proposito, perche' questa e' la lista che alimenta il sollecito. Si vedono
    in dashboard, dove c'e' il pulsante per chiuderle.
    """
    voci = []
    for voce in leggi_registro(REGISTRO_ATTESA):
        if voce.get("stato") != IN_ATTESA:
            continue
        giorni = giorni_in_attesa(voce)
        if giorni < giorni_minimi:
            continue
        voci.append({**voce, "giorni_attesa": giorni})

    return sorted(voci, key=lambda v: v["giorni_attesa"], reverse=True)


def fatture_da_accoppiare(giorni_minimi=0):
    """Le pratiche ferme perche' aspettano una PERSONA, dalla piu' vecchia.

    Sono due situazioni diverse che condividono la cura (aprire la dashboard e
    premere un pulsante), e per questo stanno in una lista sola:
      - DA_ABBINARE: nessuno ha ancora chiesto il confronto con i DDT;
      - ABBINATA ma ancora in coda: i DDT ci sono tutti, manca la firma.

    Il motivo viaggia con la voce (`motivo_attesa`) perche' la mail deve poter
    dire quale dei due pulsanti serve: "Abbina" non e' "Accoppia".

    Non e' la stessa lista di fatture_in_attesa(), che elenca chi aspetta un
    DOCUMENTO: quella manda qualcuno in magazzino, questa manda qualcuno in
    dashboard. Confonderle vorrebbe dire far cercare una bolla gia' archiviata.
    """
    voci = []
    for voce in leggi_registro(REGISTRO_ATTESA):
        stato = voce.get("stato")
        if stato == DA_ABBINARE:
            motivo = "da_abbinare"
        elif stato == ABBINATA:
            motivo = "da_confermare"
        else:
            continue

        giorni = giorni_in_attesa(voce)
        if giorni < giorni_minimi:
            continue
        voci.append({**voce, "giorni_attesa": giorni, "motivo_attesa": motivo})

    return sorted(voci, key=lambda v: v["giorni_attesa"], reverse=True)


def ddt_senza_fattura(giorni_minimi=0):
    """I DDT archiviati che nessuna fattura ha ancora agganciato.

    E' l'altra meta' della stessa attesa: la coda ATTESA.json elenca le fatture
    a cui manca una bolla, questa elenca le bolle a cui manca una fattura. Il
    riconoscimento e' l'annotazione "fattura" scritta da annota_ddt_abbinati()
    alla chiusura della pratica, quindi un DDT smette di comparire qui appena la
    sua fattura si chiude.

    Non serve nessun ricontrollo ciclico da questo lato: ogni fattura nuova
    viene confrontata con TUTTI i DDT archiviati, quindi un DDT che aspetta si
    aggancia da solo il giorno in cui l'XML arriva. Qui c'e' solo il conteggio
    del tempo, che e' quello che alimenta il sollecito.
    """
    voci = []

    for stato in STATI_DDT_DA_FATTURARE:
        for documento in leggi_registro(stato):
            if documento.get("fattura"):
                continue

            giorni = giorni_in_attesa(documento)
            if giorni < giorni_minimi:
                continue

            dati = documento.get("dati", {})
            voci.append({
                "id": documento.get("id", ""),
                "stato": stato,
                "giorni_attesa": giorni,
                "fornitore": dati.get("fornitore", ""),
                "numero_ddt": dati.get("numero_ddt", ""),
                "data_ddt": dati.get("data_ddt", ""),
                "ragione_sociale_consegna": dati.get("ragione_sociale_consegna", ""),
            })

    return sorted(voci, key=lambda v: v["giorni_attesa"], reverse=True)


def completate_da(istante):
    """Le fatture uscite dalla coda dopo un certo momento.

    E' cio' che permette alla mail di fine estrazione di dire "durante questa
    elaborazione si sono chiuse 2 fatture": l'informazione non sta nei registri
    DDT, ma nel campo "completata" scritto da _chiudi().
    """
    completate = []
    for voce in leggi_registro(REGISTRO_FATTURE):
        momento = leggi_timestamp(voce.get("completata"))
        if istante is not None and (momento is None or momento < istante):
            continue
        completate.append({
            "id": voce.get("id"),
            "numero_fattura": voce.get("dati", {}).get("numero_fattura", ""),
            "fornitore": voce.get("dati", {}).get("fornitore", ""),
            "ddt": len(voce.get("ddt", [])),
        })
    return completate


def trova_fattura(id_fattura):
    """(registro, voce) cercando in entrambi i registri del flusso."""
    for registro in (REGISTRO_ATTESA, REGISTRO_FATTURE):
        for voce in leggi_registro(registro):
            if voce.get("id") == id_fattura:
                return registro, voce
    return None, None


# ---------------------------------------------------------------------------
# L'accoppiamento manuale (il pulsante ACCOPPIA)
# ---------------------------------------------------------------------------

def proponi_accoppiamento(id_fattura, documenti=None):
    """Ricalcola l'abbinamento di UNA fattura e restituisce la voce aggiornata.

    E' il primo tempo del pulsante ACCOPPIA: cerca fra i DDT archiviati quelli
    che la fattura cita, cosi' l'operatore li vede prima di firmare. Non scrive
    niente nell'archivio — nessun file unico, nessuna annotazione sui DDT:
    quelle arrivano solo con conferma_accoppiamento(). Riscrive pero' la voce in
    coda, altrimenti un abbinamento ricalcolato e non salvato tornerebbe a
    mostrare i vecchi esiti alla prossima apertura del modale.

    Su una pratica gia' confermata non ricalcola niente: quella e' chiusa, e
    rifare il confronto contraddirebbe un file gia' consegnato.
    """
    with _LUCCHETTO:
        registro, voce = trova_fattura(id_fattura)
        if voce is None:
            return None, "non trovata"
        if registro == REGISTRO_FATTURE:
            return voce, "gia confermata"

        documenti = carica_documenti() if documenti is None else documenti
        stato, righe, _tipo = abbina_fattura(
            riferimenti_da_voce(voce), documenti, voce.get("tipo_abbinamento"))

        voce["ddt"] = righe
        voce["stato"] = stato
        voce["ultimo_controllo"] = timestamp_locale()
        voce["controlli"] = voce.get("controlli", 0) + 1
        voce.pop("attesa", None)
        if stato != ABBINATA:
            voce["attesa"] = riepilogo_attesa(righe)

        # aggiorna_registro() accoda: qui la voce esiste gia' e va SOSTITUITA,
        # altrimenti la coda si riempie di copie della stessa pratica a ogni
        # click su ACCOPPIA.
        salva_registro(REGISTRO_ATTESA, [
            voce if v.get("id") == id_fattura else v
            for v in leggi_registro(REGISTRO_ATTESA)
        ])

    return voce, None


def conferma_accoppiamento(id_fattura):
    """Secondo tempo: l'operatore ha visto i DDT agganciati e firma.

    Da qui — e solo da qui — nasce il file unico in ACCOPPIATE, i DDT ricevono
    l'annotazione della loro fattura e la pratica passa in FATTURE.json.
    """
    with _LUCCHETTO:
        registro, voce = trova_fattura(id_fattura)
        if voce is None:
            return None, "non trovata"
        if registro == REGISTRO_FATTURE:
            return voce, "gia confermata"

        _chiudi(voce)
        salva_registro(
            REGISTRO_ATTESA,
            [v for v in leggi_registro(REGISTRO_ATTESA) if v.get("id") != id_fattura],
        )

    dati = voce.get("dati", {})
    print(f"📎 Accoppiata la fattura {dati.get('numero_fattura', '')} "
          f"({dati.get('fornitore', '')}) con {len(voce.get('ddt', []))} DDT "
          f"→ {voce.get('fascicolo', '')}")
    return voce, None


def anteprima_fascicolo(voce):
    """Costruisce in un file temporaneo il fascicolo di una fattura in coda.

    Il fascicolo definitivo lo scriviamo solo per le pratiche chiuse: quello di
    una fattura in attesa sarebbe gia' vecchio al prossimo DDT. Quando pero'
    dall'interfaccia si chiede di vederlo vale la stessa regola del fascicolo
    parziale di prima: e' il modo piu' comodo per capire cosa manca. Chi chiama
    e' responsabile di cancellare la cartella temporanea (vedi /api/pdf-fattura).
    """
    cartella = tempfile.mkdtemp(prefix="anteprima_fascicolo_")
    percorso = os.path.join(cartella, f"{voce['id']}.pdf")

    try:
        costruisci_fascicolo(fattura_per_fascicolo(voce), voce.get("ddt", []), percorso)
    except Exception:
        shutil.rmtree(cartella, ignore_errors=True)
        raise

    return percorso
