# Braccio Fatture — come importarlo in n8n

`braccio_fatture.json` è il ramo **fatture elettroniche → abbinamento ai DDT**, da
affiancare a quello già esistente ("Gruppo CR", che legge i PDF dei DDT).
Non tocca `n8n_config/`: si importa dall'interfaccia.

## Import

1. Apri n8n (`http://localhost:5678`) e il workflow **Gruppo CR**.
2. Copia negli appunti il contenuto di `braccio_fatture.json`.
3. Clicca sulla canvas e incolla (`Ctrl+V`): i 5 nodi compaiono già collegati,
   sotto il ramo esistente (y = 320), senza sovrapporsi.
4. Sul nodo **Email Fatture** ricontrolla che la credenziale SMTP sia agganciata
   (è la stessa `SMTP account` dell'altro ramo, ma l'id viene rimappato in import).
5. Salva e lancia con il trigger **Manuale Fatture**.

## I nodi

| Nodo | Cosa fa |
|---|---|
| `Manuale Fatture` | Trigger. Da sostituire con uno *Schedule Trigger* quando il flusso va in automatico. |
| `Leggi Fatture` | Legge `/FATTURE/da_leggere/*.xml*` — il glob prende sia `.xml` sia `.xml.p7m`. Un item per file. |
| `Abbina Fattura` | `POST http://api-gestione-fatture:8000/abbina-fattura` (multipart, campo `file`). `onError: continueRegularOutput`: una fattura illeggibile non ferma il batch. |
| `Html Fatture` | Copia del Code node versionata in `riepilogo_fatture_email.js`. Compone `oggetto` + `corpo_html`. |
| `Email Fatture` | Invio SMTP. Subject `{{ $json.oggetto }}`, HTML `{{ $json.corpo_html }}`. |

Timeout dell'HTTP Request: **60 s**, non 1800 s come nel ramo DDT. Qui il modello
non entra mai — l'abbinamento è parsing XML più confronto di stringhe e sta
sotto il secondo per fattura.

## Cosa NON fa (per scelta)

- **Non sposta né cancella i file** da `/FATTURE/da_leggere/`, e adesso non
  serve più che lo faccia: il backend deduplica per P.IVA + numero + data
  fattura, quindi rilanciare il ramo ripassa gli stessi file e li salta con
  esito `DUPLICATA`. È anche ciò che permette di lasciare ferme lì le fatture
  scartate (fornitore non autorizzato) senza che diano fastidio a ogni giro.
- Non c'è un `GET /riepilogo-fatture`: la mail si costruisce dalla risposta
  dell'abbinamento stesso, che contiene già stato e righe DDT di ogni fattura.
- **Non richiama l'abbinamento delle fatture rimaste in attesa.** Quello lo fa
  il backend da solo a ogni evento sui DDT (fine estrazione, inserimento
  manuale, unione, rianalisi, correzione dei dati in dashboard): metà di quegli
  eventi non muove un file e n8n non avrebbe modo di accorgersene.

## Stati nella risposta di `POST /abbina-fattura`

| Stato | Significato |
|---|---|
| `ABBINATA` | Tutti i DDT citati sono stati trovati: fascicolo PDF generato, pratica chiusa in `FATTURE.json`. |
| `IN_ATTESA` | **Coda**, non errore: manca almeno un DDT. La voce va in `ATTESA.json` e viene ricontrollata a ogni nuova estrazione finché si chiude. |
| `NON_ABBINATA` | La fattura non cita alcun DDT e non riporta dati di trasporto (servizi, note di credito): non c'è niente da aspettare. |
| `IGNORATA` | Cedente non autorizzato in anagrafica fornitori. Il file resta dov'è, la fattura non entra nel flusso. |
| `DUPLICATA` | Già registrata in un giro precedente. |

# Ramo Sollecito (`braccio_sollecito.json`)

Secondo ramo, indipendente: `Ogni Mattina` (Schedule, 08:00) → `Fatture In Attesa`
(`GET /api/fatture/attese`) → `DDT Senza Fattura` (`GET /api/ddt/senza-fattura`)
→ `Html Sollecito` (Code, copia in `sollecito_attese_email.js`) →
`Email Sollecito`.

Le due chiamate stanno **in catena** e il Code node le legge per nome
(`$('Fatture In Attesa')`, `$('DDT Senza Fattura')`): in n8n l'output di un nodo
sostituisce quello del precedente, ma i nodi restano raggiungibili. Una sola
mail per due domande opposte — fatture a cui manca una bolla, bolle a cui manca
una fattura — perché è lo stesso magazziniere a doverle cercare.

Si importa allo stesso modo (copia il JSON, `Ctrl+V` sulla canvas): i nodi
compaiono a `y = 560`, sotto il ramo fatture.

È l'unico pezzo del flusso fatture che *deve* stare in n8n: "in attesa da più
di N giorni" è un trigger temporale, e nessun evento del backend scatta al
trentesimo giorno.

- **La soglia non è nel nodo**: l'HTTP Request chiama `/api/fatture/attese`
  senza parametri e il backend applica `GIORNI_ATTESA_SOLLECITO`
  (`docker-compose.yml`, 30 giorni). Un `?giorni=30` scritto nel nodo sarebbe
  una seconda copia del numero, destinata a divergere.
- **Se non c'è niente da sollecitare non parte nessuna mail**: il Code node
  restituisce zero item e il nodo Email non viene eseguito.
- La sezione **bolle senza fattura** è il lato speculare: un DDT scansionato da
  oltre un mese che nessuna fattura ha agganciato. Da quel lato non c'è nessun
  ricontrollo da fare (ogni fattura nuova viene confrontata con tutto
  l'archivio), quindi se dopo 30 giorni è ancora lì o la fattura non è mai
  arrivata o il suo cedente non è autorizzato in anagrafica.
- La mail separa le fatture che **aspettano una persona** (DDT già in archivio
  ma con un numero letto male: si sblocca solo correggendolo in dashboard) da
  quelle che **aspettano un documento** (bolla mai scansionata: si chiude da
  sola quando arriva). Sono le due voci che rendono la mail utile.

## Da sistemare nel ramo esistente

Il nodo **`Leggi PDF`** punta ancora a `/fatture/cane.pdf`, percorso che non
esiste più dopo la riorganizzazione delle cartelle: va cambiato in
`/DDT/da_leggere/*.pdf`. Anche il nodo **`Email riepilogo`** ha il Subject
scritto a mano (`Ripeilogo TEst`) invece di `={{ $json.oggetto }}`, che il Code
node calcola già.
