import React from 'react';
import { FileText, RefreshCw, BrainCircuit, FilePlus, Truck, Receipt, Sliders } from 'lucide-react';

// Le sezioni del gestionale: le tre entita' del dominio piu' le impostazioni.
// Il badge non conta le righe della sezione ma SOLO quelle che chiedono un
// intervento (DDT da verificare, fatture in coda, P.IVA da confermare): un
// numero che non cala mai smette di essere letto dopo tre giorni. La
// Configurazione non ne ha: non e' lavoro arretrato, e' un pannello.
const SEZIONI = [
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

export default function Header({ vista, onVista, onRefresh, isLoading, onManualAdd, badge = {} }) {
  return (
    <nav className="navbar navbar-expand-lg bg-dark border-bottom border-secondary mb-4 sticky-top">
      <div className="container-fluid px-4 py-2 d-flex justify-content-between align-items-center gap-3">

        {/* 1. SINISTRA: Logo e Titolo */}
        <div className="d-flex align-items-center gap-2 flex-shrink-0">
          <div className="bg-primary p-2 rounded text-white d-flex align-items-center shadow-sm">
            <FileText size={22} />
          </div>
          <span className="navbar-brand mb-0 h6 fw-bold text-light ms-2 d-none d-xl-inline">
            Gestione D.D.T. &amp; Fatture
          </span>
        </div>

        {/* 2. CENTRO: le tre sezioni del gestionale */}
        <ul className="nav nav-pills gap-2 flex-nowrap justify-content-center flex-grow-1">
          {SEZIONI.map(({ id, etichetta, icona: Icona, titolo }) => {
            const attiva = vista === id;
            const daFare = badge[id] || 0;

            return (
              <li className="nav-item" key={id}>
                <button
                  type="button"
                  className={`nav-link d-flex align-items-center gap-2 px-3 ${
                    attiva ? 'active bg-primary text-white fw-bold' : 'text-secondary border border-secondary'
                  }`}
                  onClick={() => onVista(id)}
                  title={titolo}
                >
                  <Icona size={18} />
                  <span className="d-none d-md-inline">{etichetta}</span>
                  {daFare > 0 && (
                    <span
                      className={`badge rounded-pill ${attiva ? 'bg-white text-primary' : 'bg-warning text-dark'}`}
                      title="Righe che aspettano un intervento"
                    >
                      {daFare}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>

        {/* 3. DESTRA: azioni globali */}
        <div className="d-flex align-items-center justify-content-end gap-2 flex-shrink-0">
          <div className="text-end d-none d-xxl-block me-2">
            <small className="text-secondary d-block">Powered by Bordao Studio</small>
            <small className="text-muted" style={{ fontSize: '0.7rem' }}>Author: Lorenzo Bordi</small>
          </div>

          {vista === 'DDT' && (
            <button
              className="btn btn-success d-flex align-items-center gap-2 shadow-sm"
              onClick={onManualAdd}
              title="Aggiungi a mano un D.D.T. già verificato, senza passare dall'AI"
            >
              <FilePlus size={18} />
              <span className="d-none d-lg-inline">Aggiungi Manuale</span>
            </button>
          )}

          <button
            className="btn btn-primary d-flex align-items-center gap-2 shadow-sm"
            onClick={onRefresh}
            disabled={isLoading}
            title="Ricarica documenti, fatture e anagrafica"
          >
            <RefreshCw size={18} className={isLoading ? 'fa-spin' : ''} />
            <span className="d-none d-lg-inline">
              {isLoading ? 'Sincronizzazione...' : 'Sincronizza'}
            </span>
          </button>
        </div>
      </div>
    </nav>
  );
}
