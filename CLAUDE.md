## 🤖 AREA: Motore AI Locale per Estrazione D.D.T. (Fatturazione)
Monorepo con due servizi containerizzati (Docker + `docker-compose`, orchestrati insieme a n8n):
- `backend/` — microservizio Python (FastAPI) che analizza scansioni di D.D.T. italiani.
- `frontend/` — dashboard web React per revisionare/correggere i documenti estratti.

### Stack Tecnologico
- **Backend:** Python 3.12, FastAPI + Uvicorn, PyMuPDF (`fitz`) per il rendering PDF→immagine, Pillow per il riassemblaggio PDF.
- **Frontend:** React 19 + Vite, Bootstrap 5, `lucide-react` (icone), `react-pdf`/iframe per l'anteprima PDF, Nginx per servire la build in produzione.
- **Container:** Docker + `docker-compose` (3 servizi: `api-gestione-fatture`, `frontend-gestione-fatture`, `n8n`).
- **Infrastruttura Hardware:** AMD Ryzen 7 5700X3D, 32GB RAM, AMD Radeon RX 7600 XT, NVMe SSD.
- **Motore AI:** Ollama su una **macchina separata in LAN aziendale** (`10.1.20.25:11434`, esposto con `OLLAMA_HOST=0.0.0.0`), raggiunta dal container backend tramite la variabile `OLLAMA_HOST` in `docker-compose.yml` — la libreria python `ollama` la legge da sola, in `llm_engine.py` non c'è nessun host hardcoded (spostato dal locale `host.docker.internal` il 2026-09-02). È una GPU **condivisa** con altri modelli (`qwen2.5-coder:32b`, `qwen3.6:35b`, `deepseek-r1:32b`): un'estrazione può attendere se qualcun altro la sta occupando. L'`extra_hosts: host.docker.internal` resta nel compose perché serve ancora a n8n.
- **Modello Attuale:** `qwen2.5vl:7b` (Modello Vision multimodale nativo — nome esatto usato in `src/llm_engine.py`, senza trattino tra "qwen2.5" e "vl").
- **Automazione:** n8n (container separato) monitora `fatture_da_leggere/`, chiama l'API di estrazione e gestisce notifiche/report; dati persistiti in `n8n_config/`.
- **Storico Decisioni:** Inizialmente usava Surya OCR + Llama 3.1 testuale. È stato scartato a favore di un approccio "Pure Vision" (Qwen2.5-VL) per azzerare la perdita di contesto spaziale, eliminando la necessità di estrarre preventivamente il testo grezzo.

### Logica di Estrazione (Prompting e Regole Rigide)
Il modello (`src/llm_engine.py`, funzione `estrai_dati_da_immagine`) analizza le immagini dei D.D.T. — una per pagina, ottenute da `src/pdf_processor.py` a ~180 DPI — e restituisce ESCLUSIVAMENTE un JSON con i seguenti campi:
- `fornitore`: L'azienda emittente (es. S.p.A., S.r.l.). IGNORA categoricamente vettori, diciture di trasporto, indirizzi email o siti web.
- `numero_ddt`: Codice alfanumerico esatto (rimuovendo gli zeri iniziali *solo* se puramente numerico; se contiene un prefisso alfanumerico tipo `SGE/0705580` resta invariato — logica applicata lato Python dopo la risposta del modello, non dal prompt).
- `data_ddt`: Formato GG-MM-AAAA.
- `ragione_sociale_consegna`: Nome del punto vendita finale (es. CONAD, C.R. MARKET SRL).
- `indirizzo_consegna`: VERO indirizzo di destinazione merce.
  - *Regola Critica:* Deve escludere sempre l'indirizzo di fatturazione/sede legale. Deve cercare le etichette specifiche come "Consegna a", "Luogo di destinazione", "Spedizione a". Se esiste un indirizzo etichettato così, ha la priorità assoluta rispetto al campo generico "Destinatario".
- `leggibilita_bassa`: Booleano (true/false) in base alla qualità dell'immagine.

Campi mancanti/non leggibili vanno restituiti come stringa vuota `""`, mai come testo tipo "dato mancante" — il resto della pipeline (classificazione, accorpamento) si basa su questa convenzione.

### Normalizzazione a valle (`src/normalizzatore.py`)
Il prompt chiede formati precisi ma un 7B non li rispetta in modo affidabile (misurato sui primi 17 documenti OK: solo **3 date su 17** erano nel formato richiesto). Tutto ciò che è esprimibile come regola esatta viene quindi ripulito lato Python: `normalizza_dati()` è chiamata da `estrai_dati_da_immagine()` subito dopo il `json.loads`.
- `normalizza_data`: qualsiasi separatore (`-`, `/`, `.`, spazio), anno a 2 cifre, forma ISO e nomi di mese italiani → `GG-MM-AAAA`.
- `normalizza_numero_ddt`: rimuove l'etichetta trascinata dentro il valore (`"DOC.DI TRASPORTO 2 7071"`) e la data appiccicata in coda (`"374764/01/07/2026"` → `"374764"`), poi gli zeri iniziali *solo* se il valore è interamente numerico.
- `normalizza_indirizzo`: maiuscolo, virgola davanti al CAP, provincia finale tra parentesi. Serve anche all'accorpatore: lo stesso magazzino tornava scritto in 4 modi diversi.
- `normalizza_azienda`: maiuscolo + forma giuridica compatta (`S.r.l.`/`S.R.L.` → `SRL`), applicata a `fornitore` e `ragione_sociale_consegna`.
- **Principio:** in caso di formato non riconosciuto restituisce il dato grezzo ripulito, **mai** stringa vuota — perdere un dato è peggio che tenerlo in un formato strano. Non cambiare questo comportamento senza motivo: azzerare un campo cambia la classificazione OK/CHECK/KO.
- La normalizzazione **non** viene applicata alle correzioni manuali fatte da dashboard (`PUT /api/documents/{id}`): quello che l'utente scrive a mano resta com'è.

### Classificazione (`src/classificatore.py`)
`determina_stato()` decide lo stato in base a quanti dei 4 `CAMPI_OBBLIGATORI` (`fornitore`, `numero_ddt`, `data_ddt`, `indirizzo_consegna`) sono stati estratti:
- **0 campi trovati** → `KO`
- **tutti i campi trovati E `leggibilita_bassa == false`** → `OK`
- **tutti gli altri casi** (parziale, oppure completo ma con leggibilità bassa) → `CHECK`

### Accorpamento Pagine Multi-DDT (`src/raggruppatore.py` + `src/accorpatore.py`)
Un D.D.T. può occupare più pagine: ogni pagina viene comunque analizzata ed elaborata singolarmente (per non rallentare la pipeline), poi un passaggio **a posteriori** (`accorpa_documenti()`, invocato a fine batch dentro `POST /estrai-ddt`) rilegge tutte le voci già salvate in `OK.json`/`CHECK.json`, raggruppa quelle con lo stesso `numero_ddt` (match esatto) e fornitore simile (`SequenceMatcher` ratio ≥ 0.5), fonde i PDF di pagina in un unico multi-pagina e riscrive i registri con una voce per documento reale. Lo stato finale viene ricalcolato sui dati uniti (due pagine `CHECK` che insieme coprono tutti i campi possono diventare `OK`).

**Unione manuale da dashboard (`POST /api/documents/unisci` + `MergeBar.jsx`, 2026-09-02).** L'accorpamento automatico pretende un `numero_ddt` **identico**: basta una cifra letta male su una pagina e le pagine dello stesso D.D.T. restano separate, spesso in tab diversi (il caso che ha motivato la feature: 4 pagine, 2 in `OK` e 2 in `CHECK` solo per un numero letto male). `unisci_documenti_manuale(ids)` in `accorpatore.py` bypassa il confronto e unisce quello che l'utente ha selezionato:
- **L'ordine degli `ids` conta**: il primo è il documento principale, i suoi dati vincono e gli altri riempiono solo i campi vuoti (stesso `unisci_dati_pagina` dell'automatico, quindi il numero DDT sbagliato non sovrascrive quello giusto). I PDF si concatenano nello stesso ordine.
- A differenza di `accorpa_documenti()` lavora anche su **KO** (`STATI_TUTTI`): una pagina illeggibile appartiene comunque a un documento reale. La voce finale parte dal master (per non perdere metadati suoi tipo `inserimento: manuale`) e riceve `unione: "manuale"`, `numero_pagine` sommato e i `file_origine` uniti.
- Lo stato finale è ricalcolato con `determina_stato()` sui dati uniti, come nell'automatico. Il risultato non viene mai ri-spezzato: `accorpa_documenti()` sa solo raggruppare, non dividere.
- Lato frontend la selezione vive in `App.jsx` e **non** in `Dashboard`, apposta: deve sopravvivere al cambio tab, perché le pagine da unire stanno per definizione in stati diversi.

### Gestione Memoria Fornitori (`backend/src/memory_manager.py`)
Il sistema include un gestore di memoria basato su `backend/data/fornitori_memoria.json` (path relativo `data/fornitori_memoria.json`, montato come volume Docker su `./backend/data`).
- Serve a iniettare regole personalizzate nel prompt se l'AI riconosce un fornitore specifico (es. "Se vedi UNIVERSO PANE S.R.L., ignora l'indirizzo di Ponte Felcino"). Le regole vengono iniettate SOLO se il fornitore ha `"confermato": "yes"` nel JSON — l'utente le approva dalla dashboard (`SuppliersManager.jsx`) dopo che l'AI le ha auto-censite alla prima occorrenza (`aggiorna_fornitore`, chiamata da `main.py` dopo ogni estrazione).
- **Robustezza:** `carica_memoria()` intercetta `JSONDecodeError`/`OSError` e riparte da `{}` (corretto il 2026-08-30). Prima la protezione esisteva solo nell'endpoint `GET /api/fornitori`, quindi un file vuoto/corrotto faceva fallire anche `POST /estrai-ddt` con 500 passando per `ottieni_regole_formattate`.
- **Deduplica per somiglianza (2026-08-30):** le chiavi sono tutte in MAIUSCOLO (`normalizza_azienda`) e `aggiorna_fornitore()` cerca un fornitore *simile* con `trova_fornitore_simile()` prima di censirne uno nuovo. Il confronto case-insensitive da solo non bastava: il file era arrivato a **37 voci per 23 fornitori reali** (`Cerealdolci S.r.l.` + `CEREALDOLCI SRL`, `PERFETTI van Melle S.p.A.` ×3, `Nutrition & Santè`/`Nutrition&Sanità` ×4).
- `stesso_fornitore()` usa due criteri complementari su nomi ridotti alla parte identificante (`chiave_confronto`: maiuscolo, senza forma giuridica, senza punteggiatura):
  1. **contenimento per PAROLE** (`COPERTURA_MINIMA_TOKEN = 0.6`) per i nomi accorciati — `MARIANANTONI SILVIO` copre 2 token su 3 di `PANIFICIO MARIANANTONI SILVIO`. Il confronto è per parole e non per caratteri di proposito: `ITALIA SRL` è contenuto in `ABC ITALIA SRL` come sottostringa ma copre 1 token su 2, e va scartato.
  2. **`SequenceMatcher` ≥ `SOGLIA_SIMILARITA` (0.85)** per gli errori di lettura (`SANTÈ`/`SANITÀ`).
  La soglia è alta di proposito, misurata sulle 37 voci reali: i duplicati veri stavano a 0.80–1.00, i fornitori diversi non superavano 0.59. Fondere due fornitori distinti cancellerebbe una regola già confermata, quindi il margine sta tutto da quel lato. **Non abbassarla senza rimisurare** — è una soglia diversa e più severa di `SOGLIA_SIMILARITA_FORNITORE = 0.5` in `raggruppatore.py`, che risolve un problema diverso (pagine consecutive con lo stesso `numero_ddt` già identico).
- `unifica_memoria()` è applicata dentro `salva_memoria()`, unico punto di scrittura del file: né il censimento automatico né il `PUT /api/fornitori` dalla dashboard possono reintrodurre doppioni. Nella fusione non si perde nulla — vince `confermato: yes` se presente su una qualsiasi, si tiene la nota più lunga e come chiave il nome più informativo (il più lungo).
- **Attenzione:** `PUT /api/fornitori` **sovrascrive l'intero file**, non fa merge parziale. La dashboard rimanda sempre il dizionario completo; una PUT con poche voci cancella tutto il resto.
- **Limite noto:** il censimento è automatico e non distingue i vettori: `data/fornitori_memoria.json` contiene `TRASPORTO IO SRL`, che il prompt dice esplicitamente di ignorare come fornitore. Le voci sporche sono innocue finché restano `"confermato": "no"` (non vengono iniettate nel prompt), ma vanno ripulite a mano dalla dashboard. Stesso discorso per `M SRL`, residuo di una lettura troncata.
- L'import in `main.py` è `from src.memory_manager import carica_memoria, salva_memoria, aggiorna_fornitore` (corretto il 2026-08-30: prima puntava a un inesistente `src.memoria` e impediva l'avvio del backend).

### API Backend (`backend/main.py`)
- `POST /estrai-ddt` — upload PDF/immagine, split in pagine, estrazione AI, classificazione, salvataggio PDF+registro, accorpamento a fine batch.
- `GET /riepilogo?da=<ISO8601>` — conteggi OK/CHECK/KO e dettaglio voci CHECK da un timestamp in poi (consumato da n8n per le notifiche).
- `GET /api/documents`, `GET /api/documents/{id}`, `PUT /api/documents/{id}`, `DELETE /api/documents/{id}` — CRUD sui registri OK/CHECK/KO (usato dalla dashboard).
- `POST /api/documents/manuale` — inserimento manuale (multipart: `file` + i 5 campi come `Form`). Archivia il documento **senza interpellare il modello**. Dettagli in "Inserimento manuale" qui sotto.
- `POST /api/documents/unisci` — unione manuale di più documenti in un unico multi-pagina (body `{"ids": [...]}`, ordine significativo). Dettagli in "Accorpamento Pagine Multi-DDT".
- `GET /api/pdf/{id}.pdf` — serve il PDF associato a un documento (con fallback di ricerca sulla root di `fatture_lette` per documenti "vecchi").
- `GET /api/fornitori`, `PUT /api/fornitori` — lettura/scrittura della memoria fornitori (usato da `SuppliersManager.jsx`).

### Frontend (`frontend/src/`)
Dashboard React (tema dark) composta da `Header`, `Stats`, `Dashboard` (tab OK/CHECK/KO) → `DocumentTable`, `ComparisonModal` (confronto PDF/dati estratti + editing + download con nome file generato da fornitore/data), `SuppliersManager` (editor della memoria fornitori), `MergeBar` (barra di unione manuale, visibile quando ci sono righe selezionate). `App.jsx` fa da router minimale tra dashboard e gestione fornitori.
- L'URL dell'API è letto da `import.meta.env.VITE_API_URL` (fallback `http://localhost:8000`). Essendo Vite, questa variabile va iniettata **in fase di build**, non a runtime: `frontend/Dockerfile` accetta `ARG VITE_API_URL` e `docker-compose.yml` la passa tramite `build.args` (corretto il 2026-08-30: prima veniva passata a runtime come `REACT_APP_API_URL`, senza alcun effetto).

### Inserimento manuale (`POST /api/documents/manuale` + `ManualEntryModal.jsx`)
Pulsante verde "Aggiungi Manuale" nell'`Header`: si allega un file e si trascrivono i dati a mano, per i D.D.T. che l'utente ha già davanti e non vuole far leggere all'AI. Scelte fatte, da non ribaltare per distrazione:
- **Nessuna normalizzazione** sui dati digitati, per coerenza con la regola già valida per `PUT /api/documents/{id}`: quello che l'utente scrive a mano resta com'è. Il form mostra il placeholder `GG-MM-AAAA` per orientarlo. Se un giorno si volesse normalizzare anche qui, è una riga (`normalizza_dati(dati)`) — ma allora va cambiata anche la regola sulle correzioni da dashboard, non solo questa.
- **Lo stato lo decide `determina_stato()` come per tutti gli altri**, non è forzato a `OK`: un inserimento incompleto finisce in `CHECK` e resta visibile tra i documenti da verificare. Il backend rifiuta con 400 solo il caso di tutti i campi vuoti.
- **I PDF vengono archiviati com'è (`shutil.copyfile`)**, non rasterizzati: passare da immagine come fa la pipeline AI ne peggiorerebbe soltanto la qualità. Solo le immagini passano da `salva_pdf_multipagina`.
- La voce di registro ha in più `"inserimento": "manuale"`, per distinguerla a posteriori da quelle prodotte dal modello.
- Il fornitore digitato **entra comunque nella memoria AI** (`aggiorna_fornitore`): è anzi la fonte più affidabile, perché non passa da una lettura del modello.

### Evoluzione prevista: righe articolo
Obiettivo dichiarato dal committente (2026-08-30, non ancora implementato): estrarre anche **i dati dei singoli prodotti** di ogni D.D.T. (codice articolo, descrizione, quantità, unità di misura, prezzo), oggi completamente ignorati — il modello legge solo la testata. Impatti da valutare quando si affronterà:
- è un cambio strutturale del JSON restituito da `llm_engine.py` (da 6 campi piatti a testata + lista righe), quindi tocca `classificatore.py` (i `CAMPI_OBBLIGATORI` restano quelli di testata?), `accorpatore.py`/`raggruppatore.py` (unendo due pagine le righe vanno **concatenate**, non sovrascritte come fa oggi `unisci_dati_pagina`) e la tabella del frontend;
- è anche il caso d'uso che più soffre la risoluzione: le righe articolo sono in corpo piccolo, quindi va rivalutato `PDF_RENDER_ZOOM` e probabilmente `num_ctx` (oggi 8192), perché l'output diventa molto più lungo di adesso.

### Nota sul repository
`n8n_config/` è interamente tracciato in git (dati runtime di n8n: cache statica, `database.sqlite`, log, binary data delle esecuzioni — migliaia di file, centinaia di MB) e non è coperto dal `.gitignore`. **Lasciato intenzionalmente così**: il progetto deve essere spostato su un'altra macchina e questi dati (workflow, credenziali, storico esecuzioni) servono a portare l'ambiente n8n com'è. Non toccarlo/ripulirlo senza chiedere esplicitamente.

---

## 🎯 Obiettivi e Regole per l'Assistente AI (Claude)
- Quando ti viene chiesto di fare refactoring o aggiungere feature, mantieni la coerenza con lo stack sopra descritto.
- Rispetta le logiche di parsing dei D.D.T. (soprattutto la delicata differenza tra Destinatario e Luogo di Consegna).
- Considera sempre che il codice Python gira in un ambiente Dockerizzato (`backend/`) e comunica con un server Ollama accessibile via rete locale.
- Il modulo di memoria fornitori si chiama `memory_manager.py`, non `memoria.py`: non reintrodurre l'import sbagliato se tocchi `main.py`.
- Prima di irrigidire il prompt per un problema di formato, chiediti se è una regola esatta: in quel caso va in `normalizzatore.py`, non nel prompt. Il modello è inaffidabile sui formati, Python no.
- La risoluzione di rendering è in `PDF_RENDER_ZOOM` (default `2.5` ≈ 180 DPI, definita in `docker-compose.yml`): è la leva da alzare quando il modello perde cifre nei numeri DDT, al costo di più tempo per pagina.
- Le pagine vengono sempre elaborate singolarmente prima e accorpate dopo (`accorpatore.py`/`raggruppatore.py`): non spostare la logica di merge dentro il loop di estrazione per pagina, è una scelta deliberata per non rallentare l'analisi.
- I log del backend devono restare leggibili in tempo reale: `backend/Dockerfile` imposta `ENV PYTHONUNBUFFERED=1` (2026-09-02). Senza, i `print` per pagina restano nel buffer di stdout e compaiono tutti insieme a fine elaborazione, rendendo inutile il tracciamento pagina per pagina.
- Non toccare `n8n_config/` a cuor leggero: contiene stato runtime reale di n8n (workflow, credenziali, esecuzioni), non solo configurazione statica.
