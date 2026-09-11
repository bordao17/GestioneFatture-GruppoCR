import { BrainCircuit, Truck, Receipt, Sliders } from 'lucide-react';

// Le sezioni del gestionale: le tre entita' del dominio piu' le impostazioni.
// Stanno in un modulo loro e non dentro la barra laterale perche' le legge
// anche la barra in alto, per scriverci titolo e sottotitolo della pagina: il
// nome di una sezione e' uno solo, e in due posti diversi divergerebbe.
//
// Il badge non conta le righe della sezione ma SOLO quelle che chiedono un
// intervento (DDT da verificare, fatture in coda, P.IVA da confermare): un
// numero che non cala mai smette di essere letto dopo tre giorni. La
// Configurazione non ne ha: non e' lavoro arretrato, e' un pannello.
export const SEZIONI = [
  {
    id: 'DDT',
    etichetta: 'D.D.T.',
    icona: Truck,
    titolo: 'Bolle scansionate e lette dal modello',
  },
  {
    id: 'FATTURE',
    etichetta: 'Fatture',
    icona: Receipt,
    titolo: 'Fatture elettroniche e loro abbinamento ai D.D.T.',
  },
  {
    id: 'FORNITORI',
    etichetta: 'Fornitori',
    icona: BrainCircuit,
    titolo: 'Anagrafica: P.IVA, indirizzi vietati e regole per il modello',
  },
  {
    id: 'CONFIGURAZIONE',
    etichetta: 'Configurazione',
    icona: Sliders,
    titolo: 'Server Ollama, modello vision e soglie dei solleciti',
  },
];

export function sezione(id) {
  return SEZIONI.find((s) => s.id === id) || SEZIONI[0];
}
