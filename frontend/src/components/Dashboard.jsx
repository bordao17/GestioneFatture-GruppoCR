import React from 'react';
import { CheckCircle, AlertTriangle, XOctagon } from 'lucide-react';
import DocumentTable from './DocumentTable'; // Importiamo il tuo componente
import Paginazione, { usePaginazione } from './Paginazione';

export default function Dashboard({ documents, activeTab, setActiveTab, onEdit, onDelete, selectedIds, onToggleSelect, onApriFattura, chiaveVista }) {
  // Filtriamo i documenti in base al tab selezionato
  const filteredDocs = documents.filter(doc => doc.status === activeTab);
  // La selezione per l'unione vive in App e non nella pagina: le pagine da
  // unire possono stare su pagine diverse della tabella, come gia' stavano su
  // tab diversi.
  const pagine = usePaginazione(filteredDocs, `${chiaveVista}|${activeTab}`);

  return (
    <div className="card shadow-sm">
      <div className="card-header bg-transparent pt-3 pb-3 px-4">
        <ul className="nav nav-pills gap-2">
          <li className="nav-item">
            <button 
              className={`nav-link d-flex align-items-center gap-2 ${activeTab === 'OK' ? 'active bg-success text-white fw-bold' : 'text-body-secondary border'}`}
              onClick={() => setActiveTab('OK')}
            >
              <CheckCircle size={18} /> Completati
              <span className={`badge ms-2 ${activeTab === 'OK' ? 'bg-white text-success' : 'bg-secondary text-dark'}`}>
                {documents.filter(d => d.status === 'OK').length}
              </span>
            </button>
          </li>
          <li className="nav-item">
            <button 
              className={`nav-link d-flex align-items-center gap-2 ${activeTab === 'CHECK' ? 'active bg-warning text-dark fw-bold' : 'text-body-secondary border'}`}
              onClick={() => setActiveTab('CHECK')}
            >
              <AlertTriangle size={18} /> Da Verificare
              <span className={`badge ms-2 ${activeTab === 'CHECK' ? 'bg-dark text-warning' : 'bg-secondary text-dark'}`}>
                {documents.filter(d => d.status === 'CHECK').length}
              </span>
            </button>
          </li>
          <li className="nav-item">
            <button 
              className={`nav-link d-flex align-items-center gap-2 ${activeTab === 'KO' ? 'active bg-danger text-white fw-bold' : 'text-body-secondary border'}`}
              onClick={() => setActiveTab('KO')}
            >
              <XOctagon size={18} /> Errori
              <span className={`badge ms-2 ${activeTab === 'KO' ? 'bg-white text-danger' : 'bg-secondary text-dark'}`}>
                {documents.filter(d => d.status === 'KO').length}
              </span>
            </button>
          </li>
        </ul>
      </div>

      <div className="card-body p-0">
        {/* Usiamo il tuo componente passandogli solo i dati filtrati */}
        <DocumentTable 
          documents={pagine.visibili} 
          onEdit={onEdit} 
          onDelete={onDelete} 
          selectedIds={selectedIds}
          onToggleSelect={onToggleSelect}
          onApriFattura={onApriFattura}
        />

        <Paginazione {...pagine} etichetta="documenti" />
      </div>
    </div>
  );
}