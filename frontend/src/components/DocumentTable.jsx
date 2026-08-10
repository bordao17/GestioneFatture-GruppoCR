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
    <div className="card border-0 shadow-sm">
      <div className="card-body p-0">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th className="px-4 py-3">Data</th>
                <th className="py-3">File Originale</th>
                <th className="py-3">Stato</th>
                <th className="py-3">Fornitore</th>
                <th className="py-3">N. Documento</th>
                <th className="px-4 py-3 text-end">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {documents.length === 0 ? (
                <tr>
                  <td colSpan="6" className="text-center py-5 text-muted">Nessun documento trovato.</td>
                </tr>
              ) : (
                documents.map((doc) => (
                  <tr key={doc.id}>
                    <td className="px-4 text-muted small">{new Date(doc.timestamp).toLocaleString('it-IT')}</td>
                    <td className="fw-medium">{doc.file_origine}</td>
                    <td><span className={`badge rounded-pill ${getStatusBadge(doc.status)}`}>{doc.status}</span></td>
                    <td>{doc.dati?.fornitore || <i className="text-muted">Mancante</i>}</td>
                    <td className="font-monospace text-muted">{doc.dati?.numero_ddt || '-'}</td>
                    <td className="px-4 text-end">
                      <button className="btn btn-sm btn-light text-primary border me-2 shadow-sm" onClick={() => onEdit(doc)}>
                        <Edit2 size={16} /> Revisiona
                      </button>
                      <button className="btn btn-sm btn-light text-danger border shadow-sm" onClick={() => onDelete(doc.id)}>
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