"""Gli aiutanti condivisi dalle route, senza nessuna route dentro.

Non e' un "utils": sono le cinque funzioni che piu' di un router chiama e che
non appartengono a nessuno dei due flussi in particolare — verificare che il
motore AI risponda prima di avviare un'analisi, trovare un D.D.T. nei tre
registri, spostarlo portandosi dietro il PDF, annotare in lettura lo stato
della sua P.IVA e far ripartire il ricontrollo della coda fatture.

Stanno qui e non in src/comune/ per la regola gia' scritta in CLAUDE.md: in
comune/ ci va cio' che serve alle PIPELINE, qui cio' che serve alle ROUTE.
Questo modulo non importa nessun router: le dipendenze dentro src/api/ scorrono
tutte verso supporto.py e lavorazione.py, mai all'indietro.
"""

import os
import shutil

from fastapi import HTTPException

from src.comune.memory_manager import (
    carica_memoria, partita_iva_per, voce_fornitore_estero,
)
from src.comune.percorsi import CARTELLA_DDT
from src.comune.registro import (
    aggiorna_registro, leggi_registro, rimuovi_dal_registro,
    aggiorna_documento_registro, percorso_pdf_documento,
)
from src.ddt.llm_engine import verifica_motore
from src.fatture.coda import ricontrolla_attese


def esigi_motore_pronto():
    """Ferma un'analisi PRIMA che cominci se il motore AI non risponde.

    Senza, un Ollama spento si scopre a meta' lavoro: le pagine gia' lette sono
    archiviate, quelle dopo no, e il file torna un errore generico — un
    documento elaborato a meta' che nessuno sa di dover riprendere, che e'
    peggio di uno non elaborato affatto. Qui invece, quando dice di no, non e'
    stato ancora toccato niente: nessun PDF scritto, nessuna voce nei registri,
    nessun file rimosso dalla cartella in ingresso.

    Costa un giro di rete di pochi millisecondi contro i minuti di una
    scansione, quindi si paga volentieri anche per file.

    **503 e non 500**: non e' un guasto di questo servizio ma una dipendenza
    esterna che non c'e' (la GPU sta su un'altra macchina in LAN), e chi lo
    riceve deve capire che riprovare piu' tardi ha senso.
    """
    esito = verifica_motore()
    if not esito["pronto"]:
        print(f"⛔ Analisi non avviata: {esito['motivo']}")
        raise HTTPException(status_code=503, detail=esito["motivo"])
    return esito


def ricontrolla_fatture_in_attesa(motivo):
    """Riprova l'abbinamento delle fatture in coda dopo un evento sui DDT.

    Chiamata da TUTTI i punti in cui un DDT prima invisibile diventa
    abbinabile: fine estrazione, inserimento manuale, unione manuale, rianalisi
    e correzione a mano dei dati (quest'ultima è proprio il caso che sblocca gli
    abbinamenti "probabili", cioè le cifre lette male dal modello).

    Non deve mai far fallire l'operazione sui DDT che l'ha innescata: il
    documento è già stato archiviato, e una coda che esplode è un problema del
    flusso fatture, non di chi stava salvando una bolla.
    """
    try:
        report = ricontrolla_attese()
    except Exception as e:
        print(f"⚠️ Ricontrollo delle fatture in attesa fallito ({motivo}): {e}")
        return {"in_coda": 0, "sbloccate": [], "restano": 0}

    if report["sbloccate"]:
        print(f"🔓 {len(report['sbloccate'])} fatture completate dopo {motivo}")
    return report


def trova_documento(doc_id):
    """Cerca un D.D.T. nei tre registri: (stato, indice, documento), altrimenti None."""
    for stato in ["OK", "CHECK", "KO"]:
        for indice, doc in enumerate(leggi_registro(stato)):
            if doc.get('id') == doc_id:
                return stato, indice, doc

    return None, None, None


def sposta_documento(doc_id, stato_origine, indice, documento, stato_finale, path_pdf=None):
    """Riscrive la voce nel registro dello stato finale, portandosi dietro il PDF.

    Se lo stato non cambia si limita ad aggiornare la voce dov'è. Il file deve
    seguire il registro: GET /api/pdf/{id}.pdf lo ritroverebbe comunque
    scorrendo gli stati, ma i due archivi resterebbero disallineati e il
    fallback esiste per i documenti vecchi, non per coprire uno spostamento
    fatto a metà.
    """
    if stato_finale == stato_origine:
        aggiorna_documento_registro(stato_origine, indice, documento)
        return

    origine = path_pdf or percorso_pdf_documento(stato_origine, doc_id)

    rimuovi_dal_registro(stato_origine, indice)
    aggiorna_registro(stato_finale, documento)

    if not origine:
        return

    destinazione = os.path.join(CARTELLA_DDT, stato_finale, f"{doc_id}.pdf")
    if os.path.abspath(origine) != os.path.abspath(destinazione):
        os.makedirs(os.path.dirname(destinazione), exist_ok=True)
        shutil.move(origine, destinazione)

def annota_stato_piva(documenti):
    """Aggiunge a ogni documento lo stato della P.IVA del suo fornitore.

    Non e' un dato del documento e non viene mai scritto nei registri: la
    verita' sta in anagrafica, e una copia sul registro invecchierebbe alla
    prima conferma fatta da un'altra bolla dello stesso fornitore. Sta
    accanto a 'status', calcolato in lettura come lui.

    Serve al modale di revisione per decidere se la P.IVA e' ancora da
    confermare (campo editabile + pulsante) o e' gia' una chiave (campo in
    sola lettura: da li' in poi si corregge dall'anagrafica).

    Su un fornitore ESTERO non c'e' niente da confermare: si riporta il flag
    (cosi' il modale puo' dirlo invece di mostrare un campo vuoto in attesa) e
    si dichiara la P.IVA confermata, altrimenti resterebbe per sempre un
    invito a completare una chiave che non esiste.

    La cache tiene la ricerca per somiglianza a una volta per nome distinto,
    non a una per documento.
    """
    memoria = carica_memoria()
    cache = {}
    for doc in documenti:
        nome = ((doc.get('dati') or {}).get('fornitore') or "").strip()
        if nome not in cache:
            cache[nome] = (
                partita_iva_per(nome, memoria) + voce_fornitore_estero(nome, memoria)
                if nome else ("", False, False, "")
            )
        piva, confermata, estero, identificativo = cache[nome]
        doc['partita_iva_anagrafica'] = piva
        doc['partita_iva_confermata'] = estero or (bool(piva) and confermata)
        doc['fornitore_estero'] = estero
        doc['identificativo_estero'] = identificativo
    return documenti
