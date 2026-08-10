import React from 'react';

export default function ComparisonModal({ selectedDoc, editData, setEditData, onClose, onSave, isSaving, apiUrl }) {
  if (!selectedDoc) return null;

  return (
    <div className="modal show d-block" style={{ backgroundColor: 'rgba(0,0,0,0.6)' }} tabIndex="-1">
      <div className="modal-dialog modal-xl modal-dialog-centered modal-fullscreen-lg-down">
        <div className="modal-content border-0 shadow-lg" style={{ height: '90vh' }}>
          
          <div className="modal-header bg-light py-3">
            <div>
              <h5 className="modal-title fw-bold">Validazione Documento</h5>
              <small className="text-muted">File: {selectedDoc.file_origine}</small>
            </div>
            <button type="button" className="btn-close" onClick={onClose}></button>
          </div>
          
          <div className="modal-body p-0 overflow-hidden">
            <div className="row g-0 h-100">
              
              {/* Sinistra: PDF */}
              <div className="col-lg-6 h-100 bg-secondary bg-opacity-10 border-end d-flex flex-column">
                <div className="p-2 bg-light border-bottom text-center small fw-bold text-muted text-uppercase">Documento Scansionato</div>
                <iframe src={`${apiUrl}/api/pdf/${selectedDoc.id}.pdf#toolbar=0`} className="w-100 h-100 border-0" title="Anteprima PDF" />
              </div>

              {/* Destra: Dati */}
              <div className="col-lg-6 h-100 d-flex flex-column bg-white">
                <div className="p-2 bg-light border-bottom text-center small fw-bold text-muted text-uppercase">Dati Estratti</div>
                
                <div className="flex-grow-1 overflow-auto p-4">
                  {selectedDoc.status === 'KO' && (
                    <div className="alert alert-danger small mb-4"><strong>Estrazione Fallita:</strong> Compila manualmente i dati guardando il PDF.</div>
                  )}

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-muted">Fornitore</label>
                    <input type="text" className="form-control bg-light" value={editData.fornitore || ''} onChange={(e) => setEditData({...editData, fornitore: e.target.value})} />
                  </div>
                  
                  <div className="row mb-3">
                    <div className="col-6">
                      <label className="form-label small fw-bold text-muted">Numero D.D.T.</label>
                      <input type="text" className="form-control bg-light" value={editData.numero_ddt || ''} onChange={(e) => setEditData({...editData, numero_ddt: e.target.value})} />
                    </div>
                    <div className="col-6">
                      <label className="form-label small fw-bold text-muted">Data D.D.T.</label>
                      <input type="text" className="form-control bg-light" value={editData.data_ddt || ''} onChange={(e) => setEditData({...editData, data_ddt: e.target.value})} placeholder="GG-MM-AAAA" />
                    </div>
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-muted">Ragione Sociale Consegna</label>
                    <input type="text" className="form-control bg-light" value={editData.ragione_sociale_consegna || ''} onChange={(e) => setEditData({...editData, ragione_sociale_consegna: e.target.value})} />
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-muted">Indirizzo di Consegna</label>
                    <textarea rows="3" className="form-control bg-light" value={editData.indirizzo_consegna || ''} onChange={(e) => setEditData({...editData, indirizzo_consegna: e.target.value})} />
                  </div>
                </div>

                <div className="p-3 bg-light border-top text-end">
                  <button className="btn btn-secondary me-2 px-4" onClick={onClose}>Annulla</button>
                  <button className="btn btn-primary px-4 fw-bold" onClick={onSave} disabled={isSaving}>
                    {isSaving ? 'Salvataggio...' : 'Salva e Approva'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}