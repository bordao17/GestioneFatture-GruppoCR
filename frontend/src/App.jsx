import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editData, setEditData] = useState({});
  const [pdfUrl, setPdfUrl] = useState(null);
  const [showPdfModal, setShowPdfModal] = useState(false);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/api/documents`);
      // Ordina per timestamp decrescente (più recenti prima)
      const sorted = response.data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
      setDocuments(sorted);
      setError(null);
    } catch (err) {
      setError('Impossibile caricare i documenti. Assicurati che il backend sia attivo.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleView = async (doc) => {
    try {
      const response = await axios.get(`${API_URL}/api/pdf/${doc.filename}`, {
        responseType: 'blob'
      });
      const url = URL.createObjectURL(response.data);
      setPdfUrl(url);
      setShowPdfModal(true);
    } catch (err) {
      alert('Errore nel caricamento del PDF');
      console.error(err);
    }
  };

  const handleEdit = (doc) => {
    setSelectedDoc(doc);
    setEditData({ ...doc.extracted_data });
    setShowModal(true);
  };

  const handleSave = async () => {
    try {
      await axios.put(`${API_URL}/api/documents/${selectedDoc.id}`, {
        extracted_data: editData
      });
      setShowModal(false);
      fetchDocuments();
      alert('Documento aggiornato con successo!');
    } catch (err) {
      alert('Errore nell\'aggiornamento del documento');
      console.error(err);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Sei sicuro di voler eliminare questo documento?')) return;
    
    try {
      await axios.delete(`${API_URL}/api/documents/${id}`);
      fetchDocuments();
      alert('Documento eliminato con successo!');
    } catch (err) {
      alert('Errore nell\'eliminazione del documento');
      console.error(err);
    }
  };

  const handleClosePdf = () => {
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
    }
    setShowPdfModal(false);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'OK': return 'bg-success';
      case 'CHECK': return 'bg-warning text-dark';
      case 'KO': return 'bg-danger';
      default: return 'bg-secondary';
    }
  };

  if (loading) {
    return (
      <div className="container mt-5 text-center">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Caricamento...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mt-5">
        <div className="alert alert-danger">{error}</div>
        <button className="btn btn-primary" onClick={fetchDocuments}>Riprova</button>
      </div>
    );
  }

  return (
    <div className="container-fluid py-4">
      <div className="row mb-4">
        <div className="col">
          <h1 className="display-6">📄 Gestione DDT & Fatture</h1>
          <p className="text-muted">Dashboard per la visualizzazione e gestione dei documenti estratti</p>
        </div>
        <div className="col-auto">
          <button className="btn btn-outline-primary" onClick={fetchDocuments}>
            🔄 Aggiorna
          </button>
        </div>
      </div>

      <div className="card shadow-sm">
        <div className="card-body">
          <div className="table-responsive">
            <table className="table table-hover align-middle">
              <thead className="table-light">
                <tr>
                  <th>Data/Ora</th>
                  <th>File</th>
                  <th>Stato</th>
                  <th>Fornitore</th>
                  <th>Totale</th>
                  <th>Azioni</th>
                </tr>
              </thead>
              <tbody>
                {documents.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="text-center py-4 text-muted">
                      Nessun documento trovato
                    </td>
                  </tr>
                ) : (
                  documents.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        {new Date(doc.timestamp).toLocaleString('it-IT')}
                      </td>
                      <td>
                        <strong>{doc.filename}</strong>
                      </td>
                      <td>
                        <span className={`badge ${getStatusBadge(doc.status)}`}>
                          {doc.status}
                        </span>
                      </td>
                      <td>
                        {doc.extracted_data?.fornitore || '-'}
                      </td>
                      <td>
                        {doc.extracted_data?.totale || '-'}
                      </td>
                      <td>
                        <button 
                          className="btn btn-sm btn-info me-2"
                          onClick={() => handleView(doc)}
                          title="Visualizza PDF"
                        >
                          👁️
                        </button>
                        <button 
                          className="btn btn-sm btn-warning me-2"
                          onClick={() => handleEdit(doc)}
                          title="Modifica"
                        >
                          ✏️
                        </button>
                        <button 
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDelete(doc.id)}
                          title="Elimina"
                        >
                          🗑️
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

      {/* Modale di modifica */}
      {showModal && (
        <div className="modal show d-block" tabIndex="-1">
          <div className="modal-dialog modal-lg">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Modifica Documento: {selectedDoc?.filename}</h5>
                <button type="button" className="btn-close" onClick={() => setShowModal(false)}></button>
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">Fornitore</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editData.fornitore || ''}
                    onChange={(e) => setEditData({...editData, fornitore: e.target.value})}
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label">Data Documento</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editData.data_documento || ''}
                    onChange={(e) => setEditData({...editData, data_documento: e.target.value})}
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label">Numero Documento</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editData.numero_documento || ''}
                    onChange={(e) => setEditData({...editData, numero_documento: e.target.value})}
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label">Totale</label>
                  <input
                    type="text"
                    className="form-control"
                    value={editData.totale || ''}
                    onChange={(e) => setEditData({...editData, totale: e.target.value})}
                  />
                </div>
                <div className="mb-3">
                  <label className="form-label">Note</label>
                  <textarea
                    className="form-control"
                    rows="3"
                    value={editData.note || ''}
                    onChange={(e) => setEditData({...editData, note: e.target.value})}
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>
                  Annulla
                </button>
                <button type="button" className="btn btn-primary" onClick={handleSave}>
                  Salva
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modale Visualizzazione PDF */}
      {showPdfModal && pdfUrl && (
        <div className="modal show d-block" tabIndex="-1">
          <div className="modal-dialog modal-xl">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Anteprima PDF</h5>
                <button type="button" className="btn-close" onClick={handleClosePdf}></button>
              </div>
              <div className="modal-body" style={{ height: '80vh' }}>
                <iframe 
                  src={pdfUrl} 
                  width="100%" 
                  height="100%" 
                  title="PDF Preview"
                  style={{ border: 'none' }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {showModal && <div className="modal-backdrop fade show"></div>}
      {showPdfModal && <div className="modal-backdrop fade show"></div>}
    </div>
  );
}

export default App;
