import React, { useState } from 'react';
import Stats from './Stats';
import BarraIngresso from './BarraIngresso';
import ProcessingBar from './ProcessingBar';
import SearchBar from './SearchBar';
import MergeBar from './MergeBar';
import Dashboard from './Dashboard';
import GrigliaPuntiVendita from './GrigliaPuntiVendita';

/**
 * Sezione D.D.T.: le bolle scansionate, divise per esito della lettura AI.
 *
 * È il vecchio corpo della dashboard, estratto da App.jsx quando le sezioni
 * sono diventate tre. I dati non vivono qui: la selezione per l'unione deve
 * sopravvivere al cambio di tab (e ora anche al cambio di sezione), quindi
 * resta in App insieme al resto.
 *
 * L'unica cosa che vive qui è QUALE DELLE DUE VISTE si sta guardando (tabella
 * per esito / cartelle per punto vendita): non è un dato, è dove si è arrivati
 * a guardare, e non deve sopravvivere al cambio di sezione — tornando sui
 * D.D.T. la vista di partenza è la tabella, che è quella in cui si lavora.
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
  puntiVendita,
}) {
  const [vista, setVista] = useState('tabella');

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
        controllaMotore
        puntiVendita={puntiVendita}
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

      {/*
        La griglia per punto vendita sta DENTRO la card della tabella e prende
        il suo posto quando la si chiede col pulsante in fondo ai tre tab: sono
        due modi di guardare lo stesso elenco, e impilati uno sotto l'altro
        sembravano due archivi diversi.

        Riceve filteredDocuments e non documents apposta — la ricerca in alto
        deve valere anche qui, altrimenti cercando un numero la tabella
        mostrerebbe una riga e la griglia cinquecento.
      */}
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
        vista={vista}
        setVista={setVista}
      >
        <GrigliaPuntiVendita
          documents={filteredDocuments}
          puntiVendita={puntiVendita}
          onEdit={onEdit}
        />
      </Dashboard>
    </div>
  );
}
