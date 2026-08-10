# Frontend - Dashboard Gestione Fatture

Dashboard web moderna per la visualizzazione e gestione dei documenti estratti (DDT e Fatture).

## 🚀 Tecnologie Utilizzate

- **React 19** - Libreria UI moderna con hooks
- **Vite** - Build tool ultra-veloce per sviluppo e produzione
- **Bootstrap 5** - Framework CSS per il design responsive
- **Axios** - Client HTTP per le chiamate API
- **Lucide React** - Libreria di icone moderne e leggere

## 📦 Installazione

```bash
# Installa le dipendenze
npm install

# Avvia il server di sviluppo
npm run dev

# Build per produzione
npm run build

# Preview della build production
npm run preview

# Esegui linting
npm run lint
```

## 🏗️ Architettura Componenti

```
src/
├── App.jsx                 # Componente principale dell'applicazione
├── components/
│   ├── Header.jsx          # Barra di navigazione con titolo e pulsante refresh
│   ├── Stats.jsx           # Widget statistici (Totali, Da Verificare, Completati)
│   ├── DocumentTable.jsx   # Tabella documenti con azioni (modifica, elimina, anteprima)
│   └── ComparisonModal.jsx # Modale per confronto dati estratti vs modificati
├── assets/                 # Risorse statiche (immagini, font)
├── index.css               # Stili globali
└── main.jsx                # Punto di ingresso dell'applicazione
```

## 🔧 Configurazione

### Variabili d'Ambiente

Crea un file `.env` nella root del frontend per configurare l'URL dell'API:

```env
VITE_API_URL=http://localhost:8000
```

Se non specificato, il frontend si connetterà automaticamente a `http://localhost:8000`.

## 🎯 Funzionalità

- **Dashboard Principale**: Visualizzazione cronologica di tutti i documenti elaborati
- **Statistiche in Tempo Reale**: Contatori per documenti OK, CHECK e KO
- **Ricerca e Filtri**: Filtra documenti per stato o cerca per numero/fornitore
- **Modifica Dati**: Correggi i dati estratti dall'AI direttamente dal browser
- **Anteprima PDF**: Visualizza i documenti PDF senza scaricare file
- **Eliminazione Documenti**: Rimuovi documenti e i relativi PDF dal sistema
- **Design Responsive**: Interfaccia ottimizzata per desktop, tablet e mobile

## 🐳 Docker

Il frontend è containerizzato e può essere avviato con Docker Compose:

```bash
# Dalla root del progetto
docker-compose up --build -d
```

Il servizio sarà disponibile su: http://localhost:3000

## 📝 Script Disponibili

| Comando | Descrizione |
|---------|-------------|
| `npm run dev` | Avvia il server di sviluppo con hot-reload |
| `npm run build` | Crea build ottimizzata per produzione |
| `npm run preview` | Anteprima locale della build production |
| `npm run lint` | Esegue controlli di qualità del codice |

## 🔌 Integrazione API

Il frontend comunica con il backend FastAPI attraverso i seguenti endpoint:

- `GET /api/documents` - Lista tutti i documenti
- `PUT /api/documents/:id` - Aggiorna i dati di un documento
- `DELETE /api/documents/:id` - Elimina un documento e il suo PDF
- `GET /api/documents/:id/pdf` - Ottieni il PDF per l'anteprima

## 🎨 Personalizzazione

### Temi Bootstrap

Il frontend utilizza Bootstrap 5 con classi utility. Puoi personalizzare i colori e gli stili modificando:

- `src/index.css` - Stili globali e personalizzati
- `src/App.css` - Stili specifici dell'applicazione

### Icone

Le icone sono fornite da [Lucide React](https://lucide.dev/guide/packages/lucide-react). Consulta la documentazione per aggiungere nuove icone ai componenti.

## 🛠️ Sviluppo

### Struttura del Codice

Ogni componente è modulare e riutilizzabile:

- **Header**: Gestisce il titolo e l'azione di refresh
- **Stats**: Mostra le metriche principali calcolate dai documenti
- **DocumentTable**: Renderizza la tabella con pagination e azioni
- **ComparisonModal**: Modale per editing con confronto side-by-side

### Best Practices

- Utilizza React Hooks (`useState`, `useEffect`) per la gestione dello stato
- Axios per le chiamate API con gestione errori
- Classi utility di Bootstrap per styling rapido e consistente
- Componenti funzionali con props per il passaggio dati

## 📄 Licenza

Questo progetto è proprietà di Bordao Studio. Tutti i diritti riservati.
