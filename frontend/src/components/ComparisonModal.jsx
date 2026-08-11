import React, { useState } from 'react';

export default function ComparisonModal({ selectedDoc, editData, setEditData, onClose, onSave, isSaving, apiUrl }) {
  const [loadError, setLoadError] = useState(false);

  if (!selectedDoc) return null;

  const pdfUrl = `${apiUrl}/api/pdf/${selectedDoc.id}.pdf`;

  // Aggiungiamo un parametro anti-cache per evitare problemi
  const pdfUrlWithCache = `${pdfUrl}?t=${Date.now()}`;

  const handleRetry = () => {
    setLoadError(false);
  };

  return (
    <div className="modal show d-block" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }} tabIndex="-1">
      <div className="modal-dialog modal-xl modal-dialog-centered modal-fullscreen-lg-down">
        <div className="modal-content bg-dark text-light border-secondary shadow-lg" style={{ height: '90vh' }}>
          
          <div className="modal-header border-secondary py-3">
            <div>
              <h5 className="modal-title fw-bold">Validazione Documento</h5>
              <small className="text-secondary">
                File: {selectedDoc.file_origine}
              </small>
            </div>
            <button type="button" className="btn-close btn-close-white" onClick={onClose}></button>
          </div>
          
          <div className="modal-body p-0 overflow-hidden">
            <div className="row g-0 h-100">
              
              {/* Sinistra: Anteprima PDF */}
              <div className="col-lg-7 h-100 bg-dark border-end border-secondary d-flex flex-column">
                <div className="p-2 border-bottom border-secondary text-center small fw-bold text-secondary text-uppercase">
                  Documento Scansionato
                </div>
                
                <div className="flex-grow-1 bg-light" style={{ minHeight: 0 }}>
                  {loadError ? (
                    <div className="d-flex flex-column align-items-center justify-content-center h-100 text-center p-4">
                      <div style={{ fontSize: '64px' }} className="mb-3">📄</div>
                      <h5 className="text-dark mb-2">PDF non disponibile</h5>
                      <p className="text-muted mb-3">Il browser non riesce a visualizzare questo PDF</p>
                      <div className="d-flex gap-2">
                        <button 
                          className="btn btn-primary"
                          onClick={handleRetry}
                        >
                          Riprova
                        </button>
                        <a 
                          href={pdfUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-outline-primary"
                        >
                          Apri in nuova scheda
                        </a>
                      </div>
                    </div>
                  ) : (
                    <object
                      data={pdfUrlWithCache}
                      type="application/pdf"
                      style={{ width: '100%', height: '100%' }}
                      onError={() => setLoadError(true)}
                    >
                      <div className="d-flex flex-column align-items-center justify-content-center h-100 text-center p-4">
                        <div style={{ fontSize: '64px' }} className="mb-3">📄</div>
                        <h5 className="text-dark mb-2">Visualizzazione non supportata</h5>
                        <p className="text-muted mb-3">Il tuo browser non supporta la visualizzazione PDF integrata</p>
                        <a 
                          href={pdfUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-primary"
                        >
                          Apri PDF
                        </a>
                      </div>
                    </object>
                  )}
                </div>
              </div>

              {/* Destra: Form Dati */}
              <div className="col-lg-5 h-100 d-flex flex-column bg-dark">
                <div className="p-2 border-bottom border-secondary text-center small fw-bold text-secondary text-uppercase">
                  Dati Estratti
                </div>
                
                <div className="flex-grow-1 overflow-auto p-4">
                  {selectedDoc.status === 'KO' && (
                    <div className="alert alert-danger bg-danger bg-opacity-10 border-danger text-danger small mb-4">
                      <strong>Estrazione Fallita:</strong> Compila manualmente i dati guardando il PDF.
                    </div>
                  )}

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-secondary">Fornitore</label>
                    <input
                      type="text"
                      className="form-control bg-dark text-light border-secondary"
                      value={editData.fornitore || ''}
                      onChange={(e) => setEditData({...editData, fornitore: e.target.value})}
                    />
                  </div>
                  
                  <div className="row mb-3">
                    <div className="col-6">
                      <label className="form-label small fw-bold text-secondary">Numero D.D.T.</label>
                      <input
                        type="text"
                        className="form-control bg-dark text-light border-secondary"
                        value={editData.numero_ddt || ''}
                        onChange={(e) => setEditData({...editData, numero_ddt: e.target.value})}
                      />
                    </div>
                    <div className="col-6">
                      <label className="form-label small fw-bold text-secondary">Data D.D.T.</label>
                      <input
                        type="text"
                        className="form-control bg-dark text-light border-secondary"
                        value={editData.data_ddt || ''}
                        onChange={(e) => setEditData({...editData, data_ddt: e.target.value})}
                        placeholder="GG-MM-AAAA"
                      />
                    </div>
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-secondary">Ragione Sociale Consegna</label>
                    <input
                      type="text"
                      className="form-control bg-dark text-light border-secondary"
                      value={editData.ragione_sociale_consegna || ''}
                      onChange={(e) => setEditData({...editData, ragione_sociale_consegna: e.target.value})}
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-secondary">Indirizzo di Consegna</label>
                    <textarea
                      rows="3"
                      className="form-control bg-dark text-light border-secondary"
                      value={editData.indirizzo_consegna || ''}
                      onChange={(e) => setEditData({...editData, indirizzo_consegna: e.target.value})}
                    />
                  </div>
                </div>

                <div className="p-3 border-top border-secondary text-end bg-dark">
                  <button className="btn btn-outline-secondary me-2 px-4" onClick={onClose}>
                    Annulla
                  </button>
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