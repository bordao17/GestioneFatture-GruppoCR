import React from 'react';
import { FileSearch } from 'lucide-react';

// Le estrazioni "classiche" (PDF intero, di solito lanciate da n8n sulla
// cartella monitorata) durano minuti: senza questa barra la dashboard sembra
// ferma e non c'è modo di capire che il modello sta lavorando.
function formattaDurata(secondi) {
  const totale = Math.max(0, Math.round(secondi || 0));
  const minuti = Math.floor(totale / 60);
  const resto = totale % 60;
  return minuti > 0 ? `${minuti}m ${resto}s` : `${resto}s`;
}

export default function ProcessingBar({ lavori }) {
  if (!lavori || lavori.length === 0) return null;

  return (
    <div className="card bg-dark border-info border-opacity-50 shadow-sm mb-4">
      <div className="card-body py-3">
        {lavori.map((lavoro, indice) => {
          const totale = lavoro.pagine_totali || 0;
          const corrente = lavoro.pagina_corrente || 0;

          // Finché il PDF non è stato diviso in pagine non sappiamo quanto
          // manca: meglio una barra indeterminata di una percentuale inventata.
          const indeterminata = totale === 0;
          const percentuale = indeterminata
            ? 100
            : Math.min(100, Math.round((corrente / totale) * 100));

          return (
            <div key={lavoro.id} className={indice < lavori.length - 1 ? 'mb-3' : ''}>
              <div className="d-flex justify-content-between align-items-center small mb-1 gap-3">
                <span className="fw-bold text-info d-flex align-items-center gap-2 text-truncate">
                  <FileSearch size={16} className="flex-shrink-0" />
                  <span className="text-truncate">
                    {lavoro.tipo === 'rianalisi' ? 'Rianalisi AI' : 'Analisi AI'}: {lavoro.file}
                  </span>
                </span>
                <span className="text-secondary text-nowrap">
                  {indeterminata ? 'preparazione pagine...' : `pagina ${corrente} di ${totale}`}
                  {' · '}
                  {formattaDurata(lavoro.secondi)}
                </span>
              </div>

              <div className="progress bg-black" style={{ height: '8px' }}>
                <div
                  className="progress-bar bg-info progress-bar-striped progress-bar-animated"
                  role="progressbar"
                  aria-valuenow={indeterminata ? undefined : percentuale}
                  aria-valuemin="0"
                  aria-valuemax="100"
                  style={{ width: `${percentuale}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
