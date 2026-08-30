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
- **Automazione n8n**: Include configurazione per flussi di lavoro automatizzati tramite n8n
- **Privacy-First**: Elabora i documenti localmente senza inviarli a servizi cloud esterni

---

## 🏗️ Architettura del Progetto

```
GestioneFatture - GruppoCR/
├── docker-compose.yml       # Orchestrazione container (API + Frontend + n8n)
├── backend/                 # Microservizio Python (FastAPI)
│   ├── main.py              # Server API principale
│   ├── requirements.txt     # Dipendenze Python
│   ├── Dockerfile           # Configurazione Docker per l'API
│   ├── data/
│   │   └── fornitori_memoria.json  # Memoria AI sui fornitori (regole custom)
│   └── src/                 # Moduli del sistema
│       ├── pdf_processor.py    # Conversione PDF in immagini
│       ├── llm_engine.py       # Integrazione con Ollama per estrazione dati
│       ├── classificatore.py   # Logica di classificazione documenti (OK/CHECK/KO)
│       ├── registro.py         # Gestione registro documenti elaborati
│       ├── pdf_writer.py       # Salvataggio PDF multipagina
│       ├── raggruppatore.py    # Confronto pagine per capire se appartengono allo stesso DDT
│       ├── accorpatore.py      # Unione a posteriori dei documenti multi-pagina
│       ├── normalizzatore.py   # Pulizia formati dei campi estratti (date, numeri, indirizzi)
│       ├── memory_manager.py   # Lettura/scrittura memoria fornitori
│       └── notificatore.py     # Calcolo riepiloghi per le notifiche n8n
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
└── n8n_config/                # Dati/configurazione runtime di n8n
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

# Avvia tutti i servizi (API + n8n)
docker-compose up --build -d
```

I servizi saranno disponibili alle seguenti porte:
- **API Gestione Fatture**: http://localhost:8000
- **Dashboard Web (Frontend)**: http://localhost:3000
- **Interfaccia n8n**: http://localhost:5678

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

### Volumi Docker

Il sistema utilizza le seguenti cartelle per la persistenza dei dati:

- `./fatture_da_leggere`: Posiziona qui i PDF da elaborare
- `./fatture_lette`: Contiene i risultati dell'elaborazione (suddivisi per stato)
- `./data`: Dati interni dell'applicazione
- `./n8n_config`: Configurazione delle automazioni n8n

---

## 🤖 Automazione con n8n

Il progetto include una configurazione predefinita per n8n, un potente strumento di automazione del flusso di lavoro.

### Accesso a n8n

1. Apri il browser e vai su: http://localhost:5678
2. Completa la configurazione iniziale al primo accesso
3. Importa i workflow dalla cartella `n8n_config/`

### Workflow Disponibili

I workflow preconfigurati permettono di:
- Monitorare la cartella `fatture_da_leggere` per nuovi documenti
- Chiamare automaticamente l'API di estrazione
- Inviare notifiche per documenti in stato `CHECK` o `KO`
- Generare report periodici

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
2. La porta 8000 e 5678 non siano già occupate
3. Ollama sia in esecuzione sulla macchina host

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
- **Automazione**: n8n
- **Server Web Frontend**: Nginx (in produzione)
- **Containerizzazione**: Docker e Docker Compose

### ⚠️ Problemi noti

- `n8n_config/` è interamente tracciato in git (dati di runtime: cache, `database.sqlite`, log, binary data delle esecuzioni), non è escluso dal `.gitignore`. Lasciato così di proposito: il progetto va spostato su un'altra macchina e questi dati (workflow, credenziali, storico esecuzioni n8n) servono a portare l'ambiente com'è.

---

## 👥 Autori

**Lorenzo Bordi: GestioneFatture - GruppoCR**  
Developed by *Bordao Studio*

---

## 📄 Licenza

Questo progetto è proprietà di Bordao Studio. Tutti i diritti riservati.
