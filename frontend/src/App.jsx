import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Header from './components/Header';
import Stats from './components/Stats';
import DocumentTable from './components/DocumentTable';
import ComparisonModal from './components/ComparisonModal';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [editData, setEditData] = useState({});
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => { fetchDocuments(); }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/api/documents`);
      setDocuments(response.data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)));
      setError(null);
    } catch (err) {
      setError('Impossibile caricare i documenti dal backend.');
    } finally {
      setLoading(false);
    }
  };

  const stats = {
    totali: documents.length,
    daVerificare: documents.filter(d => d.status === 'CHECK' || d.status === 'KO').length,
    completati: documents.filter(d => d.status === 'OK').length
  };

  return (
    <div className="bg-light min-vh-100 pb-5">
      <Header onRefresh={fetchDocuments} isLoading={loading} />
      <div className="container-fluid px-4">
        {error && <div className="alert alert-danger shadow-sm">{error}</div>}
        <Stats stats={stats} />
        <DocumentTable 
          documents={documents} 
          onEdit={(doc) => { setSelectedDoc(doc); setEditData({ ...doc.dati }); }}
          onDelete={async (id) => {
            if (!window.confirm('Eliminare questo documento e il PDF?')) return;
            await axios.delete(`${API_URL}/api/documents/${id}`);
            fetchDocuments();
          }}
        />
      </div>
      <ComparisonModal
        selectedDoc={selectedDoc} editData={editData} setEditData={setEditData}
        onClose={() => setSelectedDoc(null)}
        apiUrl={API_URL} isSaving={isSaving}
        onSave={async () => {
          setIsSaving(true);
          await axios.put(`${API_URL}/api/documents/${selectedDoc.id}`, { extracted_data: editData });
          setIsSaving(false); setSelectedDoc(null); fetchDocuments();
        }}
      />
    </div>
  );
}

export default App;