"""
Abbinamento fattura -> DDT gia' archiviati.

Il lato fattura e' esatto (viene da un XML strutturato), il lato DDT no: e'
quello che ha letto il modello da una scansione. Il confronto va quindi
sempre pensato in questa direzione, e un mancato abbinamento e' spesso il
sintomo di una cifra letta male sul DDT, non di un DDT assente.

Le soglie di somiglianza sul FORNITORE non vengono reinventate qui: si usa
stesso_fornitore() di memory_manager, gia' tarata sulle voci reali.
"""

from difflib import SequenceMatcher

from src.comune.memory_manager import stesso_fornitore
from src.comune.normalizzatore import normalizza_numero_ddt
from src.comune.registro import leggi_registro, salva_registro

# Somiglianza minima tra numero DDT della fattura e numero letto sul documento
# per proporre un abbinamento "probabile". A 0.7 "81197691" e "81197B91"
# (una cifra sbagliata su otto) passano, due DDT diversi no.
SOGLIA_NUMERO_SIMILE = 0.7

STATI_DDT = ["OK", "CHECK", "KO"]

# Esiti possibili per un singolo riferimento DDT della fattura.
ABBINATO = "abbinato"        # numero identico + fornitore compatibile: certo
PROBABILE = "probabile"      # somiglianza forte ma non certezza: la conferma la da' una persona
NON_TROVATO = "non_trovato"
DA_ABBINARE_RIGA = "da_abbinare"  # il confronto non e' ancora stato chiesto

# Stato della PRATICA fattura. IN_ATTESA non e' un esito: e' una coda.
# Una fattura i cui DDT non sono ancora tutti arrivati non ha finito il suo
# percorso, e viene rimessa in discussione a ogni nuovo DDT archiviato
# (src/fatture/coda.py). NON_ABBINATA invece e' definitivo per costruzione:
# senza <DatiDDT> non c'e' nessun documento da aspettare.
ABBINATA = "ABBINATA"
IN_ATTESA = "IN_ATTESA"
NON_ABBINATA = "NON_ABBINATA"

# Stato di partenza dal 2026-09-08: la lettura dell'XML e il confronto con i DDT
# sono due gesti separati. Caricare una fattura la registra e basta; il
# confronto lo chiede l'operatore, sulla singola o su tutta la coda. Una voce
# DA_ABBINARE non e' mai stata confrontata con niente, ed e' la ragione per cui
# ricontrolla_attese() la salta: ricalcolarla di nascosto, all'arrivo di un DDT,
# vorrebbe dire fare proprio l'abbinamento che non e' stato chiesto.
DA_ABBINARE = "DA_ABBINARE"

# Le due forme in cui una fattura si lega alla merce. Non e' una sfumatura
# formale: cambia COSA si cerca tra i DDT archiviati.
#   DIFFERITA        i DDT sono elencati in <DatiDDT>, rapporto 1 -> N.
#   ACCOMPAGNATORIA  la merce viaggia con la fattura, che vale da documento di
#                    trasporto: non c'e' nessun <DatiDDT> da leggere perche' il
#                    DDT *e'* la fattura. Il numero da cercare sul documento
#                    scansionato e' quello della fattura, rapporto 1 -> 1.
#   SENZA_DDT        nessun riferimento e nessun trasporto (servizi, note di
#                    credito): non c'e' merce da agganciare.
DIFFERITA = "differita"
ACCOMPAGNATORIA = "accompagnatoria"
SENZA_DDT = "senza_ddt"


def classifica_fattura(fattura):
    """differita / accompagnatoria / senza_ddt, letto dalla struttura dell'XML.

    L'ordine dei controlli e' quello della certezza: <DatiDDT> e' una
    dichiarazione esplicita dei documenti collegati e vince su tutto. In sua
    assenza il segnale e' <DatiTrasporto>, che dice che la merce ha viaggiato
    con questa fattura.

    Il TipoDocumento NON viene usato per decidere: TD01 e' allo stesso tempo il
    codice della accompagnatoria e quello della fattura di consulenza, e TD24
    compare anche su differite a cui il fornitore ha dimenticato i <DatiDDT>.
    Preferiamo un segnale che descrive il documento a uno che lo etichetta.
    """
    if fattura.get("ddt"):
        return DIFFERITA
    if fattura.get("trasporto"):
        return ACCOMPAGNATORIA
    return SENZA_DDT


def riferimenti_fattura(fattura, tipo=None):
    """I numeri da cercare tra i DDT archiviati.

    Per la differita sono i <DatiDDT>. Per la accompagnatoria e' UNO solo,
    costruito dal numero della fattura: il documento che il magazzino scansiona
    e' la fattura stessa, e il modello ne legge il numero come numero_ddt. Passa
    dalla stessa normalizza_numero_ddt del lato DDT, altrimenti "0047" e "47"
    non si incontrerebbero mai.

    Il primo ramo copre anche il ricontrollo dalla coda, dove i riferimenti sono
    gia' stati costruiti alla prima passata e non vanno ricalcolati.
    """
    if fattura.get("ddt"):
        return list(fattura["ddt"])

    if (tipo or classifica_fattura(fattura)) == DIFFERITA:
        return []

    numero = fattura.get("numero_fattura", "")
    if not numero:
        return []

    return [{
        "numero_ddt": normalizza_numero_ddt(numero),
        "data_ddt": fattura.get("data_fattura", ""),
        "numero_ddt_xml": numero,
        "origine": "numero_fattura",
    }]


def righe_da_abbinare(fattura, tipo=None):
    """I riferimenti della fattura come righe di esito, prima del confronto.

    Servono a registrare una fattura senza abbinarla: i numeri citati vanno
    conservati comunque (il modale li mostra, e riferimenti_da_voce() li rilegge
    di li' quando l'operatore preme Abbina), ma nessuno di essi e' ancora stato
    cercato tra i DDT. Un esito esplicito "da_abbinare" e' meglio di una lista
    vuota: dice che il confronto manca, invece di far sembrare che sia stato
    fatto e non abbia trovato nulla.
    """
    return [
        {
            **{campo: riferimento.get(campo, "") for campo in
               ("numero_ddt", "data_ddt", "numero_ddt_xml", "origine")},
            "esito": DA_ABBINARE_RIGA,
            "motivo": "abbinamento non ancora eseguito",
            "documento_id": None,
        }
        for riferimento in riferimenti_fattura(fattura, tipo)
    ]


def carica_documenti():
    """Tutti i DDT archiviati, con lo stato di provenienza attaccato a ogni voce."""
    documenti = []

    for stato in STATI_DDT:
        for indice, documento in enumerate(leggi_registro(stato)):
            documenti.append({
                "stato": stato,
                "indice": indice,
                "documento": documento,
            })

    return documenti


def somiglianza_numero(numero_a, numero_b):
    if not numero_a or not numero_b:
        return 0.0
    return SequenceMatcher(None, str(numero_a).upper(), str(numero_b).upper()).ratio()


def _candidato(voce, esito, motivo):
    documento = voce["documento"]
    dati = documento.get("dati", {})

    return {
        "esito": esito,
        "motivo": motivo,
        "documento_id": documento.get("id"),
        "stato_ddt": voce["stato"],
        "numero_ddt_letto": dati.get("numero_ddt", ""),
        "data_ddt_letta": dati.get("data_ddt", ""),
        "fornitore_letto": dati.get("fornitore", ""),
        # Un DDT gia' agganciato a un'altra fattura non e' un errore (puo'
        # essere una nota di credito), ma chi rivede deve saperlo.
        "gia_abbinato": documento.get("fattura", {}).get("numero_fattura", ""),
    }


def cerca_ddt(riferimento, fornitore_fattura, documenti):
    """
    Cerca tra i DDT archiviati quello citato dalla fattura.

    Restituisce sempre un dizionario di esito, anche quando non trova nulla:
    il riferimento resta comunque tracciato nel registro fatture.
    """
    numero_atteso = riferimento.get("numero_ddt", "")
    data_attesa = riferimento.get("data_ddt", "")

    certi = []
    probabili = []

    for voce in documenti:
        dati = voce["documento"].get("dati", {})
        numero_letto = dati.get("numero_ddt", "")
        fornitore_letto = dati.get("fornitore", "")

        if not numero_letto:
            continue

        stesso_numero = numero_letto == numero_atteso
        fornitore_compatibile = stesso_fornitore(fornitore_fattura, fornitore_letto)
        stessa_data = bool(data_attesa) and dati.get("data_ddt", "") == data_attesa

        if stesso_numero and fornitore_compatibile:
            certi.append(_candidato(voce, ABBINATO, "numero DDT e fornitore corrispondenti"))
        elif stesso_numero:
            # Stesso numero ma fornitore diverso: numeri come "123" si ripetono
            # tra fornitori, quindi non basta.
            probabili.append(_candidato(
                voce, PROBABILE,
                f"numero DDT corrispondente ma fornitore diverso ({fornitore_letto or 'non letto'})"
            ))
        elif fornitore_compatibile and stessa_data:
            similarita = somiglianza_numero(numero_atteso, numero_letto)
            if similarita >= SOGLIA_NUMERO_SIMILE:
                probabili.append(_candidato(
                    voce, PROBABILE,
                    f"fornitore e data coincidono, numero letto '{numero_letto}' invece di '{numero_atteso}'"
                ))

    # Piu' DDT certi per lo stesso riferimento: la data scioglie quasi sempre
    # il dubbio, ma se non basta si degrada a "probabile" invece di scegliere a
    # caso. Sbagliare l'aggancio in silenzio e' peggio che chiedere.
    if certi:
        if len(certi) == 1:
            return certi[0]

        con_data = [c for c in certi if c["data_ddt_letta"] == data_attesa]
        if len(con_data) == 1:
            return con_data[0]

        ambiguo = dict(certi[0])
        ambiguo["esito"] = PROBABILE
        ambiguo["motivo"] = f"{len(certi)} DDT archiviati con lo stesso numero e fornitore: da scegliere a mano"
        ambiguo["ambiguo"] = True
        return ambiguo

    if probabili:
        return probabili[0]

    return {
        "esito": NON_TROVATO,
        "motivo": "nessun DDT archiviato con questo numero",
        "documento_id": "",
        "stato_ddt": "",
        "numero_ddt_letto": "",
        "data_ddt_letta": "",
        "fornitore_letto": "",
        "gia_abbinato": "",
    }


def determina_stato_fattura(righe, tipo=DIFFERITA):
    """
    ABBINATA / IN_ATTESA / NON_ABBINATA, con la stessa filosofia di OK/CHECK/KO:
    va in ABBINATA solo cio' che e' certo, tutto il resto resta in coda.

    Il vecchio PARZIALE era un vicolo cieco — calcolato una volta e mai piu'
    riguardato — mentre quasi sempre significa solo che il DDT non e' ancora
    stato scansionato. Adesso quel caso e' IN_ATTESA e viene ricontrollato a
    ogni nuovo documento.

    Il tipo decide chi ha diritto di aspettare. Differita e accompagnatoria
    citano (o sono) un documento di trasporto che prima o poi verra' scansionato,
    quindi vanno in coda. Una fattura senza riferimenti e senza trasporto no: il
    tentativo sul numero e' gratis e se trova qualcosa tanto meglio, ma se non
    trova nulla non c'e' nessuna bolla da attendere e metterla in coda vorrebbe
    dire solleticare per sempre un magazziniere che non ha niente da cercare.
    """
    if not righe:
        return NON_ABBINATA

    if all(riga["esito"] == ABBINATO for riga in righe):
        return ABBINATA

    if tipo == SENZA_DDT:
        return NON_ABBINATA

    return IN_ATTESA


def riepilogo_attesa(righe):
    """Perche' la fattura e' in coda, distinguendo i due motivi.

    Non sono la stessa cosa e non si risolvono nello stesso modo:
      - "mancanti": il DDT non e' ancora stato scansionato. Si sblocca da solo
        quando arriva, senza che nessuno faccia niente.
      - "da_confermare": il DDT probabilmente c'e' gia', ma il match non e'
        certo (di solito una cifra letta male dal modello). Ricontrollarlo
        all'infinito dara' sempre lo stesso risultato: aspetta una persona.
    Tenerli separati e' cio' che rende utile la mail di sollecito, che
    altrimenti direbbe solo "queste 12 fatture sono ferme".
    """
    mancanti = [r for r in righe if r["esito"] == NON_TROVATO]
    da_confermare = [r for r in righe if r["esito"] == PROBABILE]

    return {
        "mancanti": len(mancanti),
        "da_confermare": len(da_confermare),
        "abbinati": sum(1 for r in righe if r["esito"] == ABBINATO),
        "numeri_mancanti": [r.get("numero_ddt", "") for r in mancanti],
        "numeri_da_confermare": [r.get("numero_ddt", "") for r in da_confermare],
    }


def abbina_fattura(fattura, documenti=None, tipo=None):
    """
    Confronta i riferimenti DDT di una fattura con i documenti archiviati.

    Restituisce (stato, righe, tipo): una riga per riferimento, nell'ordine in
    cui compare nell'XML — e' anche l'ordine in cui i PDF finiranno nel
    fascicolo. Il tipo viene restituito perche' va conservato nel registro: al
    ricontrollo la voce in coda porta gia' i riferimenti costruiti, e da soli
    non direbbero piu' se venivano da <DatiDDT> o dal numero della fattura.

    'tipo' si passa solo quando e' gia' noto (appunto il ricontrollo dalla coda).
    """
    if documenti is None:
        documenti = carica_documenti()

    tipo = tipo or classifica_fattura(fattura)

    righe = []
    for riferimento in riferimenti_fattura(fattura, tipo):
        esito = cerca_ddt(riferimento, fattura.get("fornitore", ""), documenti)
        righe.append({
            "numero_ddt": riferimento.get("numero_ddt", ""),
            "data_ddt": riferimento.get("data_ddt", ""),
            "numero_ddt_xml": riferimento.get("numero_ddt_xml", ""),
            "origine": riferimento.get("origine", "dati_ddt"),
            **esito,
        })

    stato = determina_stato_fattura(righe, tipo)

    # Il tentativo sul numero fattura di una SENZA_DDT che non ha trovato nulla
    # non va tenuto: registrarlo come "DDT mancante" inventerebbe un documento
    # che la fattura non ha mai citato.
    if stato == NON_ABBINATA and tipo == SENZA_DDT:
        righe = []

    return stato, righe, tipo


def annota_ddt_abbinati(righe, riferimento_fattura):
    """
    Scrive sui DDT coinvolti il riferimento alla fattura che li ha agganciati.

    E' un'annotazione e basta: il documento NON cambia stato e NON si sposta di
    registro. Un DDT resta un DDT anche dopo essere finito in un fascicolo, e
    chi rivede la dashboard deve continuare a trovarlo dov'era.
    """
    da_annotare = {}
    for riga in righe:
        if riga["esito"] == NON_TROVATO or not riga.get("documento_id"):
            continue
        da_annotare.setdefault(riga["stato_ddt"], set()).add(riga["documento_id"])

    annotati = 0
    for stato, ids in da_annotare.items():
        registro = leggi_registro(stato)
        modificato = False

        for documento in registro:
            if documento.get("id") in ids:
                documento["fattura"] = dict(riferimento_fattura)
                modificato = True
                annotati += 1

        if modificato:
            salva_registro(stato, registro)

    return annotati


def dimentica_fattura(id_fattura):
    """Toglie dai DDT l'annotazione di una fattura che non esiste piu'.

    Serve alla cancellazione di una pratica, che e' il modo in cui si disfa un
    accoppiamento sbagliato. L'annotazione non e' decorativa: ddt_senza_fattura()
    riconosce le bolle libere proprio dalla sua assenza, quindi lasciarla dopo
    aver cancellato la fattura toglierebbe quei DDT dal sollecito per sempre —
    resterebbero agganciati a una pratica che non c'e' piu'.
    """
    dimenticati = 0
    for stato in STATI_DDT:
        registro = leggi_registro(stato)
        modificato = False

        for documento in registro:
            riferimento = documento.get("fattura")
            if isinstance(riferimento, dict) and riferimento.get("id_fattura") == id_fattura:
                documento.pop("fattura", None)
                modificato = True
                dimenticati += 1

        if modificato:
            salva_registro(stato, registro)

    return dimenticati
