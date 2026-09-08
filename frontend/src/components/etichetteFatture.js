// Vocabolario condiviso tra la tabella delle fatture e il modale del fascicolo.
// Sta in un file solo perché gli stessi stati, gli stessi colori e le stesse
// spiegazioni compaiono in entrambi: due copie divergono al primo ritocco.

/** Stato della pratica, come lo scrive il backend in FATTURE.json / ATTESA.json. */
export const STATI_FATTURA = {
  ABBINATA: {
    etichetta: 'Abbinata',
    badge: 'bg-success text-white',
    colore: 'success',
    spiegazione: 'Accoppiata: l’operatore ha confermato e il file unico fattura + D.D.T. è nella cartella ACCOPPIATE.',
  },
  IN_ATTESA: {
    etichetta: 'In attesa',
    badge: 'bg-warning text-dark',
    colore: 'warning',
    spiegazione: 'Manca ancora qualche D.D.T. La pratica resta aperta e viene ricontrollata da sola a ogni nuova bolla.',
  },
  DA_ABBINARE: {
    etichetta: 'Da abbinare',
    badge: 'bg-primary text-white',
    colore: 'primary',
    // Stato di partenza dal 2026-09-08: leggere una fattura e cercarle i D.D.T.
    // sono due gesti diversi, e il secondo lo chiede una persona.
    spiegazione: 'Fattura letta e archiviata, ma il confronto con i D.D.T. non e ancora stato chiesto. Premi ABBINA su questa riga, oppure "Abbina tutte" per l intera coda.',
  },
  NON_ABBINATA: {
    etichetta: 'Non abbinata',
    badge: 'bg-secondary text-white',
    colore: 'secondary',
    spiegazione: 'La fattura non cita nessun documento di trasporto (consulenze, note di credito): non c’è merce da agganciare.',
  },
};

/**
 * Pratica pronta ma non ancora firmata.
 *
 * Non è uno stato del backend ma la combinazione di due cose: stato ABBINATA e
 * voce ancora in coda (in_coda). Da quando la chiusura è manuale lo stato da
 * solo non basta più a distinguere "i D.D.T. sono stati tutti trovati" da
 * "l'operatore ha confermato e il file unico esiste", e sono due situazioni
 * molto diverse per chi guarda l'elenco: la prima chiede un'azione.
 */
export const PRONTA = {
  etichetta: 'Da accoppiare',
  badge: 'bg-info text-dark',
  colore: 'info',
  spiegazione: 'Tutti i D.D.T. citati sono stati trovati. Manca la conferma: il pulsante Accoppia crea il file unico fattura + D.D.T. nella cartella ACCOPPIATE.',
};

/** Esito del singolo riferimento D.D.T. dentro la fattura. */
export const ESITI_RIGA = {
  abbinato: {
    etichetta: 'Abbinato',
    badge: 'bg-success text-white',
    colore: 'success',
  },
  probabile: {
    etichetta: 'Da confermare',
    badge: 'bg-info text-dark',
    colore: 'info',
    // È il caso che dà valore a tutto il flusso: la fattura è esatta, quindi
    // un quasi-match segnala una cifra letta male sul D.D.T., non una bolla
    // mancante. Ricontrollarlo all'infinito darebbe sempre lo stesso esito.
    azione: 'Il D.D.T. probabilmente c’è già ma con il numero letto male: aprilo, correggi il numero e la fattura si chiude da sola.',
  },
  da_abbinare: {
    etichetta: 'Da abbinare',
    badge: 'bg-primary text-white',
    colore: 'primary',
    azione: 'Il confronto con i D.D.T. archiviati non e ancora stato eseguito: premi ABBINA.',
  },
  non_trovato: {
    etichetta: 'Mancante',
    badge: 'bg-danger text-white',
    colore: 'danger',
    azione: 'Nessun D.D.T. archiviato con questo numero: va cercata la bolla in magazzino e scansionata.',
  },
};

/** Forma della fattura, decisa da classifica_fattura() sulla struttura dell'XML. */
export const TIPI_ABBINAMENTO = {
  differita: {
    etichetta: 'Differita',
    badge: 'bg-primary text-white',
    spiegazione: 'I documenti di trasporto sono elencati nell’XML (1 fattura → N D.D.T.).',
  },
  accompagnatoria: {
    etichetta: 'Accompagnatoria',
    badge: 'bg-info text-dark',
    spiegazione: 'La merce ha viaggiato con la fattura: il documento di trasporto è la fattura stessa, e il numero cercato è il suo (1 → 1).',
  },
  senza_ddt: {
    etichetta: 'Senza D.D.T.',
    badge: 'bg-secondary text-white',
    spiegazione: 'Né riferimenti né dati di trasporto: non c’è nessuna bolla da attendere.',
  },
};

export const statoFattura = (stato) =>
  STATI_FATTURA[stato] || { etichetta: stato || '—', badge: 'bg-secondary text-white', colore: 'secondary', spiegazione: '' };

/** Lo stato da mostrare per una voce dell'elenco, coda compresa. */
export const statoPratica = (fattura) => {
  if (fattura?.in_coda && fattura.stato === 'ABBINATA') return PRONTA;
  return statoFattura(fattura?.stato);
};

/** Una pratica ancora da firmare: i pulsanti ABBINA/ACCOPPIA hanno senso solo qui. */
export const daAccoppiare = (fattura) => Boolean(fattura?.in_coda);

/**
 * Il gesto che la riga aspetta adesso, che non e' sempre lo stesso.
 *
 * Sono due pulsanti diversi sulla stessa colonna: ABBINA cerca i D.D.T. (non
 * scrive niente), ACCOPPIA firma e crea il file unico. Chiamarli tutti e due
 * "Accoppia" farebbe sembrare irreversibile anche il primo.
 */
export const azionePratica = (fattura) => {
  if (!fattura?.in_coda) return null;
  return fattura.stato === 'DA_ABBINARE' ? 'abbina' : 'accoppia';
};

export const esitoRiga = (esito) =>
  ESITI_RIGA[esito] || { etichetta: esito || '—', badge: 'bg-secondary text-white', colore: 'secondary' };

export const tipoAbbinamento = (tipo) =>
  TIPI_ABBINAMENTO[tipo] || { etichetta: tipo || '—', badge: 'bg-secondary text-white', spiegazione: '' };

/** L'ImportoTotaleDocumento dell'XML è una stringa con il punto decimale. */
export const formattaImporto = (valore) => {
  const numero = Number.parseFloat(valore);
  if (!Number.isFinite(numero)) return '';
  return numero.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
};

/** Quanti riferimenti sono già agganciati con certezza. */
export const conteggioDdt = (fattura) => {
  const righe = fattura?.ddt || [];
  return {
    totali: righe.length,
    abbinati: righe.filter((r) => r.esito === 'abbinato').length,
    daConfermare: righe.filter((r) => r.esito === 'probabile').length,
    mancanti: righe.filter((r) => r.esito === 'non_trovato').length,
  };
};
