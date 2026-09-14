import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import useTema from './components/useTema';
import DdtSection from './components/DdtSection';
import FattureSection from './components/FattureSection';
import SuppliersManager from './components/SuppliersManager';
import ConfigSection from './components/ConfigSection';
import ComparisonModal from './components/ComparisonModal';
import InvoiceModal from './components/InvoiceModal';
import ManualEntryModal from './components/ManualEntryModal';
import Toast from './components/Toast';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  // Le tre sezioni del gestionale: D.D.T., Fatture, Fornitori.
  const [vista, setVista] = useState('DDT');

  // Chiaro/scuro. Sta qui e non nella barra laterale perche' e' una preferenza
  // dell'applicazione, non del menu: la barra lo mostra e lo commuta, ma la
  // riga che tocca l'<html> deve restarne una sola.
  const [tema, cambiaTema] = useTema();

  // --- D.D.T. ---------------------------------------------------------------
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeTab, setActiveTab] = useState('CHECK');
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [editData, setEditData] = useState({});
  const [isSaving, setIsSaving] = useState(false);
  const [isReanalyzing, setIsReanalyzing] = useState(false);
  const [isCambiandoStato, setIsCambiandoStato] = useState(false);
  const [isConfermandoPiva, setIsConfermandoPiva] = useState(false);
  // Il modale di revisione sta FUORI dai blocchi per vista, quindi puo'
  // restare aperto mentre si passa alla sezione Fornitori. Confermando una
  // P.IVA di li', l'anagrafica cambia sotto la bozza che SuppliersManager ha
  // letto al mount — e la sua PUT sovrascrive l'INTERA anagrafica, quindi
  // salvarla dopo riporterebbe la P.IVA a "da confermare". Questo contatore
  // e' il modo in cui la sezione viene a saperlo. Lo alza anche "Sincronizza",
  // che e' il gesto con cui si chiede esplicitamente di rileggere tutto.
  const [versioneAnagrafica, setVersioneAnagrafica] = useState(0);
  const [showManualEntry, setShowManualEntry] = useState(false);

  // Unione manuale: la selezione vive qui e non nel Dashboard, così resta viva
  // anche cambiando tab (le pagine da unire possono stare in OK, CHECK e KO).
  const [selectedIds, setSelectedIds] = useState([]);
  const [isMerging, setIsMerging] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [searchField, setSearchField] = useState('TUTTI');

  // --- Fatture --------------------------------------------------------------
  const [fatture, setFatture] = useState([]);
  const [loadingFatture, setLoadingFatture] = useState(true);
  const [fatturaAperta, setFatturaAperta] = useState(null);
  const [idInAccoppiamento, setIdInAccoppiamento] = useState(null);
  const [isConfermandoAccoppiamento, setIsConfermandoAccoppiamento] = useState(false);

  // --- Fornitori ------------------------------------------------------------
  // La sezione ha stato suo (è un editor con salvataggio esplicito): qui serve
  // solo il conteggio di chi aspetta un occhio, per il badge in alto.
  const [daAutorizzare, setDaAutorizzare] = useState(0);

  const [avviso, setAvviso] = useState(null);

  // Elaborazioni in corso: possono essere partite dal pianificatore notturno o
  // da un altro browser, quindi la dashboard non ha modo di saperlo se non
  // chiedendolo. Il backend le espone su /api/elaborazione.
  const [lavoriInCorso, setLavoriInCorso] = useState([]);
  const lavoriPrecedenti = useRef(0);

  // ==========================================================================
  // Caricamento dati
  // ==========================================================================
  const fetchDocuments = useCallback(async () => {
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
  }, []);

  const fetchFatture = useCallback(async () => {
    try {
      setLoadingFatture(true);
      const response = await axios.get(`${API_URL}/api/fatture`);
      setFatture(response.data || []);
    } catch (err) {
      setFatture([]);
    } finally {
      setLoadingFatture(false);
    }
  }, []);

  // Solo per il badge, e conta una cosa sola: le P.IVA da confermare. Sono
  // quelle LETTE dal modello su una scansione (partita_iva_confermata:false
  // esplicito; la chiave assente vale confermata, perché quelle vengono da XML
  // firmati). L'autorizzazione del fornitore non c'è più: dal 2026-09-08 le
  // fatture si caricano a mano, quindi non filtra niente e non è lavoro
  // arretrato — le anomalie sulla P.IVA di una fattura si segnalano sulla
  // fattura stessa.
  const fetchDaAutorizzare = useCallback(async () => {
    try {
      const response = await axios.get(`${API_URL}/api/fornitori`);
      const voci = Object.values(response.data || {});
      // Stessa condizione di pivaDaConfermare() in SuppliersManager: il badge
      // conta solo cio' che aspetta un intervento, e su un fornitore estero
      // non c'e' nessuna P.IVA italiana da confermare — resterebbe un numero
      // che non cala mai, e un numero cosi' smette di essere letto.
      setDaAutorizzare(voci.filter(
        (v) => v.partita_iva && v.partita_iva_confermata === false
              && v.fornitore_estero !== true
      ).length);
    } catch (err) {
      setDaAutorizzare(0);
    }
  }, []);

  const ricaricaTutto = useCallback(() => {
    fetchDocuments();
    fetchFatture();
    fetchDaAutorizzare();
    // "Sincronizza" promette di ricaricare anche l'anagrafica, ma fetchDaAutorizzare
    // ne ricava solo il numero sul badge: la tabella dei fornitori si rileggeva
    // soltanto al mount della sezione. Chi RESTA in Fornitori non aveva modo di
    // aggiornarla senza un F5 — e restarci e' normale, perche' il modale di un
    // D.D.T. sopravvive al cambio di sezione e perche' una scansione (anche
    // pianificata, anche da un altro browser) censisce fornitori nuovi.
    setVersioneAnagrafica((v) => v + 1);
  }, [fetchDocuments, fetchFatture, fetchDaAutorizzare]);

  useEffect(() => { ricaricaTutto(); }, [ricaricaTutto]);

  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/api/elaborazione`);
        const attive = res.data.in_corso || [];
        // Quando non c'e' nulla in corso si tiene lo stesso array: assegnarne
        // uno nuovo ogni 2 secondi farebbe ri-renderizzare tutta la dashboard
        // (modale di revisione compreso) senza motivo.
        setLavoriInCorso((precedenti) =>
          precedenti.length === 0 && attive.length === 0 ? precedenti : attive
        );

        // Appena l'ultima elaborazione finisce, i nuovi documenti sono nei
        // registri: ricaricare qui evita all'utente di premere Aggiorna. Anche
        // le fatture, perché la fine di un batch fa scattare il ricontrollo
        // della coda e qualche pratica può essersi chiusa.
        if (attive.length === 0 && lavoriPrecedenti.current > 0) {
          fetchDocuments();
          fetchFatture();
        }
        lavoriPrecedenti.current = attive.length;
      } catch (err) {
        // Backend irraggiungibile: la barra sparisce, l'errore lo segnala già
        // fetchDocuments. Niente rumore in console ogni 2 secondi.
        setLavoriInCorso((precedenti) => (precedenti.length === 0 ? precedenti : []));
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [fetchDocuments, fetchFatture]);

  // ==========================================================================
  // Il ponte tra le due sezioni
  // ==========================================================================
  // Ogni operazione su un D.D.T. fa ripartire nel backend il ricontrollo delle
  // fatture in coda, e la risposta dice quali pratiche si sono chiuse. Senza
  // questo avviso l'effetto resterebbe invisibile: la fattura sparirebbe dalla
  // coda in un'altra sezione, senza che nessuno colleghi le due cose.
  const segnalaSbloccate = useCallback((sbloccate) => {
    if (!sbloccate || sbloccate.length === 0) return;
    const elenco = sbloccate.map((f) => f.numero_fattura || f.id).join(', ');
    setAvviso({
      tipo: 'success',
      titolo: `${sbloccate.length} fattur${sbloccate.length === 1 ? 'a pronta' : 'e pronte'} da accoppiare`,
      testo: `${elenco} — tutti i D.D.T. citati sono stati trovati. Vai nella sezione Fatture e premi ACCOPPIA per salvare il file unico.`,
    });
    fetchFatture();
  }, [fetchFatture]);

  // Apre un D.D.T. nella sua sezione partendo da una riga di fattura: è il
  // percorso che chiude gli abbinamenti "da confermare", dove il documento c'è
  // già ma con il numero letto male.
  const apriDocumento = useCallback((docId) => {
    const doc = documents.find((d) => d.id === docId);
    if (!doc) {
      setAvviso({
        tipo: 'warning',
        testo: 'Il D.D.T. collegato non è più nei registri: potrebbe essere stato eliminato o unito a un altro documento.',
      });
      return;
    }
    setFatturaAperta(null);
    setVista('DDT');
    setActiveTab(doc.status);
    setSelectedDoc(doc);
    setEditData({ ...doc.dati });
  }, [documents]);

  // ==========================================================================
  // L'accoppiamento manuale
  // ==========================================================================
  // Due tempi apposta: prima si cerca e si guarda, poi si firma. La ricerca non
  // scrive niente nell'archivio, la conferma sì — è lei che crea il file unico
  // in ACCOPPIATE e annota i D.D.T. Tenerle separate è tutto il senso della
  // funzione: senza il primo tempo l'operatore firmerebbe alla cieca.
  const handleAccoppia = useCallback(async (fattura) => {
    setIdInAccoppiamento(fattura.id);
    try {
      const res = await axios.post(`${API_URL}/api/fatture/${fattura.id}/accoppia`);
      const aggiornata = res.data.fattura;

      setVista('FATTURE');
      setFatturaAperta(aggiornata);
      fetchFatture();

      if (!res.data.pronta) {
        const attesa = res.data.attesa || {};
        setAvviso({
          tipo: 'warning',
          titolo: 'Abbinamento incompleto',
          testo: `${res.data.abbinati} D.D.T. trovati. Mancano ${attesa.mancanti ?? 0} bolle e ${attesa.da_confermare ?? 0} sono da confermare a mano: puoi comunque confermare così com’è.`,
        });
      }
    } catch (err) {
      setAvviso({
        tipo: 'danger',
        testo: err.response?.data?.detail || 'Ricerca dei D.D.T. non riuscita.',
      });
    } finally {
      setIdInAccoppiamento(null);
    }
  }, [fetchFatture]);

  const handleConfermaAccoppiamento = useCallback(async (fattura) => {
    const totali = (fattura.ddt || []).filter((r) => r.documento_id).length;
    const messaggio = fattura.stato === 'ABBINATA'
      ? `Confermi l’accoppiamento? Verrà salvato un file unico con la fattura e ${totali} D.D.T. nella cartella ACCOPPIATE.`
      : `L’abbinamento non è completo: nel file unico finiranno solo i ${totali} D.D.T. trovati. Confermi comunque?`;
    if (!window.confirm(messaggio)) return;

    setIsConfermandoAccoppiamento(true);
    try {
      const res = await axios.post(`${API_URL}/api/fatture/${fattura.id}/conferma-accoppiamento`);
      setFatturaAperta(res.data.fattura);
      fetchFatture();
      // I D.D.T. accoppiati ricevono adesso l'annotazione della loro fattura:
      // la colonna Fattura della tabella D.D.T. cambia, quindi vanno riletti.
      fetchDocuments();
      setAvviso({
        tipo: 'success',
        titolo: 'Accoppiamento confermato',
        testo: `File unico salvato in ACCOPPIATE: ${res.data.fascicolo}`,
      });
    } catch (err) {
      setAvviso({
        tipo: 'danger',
        testo: err.response?.data?.detail || 'Conferma non riuscita.',
      });
    } finally {
      setIsConfermandoAccoppiamento(false);
    }
  }, [fetchFatture, fetchDocuments]);

  // Il percorso inverso: dal D.D.T. al fascicolo della fattura che lo cita.
  const apriFattura = useCallback((idFattura) => {
    const fattura = fatture.find((f) => f.id === idFattura);
    if (!fattura) {
      setAvviso({ tipo: 'warning', testo: 'Fattura non trovata: potrebbe essere stata eliminata.' });
      return;
    }
    setSelectedDoc(null);
    setVista('FATTURE');
    setFatturaAperta(fattura);
  }, [fatture]);

  // ==========================================================================
  // Azioni sui D.D.T.
  // ==========================================================================
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
      const response = await axios.put(`${API_URL}/api/documents/${selectedDoc.id}`, { extracted_data: editData });
      setSelectedDoc(null);
      fetchDocuments();
      segnalaSbloccate(response.data.fatture_sbloccate);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  // Lo stato deciso a mano da chi rivede il documento: il classificatore conta
  // i campi letti, non sa se la scansione vale qualcosa. Il modale resta
  // aperto, così si vede il documento cambiare tab senza perderlo di vista, e
  // le correzioni non ancora salvate restano nel form (l'endpoint tocca solo
  // il registro, non i dati estratti).
  // La conferma della P.IVA dal modale: l'operatore ha il PDF davanti, che e'
  // l'unico posto dove si puo' davvero verificare. Da qui in poi la chiave la
  // mette l'anagrafica e il modello non la rilegge piu' per questo fornitore.
  const handleConfermaPiva = async (partitaIva) => {
    if (!selectedDoc) return;

    setIsConfermandoPiva(true);
    try {
      const response = await axios.put(`${API_URL}/api/fornitori/partita-iva`, {
        fornitore: editData.fornitore || selectedDoc.dati?.fornitore || '',
        partita_iva: partitaIva,
        id: selectedDoc.id,
      });
      if (response.data.document) setSelectedDoc(response.data.document);
      setEditData((prec) => ({ ...prec, partita_iva: response.data.partita_iva, partita_iva_scartata: undefined }));
      setAvviso({
        tipo: 'success',
        titolo: 'Partita IVA confermata',
        testo: `${response.data.partita_iva} associata a ${response.data.fornitore}: dai prossimi D.D.T. di questo fornitore verrà usata questa, senza rileggerla.`,
      });
      fetchDocuments();
      fetchDaAutorizzare();
      setVersioneAnagrafica((v) => v + 1);
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossibile confermare la partita IVA.');
    } finally {
      setIsConfermandoPiva(false);
    }
  };

  const handleCambiaStato = async (nuovoStato) => {
    if (!selectedDoc || nuovoStato === selectedDoc.status) return;

    setIsCambiandoStato(true);
    try {
      const response = await axios.put(`${API_URL}/api/documents/${selectedDoc.id}/stato`, { stato: nuovoStato });
      setSelectedDoc(response.data.document);
      setActiveTab(nuovoStato);
      fetchDocuments();
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossibile cambiare stato al documento.');
    } finally {
      setIsCambiandoStato(false);
    }
  };

  // Rianalisi AI del singolo documento già archiviato: il PDF resta quello,
  // cambia solo la lettura del modello (utile dopo aver confermato una regola
  // in memoria fornitori). Sostituisce i dati mostrati nel modale.
  const handleReanalyze = async () => {
    if (!selectedDoc) return;
    const conferma = window.confirm(
      `Rianalizzare questo documento con l'AI?

I dati attuali (comprese le correzioni fatte a mano e non ancora salvate) verranno
sostituiti dalla nuova lettura del modello.
L'operazione può richiedere qualche minuto se la GPU è occupata.`
    );
    if (!conferma) return;

    setIsReanalyzing(true);
    try {
      const response = await axios.post(`${API_URL}/api/documents/${selectedDoc.id}/rianalizza`);
      const aggiornato = response.data.document;
      setSelectedDoc({ ...aggiornato, status: response.data.stato });
      setEditData({ ...(aggiornato.dati || {}) });
      setActiveTab(response.data.stato); // il documento può essere cambiato di tab
      setError(null);
      fetchDocuments();
      segnalaSbloccate(response.data.fatture_sbloccate);
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossibile rianalizzare il documento.');
    } finally {
      setIsReanalyzing(false);
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
      segnalaSbloccate(response.data.fatture_sbloccate);
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossibile unire i documenti selezionati.');
    } finally {
      setIsMerging(false);
    }
  };

  // ==========================================================================
  // Azioni sulle fatture
  // ==========================================================================
  const handleDeleteFattura = async (fattura) => {
    const numero = fattura.dati?.numero_fattura || fattura.id;
    if (!window.confirm(
      `Eliminare definitivamente la fattura ${numero}, il suo fascicolo PDF e l'XML archiviato?

` +
      `I D.D.T. abbinati non vengono toccati: restano nei loro registri.`
    )) return;

    try {
      await axios.delete(`${API_URL}/api/fatture/${fattura.id}`);
      setFatturaAperta(null);
      fetchFatture();
      fetchDocuments();
    } catch (err) {
      setAvviso({ tipo: 'danger', testo: 'Impossibile eliminare la fattura.' });
    }
  };

  // ==========================================================================
  const stats = {
    totali: documents.length,
    ok: documents.filter((d) => d.status === 'OK').length,
    check: documents.filter((d) => d.status === 'CHECK').length,
    ko: documents.filter((d) => d.status === 'KO').length,
  };

  // Il badge delle fatture conta chi aspetta QUALCUNO, non le righe: una
  // pratica in coda (da abbinare, o abbinata e non ancora firmata) e una che
  // aspetta una bolla mai arrivata sono entrambe lavoro fermo. Una confermata
  // no: quella è finita.
  const badge = {
    DDT: stats.check,
    FATTURE: fatture.filter((f) => f.in_coda || f.stato === 'IN_ATTESA').length,
    FORNITORI: daAutorizzare,
  };

  const apriInserimentoManuale = () => {
    setVista('DDT');
    setShowManualEntry(true);
  };

  return (
    <div className="guscio">

      <Sidebar
        vista={vista}
        onVista={setVista}
        badge={badge}
        tema={tema}
        onCambiaTema={cambiaTema}
      />

      {/* Il contenuto. La barra in alto e' sticky e sta DENTRO questa colonna,
          non sopra tutta la pagina: deve scorrere con cio' che descrive. */}
      <div className="contenuto d-flex flex-column min-vh-100">

        <TopBar
          vista={vista}
          onRefresh={ricaricaTutto}
          isLoading={loading || loadingFatture}
          onManualAdd={apriInserimentoManuale}
        />

        <main className="flex-grow-1 pt-4 pb-5">

      {error && (
        <div className="container-fluid px-4">
          <div className="alert alert-danger shadow-sm">{error}</div>
        </div>
      )}

      {vista === 'DDT' && (
        <DdtSection
          documents={documents}
          filteredDocuments={filteredDocuments}
          stats={stats}
          lavoriInCorso={lavoriInCorso}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          searchField={searchField}
          setSearchField={setSearchField}
          selectedIds={selectedIds}
          selectedDocs={selectedDocs}
          onToggleSelect={toggleSelect}
          onClearSelection={() => setSelectedIds([])}
          onMerge={handleMerge}
          isMerging={isMerging}
          onEdit={(doc) => {
            setSelectedDoc(doc);
            setEditData({ ...doc.dati });
          }}
          onDelete={handleDelete}
          onApriFattura={apriFattura}
          apiUrl={API_URL}
          onScansione={(esito) => {
            fetchDocuments();
            fetchFatture();
            segnalaSbloccate(esito?.fatture_sbloccate);
          }}
          onErrore={(testo) => setError(testo)}
        />
      )}

      {vista === 'FATTURE' && (
        <FattureSection
          apiUrl={API_URL}
          fatture={fatture}
          loading={loadingFatture}
          onRicarica={fetchFatture}
          onApri={setFatturaAperta}
          onElimina={handleDeleteFattura}
          onApriDdt={apriDocumento}
          onAccoppia={handleAccoppia}
          idInAccoppiamento={idInAccoppiamento}
          onErrore={(testo) => setAvviso({ tipo: 'danger', testo })}
        />
      )}

      {vista === 'FORNITORI' && (
        <SuppliersManager
          apiUrl={API_URL}
          versioneAnagrafica={versioneAnagrafica}
          onSaved={() => {
            fetchDaAutorizzare();
            // Lo stato della P.IVA non e' scritto sul documento: lo calcola
            // annota_stato_piva() a ogni GET /api/documents. Senza rileggerli,
            // il modale del D.D.T. continua a mostrare il campo editabile e il
            // pulsante "Conferma" per una P.IVA appena confermata di qua.
            fetchDocuments();
            // Toccare l'anagrafica cambia il riconoscimento del cedente (nomi
            // alternativi, P.IVA confermate): gli abbinamenti possibili non
            // sono più gli stessi, quindi la coda va riguardata.
            fetchFatture();
          }}
        />
      )}

      {vista === 'CONFIGURAZIONE' && (
        <ConfigSection
          apiUrl={API_URL}
          onErrore={(testo) => setAvviso({ tipo: 'danger', testo })}
          onAvviso={setAvviso}
          onRicarica={(lavoro) => {
            // Un lavoro lanciato a mano da qui ha appena estratto bolle o letto
            // fatture: gli elenchi delle altre sezioni sono vecchi, e chi torna
            // di là non ha modo di saperlo.
            if (lavoro === 'scansione_ddt') fetchDocuments();
            fetchFatture();
          }}
        />
      )}

        </main>

      {/* Inserimento manuale: allega il file e scrivi i dati, senza AI */}
      <ManualEntryModal
        show={showManualEntry}
        onClose={() => setShowManualEntry(false)}
        onSaved={(risposta) => {
          fetchDocuments();
          segnalaSbloccate(risposta?.fatture_sbloccate);
        }}
        apiUrl={API_URL}
      />

      {/* Revisione di un D.D.T.: PDF a sinistra, dati estratti a destra */}
      <ComparisonModal
        selectedDoc={selectedDoc}
        editData={editData}
        setEditData={setEditData}
        onClose={() => setSelectedDoc(null)}
        onSave={handleSaveDoc}
        isSaving={isSaving}
        onReanalyze={handleReanalyze}
        isReanalyzing={isReanalyzing}
        onCambiaStato={handleCambiaStato}
        isCambiandoStato={isCambiandoStato}
        onConfermaPiva={handleConfermaPiva}
        isConfermandoPiva={isConfermandoPiva}
        apiUrl={API_URL}
        onApriFattura={apriFattura}
      />

      {/* Fascicolo di una fattura: PDF costruito dall'XML + abbinamenti.
          La key rimonta il modale a ogni fattura diversa: così l'attesa, il
          blob del PDF e il flag di anteprima ripartono puliti senza doverli
          azzerare a mano dentro l'effetto. */}
      <InvoiceModal
        key={fatturaAperta?.id}
        fattura={fatturaAperta}
        apiUrl={API_URL}
        onClose={() => setFatturaAperta(null)}
        onApriDdt={apriDocumento}
        onElimina={handleDeleteFattura}
        onAccoppia={handleAccoppia}
        onConferma={handleConfermaAccoppiamento}
        isAccoppiando={idInAccoppiamento === fatturaAperta?.id}
        isConfermando={isConfermandoAccoppiamento}
      />

        <Toast avviso={avviso} onClose={() => setAvviso(null)} />
      </div>
    </div>
  );
}

export default App;
