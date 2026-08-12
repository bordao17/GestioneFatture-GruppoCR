import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Header from './components/Header';
import Stats from './components/Stats';
import Dashboard from './components/Dashboard';
import ComparisonModal from './components/ComparisonModal';
import SuppliersManager from './components/SuppliersManager';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [activeTab, setActiveTab] = useState('CHECK'); 
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [editData, setEditData] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [currentView, setCurrentView] = useState('DASHBOARD'); // 'DASHBOARD' o 'SUPPLIERS'

  useEffect(() => { fetchDocuments(); }, []);

  const fetchDocuments = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/api/documents`);
      setDocuments(response.data.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)));
      setError(null);
    } catch (err) {
      setError('Impossibile contattare il server. Verifica che il backend FastAPI sia acceso.');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Vuoi eliminare definitivamente questo documento e il PDF associato?')) return;
    try {
      await axios.delete(`${API_URL}/api/documents/${id}`);
      fetchDocuments();
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveDoc = async () => {
    setIsSaving(true);
    try {
      await axios.put(`${API_URL}/api/documents/${selectedDoc.id}`, { extracted_data: editData });
      setSelectedDoc(null);
      fetchDocuments(); 
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  const stats = {
    totali: documents.length,
    ok: documents.filter(d => d.status === 'OK').length,
    check: documents.filter(d => d.status === 'CHECK').length,
    ko: documents.filter(d => d.status === 'KO').length
  };

  return (
 <div className="bg-dark min-vh-100 text-light pb-5">

   {/* 1. Header Globale */}
   <Header 
     onRefresh={fetchDocuments} 
     isLoading={loading} 
     onViewSuppliers={() => setCurrentView('SUPPLIERS')} 
   />

   {/* 2. Routing molto semplice */}
   {currentView === 'SUPPLIERS' ? (

     <SuppliersManager 
       apiUrl={API_URL} 
       onBack={() => setCurrentView('DASHBOARD')} 
     />

   ) : (

     <div className="container-fluid px-4">
       {error && <div className="alert alert-danger shadow-sm">{error}</div>}

       <Stats stats={stats} />

       <Dashboard 
         documents={documents}
         activeTab={activeTab}
         setActiveTab={setActiveTab}
         onEdit={(doc) => {
           setSelectedDoc(doc);
           setEditData({ ...doc.dati });
         }}
         onDelete={handleDelete}
       />
     </div>

   )}

      {/* 3. Modale sovrapposto in trasparenza quando richiesto */}
      <ComparisonModal 
        selectedDoc={selectedDoc} 
        editData={editData} 
        setEditData={setEditData}
        onClose={() => setSelectedDoc(null)}
        onSave={handleSaveDoc}
        isSaving={isSaving}
        apiUrl={API_URL}
      />
    </div>
  );
}

export default App;