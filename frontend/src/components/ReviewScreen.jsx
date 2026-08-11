import React from 'react';
import { ArrowLeft, Save, FileQuestion } from 'lucide-react';

export default function ReviewScreen({ selectedDoc, editData, setEditData, onClose, onSave, isSaving, apiUrl }) {
  if (!selectedDoc) return null;

  return (
    <div className="position-fixed top-0 start-0 w-100 h-100 bg-dark z-3 d-flex flex-column" style={{ zIndex: 1050 }}>
      {/* Header di Revisione */}
      <div className="bg-dark border-bottom border-secondary d-flex justify-content-between align-items-center px-4 py-3 shadow-sm">
        <div className="d-flex align-items-center gap-3">
          <button className="btn btn-outline-secondary d-flex align-items-center justify-content-center" onClick={onClose} title="Torna alla Dashboard">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h5 className="mb-0 fw-bold text-light">Validazione Dati</h5>
            <small className="text-secondary">File originale: {selectedDoc.file_origine}</small>
          </div>
        </div>
        <button className="btn btn-success px-4 fw-bold d-flex align-items-center gap-2 shadow-sm" onClick={onSave} disabled={isSaving}>
          <Save size={18} />
          {isSaving ? 'Salvataggio...' : 'Salva e Approva'}
        </button>
      </div>
      
      {/* Corpo Split Screen */}
      <div className="row g-0 flex-grow-1 overflow-hidden">
        
        {/* Sinistra: Visualizzatore PDF Inline sicuro */}
        <div className="col-lg-7 h-100 border-end border-secondary bg-black">
          {/* L'uso di object impedisce il download automatico su gran parte dei browser */}
          <object 
            data={`${apiUrl}/api/pdf/${selectedDoc.id}.pdf#toolbar=0&navpanes=0`} 
            type="application/pdf" 
            className="w-100 h-100"
          >
            <div className="d-flex h-100 align-items-center justify-content-center text-secondary flex-column">
              <p>Il browser non supporta la visualizzazione inline dei PDF.</p>
              <a href={`${apiUrl}/api/pdf/${selectedDoc.id}.pdf`} target="_blank" rel="noreferrer" className="btn btn-outline-light mt-2">
                Apri PDF in un'altra scheda
              </a>
            </div>
          </object>
        </div>

        {/* Destra: Form Compilazione (Dark) */}
        <div className="col-lg-5 h-100 d-flex flex-column bg-dark overflow-auto">
          <div className="p-4">
            {selectedDoc.status === 'KO' && (
              <div className="alert alert-danger bg-danger bg-opacity-10 border-danger text-danger d-flex align-items-start gap-3 mb-4">
                <FileQuestion size={24} className="mt-1 flex-shrink-0" />
                <div>
                  <strong>Estrazione Fallita</strong><br/>
                  L'IA non ha rilevato campi validi. Compila i dati manualmente analizzando il PDF a sinistra.
                </div>
              </div>
            )}

            <div className="card bg-dark border-secondary mb-4">
              <div className="card-header border-secondary text-uppercase text-secondary fw-bold" style={{ fontSize: '0.8rem' }}>
                Anagrafica Documento
              </div>
              <div className="card-body">
                <div className="mb-3">
                  <label className="form-label small text-secondary">Azienda Fornitrice</label>
                  <input type="text" className="form-control bg-dark text-light border-secondary focus-ring" value={editData.fornitore || ''} onChange={(e) => setEditData({...editData, fornitore: e.target.value})} placeholder="Es. Mario Rossi S.r.l." />
                </div>
                <div className="row mb-3">
                  <div className="col-6">
                    <label className="form-label small text-secondary">Numero D.D.T.</label>
                    <input type="text" className="form-control bg-dark text-light border-secondary" value={editData.numero_ddt || ''} onChange={(e) => setEditData({...editData, numero_ddt: e.target.value})} />
                  </div>
                  <div className="col-6">
                    <label className="form-label small text-secondary">Data D.D.T.</label>
                    <input type="text" className="form-control bg-dark text-light border-secondary" value={editData.data_ddt || ''} onChange={(e) => setEditData({...editData, data_ddt: e.target.value})} placeholder="GG-MM-AAAA" />
                  </div>
                </div>
              </div>
            </div>

            <div className="card bg-dark border-secondary">
              <div className="card-header border-secondary text-uppercase text-secondary fw-bold" style={{ fontSize: '0.8rem' }}>
                Dati di Spedizione
              </div>
              <div className="card-body">
                <div className="mb-3">
                  <label className="form-label small text-secondary">Punto Vendita / Destinatario</label>
                  <input type="text" className="form-control bg-dark text-light border-secondary" value={editData.ragione_sociale_consegna || ''} onChange={(e) => setEditData({...editData, ragione_sociale_consegna: e.target.value})} placeholder="Es. Conad Superstore" />
                </div>
                <div className="mb-3">
                  <label className="form-label small text-secondary">Indirizzo Fisico di Consegna</label>
                  <textarea rows="4" className="form-control bg-dark text-light border-secondary" value={editData.indirizzo_consegna || ''} onChange={(e) => setEditData({...editData, indirizzo_consegna: e.target.value})} placeholder="Es. Via Roma 1, 00100 Roma (RM)" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}