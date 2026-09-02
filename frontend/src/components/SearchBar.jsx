import React from 'react';
import { Search, X } from 'lucide-react';

export const CAMPI_RICERCA = [
  { valore: 'TUTTI', etichetta: 'Tutti i campi' },
  { valore: 'numero_ddt', etichetta: 'N. DDT' },
  { valore: 'fornitore', etichetta: 'Fornitore' },
  { valore: 'data_ddt', etichetta: 'Data DDT' },
];

/**
 * Barra di ricerca sui documenti già archiviati.
 * Il filtro agisce sui dati estratti, non sul timestamp di elaborazione:
 * si cerca il D.D.T. per come è scritto sul documento.
 */
export default function SearchBar({ searchTerm, setSearchTerm, searchField, setSearchField, risultati, totali }) {
  const attiva = searchTerm.trim().length > 0;

  const placeholder = {
    TUTTI: 'Cerca per numero DDT, fornitore o data…',
    numero_ddt: 'Cerca per numero DDT (es. 12345)…',
    fornitore: 'Cerca per fornitore (es. ROSSI SPA)…',
    data_ddt: 'Cerca per data DDT (es. 01-09-2026 o 09-2026)…',
  }[searchField];

  return (
    <div className="card bg-dark border-secondary shadow-sm mb-3">
      <div className="card-body py-3 px-4">
        <div className="row g-2 align-items-center">
          <div className="col-12 col-md">
            <div className="input-group">
              <span className="input-group-text bg-secondary border-secondary text-white">
                <Search size={18} />
              </span>
              <input
                type="text"
                className="form-control bg-dark text-white border-secondary"
                placeholder={placeholder}
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                aria-label="Cerca documenti"
              />
              {attiva && (
                <button
                  className="btn btn-outline-secondary text-white"
                  onClick={() => setSearchTerm('')}
                  title="Azzera la ricerca"
                >
                  <X size={18} />
                </button>
              )}
            </div>
          </div>

          <div className="col-12 col-md-auto">
            <select
              className="form-select bg-dark text-white border-secondary"
              value={searchField}
              onChange={(e) => setSearchField(e.target.value)}
              aria-label="Campo su cui cercare"
            >
              {CAMPI_RICERCA.map((c) => (
                <option key={c.valore} value={c.valore}>{c.etichetta}</option>
              ))}
            </select>
          </div>

          <div className="col-12 col-md-auto">
            <span className={`badge ${attiva ? 'bg-info text-dark' : 'bg-secondary text-white'}`}>
              {attiva ? `${risultati} di ${totali} documenti` : `${totali} documenti`}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
