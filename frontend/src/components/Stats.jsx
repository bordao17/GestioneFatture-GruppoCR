import React from 'react';

export default function Stats({ stats }) {
  return (
    <div className="row g-4 mb-4">
      <div className="col-md-4">
        <div className="card border-0 shadow-sm h-100 border-start border-4 border-primary">
          <div className="card-body">
            <h6 className="text-muted mb-2">Documenti Totali</h6>
            <h2 className="mb-0 fw-bold">{stats.totali}</h2>
          </div>
        </div>
      </div>
      <div className="col-md-4">
        <div className="card border-0 shadow-sm h-100 border-start border-4 border-warning">
          <div className="card-body">
            <h6 className="text-muted mb-2">Richiedono Attenzione</h6>
            <h2 className="mb-0 fw-bold text-warning">{stats.daVerificare}</h2>
          </div>
        </div>
      </div>
      <div className="col-md-4">
        <div className="card border-0 shadow-sm h-100 border-start border-4 border-success">
          <div className="card-body">
            <h6 className="text-muted mb-2">Elaborati Correttamente</h6>
            <h2 className="mb-0 fw-bold text-success">{stats.completati}</h2>
          </div>
        </div>
      </div>
    </div>
  );
}