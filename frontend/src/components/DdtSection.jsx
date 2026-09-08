import React from 'react';
import Stats from './Stats';
import BarraIngresso from './BarraIngresso';
import ProcessingBar from './ProcessingBar';
import SearchBar from './SearchBar';
import MergeBar from './MergeBar';
import Dashboard from './Dashboard';

/**
 * Sezione D.D.T.: le bolle scansionate, divise per esito della lettura AI.
 *
 * È il vecchio corpo della dashboard, estratto da App.jsx quando le sezioni
 * sono diventate tre. Nessuno stato vive qui: la selezione per l'unione deve
 * sopravvivere al cambio di tab (e ora anche al cambio di sezione), quindi
 * resta in App insieme al resto.
 */
export default function DdtSection({
  documents,
  filteredDocuments,
  stats,
  lavoriInCorso,
  activeTab,
  setActiveTab,
  searchTerm,
  setSearchTerm,
  searchField,
  setSearchField,
  selectedIds,
  selectedDocs,
  onToggleSelect,
  onClearSelection,
  onMerge,
  isMerging,
  onEdit,
  onDelete,
  onApriFattura,
  apiUrl,
  onScansione,
  onErrore,
}) {
  return (
    <div className="container-fluid px-4">
      <Stats stats={stats} />

      <BarraIngresso
        apiUrl={apiUrl}
        tipo="ddt"
        accept=".pdf,.jpg,.jpeg,.png"
        etichettaCarica="Aggiungi documento"
        etichettaAnalizza="Analizza D.D.T."
        descrizione="Cartella in ingresso DDT/da_leggere: qui finiscono le scansioni in attesa di essere lette dal modello."
        onFatto={onScansione}
        onErrore={onErrore}
      />

      <ProcessingBar lavori={lavoriInCorso} />

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
        onMerge={onMerge}
        onClear={onClearSelection}
        isMerging={isMerging}
      />

      <Dashboard
        documents={filteredDocuments}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onEdit={onEdit}
        onDelete={onDelete}
        selectedIds={selectedIds}
        onToggleSelect={onToggleSelect}
        onApriFattura={onApriFattura}
        chiaveVista={`${searchField}|${searchTerm}`}
      />
    </div>
  );
}
