import React from 'react';
import { FileText, RefreshCw, BrainCircuit, FilePlus } from 'lucide-react';

export default function Header({ onRefresh, isLoading, onViewSuppliers, onManualAdd }) {
  return (
    <nav className="navbar navbar-expand-lg bg-dark border-bottom border-secondary mb-4">
      <div className="container-fluid px-4 py-2 d-flex justify-content-between align-items-center">
        
        {/* 1. SINISTRA: Logo e Titolo */}
        <div className="d-flex align-items-center gap-2" style={{ minWidth: '250px' }}>
          <div className="bg-primary p-2 rounded text-white d-flex align-items-center shadow-sm">
            <FileText size={24} />
          </div>
          <span className="navbar-brand mb-0 h5 fw-bold text-light ms-2">
            Gestione D.D.T. & Fatture
          </span>
        </div>

        {/* 2. CENTRO: Pulsante AI Prominente */}
        <div className="d-flex justify-content-center flex-grow-1">
          <button 
            className="btn btn-info px-4 py-2 fw-bold text-dark d-flex align-items-center gap-2 shadow" 
            style={{ fontSize: '1.05rem', borderRadius: '30px' }}
            onClick={onViewSuppliers}
            title="Gestisci le regole dell'Intelligenza Artificiale"
          >
            <BrainCircuit size={22} /> 
            Addestramento AI
          </button>
        </div>

        {/* 3. DESTRA: Autore, Aggiunta Manuale e Pulsante Sincronizza */}
        <div className="d-flex align-items-center justify-content-end gap-3" style={{ minWidth: '250px' }}>
          <div className="text-end d-none d-xl-block me-2">
            <small className="text-secondary d-block">Powered by Bordao Studio</small>
            <small className="text-muted" style={{ fontSize: '0.7rem' }}>Author: Lorenzo Bordi</small>
          </div>

          <button
            className="btn btn-success d-flex align-items-center gap-2 shadow-sm"
            onClick={onManualAdd}
            title="Aggiungi a mano un D.D.T. già verificato, senza passare dall'AI"
          >
            <FilePlus size={18} />
            <span className="d-none d-md-inline">Aggiungi Manuale</span>
          </button>

          <button
            className="btn btn-primary d-flex align-items-center gap-2 shadow-sm" 
            onClick={onRefresh}
            disabled={isLoading}
          >
            <RefreshCw size={18} className={isLoading ? "fa-spin" : ""} />
            <span className="d-none d-sm-inline">
              {isLoading ? 'Sincronizzazione...' : 'Sincronizza'}
            </span>
          </button>
        </div>

      </div>
    </nav>
  );
}