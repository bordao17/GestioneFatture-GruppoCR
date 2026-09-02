import React from 'react';
import { Combine, X } from 'lucide-react';

/**
 * Barra di unione manuale: compare quando si selezionano documenti dalle tabelle.
 * L'ordine di selezione è l'ordine delle pagine nel documento finale, e il primo
 * selezionato è il principale (i suoi dati vincono su quelli degli altri).
 */
export default function MergeBar({ selectedDocs, onMerge, onClear, isMerging }) {
  if (selectedDocs.length === 0) return null;

  const abbastanza = selectedDocs.length >= 2;

  return (
    <div className="card bg-dark border-info shadow-sm mb-3">
      <div className="card-body py-3 px-4 d-flex flex-wrap align-items-center gap-3">
        <div className="flex-grow-1">
          <div className="text-info fw-bold d-flex align-items-center gap-2 mb-2">
            <Combine size={18} />
            {selectedDocs.length} {selectedDocs.length === 1 ? 'documento selezionato' : 'documenti selezionati'}
          </div>

          <div className="d-flex flex-wrap gap-2">
            {selectedDocs.map((doc, i) => (
              <span key={doc.id} className="badge bg-secondary text-light fw-normal">
                <span className="badge rounded-pill bg-info text-dark me-2">{i + 1}</span>
                {doc.dati?.fornitore || 'Fornitore mancante'}
                <span className="font-monospace ms-2 text-white-50">
                  {doc.dati?.numero_ddt || 's.n.'} · {doc.status}
                </span>
              </span>
            ))}
          </div>

          <div className="small text-secondary mt-2">
            {abbastanza
              ? 'Le pagine verranno unite in questo ordine. Il n. 1 è il documento principale: i suoi dati restano, gli altri riempiono solo i campi vuoti.'
              : 'Seleziona almeno un altro documento (anche da un altro tab) per poterli unire.'}
          </div>
        </div>

        <div className="d-flex gap-2">
          <button className="btn btn-outline-secondary btn-sm" onClick={onClear} disabled={isMerging}>
            <X size={16} className="me-1" /> Annulla
          </button>
          <button className="btn btn-info btn-sm fw-bold" onClick={onMerge} disabled={!abbastanza || isMerging}>
            <Combine size={16} className="me-1" />
            {isMerging ? 'Unione in corso…' : 'Unisci in un documento'}
          </button>
        </div>
      </div>
    </div>
  );
}
