import React from 'react';
import { Edit2, Trash2 } from 'lucide-react';

export default function DocumentTable({ documents, onEdit, onDelete }) {
  const getStatusBadge = (status) => {
    switch (status) {
      case 'OK': return 'bg-success text-white';
      case 'CHECK': return 'bg-warning text-dark';
      case 'KO': return 'bg-danger text-white';
      default: return 'bg-secondary text-white';
    }
  };

  return (
    <div className="card bg-dark border-0">
      <div className="card-body p-0">
        <div className="table-responsive">
          {/* Aggiunto table-dark, table-striped per migliorare la leggibilità */}
          <table className="table table-dark table-striped table-hover align-middle mb-0">
            <thead className="table-secondary">
              <tr>
                <th className="px-4 py-3 border-0">Data</th>
                <th className="py-3 border-0">File Originale</th>
                <th className="py-3 border-0">Stato</th>
                <th className="py-3 border-0">Fornitore</th>
                <th className="py-3 border-0">N. Documento</th>
                <th className="px-4 py-3 text-end border-0">Azioni</th>
              </tr>
            </thead>
            <tbody className="border-top-0">
              {documents.length === 0 ? (
                <tr>
                  <td colSpan="6" className="text-center py-5 text-secondary">
                    Nessun documento trovato in questa categoria.
                  </td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id}>
                    <td className="px-4 text-secondary small">{new Date(doc.timestamp).toLocaleString('it-IT')}</td>
                    <td className="fw-medium text-light">{doc.file_origine}</td>
                    <td><span className={`badge rounded-pill ${getStatusBadge(doc.status)}`}>{doc.status}</span></td>
                    <td className="text-light">{doc.dati?.fornitore || <i className="text-secondary">Mancante</i>}</td>
                    <td className="font-monospace text-secondary">{doc.dati?.numero_ddt || '-'}</td>
                    <td className="px-4 text-end">
                      <button className="btn btn-sm btn-outline-info me-2 shadow-sm" onClick={() => onEdit(doc)}>
                        <Edit2 size={16} className="me-1" /> Revisiona
                      </button>
                      <button className="btn btn-sm btn-outline-danger shadow-sm" onClick={() => onDelete(doc.id)}>
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}