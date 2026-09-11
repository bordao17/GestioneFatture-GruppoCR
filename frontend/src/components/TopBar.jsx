import React from 'react';
import { RefreshCw, FilePlus } from 'lucide-react';
import { sezione } from './sezioni';

// La barra in alto del contenuto: dice DOVE si e' e offre le azioni globali.
//
// Le sezioni sono passate alla colonna di sinistra, ma "Sincronizza" e
// "Aggiungi Manuale" non sono navigazione: agiscono sulla pagina che si sta
// guardando, quindi restano in alto a destra, dove stavano. Il titolo non e'
// decorazione — con la barra laterale ridotta a icone e' l'unico posto in cui
// e' scritto per esteso in quale sezione si e' finiti.
export default function TopBar({ vista, onRefresh, isLoading, onManualAdd }) {
  const { etichetta, titolo } = sezione(vista);

  return (
    <header className="barra-alta bg-body border-bottom px-4 py-2 d-flex align-items-center justify-content-between gap-3">
      <div className="min-w-0">
        <h1 className="h6 fw-semibold mb-0 text-truncate">{etichetta}</h1>
        <div className="text-body-secondary text-truncate d-none d-md-block" style={{ fontSize: '0.78rem' }}>
          {titolo}
        </div>
      </div>

      <div className="d-flex align-items-center gap-2 flex-shrink-0">
        {vista === 'DDT' && (
          <button
            className="btn btn-success btn-sm d-flex align-items-center gap-2 shadow-sm"
            onClick={onManualAdd}
            title="Aggiungi a mano un D.D.T. già verificato, senza passare dall'AI"
          >
            <FilePlus size={16} />
            <span className="d-none d-lg-inline">Aggiungi Manuale</span>
          </button>
        )}

        <button
          className="btn btn-primary btn-sm d-flex align-items-center gap-2 shadow-sm"
          onClick={onRefresh}
          disabled={isLoading}
          title="Ricarica documenti, fatture e anagrafica"
        >
          <RefreshCw size={16} className={isLoading ? 'gira' : ''} />
          <span className="d-none d-lg-inline">
            {isLoading ? 'Sincronizzazione...' : 'Sincronizza'}
          </span>
        </button>
      </div>
    </header>
  );
}
