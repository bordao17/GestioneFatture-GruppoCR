# GestioneFatture - GruppoCR

Microservizio AI per l'estrazione automatica di dati da **DDT (Documenti di Trasporto)** e **Fatture** in formato PDF o immagine.

Il sistema utilizza un modello di linguaggio locale (Ollama) per analizzare i documenti, estrarre le informazioni chiave e classificarle automaticamente.

---

## 📋 Caratteristiche Principali

- **Estrazione Intelligente**: Analizza PDF e immagini (JPG, PNG) per estrarre dati da DDT e fatture
- **Classificazione Automatica**: Categorizza i documenti in base alla completezza dei dati estratti:
  - `OK`: Documento completo con tutti i campi obbligatori
  - `CHECK`: Documento con alcuni campi mancanti ma recuperabili
  - `KO`: Documento non leggibile o senza dati utili
- **Accorpamento Documenti**: Unisce automaticamente pagine multiple dello stesso documento
- **API REST**: Interfaccia moderna basata su FastAPI per l'integrazione con altri sistemi
- **Lavori automatici**: Le scansioni e la mail di sollecito possono partire a un'ora impostata dalla dashboard (o restare tutte a pulsante)
- **Notifiche via mail**: Riepilogo di fine scansione e sollecito di ciò che è fermo da troppi giorni, composti e spediti dal backend
- **Privacy-First**: Elabora i documenti localmente senza inviarli a servizi cloud esterni

---

## 🏗️ Architettura del Progetto

```
GestioneFatture - GruppoCR/
├── docker-compose.yml       # Orchestrazione container (API + Frontend + Postgres)
├── backend/                 # Microservizio Python (FastAPI)
│   ├── main.py              # Server API principale
│   ├── requirements.txt     # Dipendenze Python
│   ├── Dockerfile           # Configurazione Docker per l'API
│   ├── data/
│   │   └── fornitori_memoria.json  # Copia di scorta dell'anagrafica fornitori
│   │                               # (la fonte e' Postgres, vedi Note tecniche)
│   └── src/                 # Moduli del sistema
│       ├── pdf_processor.py    # Conversione PDF in immagini
│       ├── llm_engine.py       # Integrazione con Ollama per estrazione dati
│       ├── classificatore.py   # Logica di classificazione documenti (OK/CHECK/KO)
│       ├── registro.py         # Gestione registro documenti elaborati
│       ├── pdf_writer.py       # Salvataggio PDF multipagina
│       ├── raggruppatore.py    # Confronto pagine per capire se appartengono allo stesso DDT
│       ├── accorpatore.py      # Unione a posteriori dei documenti multi-pagina
│       ├── normalizzatore.py   # Pulizia formati dei campi estratti (date, numeri, indirizzi)
│       ├── memory_manager.py   # Regole e decisioni sull'anagrafica fornitori
│       ├── database.py         # Connessione a Postgres (nessuna tabella qui)
│       ├── archivio_fornitori.py # Tabelle dell'anagrafica fornitori
│       └── notificatore.py     # Calcolo riepiloghi per le mail di notifica
├── frontend/                # Dashboard web React (Vite)
│   ├── src/
│   │   ├── App.jsx          # Componente principale / routing dashboard-fornitori
│   │   ├── main.jsx         # Punto di ingresso React
│   │   └── components/      # Header, Stats, Dashboard, DocumentTable,
│   │                        # ComparisonModal, SuppliersManager
│   ├── public/               # File statici pubblici
│   ├── package.json          # Dipendenze Node.js
│   ├── Dockerfile            # Build Vite + Nginx
│   └── nginx.conf            # Configurazione server web
├── fatture_da_leggere/       # Cartella input per nuovi documenti
├── fatture_lette/            # Cartella output documenti elaborati
│   ├── OK.json / CHECK.json / KO.json   # Registri dei documenti per stato
│   ├── OK/                   # PDF dei documenti completi
│   ├── CHECK/                # PDF dei documenti da verificare
│   └── KO/                   # PDF dei documenti non elaborabili
├── postgre/dati/             # File di Postgres: le anagrafiche (ignorato da git)
└── n8n_snippets/              # Nodi Code del vecchio n8n: fonte storica delle mail
```

---

## 🚀 Come Avviare il Progetto

### Prerequisiti

1. **Docker** e **Docker Compose** installati sul tuo sistema
2. **Ollama** in esecuzione sulla macchina host (per il modello AI locale)
   - Installa Ollama da: https://ollama.ai
   - Assicurati che il servizio sia attivo sulla porta `11434`

### Avvio Rapido con Docker Compose

Questo è il metodo consigliato per avviare tutti i servizi necessari:

```bash
# Clona o posizionati nella directory del progetto
cd /workspace

# Avvia tutti i servizi (API + Frontend)
docker-compose up --build -d
```

I servizi saranno disponibili alle seguenti porte:
- **API Gestione Fatture**: http://localhost:8000
- **Dashboard Web (Frontend)**: http://localhost:3000
- **Database anagrafiche (Postgres)**: `127.0.0.1:5432`, solo da questa macchina — per puntarci un client SQL senza entrare nel container

Il primo avvio in assoluto crea il cluster Postgres in `postgre/dati/` (può volerci un minuto) e importa nel database l'anagrafica fornitori che sta nel JSON. Nel log dell'API si legge `📥 Anagrafica fornitori importata nel database: N voci.`

### Dashboard Web

Il progetto include una **dashboard web** sviluppata con React e Bootstrap che permette di:
- Visualizzare tutti i documenti elaborati in ordine cronologico
- Cercare e filtrare documenti per stato (OK, CHECK, KO)
- Visualizzare l'anteprima dei PDF direttamente nel browser
- Modificare i dati estratti dai documenti
- **Aggiungere manualmente un documento** (pulsante "Aggiungi Manuale"): si allega il PDF/immagine e si scrivono i dati a mano, senza far intervenire l'AI. Utile per i D.D.T. già verificati o che il modello non riesce a leggere
- Eliminare documenti non più necessari
- Esportare report (funzionalità futura)

Per accedere alla dashboard:
1. Avvia i servizi con `docker-compose up -d`
2. Apri il browser su http://localhost:3000
3. La dashboard si connetterà automaticamente all'API backend

### Avvio Manuale (Senza Docker)

Se preferisci eseguire il progetto direttamente sulla tua macchina:

```bash
# Installa le dipendenze Python
pip install -r requirements.txt

# Assicurati che Ollama sia in esecuzione sulla porta 11434
# Imposta la variabile d'ambiente se necessario
export OLLAMA_HOST=http://localhost:11434

# Avvia il server API
python main.py
```

L'API sarà disponibile su: http://localhost:8000

---

## 📖 Come Utilizzare il Servizio

### 1. Upload di un Documento (API Endpoint)

Per elaborare un DDT o una fattura, invia una richiesta POST all'endpoint `/estrai-ddt`:

#### Esempio con cURL:

```bash
curl -X POST "http://localhost:8000/estrai-ddt" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/percorso/del/tuo/documento.pdf"
```

#### Esempio con Python:

```python
import requests

url = "http://localhost:8000/estrai-ddt"
files = {"file": open("documento.pdf", "rb")}
response = requests.post(url, files=files)

print(response.json())
```

#### Risposta Attesa:

```json
{
  "status": "success",
  "filename": "documento.pdf",
  "pagine_elaborate": [
    {
      "id": "uuid-del-documento",
      "stato": "OK",
      "campi_trovati": ["numero_ddt", "fornitore", "data", ...]
    }
  ],
  "accorpamento": {
    "documenti_accorpati": 0,
    "dettagli": []
  }
}
```

### 2. Consultazione Riepilogo

Per ottenere un riepilogo dei documenti elaborati da una certa data:

```bash
curl "http://localhost:8000/riepilogo?da=2026-08-09T10:30:00+02:00"
```

### 3. Altri Endpoint Disponibili

Oltre a `/estrai-ddt` e `/riepilogo`, l'API espone gli endpoint usati dalla dashboard web:

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `GET` | `/api/documents` | Elenco di tutti i documenti (OK + CHECK + KO) |
| `POST` | `/api/documents/manuale` | Inserisce un documento compilato a mano (file + campi), senza usare l'AI |
| `GET` | `/api/documents/{id}` | Dettaglio di un documento |
| `PUT` | `/api/documents/{id}` | Aggiorna i dati estratti di un documento |
| `DELETE` | `/api/documents/{id}` | Elimina documento e PDF associato |
| `GET` | `/api/pdf/{id}.pdf` | Restituisce il PDF per la visualizzazione inline |
| `GET` | `/api/fornitori` | Legge la memoria AI sui fornitori |
| `PUT` | `/api/fornitori` | Sovrascrive la memoria AI sui fornitori (invia sempre il dizionario completo) |

> I nomi dei fornitori vengono salvati sempre in MAIUSCOLO e deduplicati per somiglianza: `PERFETTI van Melle S.p.A.` e `PERFETTI VAN MELLE` finiscono in un'unica voce, senza doppioni da confermare due volte in dashboard.

### 4. Documentazione API Interattiva

FastAPI fornisce automaticamente una documentazione Swagger UI interattiva:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

Visita questi endpoint per esplorare tutti gli endpoint disponibili e testarli direttamente dal browser.

---

## 🔧 Configurazione

### Variabili d'Ambiente

| Variabile | Descrizione | Valore Default |
|-----------|-------------|----------------|
| `OLLAMA_HOST` | URL del servizio Ollama | `http://host.docker.internal:11434` |
| `GENERIC_TIMEZONE` | Fuso orario per timestamp | `Europe/Rome` |
| `PDF_RENDER_ZOOM` | Zoom di rendering PDF→immagine (`2.5` ≈ 180 DPI). Alzalo a `3.5` se il modello sbaglia cifre su scansioni scadenti, al costo di più tempo per pagina | `2.5` |
| `DATABASE_URL` | Connessione al database delle anagrafiche. **Vuota** = nessun database: i fornitori tornano a vivere nel JSON e tutto il resto funziona uguale | impostata dal compose sul container `postgres-gestione-fatture` |

`DATABASE_URL` **non** è fra le impostazioni della dashboard, e apposta: come per i percorsi, una stringa di connessione sbagliata scritta di lì toglierebbe di mezzo proprio l'anagrafica che serve a correggerla.

Queste (più il modello vision, le soglie dei solleciti, gli orari dei lavori automatici e le credenziali SMTP) sono il **ripiego**, non la fonte: la sezione **Configurazione** della dashboard le sovrascrive senza ricostruire il container, e ogni campo mostra da dove viene il valore che sta girando. L'elenco completo, con i valori di partenza commentati, è nel `docker-compose.yml`.

### Volumi Docker

Il sistema utilizza le seguenti cartelle per la persistenza dei dati:

- `./DDT`: `da_leggere/` per le scansioni in arrivo, `lette/` per i registri e i PDF archiviati
- `./FATTURE`: `da_leggere/` per gli XML in arrivo, `lette/` per i registri e gli originali
- `./ACCOPPIATE`: il prodotto finito, i file unici fattura+DDT con un nome leggibile
- `./backend/data`: configurazione salvata dalla dashboard e copia di scorta dell'anagrafica fornitori
- `./postgre/dati`: i file di Postgres, cioè le anagrafiche. **Ignorata da git** (sono file di database, non configurazione) e da non cancellare a cuor leggero: è lì che vivono i fornitori

---

## ⏰ Lavori automatici e notifiche

Fino al 2026-09-09 l'orologio e l'invio delle mail erano un container n8n a parte. Oggi stanno nel backend, dove sta già tutto ciò che decide: `backend/src/comune/pianificatore.py` guarda l'ora, `backend/src/notifiche/` compone e spedisce.

### I tre lavori

| Lavoro | Cosa fa | Impostazione |
|--------|---------|--------------|
| Scansione D.D.T. | Elabora tutto ciò che è fermo in `DDT/da_leggere/` | `ORARIO_SCANSIONE_DDT` |
| Scansione fatture | Legge e archivia gli XML fermi in `FATTURE/da_leggere/` | `ORARIO_SCANSIONE_FATTURE` |
| Sollecito | Manda la mail di ciò che aspetta da troppi giorni | `ORARIO_SOLLECITO` |

Gli orari sono nel formato `HH:MM` e si impostano dalla sezione **Configurazione** della dashboard. **Il campo vuoto significa "non pianificare"**, ed è il valore di partenza: senza toccarli il sistema resta tutto a pulsanti. L'ordine consigliato è prima i D.D.T. e poi le fatture, che li cercano.

Il pannello **Lavori automatici**, in cima alla sezione Configurazione, dice quando toccherà la prossima volta e com'è andata l'ultima, e ha un pulsante **Esegui adesso** che passa dalla stessa strada dell'esecuzione notturna.

Un backend spento all'ora prevista **salta il giro**: non recupera all'avvio, per non far partire una scansione a sorpresa il mattino dopo.

### Le mail

Servono `SMTP_HOST` e `MAIL_DESTINATARI`; senza, i lavori girano lo stesso e semplicemente nessuno riceve niente — le notifiche sono un di più, non un ingranaggio. `SMTP_PASSWORD` è l'unico valore che la dashboard non rimanda mai al browser: si vede mascherato e si cancella solo svuotando il campo. Il pulsante **Invia mail di prova** serve a saperlo subito, invece di scoprirlo il mattino dopo.

- **Riepilogo scansione D.D.T.** — conteggi OK/CHECK/KO, il motivo per cui ogni CHECK è finita lì, le pratiche diventate pronte da accoppiare e i file non elaborati.
- **Riepilogo fatture** — cosa è entrato, con le anomalie sul cedente (P.IVA assente, diversa da quella in anagrafica, fornitore mai visto).
- **Sollecito** — le fatture che aspettano una bolla, quelle che aspettano solo un click e le bolle che nessuna fattura ha agganciato. Se non c'è niente da sollecitare **non parte**: una mail "nessuna fattura in attesa" verrebbe ignorata entro tre giorni, comprese le volte in cui dice qualcosa.

Le soglie del sollecito sono **tre e indipendenti**, tutte nella sezione Configurazione: `GIORNI_ATTESA_FATTURA` (30) per una fattura a cui mancano i D.D.T., `GIORNI_ATTESA_DDT` (30) per una bolla che nessuna fattura ha agganciato, `GIORNI_ATTESA_ACCOPPIAMENTO` (7, più corto) per una pratica completa che aspetta solo la firma. Partono uguali sulle prime due, ma sono due attese diverse: la prima dipende da chi deve portare la bolla, la seconda dal giro di fatturazione del fornitore.

`MAIL_RIEPILOGO_SCANSIONE` (`pianificate` | `sempre` | `mai`) decide quando mandare il riepilogo di fine scansione. Il default è `pianificate`: chi preme *Analizza* dalla dashboard sta già guardando l'esito.

---

## 📁 Struttura dei Dati Estratti

Per ogni pagina il modello restituisce esattamente questi campi (vedi `backend/src/llm_engine.py`):

- **fornitore**: Azienda emittente del documento
- **numero_ddt**: Identificativo del documento (zeri iniziali rimossi solo se puramente numerico)
- **data_ddt**: Data di emissione, formato `GG-MM-AAAA`
- **ragione_sociale_consegna**: Nome del punto vendita/destinatario finale della merce
- **indirizzo_consegna**: Indirizzo fisico di consegna (mai quello di fatturazione/sede legale)
- **leggibilita_bassa**: `true`/`false`, in base alla qualità della scansione

I valori restituiti dal modello passano poi da `backend/src/normalizzatore.py`, che uniforma i formati prima del salvataggio: date sempre in `GG-MM-AAAA` (qualunque separatore o anno a 2 cifre in origine), numeri DDT ripuliti da etichette e date appiccicate, indirizzi in maiuscolo con CAP e provincia in posizione fissa, ragioni sociali con forma giuridica compatta (`S.r.l.` → `SRL`). Se un formato non è riconoscibile viene mantenuto il dato grezzo, mai azzerato.

Un documento è classificato `OK` solo se `fornitore`, `numero_ddt`, `data_ddt` e `indirizzo_consegna` sono tutti presenti e `leggibilita_bassa` è `false` (vedi `backend/src/classificatore.py`).

Se un DDT occupa più pagine, ogni pagina viene analizzata singolarmente e poi le pagine con stesso `numero_ddt`/fornitore vengono riaccorpate automaticamente a fine elaborazione, unendo PDF e dati in un unico documento (`backend/src/accorpatore.py`).

---

## ❓ Risoluzione Problemi

### Il servizio non si avvia

Verifica che:
1. Docker sia correttamente installato e in esecuzione
2. Le porte 8000, 3000 e 5432 non siano già occupate
3. Ollama sia in esecuzione sulla macchina host

### I fornitori non si vedono più nella dashboard

Quasi sempre è il database delle anagrafiche che non risponde. Il backend **non** si ferma per questo: ripiega sulla copia su file e scrive in log `⚠️ Anagrafica fornitori non leggibile dal database (...): uso la copia su file.`, ma i salvataggi falliscono con un 500 finché il database non torna (un salvataggio che non salva niente non va raccontato come riuscito).

1. `docker compose ps` — il container `postgres_fatture_gruppocr` dev'essere `healthy`
2. `docker compose logs postgres-gestione-fatture`
3. `docker compose up -d postgres-gestione-fatture` per rialzarlo

Se serve tornare a lavorare **senza** database, svuota `DATABASE_URL` nel `docker-compose.yml` e riavvia l'API: i fornitori tornano a vivere nel JSON, com'era fino al 2026-09-10. La copia su file è aggiornata all'ultimo salvataggio riuscito.

### Errori di connessione a Ollama

Assicurati che:
- Ollama sia installato e attivo: `ollama serve`
- La variabile `OLLAMA_HOST` punti all'indirizzo corretto
- Il firewall non blocchi la porta 11434

### Documenti non elaborati correttamente

Controlla che:
- Il PDF non sia protetto da password
- La qualità della scansione sia sufficiente (minimo 150 DPI consigliati)
- Il documento sia in italiano o in una lingua supportata dal modello

---

## 📝 Note Tecniche

- **Backend API**: FastAPI con Uvicorn (Python 3.12)
- **Frontend Dashboard**: React 19 con Vite, Bootstrap 5, `lucide-react`, `react-pdf`
- **Motore AI**: Ollama, modello `qwen2.5vl:7b` (vision multimodale)
- **Elaborazione PDF**: PyMuPDF (fitz) per il rendering, Pillow per il riassemblaggio
- **Anagrafiche**: PostgreSQL 16 (container `postgres:16-alpine`, dati in `postgre/dati/`), driver `psycopg`. Ci vivono le anagrafiche — **non** i registri dei documenti, che restano file JSON accanto ai PDF e agli XML che descrivono
- **Pianificazione e mail**: thread interno al backend + `smtplib` (nessun servizio esterno)
- **Server Web Frontend**: Nginx (in produzione)
- **Containerizzazione**: Docker e Docker Compose

### ⚠️ Problemi noti

- `n8n_snippets/` è tracciato in git e non escluso dal `.gitignore`: è la fonte storica delle tre mail, oggi in `backend/src/notifiche/`. Il codice in esecuzione non lo legge.
- `n8n_config/` (327 MB di stato runtime di n8n) è stato **cancellato il 2026-09-11**. Era tracciato in git, quindi si recupera da un commit precedente con `git checkout <commit> -- n8n_config`. Attenzione: la cancellazione ha ripulito la cartella di lavoro ma **non** il repository — i blob restano nella storia e `.git` pesa comunque ~106 MB.

---

## 👥 Autori

**Lorenzo Bordi: GestioneFatture - GruppoCR**  
Developed by *Bordao Studio*

---

## 📄 Licenza

Questo progetto è proprietà di Bordao Studio. Tutti i diritti riservati.
