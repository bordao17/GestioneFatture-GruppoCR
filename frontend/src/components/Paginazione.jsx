import React, { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

// Quante righe per pagina, per tutte e tre le sezioni. Sta qui una volta sola:
// tre costanti uguali in tre file divergono al primo ritocco.
export const ELEMENTI_PER_PAGINA = 50;

/**
 * Ritaglia una lista GIA' filtrata e ordinata nella pagina corrente.
 *
 * `chiaveVista` descrive *cosa* si sta guardando (tab, ricerca, filtro): quando
 * cambia si torna a pagina 1, altrimenti restare a pagina 4 dopo aver cambiato
 * filtro mostra una tabella vuota che sembra un errore. Non ci va la lunghezza
 * della lista: cancellare una riga non deve rimandare all'inizio.
 */
export function usePaginazione(elementi, chiaveVista) {
  const [pagina, setPagina] = useState(1);

  useEffect(() => {
    setPagina(1);
  }, [chiaveVista]);

  const totale = elementi.length;
  const pagine = Math.max(1, Math.ceil(totale / ELEMENTI_PER_PAGINA));
  // Se cancellando righe l'ultima pagina sparisce, si scala invece di mostrare
  // il vuoto: la correzione e' in lettura, cosi' non serve un effetto in piu'.
  const corrente = Math.min(pagina, pagine);
  const inizio = (corrente - 1) * ELEMENTI_PER_PAGINA;

  const visibili = useMemo(
    () => elementi.slice(inizio, inizio + ELEMENTI_PER_PAGINA),
    [elementi, inizio]
  );

  return { visibili, pagina: corrente, pagine, totale, inizio, setPagina };
}

/**
 * La barra sotto la tabella. Non si mostra quando c'e' una pagina sola: su
 * archivi piccoli sarebbe rumore, e il conteggio delle righe e' gia' altrove.
 */
export default function Paginazione({ pagina, pagine, totale, inizio, setPagina, etichetta = 'elementi' }) {
  if (pagine <= 1) return null;

  const vai = (n) => setPagina(Math.min(Math.max(1, n), pagine));

  // Finestra di cinque numeri intorno alla pagina corrente: con 40 pagine
  // l'elenco completo sarebbe piu' lungo della tabella.
  const primo = Math.max(1, Math.min(pagina - 2, pagine - 4));
  const numeri = [];
  for (let n = primo; n < primo + 5 && n <= pagine; n += 1) numeri.push(n);

  const bottone = (chiave, contenuto, azione, disabilitato, titolo) => (
    <li key={chiave} className={`page-item ${disabilitato ? 'disabled' : ''}`}>
      <button
        type="button"
        className="page-link"
        onClick={azione}
        disabled={disabilitato}
        title={titolo}
      >
        {contenuto}
      </button>
    </li>
  );

  return (
    <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 px-4 py-2">
      <span className="text-body-secondary small">
        {inizio + 1}–{Math.min(inizio + ELEMENTI_PER_PAGINA, totale)} di {totale} {etichetta}
      </span>

      <nav aria-label={`Pagine ${etichetta}`}>
        <ul className="pagination pagination-sm mb-0">
          {bottone('primo', <ChevronsLeft size={15} />, () => vai(1), pagina === 1, 'Prima pagina')}
          {bottone('prec', <ChevronLeft size={15} />, () => vai(pagina - 1), pagina === 1, 'Pagina precedente')}
          {numeri.map((n) => (
            <li key={n} className={`page-item ${n === pagina ? 'active' : ''}`}>
              <button
                type="button"
                className={`page-link ${n === pagina ? 'bg-info border-info text-dark fw-bold' : ''}`}
                onClick={() => vai(n)}
              >
                {n}
              </button>
            </li>
          ))}
          {bottone('succ', <ChevronRight size={15} />, () => vai(pagina + 1), pagina === pagine, 'Pagina successiva')}
          {bottone('ultimo', <ChevronsRight size={15} />, () => vai(pagine), pagina === pagine, 'Ultima pagina')}
        </ul>
      </nav>
    </div>
  );
}
