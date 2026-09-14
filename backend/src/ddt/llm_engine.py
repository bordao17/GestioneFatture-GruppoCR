import json
import os
import re

import ollama

from src.comune.memory_manager import (
    ottieni_regole_formattate,
    applica_nome_canonico,
    filtra_fornitore_vietato,
    filtra_indirizzo_vietato,
    motivo_scarto_piva,
    regole_campo_per,
    carica_memoria,
    partita_iva_per,
    normalizza_piva,
    voce_fornitore_estero,
    annota_fornitore_critico,
)
from src.comune.configurazione import valore
from src.comune.normalizzatore import normalizza_dati, normalizza_partita_iva, partita_iva_valida

# Modello, finestra di contesto e host stanno in configurazione.py insieme a
# PDF_RENDER_ZOOM: sono le leve che si provano INSIEME quando si cambia modello,
# e vanno lette a ogni chiamata, non congelate in una costante all'import —
# altrimenti cambiarle dalla dashboard richiederebbe di nuovo un riavvio, cioe'
# esattamente cio' che quella sezione toglie di mezzo.


def _client():
    """Il client Ollama verso l'host configurato adesso.

    La libreria `ollama` legge OLLAMA_HOST dall'ambiente al momento
    dell'import del suo client globale: passando l'host esplicitamente il
    valore scritto dalla dashboard vale subito, senza riavviare il container.
    """
    return ollama.Client(host=valore("OLLAMA_HOST"))


def _opzioni():
    return {'num_ctx': valore("MODELLO_NUM_CTX"), 'temperature': 0.0}


# Quanto si aspetta il motore quando gli si chiede solo se c'e'. Corto di
# proposito, per la stessa ragione del connect_timeout del database: questo
# controllo sta sulla STRADA di una scansione, e un host spento deve dirlo
# subito invece di tenerla ferma. L'estrazione vera non ha timeout e non deve
# averne uno: sulla GPU condivisa una pagina puo' legittimamente aspettare il
# suo turno dietro a qualcun altro.
TIMEOUT_VERIFICA = 5


def _nomi_modelli(elenco):
    """I nomi dei modelli installati, da qualunque forma li dia la libreria.

    ollama >= 0.4 risponde con un oggetto pydantic (.models, campo .model), le
    versioni precedenti con un dizionario e la chiave 'name'. requirements.txt
    ammette entrambe (ollama>=0.2.0), quindi qui si reggono entrambe: questo
    controllo esiste per dire cosa non va, e sarebbe una beffa se fosse lui a
    rompersi su un aggiornamento della libreria.
    """
    modelli = getattr(elenco, "models", None)
    if modelli is None and isinstance(elenco, dict):
        modelli = elenco.get("models", [])

    nomi = []
    for modello in modelli or []:
        if isinstance(modello, dict):
            nome = modello.get("model") or modello.get("name")
        else:
            nome = getattr(modello, "model", None) or getattr(modello, "name", None)
        if nome:
            nomi.append(str(nome))
    return nomi


def _stesso_modello(configurato, installato):
    """Confronta due nomi di modello tenendo conto del tag implicito.

    "qwen2.5vl" e "qwen2.5vl:latest" sono lo stesso modello: Ollama completa il
    tag da solo quando manca, e un confronto letterale direbbe "non installato"
    di un modello che c'e'.
    """
    conf = configurato.strip()
    inst = installato.strip()
    if ":" not in conf:
        conf += ":latest"
    if ":" not in inst:
        inst += ":latest"
    return conf.casefold() == inst.casefold()


def verifica_motore():
    """Se il motore AI e' pronto ad analizzare, e se no perche'.

    Chiede l'elenco dei modelli installati: costa millisecondi, non occupa la
    GPU e risponde in un colpo solo alle due domande che fanno fallire
    un'estrazione prima ancora che cominci — l'host risponde? e ha il modello
    che stiamo per chiedergli?

    Il modello mancante e' il piu' insidioso dei due casi: Ollama risponde,
    quindi da fuori sembra tutto a posto, e l'errore arriva alla prima pagina.

    **Non solleva mai e non restituisce mai None**: e' un controllo, e un
    controllo che esplode non si distingue da un motore rotto. Chi deve
    fermarsi legge "pronto"; il "motivo" e' gia' scritto per essere mostrato a
    una persona, perche' e' l'unica cosa che quella persona potra' leggere.
    """
    host = str(valore("OLLAMA_HOST") or "").strip()
    modello = str(valore("MODELLO_VISION") or "").strip()
    esito = {
        "pronto": False,
        "host": host,
        "modello": modello,
        "motivo": "",
        "modelli_disponibili": [],
    }

    if not host:
        esito["motivo"] = ("OLLAMA_HOST non e' configurato: non c'e' nessun motore AI "
                           "a cui mandare le pagine.")
        return esito

    try:
        installati = _nomi_modelli(ollama.Client(host=host, timeout=TIMEOUT_VERIFICA).list())
    except Exception as e:
        esito["motivo"] = (f"Ollama non risponde su {host} ({type(e).__name__}). "
                           f"Controlla che la macchina sia accesa e che il servizio sia avviato.")
        return esito

    esito["modelli_disponibili"] = installati

    if not modello:
        esito["motivo"] = "MODELLO_VISION non e' configurato: non si sa quale modello usare."
        return esito

    if not any(_stesso_modello(modello, nome) for nome in installati):
        esito["motivo"] = (f"Ollama risponde su {host} ma il modello '{modello}' non e' installato "
                           f"(scaricalo con 'ollama pull {modello}'). "
                           f"Presenti: {', '.join(installati) if installati else 'nessuno'}.")
        return esito

    esito["pronto"] = True
    return esito

# Campi che si leggono INSIEME perche' stanno nello stesso riquadro del
# documento: chiedere separatamente il nome del punto vendita e il suo indirizzo
# sarebbe una domanda in piu' per guardare due volte lo stesso posto.
GRUPPO_CAMPI = {
    "fornitore": ("fornitore",),
    "partita_iva": ("partita_iva",),
    "numero_ddt": ("numero_ddt",),
    "data_ddt": ("data_ddt",),
    "ragione_sociale_consegna": ("ragione_sociale_consegna", "indirizzo_consegna"),
    "indirizzo_consegna": ("ragione_sociale_consegna", "indirizzo_consegna"),
}

# Cosa scrivere accanto a ogni campo nella domanda mirata. Sono descrizioni
# brevissime di proposito: la domanda funziona perche' e' stretta, allungarla
# la riporterebbe verso il prompt di estrazione, che su questi casi sbaglia.
DESCRIZIONE_CAMPO = {
    "fornitore": "la ragione sociale completa dell'azienda emittente",
    "partita_iva": "le 11 cifre della partita IVA, senza il prefisso IT",
    "numero_ddt": "il codice del documento, senza la data e senza l'etichetta che lo precede",
    "data_ddt": "la data del documento",
    "ragione_sociale_consegna": "il nome dell'azienda",
    "indirizzo_consegna": "via, numero civico, CAP, citta e provincia",
}


def _estrai_json(testo):
    """Ritaglia l'oggetto JSON da una risposta che puo' contenere anche prosa.

    I modelli lo incorniciano in ```json, lo fanno precedere da una frase, o
    (i modelli "thinking") lo scrivono in mezzo al ragionamento. Cercare la
    prima graffa aperta e l'ultima chiusa regge tutti e tre i casi, mentre il
    vecchio taglio a indici fissi reggeva solo il primo.
    """
    if not testo:
        return None
    inizio = testo.find("{")
    fine = testo.rfind("}")
    if inizio == -1 or fine <= inizio:
        return None
    try:
        return json.loads(testo[inizio:fine + 1])
    except json.JSONDecodeError:
        return None

def _chiedi_sotto_etichetta(image_path, etichetta, campi):
    """Una domanda sola al modello: "sotto questa dicitura, cosa c'e' scritto?".

    Restituisce il dizionario dei soli campi richiesti, oppure None se il
    modello non ha risposto con un JSON leggibile. Costa circa 1 secondo,
    contro i 5-9 dell'estrazione completa: l'immagine e' la stessa ma la
    risposta e' di pochi token.
    """
    elenco = ", ".join(f'"{c}": ""' for c in campi)
    dettagli = " ".join(f"{c} = {DESCRIZIONE_CAMPO[c]}." for c in campi)

    domanda = (
        f'Nel documento individua la dicitura "{etichetta}". '
        f"Restituisci SOLO un JSON con il testo che si trova sotto o accanto a quella dicitura:\n"
        f"{{{elenco}}}\n{dettagli}"
    )

    try:
        response = _client().chat(
            model=valore("MODELLO_VISION"),
            messages=[{'role': 'user', 'content': domanda, 'images': [image_path]}],
            options=_opzioni(),
            keep_alive='30m'
        )
    except Exception as e:
        print(f"⚠️ Domanda mirata su '{etichetta}' fallita: {e}")
        return None

    messaggio = response['message']
    risposta = _estrai_json(messaggio.get('content') or '') or \
        _estrai_json(messaggio.get('thinking') or '')

    if not isinstance(risposta, dict):
        return None

    # normalizza_dati riempie tutte le chiavi che conosce: si ricopiano solo
    # quelle effettivamente chieste, per non azzerare il resto dell'estrazione.
    normalizzata = normalizza_dati({c: risposta.get(c, "") for c in campi})
    return {c: normalizzata.get(c, "") for c in campi}


def applica_regole_campo(dati, image_path):
    """Seconda passata mirata: per ogni regola "campo X sotto etichetta Y" del
    fornitore riconosciuto, fa una domanda secca e sovrascrive quel campo.

    Perche' una seconda chiamata invece di scrivere la regola nel prompt: le
    stesse regole, iniettate nel prompt di estrazione, vengono ignorate (0 su 6
    documenti corretti su SA.BA FISH, VITAKRAFT, CEREALDOLCI e NUOVO SRL);
    poste come domanda singola danno 16 risposte corrette su 16. Il modello
    vede il dato, semplicemente non applica una condizione mentre gli si
    chiedono sei campi insieme.

    Si sovrascrive solo con un valore NON vuoto: la regola esiste perche' la
    prima passata su quel campo sbaglia, ma se la domanda mirata non trova
    niente il dato grezzo vale comunque piu' del vuoto (stesso principio del
    normalizzatore).
    """
    if not isinstance(dati, dict):
        return dati

    fornitore = dati.get("fornitore")
    if not fornitore:
        return dati

    regole = regole_campo_per(fornitore)
    if not regole:
        return dati

    # Due regole possono ricadere sullo stesso gruppo (ragione sociale e
    # indirizzo sotto la stessa dicitura): la domanda si fa una volta sola.
    gia_chiesti = set()

    for regola in regole:
        campi = GRUPPO_CAMPI.get(regola["campo"])
        if not campi:
            continue

        firma = (regola["etichetta"].casefold(), campi)
        if firma in gia_chiesti:
            continue
        gia_chiesti.add(firma)

        risposta = _chiedi_sotto_etichetta(image_path, regola["etichetta"], campi)
        if not risposta:
            print(f"⚠️ [{fornitore}] nessuna risposta alla domanda mirata "
                  f"su '{regola['etichetta']}': resto sui dati della prima passata.")
            continue

        for campo in campi:
            valore = risposta.get(campo, "")
            if not valore or valore == dati.get(campo):
                continue
            print(f"🎯 [{fornitore}] {campo}: '{dati.get(campo)}' → '{valore}' "
                  f"(regola: sotto '{regola['etichetta']}').")
            dati[campo] = valore

    return dati


def _chiedi_partita_iva(image_path):
    """Chiede al modello la sola partita IVA di chi emette il documento.

    E' una domanda mirata come quelle di applica_regole_campo, per la stessa
    ragione misurata: un campo in piu' nel prompt di estrazione viene letto
    male o preso da un'altra sezione (sul DDT ci sono anche la P.IVA del
    destinatario e il codice fiscale), mentre una domanda sola costa ~1s e
    guarda in un posto solo. Qui in piu' il campo e' verificabile: se le 11
    cifre non superano il carattere di controllo, la lettura si scarta.
    """
    domanda = (
        "Nel documento individua l'intestazione dell'azienda che EMETTE il documento "
        "(in alto, insieme al logo) e leggi la sua partita IVA. "
        "Non prendere la partita IVA del destinatario o del vettore. "
        'Rispondi SOLO con un JSON: {"partita_iva": ""} '
        "con le 11 cifre, senza il prefisso IT e senza altri caratteri."
    )

    try:
        response = _client().chat(
            model=valore("MODELLO_VISION"),
            messages=[{'role': 'user', 'content': domanda, 'images': [image_path]}],
            options=_opzioni(),
            keep_alive='30m'
        )
    except Exception as e:
        print(f"⚠️ Domanda mirata sulla partita IVA fallita: {e}")
        return ""

    messaggio = response['message']
    risposta = _estrai_json(messaggio.get('content') or '') or \
        _estrai_json(messaggio.get('thinking') or '')

    if not isinstance(risposta, dict):
        return ""

    return normalizza_partita_iva(risposta.get("partita_iva"))


def completa_partita_iva(dati, image_path):
    """Attacca al documento la partita IVA del fornitore.

    E' il campo che fa da CHIAVE tra i due flussi, quindi la fonte conta piu'
    del valore:
      - fornitore gia' in anagrafica con una P.IVA -> vince quella, sempre. Il
        modello non viene nemmeno interpellato: e' il caso di gran lunga piu'
        frequente, ed e' cio' che rende questa lettura un costo che si paga una
        volta per fornitore invece che a ogni pagina;
      - fornitore nuovo (o voce ancora senza chiave) -> una domanda mirata, il
        cui esito resta una PROPOSTA da confermare in dashboard;
      - fornitore marcato ESTERO -> non si chiede niente a nessuno: una P.IVA
        italiana non c'e' e non ci sara' mai.
    Una lettura che contraddice una P.IVA gia' confermata non sovrascrive
    niente: resta come traccia in partita_iva_scartata, come per gli indirizzi.
    """
    fornitore = dati.get("fornitore")
    if not fornitore:
        return dati

    memoria = carica_memoria()

    # Un fornitore estero non riempie mai la sua "partita_iva", quindi senza
    # questa uscita la domanda mirata (~1 s) ripartirebbe su ogni pagina di
    # ogni sua bolla, per sempre. L'identificativo fiscale estero, se l'utente
    # l'ha scritto, si porta sul documento: e' l'unica chiave che quel
    # fornitore ha, ed e' la stessa che arriva dall'XML di una sua fattura.
    estero, identificativo = voce_fornitore_estero(fornitore, memoria)
    if estero:
        letta = normalizza_piva(dati.get("partita_iva"))
        identificativo = normalizza_piva(identificativo)
        if letta and letta != identificativo:
            dati["partita_iva_scartata"] = letta
        dati["partita_iva"] = identificativo
        print(f"🌍 [{fornitore}] fornitore estero: nessuna P.IVA italiana da cercare.")
        return dati

    piva_nota, _confermata = partita_iva_per(fornitore, memoria)

    if piva_nota:
        letta = normalizza_piva(dati.get("partita_iva"))
        if letta and letta != piva_nota:
            dati["partita_iva_scartata"] = letta
            print(f"⚠️ [{fornitore}] P.IVA letta {letta} diversa da quella in anagrafica "
                  f"{piva_nota}: tengo l'anagrafica.")
        dati["partita_iva"] = piva_nota
        return dati

    # Se una regola mirata sul campo partita_iva l'ha gia' letta bene, la
    # domanda generica sarebbe una seconda lettura dello stesso posto.
    if partita_iva_valida(dati.get("partita_iva")):
        return dati

    # Da qui in poi: fornitore nuovo o senza chiave. E' l'unico caso in cui la
    # lettura vale la pena, ed e' cio' che tiene il costo a una volta per
    # fornitore invece che a ogni pagina.
    letta = _chiedi_partita_iva(image_path)
    if not letta:
        return dati

    # Sul DDT le partite IVA sono almeno due (emittente e destinatario) e
    # quella del cliente e' spesso la piu' in vista: se il numero letto risulta
    # gia' di qualcun altro in anagrafica, o e' di una voce marcata "mai un
    # fornitore", NON e' di chi stiamo leggendo. Meglio lasciare il campo vuoto
    # che proporre una chiave di un'altra azienda.
    motivo = motivo_scarto_piva(letta, fornitore, memoria)
    if motivo:
        print(f"\U0001f6ab [{fornitore}] P.IVA letta {letta} scartata: {motivo}. "
              f"La lascio vuota: si conferma a mano dall'anagrafica.")
        dati["partita_iva_scartata"] = letta
        return dati

    if not partita_iva_valida(letta):
        # Il carattere di controllo non torna: quasi sempre una cifra letta
        # male. Si tiene comunque nel documento (principio del normalizzatore:
        # meglio un dato grezzo che nessun dato) ma non diventera' la chiave
        # del fornitore, perche' aggiorna_fornitore accetta solo P.IVA valide.
        print(f"⚠️ [{fornitore}] P.IVA letta '{letta}' non valida: la tengo sul documento "
              f"ma non la propongo come chiave.")

    dati["partita_iva"] = letta
    print(f"🔑 [{fornitore}] partita IVA letta dal documento: {letta} (da confermare).")
    return dati


def estrai_dati_da_immagine(image_path):
    regole_memoria = ottieni_regole_formattate()
    sezione_memoria = ""
    
    if regole_memoria:
        sezione_memoria = f"\n\nMEMORIA STORICA DEI FORNITORI (Applica queste regole se riconosci il fornitore):\n{regole_memoria}"

    prompt = f"""
        Estrai i dati da questa pagina di un D.D.T. italiano. Se un campo non è presente o leggibile con certezza, lascia stringa vuota "" (mai "dato mancante"/"non trovato"). Non duplicare dati tra campi. Distingui bene caratteri simili (3/9, O/0).

        CONSEGNA — è l'indirizzo dove viene fisicamente recapitata la merce. Segui questa procedura in ordine, fermati al primo passo che si applica. Usa SEMPRE UN SOLO indirizzo: non concatenare mai due indirizzi diversi nello stesso campo, anche se ne vedi più di uno candidato.

        1. Cerca PRIMA le etichette più specifiche: "Consegna a", "Luogo di Consegna", "Luogo di Destinazione", "Destinazione Merce", "Luogo Dest. Merci", "Destinatario merce"/"Luogo di scarico", "Spedizione a". Se una di queste è presente, usa SEMPRE quell'indirizzo — anche se sulla stessa pagina c'è ANCHE un campo generico "Destinatario" con un indirizzo diverso. In quel caso "Destinatario" da solo indica quasi sempre il cliente fatturato/proprietario dell'ordine, NON il luogo fisico di consegna: ignoralo a favore dell'etichetta più specifica.
        2. Solo se NON è presente NESSUNA delle etichette specifiche sopra, allora usa il campo "Destinatario" (se presente) come consegna.
        3. NON usare MAI l'indirizzo sotto "Intestatario", "Fatturazione", "Cliente Fatturazione", "Sede di fatturazione" o "Cessionario/Cliente" — quello è sempre l'indirizzo di chi paga, mai il luogo fisico di consegna, a prescindere da quale indirizzo specifico contenga.
        4. In assenza di etichette, cerca un secondo blocco indirizzo nella pagina, diverso da quello di intestazione/fatturazione: quello è la consegna.
        5. Se nel documento c'è un solo indirizzo in tutto e non è chiaramente etichettato come fatturazione/intestatario, usalo come consegna.

        - ragione_sociale_consegna: nome del punto vendita/destinatario finale (es. "CONAD", "PAC 2000A", "C.R. MARKET SRL", "CR SUPERMERCATI SRL"), senza indirizzo. Cercalo attivamente vicino all'indirizzo di consegna scelto: quasi sempre un nome azienda/insegna è scritto proprio sopra o accanto all'indirizzo. Non lasciarlo vuoto se un nome è visibile. Se il documento riporta "Ragione Sociale" e "Indirizzo" già separati nella sezione destinazione, usali direttamente per i due campi rispettivamente.
        - indirizzo_consegna: solo l'indirizzo, formato esatto "VIA NUMERO, CAP CITTÀ (PROV)" — es. "VIA MARIO VISINTINI 51, 00012 GUIDONIA MONTECELIO (RM)". Niente codici cliente, partite IVA o sigle interne.

        ALTRI CAMPI:
        - fornitore: azienda emittente (in alto, es. srl/spa/snc). Riporta la ragione sociale COMPLETA come stampata, mai un'abbreviazione o una sola iniziale: se leggi solo una lettera isolata stai guardando un logo tagliato, cerca il nome per esteso altrove nella pagina (intestazione, piè di pagina, timbro).
        - numero_ddt: SOLO il codice del documento (cerca "D.D.T. N." o "Doc. N."), copiato esattamente come appare, incluso qualsiasi prefisso alfanumerico (es. "SGE/0705580" deve restare "SGE/0705580" INTERO, non tagliare mai il prefisso e non perdere cifre). Rimuovi gli zeri iniziali SOLO se il numero è composto esclusivamente da cifre (es. "00127" → "127"; ma "SGE/0705580" resta invariato).
          NON includere MAI nel campo l'etichetta che precede il numero: "DOC. DI TRASPORTO 7071" → "7071", non "DOC.DI TRASPORTO 7071".
          NON includere MAI la data: sui moduli numero e data sono spesso affiancati nella stessa riga, ma "374764 del 01/07/2026" → numero_ddt "374764" e data_ddt "01-07-2026", mai "374764/01/07/2026".
        - data_ddt: data di emissione, SEMPRE nel formato "GG-MM-AAAA" con il trattino e l'anno a 4 cifre, senza orario. Converti sempre qualunque formato tu veda sul documento: "4/6/26" → "04-06-2026", "01.07.2026" → "01-07-2026", "2026-07-08" → "08-07-2026". Non usare mai "/" o "." come separatore.{sezione_memoria}

        Se il documento è sfocato, tagliato, storto o di qualità incerta miraccomando → leggibilita_bassa: true.

        Rispondi SOLO con questo JSON, nessun testo/markdown attorno:
        {{
            "fornitore": "",
            "numero_ddt": "",
            "data_ddt": "",
            "ragione_sociale_consegna": "",
            "indirizzo_consegna": "",
            "leggibilita_bassa": false
        }}
        """

    try:
        response = _client().chat(
            model=valore("MODELLO_VISION"),
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }],
            options=_opzioni(),
            keep_alive='30m'
        )

        messaggio = response['message']
        risultato_testo = (messaggio.get('content') or '').strip()

        dati = _estrai_json(risultato_testo)

        if dati is None:
            # I modelli "thinking" (qwen3-vl) scrivono il ragionamento in un
            # campo separato e possono esaurire la finestra prima di arrivare a
            # 'content': in quel caso il JSON e' spesso gia' dentro il
            # ragionamento, e recuperarlo vale piu' che perdere la pagina.
            dati = _estrai_json(messaggio.get('thinking') or '')
            if dati is not None:
                print(f"⚠️ {image_path}: JSON recuperato dal ragionamento del modello "
                      f"(risposta vuota: alza MODELLO_NUM_CTX, ora {valore('MODELLO_NUM_CTX')}).")

        if dati is None:
            generati = response.get('eval_count')
            letti = response.get('prompt_eval_count')
            raise ValueError(
                f"il modello {valore('MODELLO_VISION')} non ha restituito JSON "
                f"(content: {len(risultato_testo)} caratteri, "
                f"ragionamento: {len(messaggio.get('thinking') or '')} caratteri, "
                f"prompt {letti} token + {generati} generati su "
                f"num_ctx={valore('MODELLO_NUM_CTX')})"
            )

        # Il prompt chiede formati precisi ma il modello non li rispetta in modo
        # affidabile: la normalizzazione deterministica avviene a valle.
        # Stesso principio per gli indirizzi vietati: chiedere al modello di NON
        # usare un indirizzo non funziona, confrontare due stringhe sì.
        #
        # L'ordine dei tre passaggi conta:
        #  1. normalizza_dati, cosi' il fornitore e' gia' in forma canonica e il
        #     confronto per somiglianza in memoria lavora su un nome pulito;
        #  2. applica_regole_campo, che puo' SOSTITUIRE l'indirizzo sbagliato
        #     con quello giusto;
        #  3. filtra_fornitore_vietato: il nome letto e' quello del cliente
        #     (gruppo d'acquisto, insegna del punto vendita)? Va PRIMA della
        #     P.IVA, perche' su un fornitore che non esiste non ha senso ne'
        #     cercare una chiave in anagrafica ne' chiederne una al modello;
        #  4. applica_nome_canonico: il fornitore riconosciuto prende il nome
        #     con cui e' censito, cosi' l'alias inserito una volta vale anche
        #     nell'abbinamento con le fatture, che gli alias non li legge;
        #  5. completa_partita_iva, dopo le regole (una regola mirata puo'
        #     riguardare proprio la P.IVA);
        #  6. filtra_indirizzo_vietato, come rete di sicurezza: se anche la
        #     domanda mirata e' finita sull'indirizzo vietato, il campo va
        #     comunque svuotato e il documento mandato in CHECK;
        #  7. annota_fornitore_critico per ultimo, perche' cerca la voce in
        #     anagrafica e va fatto sul nome CANONICO (passo 4), che e' quello
        #     con cui il confronto ha piu' probabilita' di riuscire — e su un
        #     nome svuotato dal passo 3 non ci sarebbe niente da cercare.
        dati = applica_regole_campo(normalizza_dati(dati), image_path)
        dati = filtra_fornitore_vietato(dati)
        dati = applica_nome_canonico(dati)
        dati = completa_partita_iva(dati, image_path)
        return annota_fornitore_critico(filtra_indirizzo_vietato(dati))
    except Exception as e:
        print(f"❌ Errore sull'immagine {image_path}: {e}")
        return None