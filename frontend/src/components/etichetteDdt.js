// Vocabolario condiviso tra la tabella dei D.D.T. e il modale di revisione: gli
// stessi tre stati, con gli stessi colori e le stesse spiegazioni, compaiono in
// entrambi. Stessa ragione di etichetteFatture.js: due copie divergono al primo
// ritocco.

/** Stato del documento, come lo scrive il backend in OK.json / CHECK.json / KO.json. */
export const STATI_DDT = {
  OK: {
    etichetta: 'Completato',
    badge: 'bg-success text-white',
    colore: 'success',
    spiegazione: 'Tutti i campi obbligatori sono stati letti e la scansione era leggibile.',
  },
  CHECK: {
    etichetta: 'Da verificare',
    badge: 'bg-warning text-dark',
    colore: 'warning',
    spiegazione: 'Manca qualche campo, oppure la scansione è poco leggibile: va riguardato a mano.',
  },
  KO: {
    etichetta: 'Errore',
    badge: 'bg-danger text-white',
    colore: 'danger',
    spiegazione: 'Documento inservibile: nessun campo letto, retro bianco, scansione doppia, bolla da rifare.',
  },
};

/** L'ordine in cui gli stati si mostrano: dal documento buono a quello da buttare. */
export const ORDINE_STATI = ['OK', 'CHECK', 'KO'];

/** Non lascia mai scoperta una voce con uno stato imprevisto (registri vecchi). */
export const infoStato = (stato) => STATI_DDT[stato] || {
  etichetta: stato || '—',
  badge: 'bg-secondary text-white',
  colore: 'secondary',
  spiegazione: '',
};
