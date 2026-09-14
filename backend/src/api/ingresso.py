"""Le due cartelle in ingresso e i tre lavori che il pianificatore fa partire.

Caricare e analizzare restano due gesti: si mettono in coda dieci bolle in
pochi secondi e si fa partire l'analisi (minuti, sulla GPU condivisa) una volta
sola. Le route sono sottili sopra _scansione_ddt() / _scansione_fatture(), che
prendono l'origine (manuale | pianificata) e in coda mandano la mail se serve.

I tre lavoro_* in fondo sono cio' che main.py passa a pianificatore.avvia():
il pianificatore sa QUANDO, non COSA, e importare le pipeline dentro un modulo
di src/comune/ lo legherebbe a tutti e due i flussi.
"""

import os
import shutil
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException

from src.api.lavorazione import elabora_ddt, elabora_fattura
from src.api.supporto import esigi_motore_pronto
from src.comune.configurazione import valore
from src.comune.percorsi import CARTELLA_DDT_INGRESSO, CARTELLA_FATTURE_INGRESSO
from src.comune.tempo import adesso
from src.ddt.notificatore import calcola_riepilogo
from src.fatture.coda import (
    ddt_senza_fattura, fatture_da_accoppiare, fatture_in_attesa,
    giorni_accoppiamento, giorni_attesa_ddt, giorni_attesa_fattura,
)
from src.notifiche import mailer, riepilogo_ddt, riepilogo_fatture, sollecito

router = APIRouter()


ESTENSIONI_DDT = (".pdf", ".jpg", ".jpeg", ".png")
ESTENSIONI_FATTURA = (".xml", ".p7m")


def _file_in_ingresso(cartella, estensioni):
    """I file lavorabili di una cartella, in ordine alfabetico."""
    if not os.path.isdir(cartella):
        return []
    return sorted(
        nome for nome in os.listdir(cartella)
        if nome.lower().endswith(estensioni)
        and os.path.isfile(os.path.join(cartella, nome))
    )


def _deposita(cartella, files, estensioni, etichetta):
    """Scrive gli upload nella cartella in ingresso, senza mai sovrascrivere.

    Un nome già presente prende un suffisso numerico: due bolle scansionate lo
    stesso giorno si chiamano spesso "scan.pdf", e una sovrascritta in silenzio
    è un documento perso — lo stesso motivo per cui il file unico in ACCOPPIATE
    porta in coda le cifre dell'id.
    """
    os.makedirs(cartella, exist_ok=True)
    caricati, scartati = [], []

    for file in files:
        nome = os.path.basename(file.filename or "")
        if not nome.lower().endswith(estensioni):
            scartati.append({"file": nome, "motivo": f"non è un file {etichetta}"})
            continue

        radice, estensione = os.path.splitext(nome)
        destinazione = os.path.join(cartella, nome)
        contatore = 2
        while os.path.exists(destinazione):
            destinazione = os.path.join(cartella, f"{radice}_{contatore}{estensione}")
            contatore += 1

        with open(destinazione, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        caricati.append(os.path.basename(destinazione))
        print(f"📂 {etichetta}: '{nome}' depositato come '{os.path.basename(destinazione)}'.")

    return caricati, scartati


@router.post("/api/ddt/carica")
def carica_ddt(files: List[UploadFile] = File(...)):
    """Deposita una o più scansioni in DDT/da_leggere, senza analizzarle.

    Caricare e analizzare restano due gesti: si possono mettere in coda dieci
    bolle in pochi secondi e far partire l'analisi (minuti, sulla GPU condivisa)
    una volta sola.
    """
    caricati, scartati = _deposita(CARTELLA_DDT_INGRESSO, files, ESTENSIONI_DDT, "D.D.T.")
    return {
        "caricati": caricati,
        "scartati": scartati,
        "in_attesa": len(_file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT)),
    }


@router.post("/api/fatture/carica")
def carica_fatture(files: List[UploadFile] = File(...)):
    """Deposita una o più fatture elettroniche in FATTURE/da_leggere."""
    caricati, scartati = _deposita(CARTELLA_FATTURE_INGRESSO, files, ESTENSIONI_FATTURA, "fattura")
    return {
        "caricati": caricati,
        "scartati": scartati,
        "in_attesa": len(_file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA)),
    }


@router.get("/api/ingresso")
async def stato_ingresso():
    """Quanti file aspettano nelle due cartelle: è il numero sul pulsante Analizza."""
    return {
        "ddt": _file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT),
        "fatture": _file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA),
    }


def _scansione_ddt(origine="manuale"):
    """Analizza tutte le scansioni ferme in DDT/da_leggere.

    Il file elaborato viene RIMOSSO dalla cartella: la scansione resta
    nell'archivio come PDF sotto DDT/lette/<stato>/, che è la copia buona, e
    lasciarla anche in ingresso vorrebbe dire ritrovarsela a ogni click su
    Analizza. Un file che fallisce resta dov'è: sarà riprovabile dopo aver
    capito perché.

    Un file le cui pagine risultano TUTTE già archiviate conta come elaborato e
    viene rimosso lo stesso — è stato guardato, e il suo contenuto è al sicuro
    da un'altra parte. Le pagine saltate finiscono in 'duplicati', perché una
    risposta con zero pagine e un file scartato per intero si assomigliano
    troppo, e la prima sembra un errore.

    Sincrona: chiama elabora_ddt(), che è bloccante.

    origine dice chi l'ha chiesta ("manuale" dalla dashboard, "pianificata" dal
    pianificatore notturno) e serve solo a decidere se mandare la mail di
    riepilogo: chi ha appena premuto Analizza sta già guardando l'esito.
    """
    inizio = adesso()
    nomi = _file_in_ingresso(CARTELLA_DDT_INGRESSO, ESTENSIONI_DDT)
    print(f"📥 Scansione {origine} di DDT/da_leggere: {len(nomi)} file da elaborare.")

    # Il motore si controlla una volta per batch, e solo se c'e' davvero
    # qualcosa da analizzare: su una cartella vuota non c'e' niente da fermare.
    # elabora_ddt() ha lo stesso controllo, ma la' finirebbe N volte identico
    # nell'elenco dei falliti, e "10 file non elaborati" non dice PERCHE'. Qui
    # invece la scansione non parte affatto e il motivo e' uno solo: la
    # dashboard lo mostra al posto dell'esito, e il pianificatore lo registra
    # come esito del lavoro notturno — che e' l'unico modo di sapere il mattino
    # dopo che la scansione delle 2:00 non e' partita, invece di trovare
    # semplicemente la cartella ancora piena.
    if nomi:
        esigi_motore_pronto()

    elaborati, falliti, sbloccate, duplicati = [], [], [], []

    for nome in nomi:
        percorso = os.path.join(CARTELLA_DDT_INGRESSO, nome)
        try:
            esito = elabora_ddt(percorso, nome)
        except HTTPException as e:
            print(f"❌ '{nome}' non elaborato: {e.detail}")
            falliti.append({"file": nome, "motivo": str(e.detail)})
            continue
        except Exception as e:
            print(f"❌ '{nome}' non elaborato: {e}")
            falliti.append({"file": nome, "motivo": str(e)})
            continue

        elaborati.append({
            "file": nome,
            "pagine": len(esito["pagine_elaborate"]),
            "duplicate": len(esito.get("duplicati", [])),
        })
        sbloccate.extend(esito.get("fatture_sbloccate", []))
        duplicati.extend(esito.get("duplicati", []))
        try:
            os.remove(percorso)
        except OSError as e:
            print(f"⚠️ '{nome}' elaborato ma non rimosso dalla cartella ({e}): rimuovilo a mano, "
                  f"altrimenti la prossima analisi lo archivierà una seconda volta.")

    esito = {
        "elaborati": elaborati,
        "falliti": falliti,
        "duplicati": duplicati,
        "pagine_totali": sum(e["pagine"] for e in elaborati),
        "fatture_sbloccate": sbloccate,
    }

    if _riepilogo_da_mandare(origine) and (elaborati or falliti):
        oggetto, corpo = riepilogo_ddt.componi(calcola_riepilogo(inizio), sbloccate, falliti,
                                               duplicati)
        mailer.invia_silenzioso(oggetto, corpo, "riepilogo D.D.T.")

    return esito


@router.post("/api/ddt/scansiona")
def scansiona_ddt():
    """Il pulsante Analizza dei D.D.T.: sincrona, perché elabora_ddt() è bloccante."""
    return _scansione_ddt("manuale")


def _scansione_fatture(origine="manuale"):
    """Legge e archivia tutte le fatture ferme in FATTURE/da_leggere.

    NON le abbina: dal 2026-09-08 leggere una fattura e cercarle i D.D.T. sono
    due gesti distinti, e il secondo lo chiede l'operatore (ABBINA su una riga,
    "Abbina tutte" sulla coda).

    Il file viene rimosso quando è stato archiviato o riconosciuto come
    duplicato — in entrambi i casi la fattura è già nei registri, e l'XML
    originale è conservato accanto alla voce, che è la copia che conta.
    """
    nomi = _file_in_ingresso(CARTELLA_FATTURE_INGRESSO, ESTENSIONI_FATTURA)
    print(f"📥 Scansione {origine} di FATTURE/da_leggere: {len(nomi)} file da leggere.")

    lette, falliti = [], []

    for nome in nomi:
        percorso = os.path.join(CARTELLA_FATTURE_INGRESSO, nome)
        try:
            with open(percorso, "rb") as f:
                contenuto = f.read()
            esito = elabora_fattura(nome, contenuto)
        except HTTPException as e:
            print(f"❌ '{nome}' non letto: {e.detail}")
            falliti.append({"file": nome, "motivo": str(e.detail)})
            continue
        except Exception as e:
            print(f"❌ '{nome}' non letto: {e}")
            falliti.append({"file": nome, "motivo": str(e)})
            continue

        lette.extend(esito["fatture"])
        try:
            os.remove(percorso)
        except OSError as e:
            print(f"⚠️ '{nome}' letto ma non rimosso dalla cartella ({e}).")

    # Le anomalie sul cedente si tirano fuori appiattite: la barra di ingresso
    # deve poter dire "2 fatture con anomalie" senza aprire ogni voce. Restano
    # comunque scritte sulla pratica, perché chi le guarda spesso non è chi ha
    # premuto il pulsante.
    segnalate = [
        {
            "numero_fattura": f.get("numero_fattura", ""),
            "fornitore": f.get("fornitore", ""),
            "messaggi": [s["messaggio"] for s in f.get("segnalazioni", [])],
        }
        for f in lette if f.get("segnalazioni")
    ]

    esito = {
        "fatture": lette,
        "falliti": falliti,
        "totale": len(lette),
        "duplicate": sum(1 for f in lette if f.get("stato") == "DUPLICATA"),
        "segnalate": segnalate,
    }

    if _riepilogo_da_mandare(origine) and (lette or falliti):
        oggetto, corpo = riepilogo_fatture.componi(esito)
        mailer.invia_silenzioso(oggetto, corpo, "riepilogo fatture")

    return esito


@router.post("/api/fatture/scansiona")
def scansiona_fatture():
    """Il pulsante Analizza delle fatture."""
    return _scansione_fatture("manuale")

def _riepilogo_da_mandare(origine):
    """Se questa scansione merita una mail di riepilogo.

    'pianificate' (il valore di partenza) manda la mail solo per le scansioni
    notturne: chi preme Analizza dalla dashboard vede l'esito sullo schermo, e
    una mail per ogni click smetterebbe di essere letta — con lei anche quelle
    delle scansioni automatiche, che sono le uniche che nessuno sta guardando.
    """
    modo = valore("MAIL_RIEPILOGO_SCANSIONE")
    if modo == "mai":
        return False
    if modo == "pianificate":
        return origine == "pianificata"
    return True


def lavoro_scansione_ddt():
    esito = _scansione_ddt("pianificata")
    duplicate = len(esito["duplicati"])
    return {"riassunto": f"{len(esito['elaborati'])} file elaborati, "
                         f"{esito['pagine_totali']} pagine, "
                         + (f"{duplicate} pagine già archiviate, " if duplicate else "")
                         + f"{len(esito['falliti'])} falliti"}


def lavoro_scansione_fatture():
    esito = _scansione_fatture("pianificata")
    return {"riassunto": f"{esito['totale']} fatture lette, "
                         f"{esito['duplicate']} duplicate, {len(esito['falliti'])} falliti"}


def lavoro_sollecito():
    """La mail del mattino: l'unico lavoro guidato dal tempo e non da un documento.

    Se non c'è niente di fermo, componi() restituisce None e non parte niente:
    una mail "nessuna fattura in attesa" verrebbe ignorata entro tre giorni,
    comprese le volte in cui dice qualcosa.
    """
    soglia_fattura = giorni_attesa_fattura()
    soglia_ddt = giorni_attesa_ddt()
    soglia_click = giorni_accoppiamento()

    composto = sollecito.componi(
        fatture_in_attesa(soglia_fattura),
        fatture_da_accoppiare(soglia_click),
        ddt_senza_fattura(soglia_ddt),
        soglia_fattura,
        soglia_click,
        soglia_ddt,
    )

    if composto is None:
        return {"riassunto": "niente da sollecitare"}

    oggetto, corpo = composto
    esito = mailer.invia_silenzioso(oggetto, corpo, "sollecito")
    return {"riassunto": oggetto if esito["inviata"] else f"non inviata: {esito['motivo']}"}
