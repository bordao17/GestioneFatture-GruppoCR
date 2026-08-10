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
/workspace
├── main.py                 # Server API FastAPI principale
├── requirements.txt        # Dipendenze Python
├── Dockerfile             # Configurazione Docker per l'API
├── docker-compose.yml     # Orchestrazione container (API + n8n)
├── src/                   # Moduli del sistema
│   ├── pdf_processor.py   # Conversione PDF in immagini
│   ├── llm_engine.py      # Integrazione con Ollama per estrazione dati
│   ├── classificatore.py  # Logica di classificazione documenti
│   ├── registro.py        # Gestione registro documenti elaborati
│   ├── pdf_writer.py      # Salvataggio PDF multipagina
│   ├── accorpatore.py     # Unione documenti correlati
│   └── notificatore.py    # Calcolo riepiloghi e notifiche
├── fatture_da_leggere/    # Cartella input per nuovi documenti
├── fatture_lette/         # Cartella output documenti elaborati
│   ├── OK/                # Documenti completi
│   ├── CHECK/             # Documenti da verificare
│   └── KO/                # Documenti non elaborabili
├── data/                  # Dati persistenti dell'applicazione
└── n8n_config/            # Configurazione automazioni n8n
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
- **Interfaccia n8n**: http://localhost:5678

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

### 3. Documentazione API Interattiva

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

Il sistema estrae i seguenti campi principali dai documenti:

- **Numero DDT/Fattura**: Identificativo del documento
- **Fornitore**: Nome o ragione sociale del mittente
- **Data**: Data di emissione del documento
- **Destinatario**: Cliente o destinatario della merce
- **Articoli**: Lista dei prodotti/servizi con quantità e prezzi
- **Totale**: Importo complessivo del documento
- **Note**: Eventuali annotazioni aggiuntive

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

- **Framework API**: FastAPI con Uvicorn
- **Motore AI**: Ollama (modelli LLM locali)
- **Elaborazione PDF**: PyMuPDF (fitz)
- **Automazione**: n8n
- **Linguaggio**: Python 3.12+

---

## 👥 Autori

**GestioneFatture - GruppoCR**  
Developed by *Lo Staff di Pa.Rea S.n.C.*

---

## 📄 Licenza

Questo progetto è proprietà di GruppoCR. Tutti i diritti riservati.
