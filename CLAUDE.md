## 🤖 Motore AI Locale per Estrazione D.D.T. (Fatturazione)

Monorepo, quattro servizi in `docker-compose`:
- `backend/` — FastAPI: analizza scansioni di D.D.T. italiani e legge le fatture elettroniche.
- `frontend/` — dashboard React per revisionare i documenti estratti.
- `postgres-gestione-fatture` — database delle **anagrafiche** (fornitori, punti vendita), dati in `postgre/dati/`.
- `uptime-kuma` — il guardiano, vedi in fondo.

### Cartelle su disco
Un albero per flusso, alla radice, con `da_leggere/` (ingresso) e `lette/` (archivio):
```
DDT/da_leggere/        scansioni PDF in attesa
DDT/lette/             OK.json, CHECK.json, KO.json + OK/, CHECK/, KO/ con i PDF
FATTURE/da_leggere/    .xml / .xml.p7m in attesa
FATTURE/lette/         FATTURE.json (chiuse) + ATTESA.json (coda) + originali XML
ACCOPPIATE/            i file unici fattura+DDT confermati dall'operatore
postgre/dati/          file di Postgres — ignorati da git
```
- **I percorsi nel container sono identici a quelli sull'host** (`./DDT:/DDT`, ecc.): un path letto in un log si trova sul disco senza tradurlo.
- **Unica fonte di verità: `src/comune/percorsi.py`** (`CARTELLA_*`, `cartella_registro(stato)`, tutte sovrascrivibili da env). Niente costanti di percorso nei moduli. `cartella_registro()` serve cinque registri su due alberi.
- **`ACCOPPIATE/` è l'unica cartella pensata per essere aperta a mano**: nomi leggibili da `nome_fascicolo()` (`CRIK_CROK_SRL_47_V9_31-08-2026_97262164.pdf`) invece degli UUID. Le 8 cifre finali servono perché due fornitori possono emettere la fattura "47" lo stesso giorno.
- Le `da_leggere/` si riempiono dalla dashboard (`/api/{ddt,fatture}/carica`) e si svuotano con `/scansiona`, a mano o all'ora impostata.
  - **Un nome già presente non viene mai sovrascritto**: `_deposita()` aggiunge `_2`, `_3`… (due scansioni si chiamano quasi sempre `scan.pdf`).
  - **Il file elaborato viene rimosso**, altrimenti ogni scansione successiva ci ripasserebbe sopra. La copia buona è il PDF in `DDT/lette/<stato>/`, o l'XML originale per le fatture. **Un file che fallisce resta dov'è** e torna in `falliti`.

### Organizzazione del codice Python (`backend/src/`)
Divisione **per flusso, non per layer**:
- `src/ddt/` — scansioni → modello vision: `pdf_processor`, `llm_engine`, `classificatore`, `raggruppatore`, `accorpatore`, `impronte`, `notificatore`.
- `src/fatture/` — XML → abbinamento ai DDT: `lettore_xml`, `abbinatore`, `fascicolatore`, `coda`. **Non importa nulla da `src/ddt/`**: si incontrano solo sui registri.
- `src/comune/` — ciò che serve a **entrambi**: `normalizzatore`, `registro`, `memory_manager`, `archivio_fornitori`, `archivio_punti_vendita`, `punti_vendita`, `database`, `pdf_writer`, `stato_elaborazione`, `percorsi`, `tempo`, `configurazione`, `pianificatore`. Non spostarci roba solo perché "sembra generica".
- `src/notifiche/` — le mail (`mailer`, `impaginazione`, `riepilogo_ddt`, `riepilogo_fatture`, `sollecito`). È il postino: non decide niente.
- `src/api/` — le route, una per entità.

`src/comune/tempo.py` tiene fuso e formato dei timestamp: li scrivono i registri di entrambi i flussi e li rilegge chi filtra per data. Un formato diverso falsa in silenzio l'anzianità della coda.

### Configurazione a caldo (`src/comune/configurazione.py`)
Le impostazioni che si cambiano davvero (host Ollama, modello, `num_ctx`, zoom, soglie, orari, SMTP) stanno in `data/configurazione.json`, su volume, modificabili da dashboard senza ricostruire.
- **Tre livelli in quest'ordine: `data/configurazione.json` → env → default nel codice.** `origine()` dice da dove viene un valore ed è scritto accanto al campo in dashboard.
- **Il campo vuoto significa "torna al valore del compose"**, non è un errore: è la via d'uscita se una modifica rompe qualcosa. Per questo il compose resta popolato.
- **I valori si leggono con `valore()` dove servono, mai in una costante di modulo**: una costante congelerebbe il valore all'import. Per la stessa ragione `llm_engine.py` crea un `ollama.Client(host=valore("OLLAMA_HOST"))` a ogni chiamata. Cache invalidata sull'mtime sotto `threading.Lock`.
- `IMPOSTAZIONI` è l'elenco chiuso del configurabile (tipo, default, gruppo, aiuto, `minimo`/`massimo`). Tipi: `TESTO`, `INTERO`, `DECIMALE`, `ORARIO` (`HH:MM`, vuoto = disattivato), `SCELTA`. **Un valore fuori intervallo o di tipo sbagliato viene scartato** (elencato in `scartate`), non salvato: un `MODELLO_NUM_CTX: "banana"` non deve impedire l'avvio.
- **`segreto: True` (oggi solo `SMTP_PASSWORD`) non arriva mai al browser**: si manda `MASCHERA` e `salva_configurazione()` la riconosce al ritorno. Serve perché la dashboard rimanda sempre la bozza intera: senza, salvare un orario cancellerebbe la password. Svuotare davvero il campo la rimuove.
- **`PUT /api/configurazione` riscrive l'intero file**: chiave assente = chiave svuotata. Non è un merge.
- **I percorsi e `DATABASE_URL` restano fuori di qui**, nell'ambiente: un path sbagliato scritto da dashboard renderebbe irraggiungibile la dashboard stessa.

### Lavori automatici e mail (`src/comune/pianificatore.py` + `src/notifiche/`)
Dal 2026-09-09 l'orologio e il postino stanno dove sta lo stato (prima era n8n, che non decideva nulla e teneva l'HTML delle mail in un sqlite).

**Pianificatore**: thread daemon avviato dal `lifespan`, gira ogni 30 s. Tre lavori: `scansione_ddt`, `scansione_fatture`, `sollecito`.
- Orari in `configurazione.py` (`ORARIO_*`), riletti a ogni giro. **Vuoto = non pianificare**, ed è il default.
- **Non tiene "l'ultima esecuzione" ma l'istante dell'ultimo controllo**, e parte se l'ora prevista cade in `(ultimo_controllo, adesso]`. Così un backend spento **salta il giro** invece di lanciare una scansione a sorpresa al riavvio; e una scansione lunga tiene fermo il ciclo, quindi le fatture partono subito dopo le bolle — **l'ordine di `LAVORI` conta**.
- **Un lavoro alla volta**, un thread solo: due estrazioni in parallelo si contenderebbero la stessa GPU.
- **Le azioni gliele passa `main.py`** (`avvia({...})`): il pianificatore sa QUANDO, non COSA. `esegui()` non solleva mai ed è la stessa strada del pulsante "Esegui adesso".

**Mail**: senza `SMTP_HOST` o destinatari non parte nulla e **nessuna pipeline se ne accorge**.
- `mailer.py` è l'unico punto che parla con SMTP. Le pipeline usano `invia_silenzioso()` (logga e prosegue): un errore di posta non deve far fallire un'estrazione riuscita. Solo i pulsanti espliciti usano `invia()`.
- `impaginazione.py`: `esc()` su **tutto** ciò che viene da un documento, tabelle con stili inline e niente flex/grid (deve reggere Outlook), guscio 600 px con pulsante verso `URL_DASHBOARD`.
- Tre messaggi: `riepilogo_ddt` (conteggi, **perché** ogni CHECK è tale, pratiche pronte, file non elaborati, pagine già archiviate), `riepilogo_fatture` (racconta un *ingresso*: tutto entra `DA_ABBINARE`, più le anomalie sul cedente), `sollecito`.
- **`sollecito.componi()` torna `None` se non c'è niente da sollecitare**, così la mail non parte: una "nessuna fattura in attesa" verrebbe ignorata entro tre giorni, comprese le volte in cui dice qualcosa.
- `MAIL_RIEPILOGO_SCANSIONE` (`pianificate` default | `sempre` | `mai`): chi preme *Analizza* guarda già l'esito, e una mail per click farebbe smettere di leggere anche quelle notturne.

### Stack
- **Backend:** Python 3.12, FastAPI + Uvicorn, PyMuPDF (`fitz`) per PDF→immagine, Pillow, `asn1crypto` (buste firmate), `smtplib`, `psycopg[binary]`.
- **Frontend:** React 19 + Vite, Bootstrap 5, `lucide-react`, Nginx per la build.
- **Container:** il backend ha `depends_on: condition: service_healthy` su Postgres, altrimenti partirebbe durante `initdb` e la prima lettura ripiegherebbe sul JSON in silenzio.
- **Infrastruttura:** Ryzen 7 5700X3D, 32 GB, RX 7600 XT.
- **Motore AI:** Ollama su **macchina separata in LAN** (`10.1.20.25:11434`) via `OLLAMA_HOST`. GPU **condivisa**: un'estrazione può attendere.
- **Modello:** `qwen2.5vl:7b`. `MODELLO_VISION`, `MODELLO_NUM_CTX`, `PDF_RENDER_ZOOM` si provano **insieme** e senza ricostruire.

**Modelli provati e scartati** (non riproporli senza una misura nuova):
- `qwen3-vl` (2026-09-07) — è **thinking** e il template Ollama ignora `think=False` in silenzio: con `num_ctx 8192` esaurisce i token prima di `content` (1/4). A `16384` fa 4/4 ma **44 s/pagina contro 6**, e sbaglia proprio dove il ragionamento dovrebbe aiutare. L'estrazione di testata è lettura, non deduzione.
- `qwen2.5vl:32b` (2026-09-07) — 21 GB, risultati *peggiori* del 7b: il collo di bottiglia non è la taglia. Gli errori residui sono di formato e campo trascinato, cioè roba da `normalizzatore.py`.
- `llava:13b` (2026-09-07) — 0/4 numeri DDT. Encoder a risoluzione fissa: A4 in 336×336 px = 593 token contro 4053. Ricopiava gli esempi del prompt (segno che non vede il documento). **Più parametri ≠ più risoluzione.**
- **`format='json'` è controproducente** coi thinking: `content` sempre vuoto.
- Prima di cambiare modello verifica se **ragiona** (`/api/show` → `capabilities`) e alza `num_ctx`. `_estrai_json()` ritaglia fra la prima `{` e l'ultima `}` e, se `content` è vuoto, ripesca il JSON da `thinking`.
- **`PDF_RENDER_ZOOM` default `2.5` (~180 DPI). Provato a `3.5` e rimesso a `2.5`**: sullo stesso PDF sbagliava *più* campi. Non rialzarlo senza una misura su un batch reale.

### Estrazione (`src/ddt/llm_engine.py`)
`estrai_dati_da_immagine` analizza **una pagina per volta** e restituisce solo un JSON:
- `fornitore` — l'emittente. IGNORA vettori, diciture di trasporto, email, siti.
- `numero_ddt` — alfanumerico esatto (zeri iniziali tolti *solo* se puramente numerico, lato Python: `SGE/0705580` resta).
- `data_ddt` — `GG-MM-AAAA`.
- `ragione_sociale_consegna` — il punto vendita finale.
- `indirizzo_consegna` — il VERO indirizzo di destinazione merce. *Regola critica:* mai l'indirizzo di fatturazione/sede legale; le etichette "Consegna a", "Luogo di destinazione", "Spedizione a" hanno **priorità assoluta** sul generico "Destinatario".
- `leggibilita_bassa` — booleano sulla qualità.

`partita_iva` **non è nel prompt**: la riempie un passaggio a parte. Campi non letti = stringa vuota `""`, mai "dato mancante": tutta la pipeline conta su questo.

**Ordine dei passi** (conta): `normalizza_dati` → `applica_regole_campo` → `filtra_indirizzo_vietato` → `applica_nome_canonico` → `filtra_fornitore_vietato` → `annota_fornitore_critico` → `completa_partita_iva`.

### Normalizzazione (`src/comune/normalizzatore.py`)
Il prompt chiede formati precisi, un 7B non li rispetta (misurato: **3 date su 17** nel formato richiesto). Tutto ciò che è regola esatta si ripulisce in Python, subito dopo il `json.loads`.
- `normalizza_data`: qualsiasi separatore, anno a 2 cifre, ISO, mesi italiani → `GG-MM-AAAA`.
- `normalizza_numero_ddt`: toglie l'etichetta trascinata (`"DOC.DI TRASPORTO 2 7071"`) e la data in coda (`"374764/01/07/2026"` → `"374764"`), poi gli zeri iniziali se tutto numerico.
- `normalizza_indirizzo`: maiuscolo, virgola davanti al CAP, provincia fra parentesi. Serve anche all'accorpatore (lo stesso magazzino tornava scritto in 4 modi).
- `normalizza_azienda`: maiuscolo + forma giuridica compatta (`S.r.l.` → `SRL`).
- `normalizza_partita_iva` + `partita_iva_valida`: 11 cifre e **carattere di controllo** (Luhn). È l'unico campo verificabile senza guardare il PDF.
- **Principio:** formato non riconosciuto → dato grezzo ripulito, **mai** stringa vuota. Azzerare un campo cambia la classificazione.
- **Non si applica alle correzioni manuali** (`PUT /api/documents/{id}`): quello che l'utente scrive resta com'è.

### Classificazione (`src/ddt/classificatore.py`)
`determina_stato()` conta i 4 `CAMPI_OBBLIGATORI` (`fornitore`, `numero_ddt`, `data_ddt`, `indirizzo_consegna`): **0** → `KO`; **tutti + `leggibilita_bassa == false`** → `OK`; il resto → `CHECK`. Tre flag nei `dati` spostano `OK` → `CHECK`: `leggibilita_bassa`, `fornitore_critico`, `consegna_discorde`.
- È una **funzione pura con cinque chiamanti**: non farle leggere l'anagrafica (sarebbe una query per pagina). Ciò che serve arriva come flag nei `dati`, e `unisci_dati_pagina()` lo propaga — **senza propagazione l'accorpamento rimette in `OK` ciò che deve restare in `CHECK`**.
- **Lo stato si può forzare a mano** (`PUT /api/documents/{id}/stato`): il classificatore sa contare i campi letti, non giudicare il documento (quattro campi pieni ma sbagliati restano `OK`). L'endpoint tocca **solo il registro**, mai i `dati`; la voce porta `stato_manuale: <timestamp>` (badge `KO*`).
- **Una rianalisi ricalcola lo stato e cancella la forzatura** (è di nuovo l'utente a chiederla). Idem l'accorpamento, ma solo su `OK`/`CHECK`: `STATI_DA_ACCORPARE` non include `KO`, che nessun automatismo tocca più.
- È **l'unica azione sui D.D.T. a non chiamare `ricontrolla_fatture_in_attesa()`**: spostare una voce non la rende più o meno agganciabile. Non aggiungerlo "per simmetria".
- Lo spostamento passa da `sposta_documento()`: il PDF segue sempre il registro.

### Accorpamento pagine (`src/ddt/raggruppatore.py` + `accorpatore.py`)
Ogni pagina si analizza da sola; a fine batch `accorpa_documenti()` rilegge `OK.json`/`CHECK.json`, raggruppa per `numero_ddt` **identico** + fornitore simile (`SequenceMatcher` ≥ 0.5), fonde i PDF e riscrive i registri con una voce per documento reale, ricalcolando lo stato sui dati uniti. **Non spostare il merge dentro il loop di estrazione: è deliberato.**

**Unione manuale (`POST /api/documents/unisci` + `MergeBar.jsx`)** — l'automatico pretende il numero identico, e basta una cifra letta male.
- **L'ordine degli `ids` conta**: il primo è il master, i suoi dati vincono, gli altri riempiono solo i vuoti. I PDF si concatenano in quell'ordine.
- Lavora anche su **KO** (`STATI_TUTTI`): una pagina illeggibile appartiene comunque a un documento reale. La voce riceve `unione: "manuale"`, `numero_pagine` sommato, `file_origine` uniti.
- Il risultato non si ri-spezza mai: `accorpa_documenti()` sa raggruppare, non dividere.
- La selezione vive in `App.jsx` e non in `Dashboard`: deve sopravvivere al cambio di tab, perché le pagine da unire stanno per definizione in stati diversi.

### Pagine già viste (`src/ddt/impronte.py`)
La stessa pila passata due volte nello scanner non dava nessun segnale: la pagina veniva riletta, archiviata e **assorbita in silenzio dall'accorpamento**, con un doppione dentro il fascicolo.
- **La chiave è l'immagine, non i dati estratti**: sui dati non esiste regola che distingua un duplicato (due bolle diverse possono avere lo stesso numero). `firma_pagina()` è lo **sha256 dei byte dell'immagine renderizzata** — nessuna soglia, nessuna somiglianza.
- **Si firma l'immagine renderizzata, non il file caricato**: un PDF va riconosciuto pagina per pagina, e la stessa pagina può arrivare in due PDF diversi. In cambio la firma dipende da `PDF_RENDER_ZOOM`: cambiandolo le firme vecchie non corrispondono più — **è il verso giusto in cui sbagliare** (si perde un riconoscimento, non si scarta un documento buono).
- **Il controllo sta prima della chiamata al modello** (in `elabora_ddt`, dopo `aggiorna_pagina`): costa un hash, risparmia 6 s di GPU e non scrive niente.
- **`archivio_firme` si legge una volta per batch e cresce strada facendo**, così un PDF che contiene due volte la stessa scansione si riconosce da solo. *Misurato:* primo passaggio 20,7 s e 1 voce; secondo 0,41 s, 0 chiamate, 0 voci.
- **`firme_pagine` vale anche per i `KO`** (è identità, non dato estratto) e va **portato a mano ovunque una voce venga ricostruita**: `accorpa_documenti()` e `unisci_documenti_manuale()` usano `_firme_unite()`, altrimenti la bolla riscansionata domani ripasserebbe come nuova.
- Le voci pre 2026-09-11 e gli inserimenti manuali non hanno firme e restano fuori dal confronto.
- Le pagine saltate **si dicono**: `duplicati` nelle risposte, riga nella `BarraIngresso`, blocco nella mail (con oggetto suo quando *tutte* erano già viste — "nessun documento elaborato" manderebbe a cercare un guasto che non c'è).
- **Limite noto, da non coprire con una soglia:** un foglio passato due volte nello scanner dà due immagini diverse e non viene riconosciuto. Un hash percettivo vorrebbe una distanza misurata su un batch reale, e qui un falso positivo è **una bolla buttata via**.

### Il database delle anagrafiche (`src/comune/database.py`)
Un `postgres:16-alpine` con i dati in `postgre/dati/` (bind mount, ignorato da git). Ci vivono le **anagrafiche**: fornitori e punti vendita.
- **Ci va ciò che è anagrafica** (elenchi con una chiave, interrogati per chiave, che crescono). **Non** ci vanno i registri dei documenti: `OK.json`, `CHECK.json`, `KO.json`, `FATTURE.json`, `ATTESA.json` restano accanto ai PDF e agli XML che descrivono, e si spostano insieme a loro (`sposta_documento()`). È una proprietà, non un ritardo tecnologico.
- **`DATABASE_URL` sta nell'ambiente, non in `configurazione.py`** (stessa regola dei percorsi). **Vuota è una scelta valida**: i fornitori tornano a vivere nel JSON e il backend parte da solo.
- **`database.py` non conosce nessuna tabella**: apre una connessione e basta. Ogni anagrafica porta schema e query proprie. Niente pool, `connect_timeout` corto di proposito — questa connessione sta sulla strada di un'estrazione e deve fallire subito.
- **Una colonna nuova su una tabella esistente vuole un `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`** dentro `SCHEMA`, accanto al `CREATE`: `prepara()` gira a ogni avvio ma il `CREATE TABLE IF NOT EXISTS` non fa niente su un database già creato, e la `SELECT` fallirebbe.
- **`_prepara_anagrafiche()` nel `lifespan` non solleva mai**, e ogni anagrafica ha il suo `try` separato: una che non si alza non deve costarne un'altra né l'avvio.
- Il volume è una **cartella del progetto**, non un volume con nome: i dati si vedono dove sta il progetto (la lezione è `n8n_config/` coi suoi 327 MB finiti in git). Porta esposta su `127.0.0.1:5432` soltanto. La `POSTGRES_PASSWORD` la scrive `initdb` **una volta sola**: cambiarla nel compose dopo non basta.

**`backend/data/fornitori_memoria.json` è la copia di scorta.** Riscritta da `salva_memoria()` dopo ogni salvataggio riuscito, riletta **solo** se il database non risponde. Non è una seconda fonte di verità. Vale per tre ragioni: è da lì che l'anagrafica viene **importata la prima volta** (`migra_da_file_a_database()`, solo a tabella vuota); tiene in piedi le estrazioni con Postgres giù; ed è l'unica forma in cui le regole restano leggibili e diffabili senza un client SQL.
- **Asimmetria voluta:** `carica_memoria()` ripiega sul file e prosegue, `salva_memoria()` **lascia risalire l'eccezione** (un salvataggio che non salva non va raccontato come riuscito). *Misurato:* con il container fermo, GET → 200 dal file, PUT → 500, copia su file non toccata.
- `scrivi()` dei fornitori è una **sostituzione, non un merge**: upsert sui padri (conserva `creato_il`), svuota-e-riscrivi sui figli, **una transazione**. Tre tabelle figlie (`fornitori_indirizzi_vietati`, `fornitori_nomi_alternativi`, `fornitori_regole_campo`) e non colonne JSONB: sono elenchi che si consultano uno per uno. La colonna `posizione` li restituisce **nell'ordine in cui l'utente li ha scritti**, altrimenti la textarea si rimescola sotto gli occhi di chi la compila.
- **Le decisioni restano in `memory_manager.py`**: l'archivio è il magazziniere, non il capo.

### I punti vendita (`archivio_punti_vendita.py` + `punti_vendita.py`)
**Ogni scansione è la posta di UN punto vendita** (richiesta del committente): chi mette i fogli nello scanner sa dove la merce è arrivata, e non c'è ragione di chiederlo a un modello. Dichiarandolo prima di *Analizza*, `ragione_sociale_consegna` e `indirizzo_consegna` — **due dei quattro campi obbligatori**, e i due su cui il modello sbaglia di più — smettono di essere una lettura.
- **Il dichiarato batte il letto.** Ciò che il modello aveva letto resta in **`consegna_letta`**, ma solo se **diverso** (una traccia identica è rumore): è l'unica via per accorgersi del negozio sbagliato.
- **`applica_consegna()` sta PRIMA di `determina_stato()`**: dopo, lascerebbe in `CHECK` proprio i documenti a cui ha appena dato i campi mancanti.
- **`trova()` confronta il codice in modo esatto, mai per somiglianza di nome**: si stanno scrivendo due campi obbligatori su ogni bolla del batch.
- **Il punto vendita viaggia dentro `dati`** (`punto_vendita` = codice, `punto_vendita_nome` = nome) ed è in `CAMPI_DA_UNIRE`: senza, un'unione fra una pagina dichiarata e una no farebbe sparire il documento dai dichiarati.
- **Facoltativo per costruzione**: senza, tutto si comporta come prima (la scansione notturna non ha nessuno a cui chiedere). `elenco()` torna `[]` se il database non risponde e il menu sparisce, invece di bloccare l'analisi.
- **Due indirizzi per voce:** `DIP_*` è il negozio (dove arriva la merce, ed è ciò che finisce sul D.D.T.), `IND_*` è la sede della società (dove arriva la fattura) — CITTADUCALE consegna a Cittaducale ma la società ha sede a Roma. Sulla bolla va `RAG_SOC`, non `DIPENDENZA`.
- **La chiave è `COD_AZI`** (codice gestionale, resta uguale se l'insegna cambia nome); `DIPENDENZA` ha un indice unico perché due etichette uguali non si distinguerebbero nel menu.
- **Il seme è `backend/data/punti_vendita.csv`** (`data/` è montata, la radice no). `importa_da_csv()` importa **solo a tabella vuota**. Qui `scrivi()` è un **upsert e non la sostituzione** dei fornitori: un export parziale del gestionale non deve cancellare punti vendita già citati dai D.D.T.
- Normalizzazioni in `punti_vendita.py`: `normalizza_azienda` e `normalizza_indirizzo`, perché dichiarato e letto devono risultare uguali quando lo sono. La `partita_iva` si tiene **solo con 11 cifre** (nel CSV ce n'è una scritta `0` con dieci spazi).
- **`GET /api/punti-vendita` è l'unica route, in sola lettura**: i punti vendita li possiede il gestionale. Modificarli da qui creerebbe la seconda fonte di verità.
- In dashboard si sceglie nella `BarraIngresso` e finché non si risponde *Analizza* resta bloccato. Campo vuoto e *Non dichiararlo* sono cose diverse. **La scelta non si ricorda fra una scansione e l'altra**: la pila dopo è di un altro negozio.

**Il negozio sbagliato nel menu (`punto_vendita_discorde()`)** — il difetto del dichiarato è che è muto: venti bolle con due campi obbligatori sbagliati finirebbero in `OK` e nessuno le riaprirebbe.
- **La prova è il CAP, e nient'altro.** Tace se un CAP letto è quello del negozio dichiarato **o della sua sede** (`sede_cap` — leggere l'indirizzo di fatturazione è l'errore più comune del modello, non una distrazione dell'operatore), e segnala **solo** se un CAP letto risulta di un **altro** punto vendita in anagrafica. Un CAP di nessuno non dice niente (magazzino del fornitore o lettura sbagliata).
- **Il nome fa solo da silenziatore, mai da prova**: misurati 38 riconoscimenti incrociati fra i 31 negozi reali (`GUIDONIA` sta nell'indirizzo di `TIBURTINA`). *Misurato:* 0 segnalazioni sulle 31 dichiarazioni giuste, 0 sull'indirizzo di sede letto al posto di quello di consegna, 810/930 sulle dichiarazioni sbagliate.
- Viaggia in `dati` come `consegna_discorde` (`codice`, `nome`, `motivo`), è la quarta ragione di `CHECK`, e `unisci_dati_pagina()` se lo porta dietro.
- Si vede in quattro punti, **il più importante è il primo**: la riga nella `BarraIngresso` subito dopo l'analisi (chi ha scelto il negozio è ancora lì, e venti pagine su venti non sono venti distrazioni ma una pila sbagliata), il badge *altro negozio?* in `DocumentTable`, il riquadro nel `ComparisonModal`, la riga in `_motivo_check()`.

### Memoria fornitori (`src/comune/memory_manager.py`)
Serve a iniettare regole nel prompt, filtrare letture sbagliate e fare da ponte verso le fatture.
- Le **note in prosa** (`note_specifiche`) entrano nel prompt solo se `"confermato": "yes"`. **Costo:** `ottieni_regole_formattate()` non filtra per fornitore, quindi **tutte** le note confermate finiscono nel prompt di **ogni** pagina.
- `carica_memoria()` intercetta `JSONDecodeError`/`OSError` e riparte da `{}`: un file corrotto non deve far fallire l'estrazione.
- **Deduplica per somiglianza:** chiavi in MAIUSCOLO, `aggiorna_fornitore()` cerca un simile prima di censire (il file era arrivato a **37 voci per 23 fornitori reali**). `stesso_fornitore()` usa due criteri su `chiave_confronto`: contenimento **per parole** (`COPERTURA_MINIMA_TOKEN = 0.6` — per parole e non per caratteri, perché `ITALIA SRL` è sottostringa di `ABC ITALIA SRL` ma copre 1 token su 2) e `SequenceMatcher` ≥ `SOGLIA_SIMILARITA` (**0.85**). Soglia misurata sulle 37 voci reali: duplicati veri a 0.80–1.00, fornitori diversi mai oltre 0.59. **Non abbassarla senza rimisurare** — è più severa di `SOGLIA_SIMILARITA_FORNITORE = 0.5` del raggruppatore, che risolve un problema diverso.
- `salva_memoria()` applica `unifica_memoria()` prima di scrivere: essendo l'unico punto di scrittura, né il censimento né la PUT possono reintrodurre doppioni. Nella fusione non si perde nulla (vince `confermato: yes`, nota più lunga, chiave più informativa).
- **`PUT /api/fornitori` sovrascrive l'intera anagrafica**: una chiave assente è una voce cancellata.

**Indirizzi vietati** (`indirizzi_vietati`) — gli indirizzi che per quel fornitore **non sono mai** la consegna (il cessionario ristampato su ogni bolla). `filtra_indirizzo_vietato()` svuota il campo (l'originale in `indirizzo_scartato`) e il documento va in CHECK invece di passare per OK con l'indirizzo sbagliato.
- Nasce da CEREALDOLCI, dove la nota nel prompt riformulata due volte non bastava: **se è una regola esatta va in Python, non nel prompt.** Un 7B ignora i divieti, un confronto di stringhe no.
- Non richiede `confermato`: la scrive solo l'utente. `stesso_indirizzo()` confronta su `chiave_indirizzo` con uguaglianza, contenimento (`LUNGHEZZA_MINIMA_CONTENIMENTO = 8`, altrimenti "VIA 2" becca mezzo archivio) e `SequenceMatcher` ≥ 0.9 per i CAP letti male. `unifica_memoria()` **somma** le liste: scartare un divieto riaprirebbe l'errore che chiudeva.

**Regole mirate `regole_campo` — è così che si dice al modello dove guardare.** Ogni voce è `{"campo": ..., "etichetta": ...}` ("il numero DDT sta sotto `Bolla Nr.`"). Non finiscono nel prompt: a estrazione avvenuta `applica_regole_campo()` fa **una domanda secca** sulla stessa immagine e sovrascrive quel campo (solo con un valore non vuoto).
- *Misurato su SA.BA FISH, VITAKRAFT, CEREALDOLCI, NUOVO SRL:* la stessa regola nel prompt sbaglia **6 su 6**, come domanda singola azzecca **16 su 16**, a ~1 s.
- **Non è la lunghezza del prompt:** provato con 9 regole (1378 caratteri), con una sola (213) e con nessuna — **sei esecuzioni, output identico byte per byte**. Un 7B non applica una condizione "se il fornitore è questo, guarda lì".
- **Le regole al negativo non funzionano**, nemmeno come domanda mirata: "NON nella sezione Destinatario" dice cosa evitare, non dove guardare. Riscritta sull'etichetta positiva stampata (`Destinazione merci e/o variazioni`) va 6/6. Il modulo in dashboard è a tendina + etichetta apposta.
- `CAMPI_REGOLABILI` elenca i campi ammessi ed **esiste due volte**, in `memory_manager.py` e in `SuppliersManager.jsx`: aggiornali entrambi. `ragione_sociale_consegna` e `indirizzo_consegna` si chiedono insieme (`GRUPPO_CAMPI`).

**Nomi alternativi `nomi_alternativi`** — altri nomi sotto cui compare lo stesso fornitore, provati da `trova_fornitore_simile()`. Nasce da SA.BA FISH (3 token su 8 = 0.375). **La risposta non è abbassare la soglia**: un alias è un dato esatto scritto a mano e non sposta nessun confronto automatico. Un alias per riga (una ragione sociale può contenere virgole).
- **Il fornitore riconosciuto prende il nome dell'anagrafica** (`applica_nome_canonico()`, il letto resta in `fornitore_letto`). Non è cosmesi: il nome è metà della chiave con cui una fattura ritrova le sue bolle, e **lì gli alias non vengono consultati** — `abbinatore` confronta il nome sul D.D.T. col cedente dell'XML.

**I tre flag li mette SOLO l'utente** (sono fatti dell'azienda, non deduzioni da un documento), e `unifica_memoria()` li propaga — nella fusione il flag acceso vince:
- **`mai_fornitore`** — chi non è mai un fornitore: gruppo d'acquisto e insegne (`PAC 2000 C/O CREF SRL`, `CREF SRL`, `CR MARKET`), stampati in cima alla bolla più in grande dell'emittente. `filtra_fornitore_vietato()` svuota `fornitore` (traccia in `fornitore_scartato`) e con lui la P.IVA letta accanto, così il documento va in CHECK invece di essere archiviato a nome del cliente. È il principio degli `indirizzi_vietati` portato dall'indirizzo al nome. `aggiorna_fornitore()` non censisce né arricchisce una voce marcata.
- **`fornitore_estero` + `identificativo_estero`** — chi non ha una P.IVA italiana e non l'avrà mai. Senza il flag `completa_partita_iva()` farebbe la domanda mirata su **ogni pagina per sempre**, le fatture uscirebbero con `piva_assente` e la voce resterebbe nella coda delle conferme (un badge che non cala smette di essere letto). Con il flag: `completa_partita_iva()` esce subito, `aggiorna_fornitore()` non propone nulla, `verifica_fornitore_fattura()` tace, `pivaDaConfermare()` la esclude.
  - **`identificativo_estero` è un campo a sé e NON va scritto in `partita_iva`**, che resta la chiave *italiana* con sopra il Luhn, la coda delle conferme e `motivo_scarto_piva()`. È facoltativo. L'abbinamento funziona lo stesso: `lettore_xml._partita_iva()` torna `IdCodice` **senza prefisso paese**, quindi `DE811128135` in anagrafica e `811128135` dall'XML sono lo stesso numero con lo **stesso confronto esatto**.
- **`fornitore_critico`** — chi sappiamo a priori che sbaglia le bolle: le sue vanno in `CHECK` a prescindere da quello che il modello legge. `annota_fornitore_critico()` è il **passo 7**, dopo `applica_nome_canonico()` e `filtra_fornitore_vietato()`, e va chiamata anche in `crea_documento_manuale` (l'unica strada che archivia senza passare da `llm_engine`). Sposta solo `OK` → `CHECK`. **Nessun effetto retroattivo** (una rianalisi sì, ed è giusto). Il motivo si vede ovunque (mail, badge *critico*, `ComparisonModal`, `etichetteDdt.js`): è l'unica ragione di CHECK che non si spiega guardando i campi.

**Una P.IVA non si attribuisce per esclusione: `motivo_scarto_piva()`.** Sul DDT ce ne sono sempre almeno due e quella del cliente è spesso la più in vista. Due regole esatte: il numero è di una voce `mai_fornitore` → è del cliente; il numero **risulta già di un'altra voce** → una P.IVA identifica una azienda sola. In entrambi i casi il campo resta **vuoto** (traccia in `partita_iva_scartata`).
- Qui **non** vale il "meglio un dato sporco che nessun dato" del normalizzatore: non è una formattazione ma una chiave, e una chiave sbagliata è un'altra azienda.
- *Misurato (2026-09-10):* `00163040546` (PAC 2000) era attaccata a **quattro** voci, `00133919993` (CREF) a **tre**. Sono P.IVA valide, semplicemente di qualcun altro: il Luhn non poteva accorgersene.

**P.IVA come chiave verso le fatture** — ogni voce ha `partita_iva`, `partita_iva_confermata`, `autorizzato` (quest'ultimo non filtra più niente, resta per le voci storiche).
- Il cedente di una fattura si riconosce **per P.IVA esatta** (`trova_fornitore_per_piva`), mai per somiglianza di nome: sull'XML è esatta, e sbagliare qui vuol dire lavorare la fattura di un'altra azienda. Il nome resta fallback solo se la voce trovata non ha una P.IVA **confermata** diversa.
- **Chiave assente = autorizzato e confermata** (le voci storiche vengono da XML firmati). Solo la lettura del modello scrive `partita_iva_confermata: False`.
- `registra_fornitore_fattura()` torna la sola chiave, ricompila la P.IVA su una voce nata da DDT e **sovrascrive una proposta non confermata**: il dato fiscale batte sempre una lettura.
- **Sui D.D.T. la P.IVA si legge solo per un fornitore nuovo o ancora senza chiave**, con una **domanda mirata** (`_chiedi_partita_iva`, ~1 s una volta per fornitore) e non come settimo campo del prompt: chiesta insieme agli altri verrebbe presa dalla sezione sbagliata. Precedenza: **anagrafica confermata > lettura** (la lettura contraddetta finisce in `partita_iva_scartata`).
- **`partita_iva` non è tra i `CAMPI_OBBLIGATORI`** e non deve entrarci: manderebbe in CHECK l'intero archivio.
- Si conferma da due posti: il modale del D.D.T. (`PUT /api/fornitori/partita-iva`, col PDF a fianco) e l'anagrafica. Digitata a mano nasce confermata. **Dal D.D.T. si conferma una volta sola**, poi lucchetto: dal documento si *legge e convalida*, dall'anagrafica si *amministra*.
- **Lo stato della chiave non sta sul documento: lo calcola `annota_stato_piva()`** in lettura, come `status` — una copia sul registro invecchierebbe alla prima conferma fatta da un'altra bolla.

**I vettori** — il censimento è automatico e non li distingue: `ITALTRANS SPA` era archiviata in **OK**. Il rimedio è `mai_fornitore`, non un secondo elenco. **Trovarli è il problema vero** in un'anagrafica di 103 voci: `SuppliersManager` marca col badge *vettore?* le voci non ancora marcate il cui nome contiene una parola da vettore, più il filtro *Sembrano vettori*. È **solo un suggerimento** — una ditta di trasporti che ci fattura il trasporto è un fornitore vero, e il codice non può dedurlo.
- **Parole misurate (2026-09-11 su 111 nomi reali):** `TRASPORT`, `SPEDIZION`, `LOGISTIC`, `CORRIER`, `VETTORE` prendono **zero**. I due vettori veri sono `ITALTRANS SPA` e `VERCHA EXPRESS SRL`, presi da `TRANS` ed `EXPRESS`, con zero falsi positivi. Le sigle (`BRT`, `GLS`, `SDA`) si confrontano **per parola intera**. Se allunghi la lista, rimisurala.

### API Backend (`backend/src/api/` + `backend/main.py`)
`main.py` è ~110 righe e tiene solo ciò che riguarda l'applicazione intera: `FiltroPollingBarra`, `_prepara_anagrafiche()`, `ciclo_di_vita`, `app` + CORS, gli `include_router`, `uvicorn.run`.

| modulo | contenuto |
| --- | --- |
| `supporto.py` | **nessuna route**: `trova_documento`, `sposta_documento`, `annota_stato_piva`, `ricontrolla_fatture_in_attesa` |
| `lavorazione.py` | **nessuna route**: `elabora_ddt()`, `elabora_fattura()` |
| `fornitori.py` | `/api/fornitori*` |
| `punti_vendita.py` | `/api/punti-vendita` |
| `documenti.py` | `/api/documents*`, `/api/pdf/{id}.pdf`, `/api/elaborazione`, `/riepilogo`, `/estrai-ddt` |
| `fatture.py` | `/abbina-fattura`, `/api/fatture*`, `/api/ddt/senza-fattura`, `/api/pdf-fattura/{id}.pdf` |
| `ingresso.py` | `/api/{ddt,fatture}/carica\|scansiona`, `/api/ingresso`, i tre `lavoro_*` |
| `impostazioni.py` | `/api/pianificazione*`, `/api/notifiche/prova`, `/api/configurazione`, `/api/motore` |

- **Nessun `prefix` sui router, percorsi assoluti e completi**: cercare `"/api/fatture/attese"` deve trovare **una riga sola**.
- **L'ordine conta su due livelli**: dentro il modulo (`/api/fatture/attese` prima di `/api/fatture/{id}`) e fra gli `include_router` (`ingresso` prima di `fatture`, altrimenti `/api/fatture/carica` diventa l'id di una fattura). **Dopo aver toccato le route riconta le 38 rotte da `GET /openapi.json`** (33 percorsi): una route mangiata da una parametrica non dà nessun errore all'avvio.
- **Le dipendenze vanno in una direzione sola**: i router importano da `supporto.py` e `lavorazione.py`, mai il contrario.
- **Le route con corpo bloccante restano `def` e non `async def`**: dentro una `async` tengono fermo l'event loop e *nessun'altra* richiesta viene servita durante un'estrazione, compresa `/api/elaborazione` (cioè la barra). Vale per `/estrai-ddt`, `/rianalizza`, `crea_documento_manuale`, `update_document`, `unisci_documenti`.

**D.D.T.** — `POST /estrai-ddt` (upload → split → estrazione → classificazione → salvataggio → accorpamento a fine batch) · `GET /riepilogo?da=<ISO8601>` · `GET/PUT/DELETE /api/documents[/{id}]` · `PUT /api/documents/{id}/stato` · `POST /api/documents/manuale` (multipart) · `POST /api/documents/unisci` (`{"ids": [...]}`, ordine significativo) · `POST /api/documents/{id}/rianalizza` · `GET /api/elaborazione` · `GET /api/pdf/{id}.pdf`.

**Anagrafiche** — `GET/PUT /api/fornitori` · `PUT /api/fornitori/partita-iva` (400 se il Luhn fallisce; con `id` riallinea anche il documento) · `GET /api/punti-vendita` (**non fallisce mai**: senza database torna elenco vuoto).

**Fatture** — `POST /abbina-fattura` (lettura, deduplica, segnalazioni, archiviazione **senza abbinamento**, stato `DA_ABBINARE`) · `POST /api/fatture/abbina-tutte` (**dichiarata prima** di `/{id}/accoppia`) · `GET /api/fatture[/{id}]`, `DELETE /api/fatture/{id}` · `POST /api/fatture/{id}/accoppia` (ABBINA + primo tempo di ACCOPPIA) · `POST /api/fatture/{id}/conferma-accoppiamento` (la firma) · `GET /api/fatture/attese?giorni=N` (**dichiarata prima** di `/{id}`) · `POST /api/fatture/ricontrolla` · `GET /api/ddt/senza-fattura?giorni=N` · `GET /api/pdf-fattura/{id}.pdf` (per una non accoppiata lo costruisce al volo, header `X-Fascicolo-Anteprima: 1`).

**Ingresso e impostazioni** — `POST /api/{ddt,fatture}/carica` · `GET /api/ingresso` (il badge su *Analizza*) · `POST /api/{ddt,fatture}/scansiona` (elaborano e **rimuovono i file riusciti**; quella dei D.D.T. accetta `{"punto_vendita": "<codice>"}`, risolto **una volta per batch**, e la risposta riporta il punto vendita **applicato**, non quello chiesto) · `GET/PUT /api/configurazione` · `GET /api/pianificazione` (orario, prossima esecuzione, ultimo esito, **senza password**) · `POST /api/pianificazione/{lavoro}/esegui` (sincrona) · `POST /api/notifiche/prova`.

**`GET /api/motore`** — se Ollama risponde e ha il modello. **Non fallisce mai**: un motore spento è un **200** con `pronto: false`, perché distinguere "spento" da "non ho potuto controllare" è il punto. La versione che *ferma* un'analisi è `esigi_motore_pronto()`, con un **503** e non un 500: non è un guasto di questo servizio ma una dipendenza esterna, e chi lo riceve deve capire che riprovare ha senso. Senza, un Ollama spento si scopre a metà lavoro, con le prime pagine archiviate e le altre no.

### Flusso fatture elettroniche (`src/fatture/`)
- **Il modello non entra mai in questo flusso.** In FatturaPA i riferimenti ai DDT sono già in `<DatiDDT>` e il cedente nell'header: la regola è *tutta* esatta, quindi il flusso è interamente Python — nessuna coda sulla GPU, risposta in millisecondi. Se ti sembra che serva il modello, quasi sempre il dato è già in un tag.
- **`lettore_xml.py`** — sbusta `.xml` e `.xml.p7m` (CAdES) riconoscendoli **dal contenuto, non dall'estensione** (dallo SdI arrivano `.xml` che dentro sono buste e viceversa), con `asn1crypto` e un fallback che ritaglia il payload cercando `<?xml` nel DER: meglio un XML recuperato a forza bruta che una fattura persa.
  - **Naviga per localname, ignorando i namespace** (`p:FatturaElettronica`, `ns2:`, o niente).
  - Un file può contenere **più `<FatturaElettronicaBody>`**: `leggi_fattura()` torna una lista.
  - I `<DatiDDT>` vengono **deduplicati**: il blocco è emesso una volta per riga, e una fattura di 40 righe sembrerebbe legata a 40 DDT identici.
  - Numeri e date passano dalle stesse `normalizza_*` del lato DDT: è ciò che rende confrontabili `0081197691` e `81197691`.
- **Le due forme, decise da `classifica_fattura()` sulla struttura dell'XML** (non aggiungere euristiche sul `TipoDocumento`):
  - **differita** — DDT in `<DatiDDT>`, **1 → N**: si cercano quei numeri.
  - **accompagnatoria** — nessun `<DatiDDT>` perché il DDT *è* la fattura: si cerca il **numero della fattura**, **1 → 1** (`riferimenti_fattura()` ne costruisce uno sintetico, `origine: "numero_fattura"`).
  - **senza_ddt** — né riferimenti né trasporto (consulenze, note di credito): non c'è merce da agganciare.
  - Il segnale che separa accompagnatoria da senza_ddt è **`<DatiTrasporto>`**, non il `TipoDocumento`: TD01 vale per entrambe e TD24 compare anche su differite senza `<DatiDDT>`. Si preferisce un tag che *descrive* a uno che *etichetta*.
  - **Il tipo decide chi ha diritto di aspettare**: differita e accompagnatoria vanno in coda, una senza_ddt chiude `NON_ABBINATA` — registrare un "DDT mancante" inventerebbe un documento mai citato e solleciterebbe per sempre.
  - `abbina_fattura()` torna `(stato, righe, tipo)`, e `tipo_abbinamento` finisce nel registro: al ricontrollo i riferimenti da soli non direbbero più da dove venivano.
- **`abbinatore.py`** — tre esiti per riferimento:
  - `abbinato`: `numero_ddt` identico **e** fornitore compatibile (`stesso_fornitore()`). Il solo numero non basta: "123" si ripete fra fornitori diversi.
  - `probabile`: numero identico ma fornitore diverso, oppure fornitore e data uguali con numero simile ≥ `SOGLIA_NUMERO_SIMILE` (0.7). **È il caso che dà valore al flusso**: la fattura è esatta, quindi un quasi-match segnala una cifra letta male sul DDT, non un DDT mancante. Non viene mai promosso da solo.
  - Se più DDT certi rispondono allo stesso riferimento decide la data; se non basta **degrada a `probabile`** (`ambiguo`) invece di sceglierne uno a caso.
  - Stato: `ABBINATA` solo se **tutti** i riferimenti sono `abbinato`, `NON_ABBINATA` se non c'è niente da aspettare, `IN_ATTESA` altrimenti. **`PARZIALE` non esiste**: un abbinamento incompleto non è un esito ma una coda.
  - `riepilogo_attesa(righe)` conta `mancanti` (nessun DDT) e `da_confermare` (un `probabile`): due code diverse — la prima si chiude da sola alla scansione, la seconda no.
  - `annota_ddt_abbinati()` scrive un campo `fattura` sulle voci DDT. **È solo un'annotazione** (il DDT non cambia stato né si sposta) e si chiama **solo alla chiusura**: prima scriverebbe un riferimento che può ancora cambiare.
  - La P.IVA del cedente **non** si usa per abbinare i DDT: sul DDT è letta, e un abbinamento deciso su una cifra sbagliata sarebbe peggio di quello attuale, che almeno degrada a `probabile`.
- **`fascicolatore.py`** — il PDF unico, in quest'ordine: riepilogo generato (senza, il fascicolo non direbbe da dove viene, visto che la fattura è un XML; per un'accompagnatoria l'allegato si chiama "DOCUMENTO" e non "DDT") → copia di cortesia da `<Allegati>` → i PDF dei DDT nell'ordine in cui la fattura li cita. **Su disco solo per le pratiche chiuse**; per una in coda si costruisce in un file temporaneo (`anteprima_fascicolo`, cancellato da un `BackgroundTask`).
- L'**originale XML/P7M** si archivia subito, anche per le fatture in attesa: il PDF è un derivato, il documento fiscale è l'XML.

### Coda delle fatture (`src/fatture/coda.py`)
Una fattura che cita 3 DDT di cui 1 scansionato **non è un fallimento**: è una pratica aperta in `ATTESA.json`, ricontrollata a ogni evento che porta DDT nuovi.
- **Nessun filtro sul fornitore, solo segnalazioni.** Da quando le fatture si caricano a mano, chi le carica ha già deciso che gli interessano, e un filtro che le scarta in silenzio fa sparire il lavoro appena fatto. `verifica_fornitore_fattura()` torna anomalie (`piva_assente`, `piva_diversa`, `fornitore_nuovo`) e la fattura si archivia **comunque**. Non reintrodurre uno scarto silenzioso.
  - Le segnalazioni **restano attaccate alla pratica** (`voce["segnalazioni"]`, chiave **assente** se non c'è niente da dire): chi apre la fattura tre giorni dopo deve vedere perché non torna. Si vedono nella `BarraIngresso`, nell'`InvoiceModal` e nella mail.
  - `piva_diversa` si scopre cercando la voce **per nome** (`trova_fornitore_simile`), non con `trova_voce_fornitore()`: quella torna `None` sia per uno sconosciuto sia per uno con P.IVA diversa, e sono due situazioni opposte.
  - Se l'anagrafica non è aggiornabile la fattura si archivia lo stesso.
- **Deduplica per identità fiscale:** `chiave_fattura()` è `(partita_iva, numero_fattura, data_fattura)`, cercata in ATTESA **e** in FATTURE. Risposta `stato: "DUPLICATA"`.
- **Cinque punti chiamano `ricontrolla_fatture_in_attesa(motivo)`**, che sono tutti i modi in cui un DDT diventa abbinabile: fine batch di `/estrai-ddt`, inserimento manuale, `PUT /api/documents/{id}` (la correzione del `numero_ddt` è il caso che sblocca i `da_confermare`), unione manuale, rianalisi. Ogni risposta porta `fatture_sbloccate`. **Se aggiungi una strada che crea o corregge un DDT, agganciala anche tu.**
  - L'helper **non solleva mai**, e dentro `ricontrolla_attese()` ogni fattura ha il suo `try/except`: una voce corrotta non deve svuotare la coda delle altre.
- **L'attesa dall'altro lato:** `ddt_senza_fattura(giorni)` elenca i DDT che nessuna fattura ha agganciato. Qui **non serve nessun ricontrollo ciclico**: ogni fattura nuova è confrontata con *tutti* i DDT archiviati. `KO` è escluso (lì il numero non è stato letto affatto).
- **Tre soglie in `configurazione.py`**, tre perché le attese non si assomigliano: `GIORNI_ATTESA_FATTURA` (30, manca una bolla da cercare in magazzino), `GIORNI_ATTESA_DDT` (30, la bolla c'è ed è la fattura a non essere arrivata — dipende dal giro di fatturazione del fornitore), `GIORNI_ATTESA_ACCOPPIAMENTO` (7, aspetta solo un click e dipende solo da noi). Partono uguali le prime due, ma si regolano separatamente. Ogni voce porta `motivo_attesa` (`da_abbinare` / `pronta`): la mail deve dire **quale** pulsante serve.
- Il lock è un `threading.RLock`: le route sincrone girano nel threadpool e due ricontrolli possono sovrapporsi su `ATTESA.json`.

### L'accoppiamento manuale
**L'automatismo prepara, l'uomo firma.** `POST /abbina-fattura` archivia e basta, stato **`DA_ABBINARE`**, con le righe già costruite dai riferimenti (`righe_da_abbinare()`). Il confronto lo chiede una persona: **ABBINA** su una riga o **Abbina tutte**.
- `ricontrolla_attese()` **salta le `DA_ABBINARE`** salvo `includi_da_abbinare=True`, che passa **solo "Abbina tutte"**. Non passarlo "per sicurezza". Così i cinque agganci continuano ad aggiornare le pratiche per cui l'abbinamento è già stato chiesto (una correzione al `numero_ddt` sblocca ancora una pratica ferma da settimane, l'effetto più utile del sistema) senza eseguirne di nascosto uno che nessuno ha chiesto.
- Stati: `DA_ABBINARE` → `ABBINATA` / `IN_ATTESA` / `NON_ABBINATA`. Solo `ABBINATA` più la firma chiude.
- **Due tempi:** `proponi_accoppiamento()` rifà il confronto e riscrive la voce in coda **senza toccare l'archivio** (salva con `salva_registro`, non `aggiorna_registro`, che accoda); `conferma_accoppiamento()` è la firma e chiama `_chiudi()`. Senza il primo tempo si firmerebbe alla cieca. Su una pratica già confermata **entrambe rifiutano**.
- **`_chiudi()` ha un solo chiamante** (il pulsante ACCOPPIA): toglie `attesa`, scrive `completata`, costruisce il fascicolo, chiama `annota_ddt_abbinati()`, sposta la voce in `FATTURE.json`. `registra_fattura()` e `ricontrolla_attese()` non chiudono più niente.
- **Si può confermare anche un abbinamento incompleto**, con l'avviso in evidenza: nel fascicolo finiscono solo i DDT trovati. Chi rivede può sapere che una bolla non arriverà mai, il sistema no.
- **`ATTESA.json` contiene tre cose diverse** — chi aspetta una bolla (`IN_ATTESA`), chi aspetta che qualcuno chieda l'abbinamento (`DA_ABBINARE`), chi aspetta la firma (`ABBINATA`) — e chi la legge deve dire quale guarda. `fatture_in_attesa()` tiene **solo `IN_ATTESA`** perché alimenta il sollecito: mandare qualcuno a cercare una bolla già archiviata farebbe smettere di leggere la mail.
- **`fatture_sbloccate` significa "diventata pronta da accoppiare"**, non "chiusa", e si annuncia **solo alla transizione**.
- **`in_coda` è calcolato in lettura**, come `status`: lo stato da solo non distingue `ABBINATA` pronta da `ABBINATA` confermata.
- **Il percorso del fascicolo sta su `voce["fascicolo"]`**, non si ricostruisce dall'id (fallback `FATTURE/lette/{id}.pdf` per le pratiche pre 2026-09-08).
- Un D.D.T. agganciato ma non firmato risulta ancora "senza fattura", ed è corretto. **Cancellare la fattura libera i suoi D.D.T.** (`dimentica_fattura()`, risposta `ddt_liberati`): è il modo in cui si disfa un accoppiamento sbagliato, e senza, quei DDT punterebbero a una pratica inesistente e sparirebbero dal sollecito.

### Frontend (`frontend/src/`)
Diviso nelle **tre entità del dominio** più le impostazioni, non nei layer: `Sidebar` naviga fra `DdtSection`, `FattureSection`, `SuppliersManager`, `ConfigSection`.
- **Guscio:** colonna sinistra richiudibile (`Sidebar.jsx`) + `TopBar.jsx` dentro il contenuto. Le sezioni cresceranno (ogni anagrafica è una voce) e in orizzontale ogni voce toglie spazio ai pulsanti globali. **L'elenco delle sezioni sta in `sezioni.js`**, letto sia dalla barra sia dalla `TopBar`: un nome scritto in due posti diverge.
  - Aperta/chiusa è stato della `Sidebar` (in `localStorage`), non di `App.jsx`: la larghezza la gestisce il flex. È `sticky` e non `fixed` (nessun margine da tenere allineato), e il contenuto ha `min-width: 0`, altrimenti una tabella larga spingerebbe la barra fuori schermo.
- **Tema (`useTema.js`)** — `data-bs-theme` sull'`<html>`, da cui discendono le variabili Bootstrap 5.3; interruttore in fondo alla barra, scelta in `localStorage`, preferenza di sistema come default. **Uno script inline in `index.html` la rifà prima che React monti**, altrimenti la pagina lampeggia nel tema sbagliato: le due letture vanno tenute allineate.
  - **Niente colori scritti a mano**: non `bg-dark`/`text-light`/`border-secondary` né esadecimali in `index.css`, ma `bg-body*`, `text-body*`, `border`. Sui componenti che si tematizzano da soli (`form-control`, `card`, `modal-content`, `page-link`, `table`) la classe scura va tolta, non tradotta. **L'unica eccezione è ciò che sta sopra a un fondo di colore fisso** (badge su una pill arancione, testo su un bottone pieno).
- **`App.jsx` è la fonte unica di `documents`, `fatture` e dei modali**, non un router che monta stati indipendenti: è ciò che rende possibili i due passaggi fra flussi (`apriDocumento` da una riga del fascicolo, `apriFattura` dalla colonna *Fattura*). Non far rifetchare gli stessi elenchi a una sezione.
- **Le fatture sbloccate si dicono**: ognuna delle cinque risposte con `fatture_sbloccate` passa da `segnalaSbloccate()` e finisce in un `Toast`, altrimenti l'effetto più utile del sistema resterebbe invisibile perché avviene in un'altra sezione.
- **I badge di menu contano solo ciò che aspetta un intervento** (CHECK; fatture `in_coda`/`IN_ATTESA`; P.IVA da confermare): un numero che non cala mai smette di essere letto.
- **`BarraIngresso`** — *Aggiungi documento* / *Analizza*, una sola per D.D.T. e fatture (cambiano estensioni ed endpoint). **Caricare e analizzare restano due gesti**: si accodano dieci bolle in pochi secondi e si fa partire l'analisi (minuti) una volta sola.
- **`DdtSection`** — `Stats`, `BarraIngresso` (col menu del punto vendita), `ProcessingBar`, `SearchBar`, `MergeBar`, `Dashboard` (tab OK/CHECK/KO) → `DocumentTable` o `GrigliaPuntiVendita`. Revisione in `ComparisonModal` (PDF a sinistra, dati a destra, rianalisi, stato forzabile, conferma P.IVA, download). Stati e colori in `etichetteDdt.js`.
- **`Dashboard`** — i tre tab e, in fondo alla stessa riga, il pulsante che **scambia** la tabella con la griglia (`vista`, stato di `DdtSection`). Interruttore a due posizioni e non un quarto tab: i tab dividono lo *stesso* elenco per esito, la griglia lo guarda tutto intero (e mentre è aperta restano cliccabili ma sbiaditi). La griglia arriva come `children`.
- **`GrigliaPuntiVendita`** — le stesse bolle raccolte in una cartella per punto vendita e, dentro, un mazzetto per fornitore. La tabella risponde a *"com'è andata la lettura"*, la griglia a *"cosa è arrivato e da chi"*.
  - **Cartelle chiuse all'apertura** (una alla volta): trenta negozi aperti rifarebbero la tabella. La cartella **unica** si apre da sé. **Si disegna dai documenti, non dall'anagrafica**: un punto vendita senza bolle non compare (l'anagrafica serve solo a scrivere per esteso il nome di un codice, e vince su `punto_vendita_nome` scritto sul documento). C'è una cartella **Senza punto vendita** in fondo: i documenti pre 2026-09-14 sono la maggioranza dell'archivio.
  - Riceve `filteredDocuments` e non `documents` (la ricerca deve valere anche qui). **Nessun fetch suo, nessuna route nuova.** Un elenco vuoto **non rende `null`** ma lo dice: è stata chiesta con un click.
- **`FattureSection`** — conteggi, filtri (fra cui **Da abbinare** e **Da accoppiare**, gli unici che contano un'azione), ricerca **anche sui numeri D.D.T. citati** (si parte dalla bolla che si ha in mano), `BarraIngresso`, *Abbina tutte*, *Ricontrolla coda*, e in fondo il pannello dei **D.D.T. senza fattura**.
  - **Su ogni riga un pulsante solo, ma non sempre lo stesso**: `azionePratica()` torna `abbina` (blu, cerca e non scrive) o `accoppia` (giallo, firma e crea il fascicolo). Chiamarli entrambi "Accoppia" farebbe sembrare irreversibile anche il primo.
- **`SuppliersManager`** — anagrafica in ordine alfabetico (`localeCompare('it')`); `addNewSupplier` imposta la ricerca sul nome inserito, altrimenti una voce nuova nascerebbe fuori pagina. Contiene P.IVA (filtro *P.IVA da confermare*), `confermato`, `indirizzi_vietati`, le **regole mirate**, i **nomi alternativi**, i tre flag, *Modifiche non salvate*. Dopo la PUT rilegge, perché `unifica_memoria()` può aver fuso voci.
- **`ConfigSection`** — impostazioni per `gruppo`, ognuna col badge dell'**origine** e il testo di aiuto; il campo si adatta al tipo (`<input type="time">`, `<select>`, `password`). In cima `PannelloLavori`: i tre lavori con orario, **prossima esecuzione** ed **esito dell'ultimo**, più "Esegui adesso" e "Invia mail di prova" — un lavoro notturno rotto non lo scoprirebbe nessuno fino al mattino.
- **Paginazione a 50 righe (`Paginazione.jsx`)**, uguale nelle tre sezioni: `usePaginazione(elementi, chiaveVista)` ritaglia una lista **già filtrata e ordinata**. La `chiaveVista` descrive *cosa* si guarda (tab/filtro + ricerca) e riporta a pagina 1 quando cambia; **non ci va la lunghezza della lista**, altrimenti cancellare una riga rimanderebbe all'inizio. Il taglio è **solo visivo**: conteggi, badge e selezione lavorano sulla lista intera.
- L'URL dell'API è `import.meta.env.VITE_API_URL` (fallback `http://localhost:8000`), iniettata **in fase di build**: `frontend/Dockerfile` ha `ARG VITE_API_URL` e il compose la passa in `build.args`.

### Visualizzare una fattura (`InvoiceModal.jsx`)
Una fattura è un XML: il modale chiede il PDF a `GET /api/pdf-fattura/{id}.pdf`, che per una pratica chiusa serve il fascicolo e per una in coda lo costruisce al momento.
- **Il PDF si scarica come blob** invece di puntarci l'`iframe`: serve a leggere `X-Fascicolo-Anteprima` (da cui il banner "anteprima provvisoria") e a mostrare un'attesa. Per questo `main.py` dichiara `expose_headers=["X-Fascicolo-Anteprima"]`: da cross-origin il browser nasconde gli header non standard.
- **È il posto in cui si firma.** Su una `DA_ABBINARE` c'è **un solo pulsante**, "Abbina": firmare prima di guardare produrrebbe un fascicolo vuoto. Su una confermata c'è il lucchetto "Accoppiata il …". Rifare la ricerca **non cambia l'id**, quindi l'effetto che scarica il blob dipende anche da `ultimo_controllo`.
- **I dati non sono modificabili** (vengono da un documento firmato): quando un abbinamento non torna l'errore è quasi sempre nella lettura del D.D.T., e "Apri il D.D.T." porta lì.
- **Ogni riga dice cosa fare:** `da_abbinare` → premi ABBINA; `probabile` → il documento c'è col numero letto male, si corregge; `non_trovato` → la bolla va cercata in magazzino.
- Montato con `key={fatturaAperta?.id}`: cambiando fattura si rimonta e blob, attesa e flag ripartono puliti.

### Inserimento manuale (`POST /api/documents/manuale` + `ManualEntryModal.jsx`)
- **Nessuna normalizzazione** sui dati digitati, per coerenza con `PUT /api/documents/{id}`. **Unica eccezione la `partita_iva`** (`normalizza_partita_iva`): non è un testo ma una chiave, e `IT 00159560366` e `00159560366` devono essere lo stesso valore. Digitata a mano entra in anagrafica già **confermata**.
- **Lo stato lo decide `determina_stato()` come per tutti**, non è forzato a `OK`: un inserimento incompleto finisce in `CHECK` e resta visibile. 400 solo se tutti i campi sono vuoti.
- **I PDF si archiviano com'è (`shutil.copyfile`)**, non rasterizzati. Solo le immagini passano da `salva_pdf_multipagina`.
- La voce porta `"inserimento": "manuale"` e il fornitore **entra comunque in anagrafica**: è anzi la fonte più affidabile, perché non passa da una lettura.

### Rianalisi (`POST /api/documents/{id}/rianalizza`)
Rimanda al modello il PDF **già archiviato**, senza ricaricare nulla. Serve soprattutto dopo aver aggiunto una regola in anagrafica.
- Su un multi-pagina le pagine si rileggono una per una e si fondono con `unisci_dati_pagina`: **non** si rifà il confronto numero/fornitore, perché appartengono già allo stesso DDT.
- **I dati precedenti vengono sostituiti**, comprese le correzioni manuali: è un'azione esplicita e il frontend lo dice nel `confirm`. Per questo il pulsante sta nel modale, col PDF a fianco.
- Se lo stato cambia, voce e PDF si spostano **mantenendo id e metadati**, più `rianalisi: <timestamp>`.
- Per i documenti nati dalla pipeline il PDF archiviato è già un raster: alzare `PDF_RENDER_ZOOM` migliora solo le estrazioni *nuove*.

### Avanzamento (`stato_elaborazione.py` + `GET /api/elaborazione` + `ProcessingBar.jsx`)
Un'estrazione dura minuti e la dashboard sembrava ferma. Un registro in memoria tiene i lavori attivi; la barra mostra file, pagina su totale e tempo trascorso, e ricarica i documenti quando l'ultimo lavoro finisce.
- Lo stato è **volutamente in memoria** (`threading.Lock` + dizionario): descrive cosa succede *adesso*, e dopo un riavvio non c'è nulla da ricostruire. Il lock serve perché le route sincrone girano nel threadpool.
- `pagine_totali` resta `0` finché il PDF non è diviso: in quella fase il frontend mostra una barra **indeterminata** invece di una percentuale inventata. `termina()` è in un `finally`.
- **Il polling ri-renderizza, quindi niente valori nuovi calcolati nel corpo dei componenti**: l'URL del PDF nel `ComparisonModal` aveva un `?t=${Date.now()}` e l'iframe si ricaricava ogni 2 s sotto gli occhi di chi revisionava. Ora è in `useMemo` con chiave `id` + `rianalisi`.
- Polling **ogni 2 s anche a vuoto**: è il prezzo per vedere partire la barra su lavori che la dashboard non ha lanciato. La riga di access log è silenziata da `FiltroPollingBarra`, altrimenti 30 righe al minuto renderebbero illeggibili i log pagina-per-pagina.

### Evoluzione prevista: righe articolo
Obiettivo del committente (2026-08-30, non implementato): estrarre anche **i dati dei singoli prodotti** (codice, descrizione, quantità, UM, prezzo). Impatti:
- cambio strutturale del JSON (da 6 campi piatti a testata + lista righe): tocca `classificatore.py` (i `CAMPI_OBBLIGATORI` restano quelli di testata?), `raggruppatore`/`accorpatore` (unendo due pagine le righe vanno **concatenate**, non sovrascritte) e la tabella del frontend;
- è il caso che più soffre la risoluzione (corpo piccolo): vanno rivalutati `PDF_RENDER_ZOOM` e `num_ctx`, perché l'output diventa molto più lungo.

### Il guardiano (`uptime-kuma`)
`louislam/uptime-kuma:2` su `http://<server>:3001`, dati in `uptime-kuma/dati/` (ignorato da git). **Non elabora niente e nessun altro servizio lo conosce**: guarda gli altri tre da fuori e avvisa una persona, che è l'unica cosa che questo sistema non può fare da sé — un backend giù non manda nessuna mail per dire che è giù.
- **Niente `depends_on`** (lo farebbe partire *dopo* ciò che sorveglia, cioè tacere nel caso che deve raccontare) e **niente rete dedicata**: sulla rete di default raggiunge gli altri **per nome**, l'unica forma che resta valida se la macchina cambia indirizzo.
- **Nessun `healthcheck` nel compose**: l'immagine ne porta uno suo (`extra/healthcheck`). `TZ=Europe/Rome` per confrontare un'interruzione coi log del backend senza tradurre l'ora.
- **Al primo accesso chiunque arrivi crea l'account di amministratore** e la porta non è limitata a `127.0.0.1` (l'interfaccia si apre dai PC dell'ufficio): va configurata subito dopo il primo avvio.

**I monitor vivono nel database di Kuma, non nel compose.** Sono cinque, e l'elenco sta qui perché è l'unico posto in cui si rileggono.

| cosa | tipo | dove | domanda |
| --- | --- | --- | --- |
| Backend vivo | HTTP(s) | `http://api-gestione-fatture:8000/api/elaborazione` | l'API risponde? |
| Motore AI | **Json Query** | `http://api-gestione-fatture:8000/api/motore`, query `pronto`, atteso `true` | si può analizzare una bolla? |
| Ollama | HTTP(s) | `http://10.1.20.25:11434/api/tags` | la macchina della GPU è su? |
| Anagrafiche | **PostgreSQL** | `postgresql://gestione_fatture:gestione_fatture@postgres-gestione-fatture:5432/gestione_fatture` | il database risponde? |
| Dashboard | HTTP(s) | `http://frontend-gestione-fatture:80/` | Nginx serve la build? |

- **Il motore AI vuole *Json Query*, non un HTTP normale**: `GET /api/motore` non fallisce mai e un motore spento è un **200**. Un monitor sul solo codice HTTP resterebbe muto esattamente nell'unico caso per cui esiste.
- **`/api/elaborazione` è la sonda giusta per il backend**: stato in memoria (nessun disco, nessuna query) e access log già silenziato.
- **Ollama si guarda anche da solo**: due monitor distinti separano *"il nostro backend è giù"* da *"la macchina della GPU è giù"*, che si risolvono in due stanze diverse. È il guasto del 2026-09-15 (porta 11434 in timeout dalla LAN), scoperto solo quando un operatore ha premuto *Analizza*.
- **Le notifiche si configurano dentro Kuma** (stesso SMTP del backend). La duplicazione è voluta: un guardiano che spedisse attraverso il servizio che sorveglia tacerebbe proprio quando quel servizio è giù.
- **Quello che Kuma NON sa fare è il lavoro arretrato**: una fattura ferma da trenta giorni resta la mail di `sollecito.py` e i badge della dashboard. Un monitor rosso perché manca una bolla verrebbe messo a tacere entro una settimana, e con lui i monitor veri.

### Nota sul repository
`n8n_snippets/` (6 file) è **tracciato apposta**: è la fonte storica delle tre mail, oggi in `src/notifiche/`. Il codice in esecuzione non lo legge. `n8n_config/` è stato cancellato il 2026-09-11 (3.615 file, 327 MB di stato runtime) per decisione del committente; si recupera da un commit precedente (`git checkout <commit> -- n8n_config`), ma **cancellarlo non ha recuperato spazio in git**: i blob restano nella storia (`.git` pesa ~106 MB).

---

## 🎯 Regole per l'Assistente (Claude)
1. **Se è una regola esatta va in Python, non nel prompt.** Formati → `normalizzatore.py`; divieti → `indirizzi_vietati`/`mai_fornitore`; duplicati → `impronte.py`. Un 7B ignora i divieti, un confronto di stringhe no.
2. **Se il modello sbaglia *dove* guarda**, la risposta non è il prompt né un modello più grande: è una `regole_campo` sull'**etichetta stampata** (0/6 nel prompt, 16/16 come domanda mirata). **Mai una regola al negativo.** E non dare la colpa alla lunghezza del prompt senza misurarla.
3. **Non toccare le soglie senza rimisurare** (`SOGLIA_SIMILARITA` 0.85, `COPERTURA_MINIMA_TOKEN` 0.6, `SOGLIA_SIMILARITA_FORNITORE` 0.5, `SOGLIA_NUMERO_SIMILE` 0.7, `PDF_RENDER_ZOOM` 2.5), e non introdurne dove non ce ne sono: identità di pagina, punto vendita e cedente di una fattura si decidono per **confronto esatto**. Lì un falso positivo non è un campo brutto da guardare, è un documento buttato via.
4. **Rispetta la differenza fra Destinatario e Luogo di Consegna**: è il caso che ha fatto nascere metà di questo sistema.
5. **La divisione è per flusso, non per layer.** Un modulo nuovo va in `src/ddt/` o `src/fatture/`, in `comune/` solo se serve **davvero** a entrambi. L'anagrafica si chiama `memory_manager.py`.
6. **Una route nuova va nel modulo della sua entità in `src/api/`**, mai in `main.py`: niente `prefix`, nessun import all'indietro, e **dopo averle toccate riconta le rotte da `/openapi.json`** — una route mangiata da una parametrica non fa fallire l'avvio. Le route con corpo bloccante restano **`def`**.
7. **Un'anagrafica nuova porta il proprio modulo** con schema e query: `database.py` resta senza tabelle e le decisioni restano fuori dall'archivio. `DATABASE_URL` sta nell'ambiente e vuota significa "torna al JSON".
8. **Nel database ci vanno le anagrafiche, non i registri**: i JSON restano accanto ai PDF e agli XML che descrivono, e si spostano insieme a loro.
9. **I valori configurabili si leggono con `valore()` dove servono**, mai in una costante di modulo. I percorsi non ci vanno.
10. **L'orologio è `pianificatore.py`** e le azioni gliele passa `main.py`: niente secondo scheduler, niente `cron` nell'immagine. Vuoto = non pianificare.
11. **Le mail non devono mai far fallire ciò che stava andando bene** (`invia_silenzioso()`), e una mail che direbbe "niente da segnalare" non si manda.
12. **Nessuna pratica si chiude o si abbina da sola**: `_chiudi()` ha un chiamante solo e `ricontrolla_attese()` salta le `DA_ABBINARE`. Non passare `includi_da_abbinare=True` "per sicurezza". L'automatismo prepara, l'uomo firma.
13. **Se aggiungi una strada che crea o corregge un DDT**, chiama `ricontrolla_fatture_in_attesa(motivo)` (oggi cinque punti) e fai passare `fatture_sbloccate` da `segnalaSbloccate()`.
14. **Se aggiungi una strada che archivia o ricostruisce una voce**, portati dietro `firme_pagine`, `punto_vendita`, `fornitore_critico`, `consegna_discorde`: altrimenti l'accorpamento rimette in `OK` ciò che doveva restare in `CHECK` e una bolla già vista ripassa come nuova.
15. **I tre flag dell'anagrafica li mette solo l'utente.** Un `identificativo_estero` non va mai dentro `partita_iva`. Una P.IVA non si attribuisce mai per esclusione.
16. **Il flusso fatture non chiama mai il modello**: se sembra servire, il dato è già in un tag FatturaPA. Le due forme le decide `classifica_fattura()` sulla struttura, non sul `TipoDocumento`.
17. **Nel frontend non si scrive un colore a mano** (`bg-body*`, `text-body*`, `border`), salvo sopra a un fondo fisso. `App.jsx` resta la fonte unica di `documents` e `fatture`, e una sezione nuova va in `sezioni.js`.
18. **I log restano leggibili in tempo reale** (`PYTHONUNBUFFERED=1`), i percorsi si leggono da `percorsi.py`, i timestamp da `tempo.py`.
19. **Il guardiano sorveglia i servizi, non il lavoro arretrato.** Il monitor del motore va in **Json Query su `pronto`**, perché `/api/motore` non fallisce mai.
