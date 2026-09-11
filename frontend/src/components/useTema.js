import { useCallback, useEffect, useState } from 'react';

// Il tema chiaro/scuro. Bootstrap 5.3 lo legge da data-bs-theme sull'<html> e
// ne fa discendere TUTTE le variabili (--bs-body-bg, --bs-border-color,
// --bs-secondary-bg...): per questo nei componenti non ci sono piu' classi
// bg-dark/text-light ma bg-body-tertiary/text-body, che cambiano da sole.
// L'unica eccezione legittima e' cio' che sta sopra a un colore FISSO — il
// badge su una pill arancione, il testo bianco su un bottone pieno — che non
// deve seguire il tema perche' il suo fondo non lo segue.
export const CHIAVE_TEMA = 'gestionale-tema';
const TEMI = ['dark', 'light'];

// La stessa scelta la rifa' uno script inline in index.html PRIMA che React
// monti: senza, la pagina lampeggia nel tema sbagliato per un fotogramma.
// Tenere le due letture allineate e' il prezzo di non avere quel lampeggio.
export function temaIniziale() {
  try {
    const salvato = localStorage.getItem(CHIAVE_TEMA);
    if (TEMI.includes(salvato)) return salvato;
  } catch {
    // localStorage negato (finestra in incognito, criterio di dominio): non e'
    // un errore da mostrare, si ripiega sulla preferenza di sistema.
  }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export default function useTema() {
  const [tema, setTema] = useState(temaIniziale);

  useEffect(() => {
    document.documentElement.setAttribute('data-bs-theme', tema);
    try {
      localStorage.setItem(CHIAVE_TEMA, tema);
    } catch {
      // Come sopra: il tema resta valido per questa sessione e basta.
    }
  }, [tema]);

  const cambiaTema = useCallback(() => {
    setTema((attuale) => (attuale === 'dark' ? 'light' : 'dark'));
  }, []);

  return [tema, cambiaTema];
}
