import React from 'react';

export default function Stats({ stats }) {
  return (
    <div className="row g-3 mb-4">
      <div className="col-md-3">
        <div className="card bg-dark border-secondary shadow-sm h-100 border-start border-4 border-primary">
          <div className="card-body py-3">
            <h6 className="text-secondary mb-1 text-uppercase fw-bold" style={{ fontSize: '0.75rem' }}>Totali</h6>
            <h3 className="mb-0 fw-bold text-light">{stats.totali}</h3>
          </div>
        </div>
      </div>
      <div className="col-md-3">
        <div className="card bg-dark border-secondary shadow-sm h-100 border-start border-4 border-success">
          <div className="card-body py-3">
            <h6 className="text-secondary mb-1 text-uppercase fw-bold" style={{ fontSize: '0.75rem' }}>Completati (OK)</h6>
            <h3 className="mb-0 fw-bold text-success">{stats.ok}</h3>
          </div>
        </div>
      </div>
      <div className="col-md-3">
        <div className="card bg-dark border-secondary shadow-sm h-100 border-start border-4 border-warning">
          <div className="card-body py-3">
            <h6 className="text-secondary mb-1 text-uppercase fw-bold" style={{ fontSize: '0.75rem' }}>Da Verificare (Check)</h6>
            <h3 className="mb-0 fw-bold text-warning">{stats.check}</h3>
          </div>
        </div>
      </div>
      <div className="col-md-3">
        <div className="card bg-dark border-secondary shadow-sm h-100 border-start border-4 border-danger">
          <div className="card-body py-3">
            <h6 className="text-secondary mb-1 text-uppercase fw-bold" style={{ fontSize: '0.75rem' }}>Errori (KO)</h6>
            <h3 className="mb-0 fw-bold text-danger">{stats.ko}</h3>
          </div>
        </div>
      </div>
    </div>
  );
}