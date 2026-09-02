import React from 'react';
import { Edit2, Trash2 } from 'lucide-react';

export default function DocumentTable({ documents, onEdit, onDelete, selectedIds = [], onToggleSelect }) {
  const getStatusBadge = (status) => {
    switch (status) {
      case 'OK': return 'bg-success text-white';
      case 'CHECK': return 'bg-warning text-dark';
      case 'KO': return 'bg-danger text-white';
      default: return 'bg-secondary text-white';
    }
  };

  // I campi non estratti restano evidenti invece di sparire in un grigio spento:
  // su questa tabella si lavora proprio per trovare i buchi da correggere.
  const campoMancante = <span className="text-warning fst-italic">Mancante</span>;

  return (
    <div className="card bg-dark border-0">
      <div className="card-body p-0">
        <div className="table-responsive">
          {/* Aggiunto table-dark, table-striped per migliorare la leggibilità */}
          <table className="table table-dark table-striped table-hover align-middle mb-0">
            <thead className="table-secondary">
              <tr>
                <th className="px-4 py-3 border-0" style={{ width: '52px' }} title="Seleziona per unire più pagine in un unico documento"></th>
                <th className="py-3 border-0">Elaborato il</th>
                <th className="py-3 border-0">File Originale</th>
                <th className="py-3 border-0">Stato</th>
                <th className="py-3 border-0">Fornitore</th>
                <th className="py-3 border-0">N. DDT</th>
                <th className="py-3 border-0">Data DDT</th>
                <th className="px-4 py-3 text-end border-0">Azioni</th>
              </tr>
            </thead>
            <tbody className="border-top-0">
              {documents.length === 0 ? (
                <tr>
                  <td colSpan="8" className="text-center py-5 text-secondary">
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
                    <td className="text-light small">{new Date(doc.timestamp).toLocaleString('it-IT')}</td>
                    <td className="fw-medium text-light">{doc.file_origine}</td>
                    <td><span className={`badge rounded-pill ${getStatusBadge(doc.status)}`}>{doc.status}</span></td>
                    <td className="text-white fw-medium">{doc.dati?.fornitore || campoMancante}</td>
                    <td className="font-monospace text-white fw-bold">{doc.dati?.numero_ddt || campoMancante}</td>
                    <td className="font-monospace text-white">{doc.dati?.data_ddt || campoMancante}</td>
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