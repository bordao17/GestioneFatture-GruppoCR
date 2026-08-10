import React from 'react';
import { FileText, RefreshCw } from 'lucide-react';

export default function Header({ onRefresh, isLoading }) {
  return (
    <nav className="navbar navbar-expand-lg navbar-light bg-white shadow-sm mb-4">
      <div className="container-fluid px-4 py-2">
        <div className="d-flex align-items-center gap-2">
          <div className="bg-primary p-2 rounded text-white d-flex align-items-center">
            <FileText size={20} />
          </div>
          <span className="navbar-brand mb-0 h5 fw-bold text-primary ms-2">
            Gestione D.D.T. & Fatture
          </span>
        </div>
        <div className="d-flex align-items-center">
          <span className="text-muted me-4 small">by Lo Staff di  S.n.C.</span>
          <button 
            className="btn btn-outline-primary btn-sm d-flex align-items-center gap-2" 
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RefreshCw size={16} className={isLoading ? "fa-spin" : ""} />
            {isLoading ? 'Aggiornamento...' : 'Aggiorna'}
          </button>
        </div>
      </div>
    </nav>
  );
}