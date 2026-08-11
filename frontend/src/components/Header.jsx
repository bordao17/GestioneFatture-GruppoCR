import React from 'react';
import { FileText, RefreshCw } from 'lucide-react';

export default function Header({ onRefresh, isLoading }) {
  return (
    <nav className="navbar navbar-expand-lg bg-dark border-bottom border-secondary mb-4">
      <div className="container-fluid px-4 py-2">
        <div className="d-flex align-items-center gap-2">
          <div className="bg-primary p-2 rounded text-white d-flex align-items-center shadow-sm">
            <FileText size={20} />
          </div>
          <span className="navbar-brand mb-0 h5 fw-bold text-light ms-2">
            Gestione D.D.T. & Fatture
          </span>
        </div>
        <div className="d-flex align-items-center gap-4">
          <div className="text-end d-none d-sm-block">
            <small className="text-secondary d-block">Powered by Bordao Studio</small>
            <small className="text-muted" style={{ fontSize: '0.7rem' }}>Author: Lorenzo Bordi</small>
          </div>
          <button 
            className="btn btn-primary btn-sm d-flex align-items-center gap-2 shadow-sm" 
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RefreshCw size={16} className={isLoading ? "fa-spin" : ""} />
            {isLoading ? 'Sincronizzazione...' : 'Sincronizza'}
          </button>
        </div>
      </div>
    </nav>
  );
}