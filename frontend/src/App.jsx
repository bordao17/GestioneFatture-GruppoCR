import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Header from './components/Header';
import Stats from './components/Stats';
import Dashboard from './components/Dashboard';
import ComparisonModal from './components/ComparisonModal';
import SuppliersManager from './components/SuppliersManager';
import ManualEntryModal from './components/ManualEntryModal';
import MergeBar from './components/MergeBar';
import SearchBar from './components/SearchBar';

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
  const [showManualEntry, setShowManualEntry] = useState(false);

  // Unione manuale: la selezione vive qui e non nel Dashboard, così resta viva
  // anche cambiando tab (le pagine da unire possono stare in OK, CHECK e KO).
  const [selectedIds, setSelectedIds] = useState([]);
  const [isMerging, setIsMerging] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [searchField, setSearchField] = useState('TUTTI');

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
      setSelectedIds((prev) => prev.filter((x) => x !== id));
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

  // Ricerca: confronto tollerante ai separatori, così "01/09/2026" trova anche
  // le date scritte "01-09-2026" (formato prodotto dal normalizzatore backend).
  const normalizzaRicerca = (valore) =>
    (valore ?? '').toString().toLowerCase().replace(/[/.]/g, '-').replace(/\s+/g, ' ').trim();

  const campiRicerca = searchField === 'TUTTI'
    ? ['numero_ddt', 'fornitore', 'data_ddt']
    : [searchField];

  const termineRicerca = normalizzaRicerca(searchTerm);
  const filteredDocuments = termineRicerca
    ? documents.filter((doc) =>
        campiRicerca.some((campo) => normalizzaRicerca(doc.dati?.[campo]).includes(termineRicerca))
      )
    : documents;

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  // I documenti nell'ordine in cui sono stati selezionati: è l'ordine delle
  // pagine nel PDF finale, e il primo fa da documento principale.
  const selectedDocs = selectedIds
    .map((id) => documents.find((d) => d.id === id))
    .filter(Boolean);

  const handleMerge = async () => {
    if (selectedDocs.length < 2) return;
    const principale = selectedDocs[0];
    const conferma = window.confirm(
      `Unire ${selectedDocs.length} documenti in uno solo?

` +
      `I dati che restano sono quelli del n. 1 (${principale.dati?.fornitore || 'fornitore mancante'} ` +
      `- ${principale.dati?.numero_ddt || 'senza numero'}); dagli altri vengono presi solo i campi vuoti.
` +
      `I PDF vengono uniti in un unico file multi-pagina.`
    );
    if (!conferma) return;

    setIsMerging(true);
    try {
      const response = await axios.post(`${API_URL}/api/documents/unisci`, { ids: selectedIds });
      setSelectedIds([]);
      setActiveTab(response.data.stato); // mostra il tab dove è finito il documento unito
      fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossibile unire i documenti selezionati.');
    } finally {
      setIsMerging(false);
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
     onManualAdd={() => {
       setCurrentView('DASHBOARD');
       setShowManualEntry(true);
     }}
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

       <SearchBar
         searchTerm={searchTerm}
         setSearchTerm={setSearchTerm}
         searchField={searchField}
         setSearchField={setSearchField}
         risultati={filteredDocuments.length}
         totali={documents.length}
       />

       <MergeBar
         selectedDocs={selectedDocs}
         onMerge={handleMerge}
         onClear={() => setSelectedIds([])}
         isMerging={isMerging}
       />

       <Dashboard 
         documents={filteredDocuments}
         activeTab={activeTab}
         setActiveTab={setActiveTab}
         onEdit={(doc) => {
           setSelectedDoc(doc);
           setEditData({ ...doc.dati });
         }}
         onDelete={handleDelete}
         selectedIds={selectedIds}
         onToggleSelect={toggleSelect}
       />
     </div>

   )}

      {/* 3. Inserimento manuale: allega il file e scrivi i dati, senza AI */}
      <ManualEntryModal
        show={showManualEntry}
        onClose={() => setShowManualEntry(false)}
        onSaved={fetchDocuments}
        apiUrl={API_URL}
      />

      {/* 4. Modale sovrapposto in trasparenza quando richiesto */}
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