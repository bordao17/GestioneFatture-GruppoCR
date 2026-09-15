import React from 'react';
import { CheckCircle, AlertTriangle, XOctagon, LayoutGrid, Table } from 'lucide-react';
import DocumentTable from './DocumentTable'; // Importiamo il tuo componente
import Paginazione, { usePaginazione } from './Paginazione';

/**
 * La tabella dei D.D.T. divisa per esito della lettura, piu' il secondo modo di
 * guardare le stesse bolle: la suddivisione per punto vendita, che arriva come
 * children e prende il posto della tabella quando la si chiede.
 *
 * Il pulsante sta in fondo ai tre tab e non in fondo alla pagina (dov'era fino
 * al 2026-09-15, in un pannello richiudibile a se'): le due viste rispondono a
 * due domande sullo STESSO elenco — "com'e' andata la lettura" e "cosa e'
 * arrivato e da chi" — e stando una sotto l'altra sembravano due elenchi
 * diversi, con la seconda sotto la paginazione della prima, cioe' dove nessuno
 * scorre.
 */
export default function Dashboard({ documents, activeTab, setActiveTab, onEdit, onDelete, selectedIds, onToggleSelect, onApriFattura, chiaveVista, vista = 'tabella', setVista, children }) {
  // Filtriamo i documenti in base al tab selezionato
  const filteredDocs = documents.filter(doc => doc.status === activeTab);
  const perPuntoVendita = vista === 'punti_vendita';
  // La selezione per l'unione vive in App e non nella pagina: le pagine da
  // unire possono stare su pagine diverse della tabella, come gia' stavano su
  // tab diversi.
  const pagine = usePaginazione(filteredDocs, `${chiaveVista}|${activeTab}`);

  return (
    <div className="card shadow-sm">
      <div className="card-header bg-transparent pt-3 pb-3 px-4 d-flex flex-wrap align-items-center gap-2">
        {/* I tre tab restano visibili anche nella griglia, che pero' mostra
            tutti e tre gli esiti insieme: sbiaditi perche' non e' quello che si
            sta guardando, ma non spenti — cliccarne uno riporta alla tabella su
            quel tab, che e' l'unica cosa che uno si aspetta premendoli. */}
        <ul className={`nav nav-pills gap-2 flex-grow-1${perPuntoVendita ? ' opacity-50' : ''}`}>
          <li className="nav-item">
            <button 
              className={`nav-link d-flex align-items-center gap-2 ${activeTab === 'OK' ? 'active bg-success text-white fw-bold' : 'text-body-secondary border'}`}
              onClick={() => { setActiveTab('OK'); setVista?.('tabella'); }}
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
              onClick={() => { setActiveTab('CHECK'); setVista?.('tabella'); }}
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
              onClick={() => { setActiveTab('KO'); setVista?.('tabella'); }}
            >
              <XOctagon size={18} /> Errori
              <span className={`badge ms-2 ${activeTab === 'KO' ? 'bg-white text-danger' : 'bg-secondary text-dark'}`}>
                {documents.filter(d => d.status === 'KO').length}
              </span>
            </button>
          </li>
        </ul>

        {setVista && (
          <button
            type="button"
            className={`btn btn-sm d-flex align-items-center gap-2 ${perPuntoVendita ? 'btn-primary' : 'btn-outline-primary'}`}
            onClick={() => setVista(perPuntoVendita ? 'tabella' : 'punti_vendita')}
            aria-pressed={perPuntoVendita}
            title={perPuntoVendita
              ? 'Torna alla tabella divisa per esito della lettura'
              : 'Raccogli le stesse bolle in una cartella per punto vendita, e dentro per fornitore'}
          >
            {perPuntoVendita ? <Table size={16} /> : <LayoutGrid size={16} />}
            {perPuntoVendita ? 'Tabella' : 'Per punto vendita'}
          </button>
        )}
      </div>

      <div className={perPuntoVendita ? 'card-body' : 'card-body p-0'}>
        {perPuntoVendita ? children : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}