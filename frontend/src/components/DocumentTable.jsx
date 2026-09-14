import React from 'react';
import { Edit2, Trash2, Receipt, AlertTriangle } from 'lucide-react';
import { infoStato } from './etichetteDdt';

export default function DocumentTable({ documents, onEdit, onDelete, selectedIds = [], onToggleSelect, onApriFattura }) {

  // I campi non estratti restano evidenti invece di sparire in un grigio spento:
  // su questa tabella si lavora proprio per trovare i buchi da correggere.
  const campoMancante = <span className="text-warning fst-italic">Mancante</span>;

  return (
    <div className="card border-0">
      <div className="card-body p-0">
        <div className="table-responsive">
          {/* table-striped per la leggibilità: i colori li mette il tema (data-bs-theme) */}
          <table className="table table-striped table-hover align-middle mb-0">
            <thead className="table-secondary">
              <tr>
                <th className="px-4 py-3 border-0" style={{ width: '52px' }} title="Seleziona per unire più pagine in un unico documento"></th>
                <th className="py-3 border-0">Elaborato il</th>
                <th className="py-3 border-0">File Originale</th>
                <th className="py-3 border-0">Stato</th>
                <th className="py-3 border-0">Fornitore</th>
                <th className="py-3 border-0">N. DDT</th>
                <th className="py-3 border-0">Data DDT</th>
                <th className="py-3 border-0" title="Fattura che ha agganciato questo D.D.T.">Fattura</th>
                <th className="px-4 py-3 text-end border-0">Azioni</th>
              </tr>
            </thead>
            <tbody className="border-top-0">
              {documents.length === 0 ? (
                <tr>
                  <td colSpan="9" className="text-center py-5 text-body-secondary">
                    Nessun documento trovato in questa categoria.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => {
                  // L'indice nella selezione fa da ordine delle pagine nel documento unito:
                  // il n. 1 è il documento principale, i suoi dati vincono sugli altri.
                  const ordineSelezione = selectedIds.indexOf(doc.id);
                  return (
                  <tr key={doc.id} className={ordineSelezione >= 0 ? 'table-active' : undefined}>
                    <td className="px-4">
                      <div className="d-flex align-items-center gap-2">
                        <input
                          type="checkbox"
                          className="form-check-input mt-0"
                          checked={ordineSelezione >= 0}
                          onChange={() => onToggleSelect?.(doc.id)}
                          aria-label={`Seleziona documento ${doc.dati?.numero_ddt || doc.id}`}
                        />
                        {ordineSelezione >= 0 && (
                          <span className="badge rounded-pill bg-info text-dark">{ordineSelezione + 1}</span>
                        )}
                      </div>
                    </td>
                    <td className="text-body small">{new Date(doc.timestamp).toLocaleString('it-IT')}</td>
                    <td className="fw-medium text-body">{doc.file_origine}</td>
                    <td>
                      <span
                        className={`badge rounded-pill ${infoStato(doc.status).badge}`}
                        title={doc.stato_manuale
                          ? 'Stato impostato a mano dalla revisione, non dal classificatore.'
                          : infoStato(doc.status).spiegazione}
                      >
                        {doc.status}{doc.stato_manuale && '*'}
                      </span>
                    </td>
                    <td className="text-body fw-medium">
                      {doc.dati?.fornitore || campoMancante}
                      {/* Senza questo badge un CHECK con tutti e quattro i campi
                          pieni sembrerebbe finito lì per errore: è l'unico stato
                          che non si spiega guardando le colonne accanto. */}
                      {doc.dati?.fornitore_critico && (
                        <span
                          className="badge bg-warning bg-opacity-25 text-warning border border-warning border-opacity-50 d-inline-flex align-items-center gap-1 ms-2"
                          title="Fornitore critico: le sue bolle vanno sempre in CHECK, anche con tutti i campi letti."
                        >
                          <AlertTriangle size={12} /> critico
                        </span>
                      )}
                    </td>
                    <td className="font-monospace text-body fw-bold">{doc.dati?.numero_ddt || campoMancante}</td>
                    <td className="font-monospace text-body">{doc.dati?.data_ddt || campoMancante}</td>
                    <td>
                      {doc.fattura?.numero_fattura ? (
                        <button
                          className="btn btn-sm btn-outline-success py-0 px-2 d-inline-flex align-items-center gap-1 font-monospace"
                          onClick={() => onApriFattura?.(doc.fattura.id_fattura)}
                          title={`Apri il fascicolo della fattura ${doc.fattura.numero_fattura}`}
                        >
                          <Receipt size={14} /> {doc.fattura.numero_fattura}
                        </button>
                      ) : (
                        <span className="text-body-secondary small" title="Nessuna fattura ha ancora citato questo D.D.T.">
                          attesa
                        </span>
                      )}
                    </td>
                    <td className="px-4 text-end">
                      <button className="btn btn-sm btn-outline-info me-2 shadow-sm" onClick={() => onEdit(doc)}>
                        <Edit2 size={16} className="me-1" /> Revisiona
                      </button>
                      <button className="btn btn-sm btn-outline-danger shadow-sm" onClick={() => onDelete(doc.id)}>
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}