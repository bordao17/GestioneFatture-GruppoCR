"""Le route delle fatture elettroniche: lettura, coda, abbinamento, fascicolo.

Qui il modello non entra mai: in FatturaPA i riferimenti ai D.D.T. sono gia'
strutturati dentro <DatiDDT> e il cedente sta nell'header, quindi tutto il
lavoro e' parsing e confronto di stringhe.

L'ORDINE DI DICHIARAZIONE CONTA, e non e' un vezzo: /api/fatture/attese e
/api/fatture/abbina-tutte devono restare PRIMA di /api/fatture/{id_fattura} e
di /api/fatture/{id_fattura}/accoppia, altrimenti la route parametrica se li
mangia e "attese" diventa l'id di una fattura che non esiste.
"""

import os
import shutil

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.api.lavorazione import elabora_fattura
from src.api.supporto import ricontrolla_fatture_in_attesa
from src.comune.percorsi import (
    CARTELLA_ACCOPPIATE, CARTELLA_FATTURE, REGISTRO_FATTURE, REGISTRO_ATTESA,
)
from src.comune.registro import leggi_registro, rimuovi_dal_registro
from src.fatture.abbinatore import dimentica_fattura, ABBINATA
from src.fatture.coda import (
    abbina_tutte, anteprima_fascicolo, conferma_accoppiamento, ddt_senza_fattura,
    fatture_da_accoppiare, fatture_in_attesa, giorni_accoppiamento,
    giorni_attesa_ddt, giorni_attesa_fattura, giorni_in_attesa,
    percorso_fascicolo, proponi_accoppiamento, trova_fattura,
)

router = APIRouter()


@router.post("/abbina-fattura")
def abbina_fattura_endpoint(file: UploadFile = File(...)):
    """Legge una fattura elettronica (.xml o .xml.p7m) e la aggancia ai DDT archiviati.

    Qui il modello NON entra mai: i riferimenti ai DDT sono già strutturati
    dentro <DatiDDT>, quindi tutto il lavoro è parsing e confronto di stringhe.
    Un file può contenere più fatture (fattura a lotti): ognuna viene valutata
    per conto suo.

    Tre filtri prima dell'abbinamento vero e proprio:
      1. il cedente dev'essere un fornitore AUTORIZZATO in anagrafica — la
         cartella da cui arrivano gli XML contiene anche fatture che non ci
         riguardano. Il riconoscimento è per P.IVA, che è esatta, non per nome;
      2. la fattura non dev'essere già passata di qui (P.IVA + numero + data):
         il ramo n8n non svuota la cartella, quindi rilanciarlo ripassa gli
         stessi file;
      3. senza <DatiDDT> non c'è niente da aspettare e la pratica nasce chiusa
         come NON_ABBINATA.
    Ciò che resta incompleto NON è un esito ma una coda (IN_ATTESA): viene
    ricontrollato a ogni nuovo DDT finché si chiude.

    Sincrona come /estrai-ddt: il corpo scrive su disco e assembla PDF.
    """
    nome_file = file.filename or "fattura.xml"
    contenuto = file.file.read()
    return elabora_fattura(nome_file, contenuto)


@router.get("/api/fatture")
async def get_fatture():
    """Tutte le fatture, chiuse e in coda, con lo stato di ognuna.

    I due registri sono file separati (FATTURE.json e ATTESA.json) ma per la
    dashboard sono un elenco solo: lo stato è già dentro la voce, come per i DDT.
    """
    fatture = []

    # "in_coda" dice in quale registro sta la voce, e va detto esplicitamente:
    # da quando la chiusura e' manuale lo stato non basta piu' a distinguere una
    # pratica pronta (ABBINATA, ancora in coda: aspetta il pulsante ACCOPPIA) da
    # una gia' confermata (ABBINATA, in FATTURE.json: il file unico esiste).
    for voce in leggi_registro(REGISTRO_ATTESA):
        fatture.append({**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)})

    for voce in leggi_registro(REGISTRO_FATTURE):
        fatture.append({**voce, "in_coda": False})

    return fatture

@router.get("/api/fatture/attese")
async def get_fatture_attese(
    giorni: int = Query(None, ge=0, description="Solo le ferme da almeno N giorni (default: la soglia configurata)")
):
    """La coda: fatture i cui DDT non sono ancora tutti arrivati.

    È l'endpoint che alimenta la mail di sollecito. Senza parametro applica
    GIORNI_ATTESA_FATTURA (30 giorni di partenza, dalla sezione Configurazione
    o dal docker-compose): la soglia resta un solo numero, letto qui, e chi la
    consuma non ne conserva una copia che prima o poi divergerebbe. La
    dashboard passa esplicitamente ?giorni=0 per avere la coda intera.

    Le fatture sono divise per motivo, perché non si risolvono nello stesso
    modo: "attende_ddt" si sblocca da sola quando il documento viene scansionato,
    "da_confermare" no — il DDT probabilmente c'è già ma con un numero letto
    male, e finché nessuno lo corregge il ricontrollo darà sempre lo stesso
    risultato.
    """
    soglia = giorni_attesa_fattura() if giorni is None else giorni
    voci = fatture_in_attesa(soglia)

    # Terza lista, e aspetta una cosa diversa dalle altre due: qui il documento
    # c'è (o non è ancora stato nemmeno cercato), manca un click in dashboard.
    # Ha una soglia sua, più corta, perché una pratica pronta non deve restare
    # ferma quanto una bolla che qualcuno deve andare a cercare in magazzino.
    soglia_accoppiamento = giorni_accoppiamento() if giorni is None else giorni
    da_accoppiare = fatture_da_accoppiare(soglia_accoppiamento)

    return {
        "soglia_giorni": soglia,
        "soglia_predefinita": giorni_attesa_fattura(),
        "soglia_accoppiamento": soglia_accoppiamento,
        "totale": len(voci),
        "da_confermare": [v for v in voci if v.get("attesa", {}).get("da_confermare")],
        "attende_ddt": [v for v in voci if not v.get("attesa", {}).get("da_confermare")],
        "fatture": voci,
        "da_accoppiare": da_accoppiare,
        "totale_da_accoppiare": len(da_accoppiare),
    }

@router.get("/api/ddt/senza-fattura")
async def get_ddt_senza_fattura(
    giorni: int = Query(None, ge=0, description="Solo i DDT fermi da almeno N giorni (default: la soglia configurata)")
):
    """I DDT archiviati che nessuna fattura ha ancora agganciato.

    È il lato speculare di /api/fatture/attese: là le fatture a cui manca una
    bolla, qui le bolle a cui manca una fattura. Serve allo stesso sollecito
    mensile — con la differenza che da questo lato non c'è niente da
    ricontrollare: ogni fattura nuova viene confrontata con tutti i DDT
    archiviati, quindi un DDT che aspetta si aggancia da solo quando l'XML
    arriva. Se dopo settimane non è successo, la fattura non è mai stata
    caricata — oppure è in coda e nessuno ne ha ancora chiesto l'abbinamento.

    Ha una soglia SUA (GIORNI_ATTESA_DDT), diversa da quella delle fatture:
    quanto si aspetta una bolla dipende da chi la deve portare, quanto si
    aspetta una fattura dipende da come fattura quel fornitore.
    """
    soglia = giorni_attesa_ddt() if giorni is None else giorni
    voci = ddt_senza_fattura(soglia)

    return {
        "soglia_giorni": soglia,
        "soglia_predefinita": giorni_attesa_ddt(),
        "totale": len(voci),
        "ddt": voci,
    }

@router.post("/api/fatture/ricontrolla")
def ricontrolla_fatture():
    """Riprova a mano l'abbinamento di tutte le fatture in coda.

    Normalmente non serve: il ricontrollo scatta da solo dopo ogni evento sui
    DDT (estrazione, inserimento manuale, unione, rianalisi, correzione dei
    dati). Resta utile dopo aver modificato l'anagrafica fornitori, che cambia
    il riconoscimento del fornitore e quindi gli abbinamenti possibili.
    """
    report = ricontrolla_fatture_in_attesa("richiesta manuale")
    return {"message": "Ricontrollo completato", **report}

@router.post("/api/fatture/abbina-tutte")
def abbina_tutte_le_fatture():
    """Cerca i D.D.T. di tutte le fatture in coda, comprese quelle mai abbinate.

    È il pulsante globale: /api/fatture/ricontrolla riguarda solo le pratiche
    che un abbinamento ce l'hanno già (e che possono essersi sbloccate da sole),
    questo prende anche le DA_ABBINARE, cioè quelle appena archiviate su cui
    nessuno ha ancora chiesto niente. Nessuna pratica si chiude: restano tutte
    in coda in attesa della firma sul singolo accoppiamento.
    """
    try:
        report = abbina_tutte()
    except Exception as e:
        print(f"❌ Abbinamento di tutta la coda fallito: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    print(f"🔗 Abbina tutte: {report['in_coda']} pratiche esaminate, "
          f"{len(report['sbloccate'])} pronte da accoppiare.")
    return {"message": "Abbinamento completato", **report}


@router.post("/api/fatture/{id_fattura}/accoppia")
def accoppia_fattura(id_fattura: str):
    """Primo tempo del pulsante ACCOPPIA: cerca i DDT di QUESTA fattura.

    Rifa' il confronto fra i riferimenti della fattura e tutti i DDT archiviati
    e restituisce la voce aggiornata, che l'interfaccia mostra nel modale.
    Non produce nessun file e non annota nessun DDT: e' una proposta, e a
    firmarla e' /conferma con l'operatore che ha appena visto cosa e' stato
    agganciato.

    Sincrona: rilegge i tre registri DDT da disco.
    """
    voce, errore = proponi_accoppiamento(id_fattura)

    if errore == "non trovata":
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if errore == "gia confermata":
        # Non e' un errore da mostrare come rosso: la pratica e' semplicemente
        # gia' chiusa, e l'interfaccia mostrera' il file unico.
        return {"message": "Accoppiamento gia' confermato", "confermata": True, "fattura": voce}

    riepilogo = voce.get("attesa") or {}
    return {
        "message": "Abbinamento ricalcolato",
        "confermata": False,
        "pronta": voce.get("stato") == ABBINATA,
        "abbinati": len([r for r in voce.get("ddt", []) if r.get("documento_id")]),
        "attesa": riepilogo,
        "fattura": {**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)},
    }

@router.post("/api/fatture/{id_fattura}/conferma-accoppiamento")
def conferma_accoppiamento_fattura(id_fattura: str):
    """Secondo tempo: l'operatore firma e nasce il file unico in ACCOPPIATE.

    E' l'unico modo in cui una pratica si chiude. Da qui i DDT ricevono
    l'annotazione della loro fattura e la voce passa in FATTURE.json.
    """
    voce, errore = conferma_accoppiamento(id_fattura)

    if errore == "non trovata":
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if errore == "gia confermata":
        raise HTTPException(status_code=409, detail="Questa fattura e' gia' stata accoppiata")

    return {
        "message": "Accoppiamento confermato",
        "fascicolo": voce.get("fascicolo", ""),
        "ddt": len(voce.get("ddt", [])),
        "fattura": {**voce, "in_coda": False},
    }

@router.get("/api/fatture/{id_fattura}")
async def get_fattura(id_fattura: str):
    registro, voce = trova_fattura(id_fattura)
    if not voce:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    if registro == REGISTRO_ATTESA:
        return {**voce, "in_coda": True, "giorni_attesa": giorni_in_attesa(voce)}
    return {**voce, "in_coda": False}

@router.get("/api/pdf-fattura/{id_fattura}.pdf")
def get_pdf_fattura(id_fattura: str):
    """Serve il fascicolo PDF (fattura + DDT).

    Per le pratiche confermate è il file unico archiviato in ACCOPPIATE. Per una
    fattura ancora in coda quel file NON esiste — sarebbe già vecchio al
    prossimo DDT, e soprattutto nessuno l'ha ancora firmato — quindi viene
    costruito qui su richiesta in un file temporaneo, cancellato subito
    dopo l'invio. L'header X-Fascicolo-Anteprima distingue i due casi, così
    l'interfaccia può dire che quello che si sta guardando è provvisorio.

    Sincrona: costruire il fascicolo è lavoro bloccante (PyMuPDF).
    """
    registro, voce = trova_fattura(id_fattura)
    if not voce:
        raise HTTPException(status_code=404, detail=f"Fascicolo non trovato per ID: {id_fattura}")

    # Il file confermato non si chiama piu' come l'id (in ACCOPPIATE i nomi sono
    # leggibili da una persona): il percorso lo sa la voce, non questa route.
    percorso = percorso_fascicolo(voce)
    if percorso:
        return FileResponse(
            path=percorso,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache, no-store, must-revalidate"
            }
        )

    try:
        percorso_temporaneo = anteprima_fascicolo(voce)
    except Exception as e:
        print(f"❌ Anteprima del fascicolo {id_fattura} non costruibile: {e}")
        raise HTTPException(status_code=500, detail=f"Impossibile costruire l'anteprima: {e}")

    return FileResponse(
        path=percorso_temporaneo,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Fascicolo-Anteprima": "1",
        },
        background=BackgroundTask(shutil.rmtree, os.path.dirname(percorso_temporaneo), True),
    )

@router.delete("/api/fatture/{id_fattura}")
async def delete_fattura(id_fattura: str):
    """Elimina una fattura (chiusa o in coda), col file unico e l'XML archiviato.

    I DDT restano dove sono — un DDT non smette di esistere perché la sua
    fattura è stata cancellata — ma PERDONO l'annotazione: cancellare la pratica
    è il modo in cui si disfa un accoppiamento sbagliato, e `ddt_senza_fattura()`
    riconosce le bolle libere proprio dall'assenza di quel campo. Lasciarlo
    terrebbe quei DDT agganciati a una fattura che non c'è più, quindi fuori dal
    sollecito per sempre."""
    for nome_registro in (REGISTRO_ATTESA, REGISTRO_FATTURE):
        registro = leggi_registro(nome_registro)

        for i, voce in enumerate(registro):
            if voce.get("id") != id_fattura:
                continue

            rimuovi_dal_registro(nome_registro, i)

            # L'XML originale e (per le pratiche vecchie) il fascicolo stanno
            # in FATTURE/lette col nome dell'id; il file unico confermato sta in
            # ACCOPPIATE con un nome leggibile, che solo la voce conosce.
            for nome in os.listdir(CARTELLA_FATTURE) if os.path.isdir(CARTELLA_FATTURE) else []:
                if nome.startswith(id_fattura):
                    os.remove(os.path.join(CARTELLA_FATTURE, nome))

            unico = voce.get("fascicolo")
            if unico:
                percorso_unico = os.path.join(CARTELLA_ACCOPPIATE, unico)
                if os.path.exists(percorso_unico):
                    os.remove(percorso_unico)

            liberati = dimentica_fattura(id_fattura)

            return {
                "message": "Fattura eliminata con successo",
                "ddt_liberati": liberati,
            }

    raise HTTPException(status_code=404, detail="Fattura non trovata")
