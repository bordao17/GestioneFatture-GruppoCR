import React, { useState } from 'react';
import { Download } from 'lucide-react';

export default function ComparisonModal({ selectedDoc, editData, setEditData, onClose, onSave, isSaving, apiUrl }) {
  const [isDownloading, setIsDownloading] = useState(false);

  if (!selectedDoc) return null;

  const pdfUrl = `${apiUrl}/api/pdf/${selectedDoc.id}.pdf`;
  const pdfUrlWithCache = `${pdfUrl}?t=${Date.now()}#toolbar=0&navpanes=0`;

  // Funzione che scarica il file bypassando le restrizioni
  const handleDownloadPDF = async () => {
    try {
      setIsDownloading(true);
      const response = await fetch(pdfUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      
      // 1. Recuperiamo Fornitore e Data (usiamo "Ignoto" se il campo è vuoto)
      let nomeFornitore = editData.fornitore || 'FornitoreIgnoto';
      let dataDocumento = editData.data_ddt || 'DataIgnota';

      // 2. Puliamo le stringhe da caratteri illegali per i file di Windows/Mac e sostituiamo gli spazi con underscore
      nomeFornitore = nomeFornitore.replace(/[\/\\:*?"<>|]/g, '').replace(/\s+/g, '_');
      dataDocumento = dataDocumento.replace(/[\/\\:*?"<>|]/g, '-').replace(/\s+/g, '_');

      // 3. Creiamo il nome finale
      const nomeFileFinale = `Fattura_${nomeFornitore}_${dataDocumento}.pdf`;
      
      const link = document.createElement('a');
      link.href = url;
      link.download = nomeFileFinale;
      document.body.appendChild(link);
      link.click();
      
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Errore durante il download del PDF:", error);
      alert("Impossibile scaricare il file in questo momento.");
    } finally {
      setIsDownloading(false);
    }
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
              <div className="col-lg-7 h-100 bg-black border-end border-secondary d-flex flex-column">
                
                {/* Header del PDF con il bottone di download */}
                <div className="p-2 border-bottom border-secondary d-flex justify-content-between align-items-center bg-dark">
                  <span className="small fw-bold text-secondary text-uppercase ps-2">
                    Documento Scansionato
                  </span>
                  <button 
                    className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-2" 
                    onClick={handleDownloadPDF}
                    disabled={isDownloading}
                    title="Scarica il file PDF rinominato"
                  >
                    <Download size={16} /> 
                    {isDownloading ? 'Scaricamento...' : 'Scarica PDF'}
                  </button>
                </div>
                
                <div className="flex-grow-1" style={{ minHeight: 0 }}>
                  <iframe 
                    src={pdfUrlWithCache} 
                    className="w-100 h-100 border-0"
                    title="Anteprima PDF"
                  />
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