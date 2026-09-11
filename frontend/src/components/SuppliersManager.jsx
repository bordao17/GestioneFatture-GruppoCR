import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import Paginazione, { usePaginazione } from './Paginazione';
import { Save, Info, Search, Plus, Ban, ShieldCheck, BrainCircuit, Trash2, AlertCircle, Crosshair, Tags, KeyRound, Check } from 'lucide-react';

// I campi che una regola mirata può indirizzare. Devono restare allineati a
// CAMPI_REGOLABILI in backend/src/comune/memory_manager.py: una regola su un
// campo che il backend non conosce viene scartata in silenzio al salvataggio.
const CAMPI_REGOLABILI = [
  { valore: 'indirizzo_consegna', etichetta: 'Indirizzo di consegna (+ ragione sociale)' },
  { valore: 'partita_iva', etichetta: 'Partita IVA del fornitore' },
  { valore: 'numero_ddt', etichetta: 'Numero D.D.T.' },
  { valore: 'data_ddt', etichetta: 'Data D.D.T.' },
  { valore: 'fornitore', etichetta: 'Fornitore' },
];

export default function SuppliersManager({ apiUrl, onSaved }) {
  const [suppliers, setSuppliers] = useState({});
  const [searchTerm, setSearchTerm] = useState('');
  const [filtro, setFiltro] = useState('TUTTI'); // TUTTI | PIVA | REGOLE | CLIENTI
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);
  // PUT /api/fornitori sovrascrive l'INTERO file: finche' non si salva, le
  // modifiche vivono solo qui e un F5 le perde. Meglio dirlo che scoprirlo.
  const [modificato, setModificato] = useState(false);

  useEffect(() => {
    fetchSuppliers();
  }, []);

  const fetchSuppliers = async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/fornitori`);
      setSuppliers(res.data);
      setModificato(false);
    } catch (err) {
      console.error("Errore nel caricamento fornitori:", err);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveMessage(null);
    try {
      await axios.put(`${apiUrl}/api/fornitori`, suppliers);
      setModificato(false);
      setSaveMessage({ type: 'success', text: 'Anagrafica fornitori aggiornata.' });
      setTimeout(() => setSaveMessage(null), 3000);
      // Il backend deduplica in salvataggio (unifica_memoria): dopo la PUT il
      // file puo' avere meno voci di quelle inviate, quindi si rilegge.
      fetchSuppliers();
      onSaved?.();
    } catch (err) {
      setSaveMessage({ type: 'danger', text: 'Errore durante il salvataggio.' });
    } finally {
      setIsSaving(false);
    }
  };

  const updateSupplier = (name, field, value) => {
    setModificato(true);
    setSuppliers(prev => ({
      ...prev,
      [name]: { ...prev[name], [field]: value }
    }));
  };

  // Le regole mirate si modificano una riga alla volta, non come testo libero:
  // e' proprio la prosa a non funzionare. Una regola scritta al negativo ("NON
  // guardare nella sezione Destinatario") non dice al modello dove guardare, e
  // infatti non produceva nessun risultato; il modulo obbliga invece a indicare
  // l'etichetta stampata sul documento sotto cui il dato si trova davvero.
  const regoleDi = (data) => Array.isArray(data.regole_campo) ? data.regole_campo : [];

  const aggiornaRegola = (name, indice, campo, valore) => {
    const regole = regoleDi(suppliers[name]).map((r, i) => i === indice ? { ...r, [campo]: valore } : r);
    updateSupplier(name, 'regole_campo', regole);
  };

  const aggiungiRegola = (name) => {
    updateSupplier(name, 'regole_campo', [
      ...regoleDi(suppliers[name]),
      { campo: 'indirizzo_consegna', etichetta: '' },
    ]);
  };

  const rimuoviRegola = (name, indice) => {
    updateSupplier(name, 'regole_campo', regoleDi(suppliers[name]).filter((_, i) => i !== indice));
  };

  // Il censimento e' automatico e non distingue i vettori: in anagrafica
  // finiscono voci come TRASPORTO IO SRL (che il prompt dice di ignorare come
  // fornitore) o i residui di letture troncate. Sono innocue finche' la regola
  // resta spenta, ma questo e' il posto per toglierle.
  const removeSupplier = (name) => {
    if (!window.confirm(
      `Rimuovere “${name}” dall'anagrafica?

` +
      `Si perdono la sua regola AI, gli indirizzi vietati, i nomi alternativi e la P.IVA. ` +
      `Se il fornitore si ripresenta su un D.D.T. o su una fattura verra' censito di nuovo, ` +
      `ma senza nessuna di quelle informazioni.

` +
      `La rimozione diventa definitiva solo con "Salva Anagrafica".`
    )) return;

    setModificato(true);
    setSuppliers(prev => {
      const copia = { ...prev };
      delete copia[name];
      return copia;
    });
  };

  const addNewSupplier = () => {
    const name = prompt("Inserisci la Ragione Sociale esatta del nuovo fornitore:");
    if (name && !suppliers[name]) {
      setModificato(true);
      setSuppliers(prev => ({
        ...prev,
        [name]: {
          confermato: "no", note_specifiche: "", indirizzi_vietati: [],
          regole_campo: [], nomi_alternativi: [], partita_iva: "",
          partita_iva_confermata: true, autorizzato: true, mai_fornitore: false,
        }
      }));
      // In ordine alfabetico e a 50 per pagina la voce appena creata puo'
      // nascere fuori schermo: la ricerca la porta subito davanti.
      setSearchTerm(name);
    }
  };

  // Stessa convenzione, stesso motivo: la chiave assente vale "confermata".
  // Le P.IVA gia' in anagrafica arrivano dagli XML delle fatture (dato fiscale
  // esatto); quelle LETTE dal modello su una scansione scrivono false
  // esplicitamente, e sono le uniche che chiedono un occhio umano.
  const isPivaConfermata = (data) => data.partita_iva_confermata !== false;
  const pivaDaConfermare = (data) => !!data.partita_iva && !isPivaConfermata(data);

  // Ordine alfabetico e non quello di inserimento: qui si cerca un fornitore
  // per nome, e l'ordine in cui le scansioni lo hanno incontrato non aiuta.
  // localeCompare con sensitivity 'base' mette 'SANTÈ' accanto a 'SANTE'.
  const voci = useMemo(
    () => Object.entries(suppliers).sort(([a], [b]) =>
      a.localeCompare(b, 'it', { sensitivity: 'base', numeric: true })),
    [suppliers]
  );
  const daConfermare = voci.filter(([, data]) => pivaDaConfermare(data)).length;

  const filteredSuppliers = voci.filter(([name, data]) => {
    if (!name.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    if (filtro === 'PIVA') return pivaDaConfermare(data);
    if (filtro === 'REGOLE') return data.confermato === 'yes' || regoleDi(data).length > 0;
    if (filtro === 'CLIENTI') return data.mai_fornitore === true;
    return true;
  });

  const pagine = usePaginazione(filteredSuppliers, `${filtro}|${searchTerm}`);

  const pulsanteFiltro = (valore, etichetta, conteggio, colore) => (
    <button
      className={`btn btn-sm ${filtro === valore ? `btn-${colore}` : 'btn-outline-secondary'} d-flex align-items-center gap-2`}
      onClick={() => setFiltro(valore)}
    >
      {etichetta}
      <span className={`badge ${filtro === valore ? 'bg-dark' : 'bg-secondary'}`}>{conteggio}</span>
    </button>
  );

  return (
    <div className="container-fluid px-4">
      <div className="d-flex justify-content-between align-items-center mb-4">
        <div>
          <h4 className="fw-bold mb-1 d-flex align-items-center gap-2 text-info">
            <BrainCircuit size={28} /> Anagrafica Fornitori
          </h4>
          <div className="text-secondary small">
            Chi è ammesso nel flusso fatture e come il modello deve leggere i suoi D.D.T.
          </div>
        </div>
        <div className="d-flex align-items-center gap-3">
          {modificato && (
            <span className="text-warning small d-flex align-items-center gap-2" title="Le modifiche vivono solo nel browser finché non salvi">
              <AlertCircle size={16} /> Modifiche non salvate
            </span>
          )}
          <button
            className={`btn ${modificato ? 'btn-warning' : 'btn-info'} px-4 fw-bold text-dark d-flex align-items-center gap-2 shadow-sm`}
            onClick={handleSave}
            disabled={isSaving}
          >
            <Save size={18} /> {isSaving ? 'Salvataggio...' : 'Salva Anagrafica'}
          </button>
        </div>
      </div>

      {saveMessage && (
        <div className={`alert alert-${saveMessage.type} shadow-sm border-0 py-2`}>
          {saveMessage.text}
        </div>
      )}

      {daConfermare > 0 && (
        <div className="alert bg-primary bg-opacity-10 border border-primary border-opacity-25 text-light d-flex align-items-center gap-3 shadow-sm">
          <KeyRound size={22} className="text-primary flex-shrink-0" />
          <div className="small">
            <strong>{daConfermare} partit{daConfermare === 1 ? 'a' : 'e'} IVA lett{daConfermare === 1 ? 'a' : 'e'} dal modello,
            ancora da confermare.</strong>{' '}
            Le ha lette sulla scansione del D.D.T., quindi possono avere una cifra sbagliata: controllale
            sul documento e premi <strong>Conferma</strong>. Finché non lo fai non fanno da chiave: una
            fattura dello stesso fornitore verrà riconosciuta sul nome, e la P.IVA proposta sostituita da
            quella dell'XML.
          </div>
        </div>
      )}

      {/* BOX ISTRUZIONI AIUTO */}
      <div className="alert bg-info bg-opacity-10 border border-info border-opacity-25 text-light mb-4 shadow-sm">
        <h6 className="fw-bold text-info d-flex align-items-center gap-2 mb-3">
          <Info size={20} /> Che cosa fa ogni campo
        </h6>
        <p className="small mb-2">
          <KeyRound size={15} className="text-primary me-1" /> <strong>La Partita IVA è una chiave</strong>,
          non un campo come gli altri: è ciò che lega la fattura elettronica al fornitore dei D.D.T. Quando
          arriva da un XML è esatta e vale subito; quando la legge il modello su una scansione è solo una
          <em> proposta</em>, e va confermata con il documento sotto gli occhi. Se la P.IVA di una fattura
          manca o contraddice quella confermata qui, la fattura viene archiviata lo stesso e la discordanza
          viene segnalata: non si scarta niente.
        </p>
        <p className="small mb-2">
          <BrainCircuit size={15} className="text-info me-1" /> <strong>Regola attiva</strong> riguarda invece
          la <strong>lettura dei D.D.T.</strong>: se accesa, la nota qui sotto viene aggiunta al prompt del
          modello. Ogni nota attiva pesa su <em>ogni</em> pagina analizzata, anche di altri fornitori: tienile
          poche e corte.
        </p>
        <p className="small mb-2">
          La nota è un <strong>suggerimento</strong> al modello: su un 7B i divieti ("mai usare X") vengono spesso ignorati.
          Se un indirizzo non è <em>mai</em> la consegna per quel fornitore, mettilo in <strong>Indirizzi MAI di consegna</strong>:
          quello non è un consiglio ma un controllo automatico fatto dopo l'estrazione, e non può essere ignorato.
        </p>
        <div className="bg-dark p-3 rounded border border-secondary mt-3">
          <span className="badge bg-success mb-2">Esempio Eccellente</span>
          <code className="d-block text-light" style={{ fontSize: '0.85rem' }}>
            "IGNORA ASSOLUTAMENTE l'indirizzo 'VIA DEL RAME 06077 PONTE FELCINO PG'. Quella è la sede legale.
            Il vero indirizzo di consegna si trova in alto a destra, esattamente sotto l'etichetta 'Luogo di destinazione'.
            Estrai solo l'indirizzo scritto lì sotto."
          </code>
        </div>
      </div>

      <div className="card bg-dark border-secondary shadow-sm mb-5">
        <div className="card-header border-secondary d-flex justify-content-between align-items-center py-3 gap-3 flex-wrap">
          <div className="position-relative" style={{ minWidth: '260px', flex: '1 1 320px' }}>
            <Search className="position-absolute top-50 translate-middle-y text-secondary ms-3" size={18} />
            <input
              type="text"
              className="form-control bg-black text-light border-secondary ps-5 focus-ring"
              placeholder="Cerca fornitore..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          <div className="d-flex align-items-center gap-2 flex-wrap">
            {pulsanteFiltro('TUTTI', 'Tutti', voci.length, 'light')}
            {pulsanteFiltro('PIVA', 'P.IVA da confermare', daConfermare, 'primary')}
            {pulsanteFiltro('REGOLE', 'Con regola AI', voci.filter(([, d]) => d.confermato === 'yes' || regoleDi(d).length > 0).length, 'info')}
            {pulsanteFiltro('CLIENTI', 'Mai fornitori', voci.filter(([, d]) => d.mai_fornitore === true).length, 'danger')}
            <button className="btn btn-outline-light btn-sm d-flex align-items-center gap-1" onClick={addNewSupplier}>
              <Plus size={16} /> Aggiungi
            </button>
          </div>
        </div>

        <div className="card-body p-0">
          <div className="list-group list-group-flush rounded-bottom">
            {pagine.visibili.map(([name, data]) => (
              <div key={name} className="list-group-item bg-dark border-secondary p-4">
                <div className="row">
                  <div className="col-md-3 border-end border-secondary">
                    <div className="d-flex justify-content-between align-items-start gap-2">
                    {/* L'icona dice a colpo d'occhio di che voce si tratta:
                        un cliente marcato "mai fornitore" non è un fornitore a
                        cui manca qualcosa, è una voce che serve a FERMARE una
                        lettura, e aprirla per scoprirlo sarebbe un giro inutile. */}
                    <h6 className="fw-bold text-light mb-1 d-flex align-items-center gap-2">
                        {data.mai_fornitore
                          ? <Ban size={16} className="text-danger flex-shrink-0" />
                          : pivaDaConfermare(data)
                            ? <KeyRound size={16} className="text-primary flex-shrink-0" />
                            : <ShieldCheck size={16} className="text-success flex-shrink-0" />}
                        {name}
                      </h6>
                      <button
                        className="btn btn-sm btn-outline-danger py-0 px-2 flex-shrink-0"
                        onClick={() => removeSupplier(name)}
                        title="Rimuovi dall'anagrafica (utile per i vettori censiti per sbaglio e le letture troncate)"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <label className="form-label small text-primary mb-1 mt-3 d-flex align-items-center gap-2">
                      Partita IVA
                      {pivaDaConfermare(data) && (
                        <span className="badge bg-primary bg-opacity-25 text-primary border border-primary border-opacity-50">
                          da confermare
                        </span>
                      )}
                    </label>
                    <div className="input-group input-group-sm">
                      <input
                        type="text"
                        className={`form-control form-control-sm bg-black text-light font-monospace ${pivaDaConfermare(data) ? 'border-primary' : 'border-secondary'}`}
                        placeholder="Non ancora nota"
                        value={data.partita_iva || ''}
                        onChange={(e) => updateSupplier(name, 'partita_iva', e.target.value.replace(/\D/g, ''))}
                      />
                      {pivaDaConfermare(data) && (
                        <button
                          className="btn btn-primary d-flex align-items-center gap-1"
                          onClick={() => updateSupplier(name, 'partita_iva_confermata', true)}
                          title="Confermo che questa è la partita IVA del fornitore"
                        >
                          <Check size={14} /> Conferma
                        </button>
                      )}
                    </div>
                    <div className="form-text text-secondary" style={{ fontSize: '0.72rem' }}>
                      {data.mai_fornitore
                        ? 'È la P.IVA del cliente: quando il modello la legge su un D.D.T. il campo viene svuotato, mai attribuito al fornitore.'
                        : pivaDaConfermare(data)
                          ? 'Letta dal modello su un D.D.T.: correggila se sbagliata, poi conferma.'
                          : 'Si compila da sola: dalla prima fattura di questo fornitore, o dalla lettura del suo primo D.D.T.'}
                    </div>

                    {/* L'interruttore "Autorizzato" e' stato tolto il 2026-09-08:
                        da quando le fatture si caricano a mano non filtra piu'
                        niente, e un interruttore che non fa nulla e' peggio di
                        nessun interruttore. Il campo resta nel JSON per le voci
                        storiche. */}

                    <div className="form-check form-switch mt-3 mb-2">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        role="switch"
                        id={`switch-${name}`}
                        checked={data.confermato === 'yes'}
                        onChange={(e) => updateSupplier(name, 'confermato', e.target.checked ? 'yes' : 'no')}
                      />
                      <label className="form-check-label small text-secondary" htmlFor={`switch-${name}`}>
                        Regola attiva — lettura D.D.T.
                      </label>
                    </div>

                    {/* Il gruppo d'acquisto e le insegne dei punti vendita sono
                        stampati in cima alla bolla con la stessa evidenza
                        dell'emittente, e il modello li scambia per il fornitore.
                        Marcarli qui li ferma: sul documento il campo resta vuoto
                        e la bolla finisce in CHECK, invece di essere archiviata
                        in OK a nome del cliente. Vale anche per la P.IVA scritta
                        qui sotto, che è la loro. */}
                    <div className="form-check form-switch mb-2">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        role="switch"
                        id={`cliente-${name}`}
                        checked={data.mai_fornitore === true}
                        onChange={(e) => updateSupplier(name, 'mai_fornitore', e.target.checked)}
                      />
                      <label className="form-check-label small text-danger" htmlFor={`cliente-${name}`}>
                        Non è mai un fornitore (cliente / gruppo)
                      </label>
                    </div>
                  </div>

                  <div className="col-md-9 ps-md-4">
                    <label className="form-label small text-warning fw-bold mb-1 d-flex align-items-center gap-2">
                      <Crosshair size={14} /> Dove si trova il dato su questo documento
                    </label>

                    {regoleDi(data).map((regola, i) => (
                      <div className="input-group input-group-sm mb-2" key={i}>
                        <select
                          className="form-select bg-black text-light border-secondary"
                          style={{ maxWidth: '17rem' }}
                          value={regola.campo || 'indirizzo_consegna'}
                          onChange={(e) => aggiornaRegola(name, i, 'campo', e.target.value)}
                        >
                          {CAMPI_REGOLABILI.map(c => (
                            <option key={c.valore} value={c.valore}>{c.etichetta}</option>
                          ))}
                        </select>
                        <span className="input-group-text bg-dark text-secondary border-secondary small">
                          sta sotto
                        </span>
                        <input
                          type="text"
                          className="form-control bg-black text-light border-secondary font-monospace"
                          placeholder="l'etichetta stampata, es. LUOGO DI DESTINAZIONE"
                          value={regola.etichetta || ''}
                          onChange={(e) => aggiornaRegola(name, i, 'etichetta', e.target.value)}
                          style={{ fontSize: '0.85rem' }}
                        />
                        <button
                          className="btn btn-outline-danger"
                          onClick={() => rimuoviRegola(name, i)}
                          title="Rimuovi questa regola"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}

                    <button className="btn btn-sm btn-outline-warning" onClick={() => aggiungiRegola(name)}>
                      <Plus size={13} className="me-1" /> Aggiungi regola mirata
                    </button>

                    <div className="form-text text-secondary" style={{ fontSize: '0.75rem' }}>
                      Dopo l'estrazione il backend fa <strong>una domanda secca</strong> al modello
                      (“sotto questa dicitura cosa c'è scritto?”) e sovrascrive il campo: costa circa
                      un secondo e funziona dove la stessa regola scritta qui sotto in prosa viene ignorata.
                      Copia l'etichetta <em>come è stampata</em> sul documento. Vale sempre, anche a regola non attiva.
                      Non usare frasi al negativo: indica dov'è il dato, non dove non è.
                    </div>

                    <label className="form-label small text-light fw-bold mb-1 mt-3 d-flex align-items-center gap-2">
                      <Tags size={14} /> Altri nomi di questo fornitore (uno per riga)
                    </label>
                    <textarea
                      className="form-control bg-black text-light border-secondary font-monospace"
                      rows="2"
                      placeholder="Es. SA.BA DI SABATINI EUGENIO FISH VENDITA SURGELATI"
                      value={(data.nomi_alternativi || []).join('\n')}
                      onChange={(e) => updateSupplier(name, 'nomi_alternativi', e.target.value.split('\n'))}
                      style={{ fontSize: '0.85rem' }}
                    />
                    <div className="form-text text-secondary" style={{ fontSize: '0.75rem' }}>
                      Serve quando il modello legge la ragione sociale per esteso mentre qui è
                      registrata in forma corta (o viceversa): senza, le regole e gli indirizzi vietati
                      scattano solo su alcune scansioni dello stesso fornitore.
                    </div>

                    <label className="form-label small text-info fw-bold mb-1 mt-3">Regola per il Modello AI (Prompt)</label>
                    <textarea
                      className="form-control bg-black text-light border-secondary font-monospace"
                      rows="3"
                      placeholder="Nessuna regola specifica per questo fornitore. Il modello userà la logica standard."
                      value={data.note_specifiche}
                      onChange={(e) => updateSupplier(name, 'note_specifiche', e.target.value)}
                      style={{ fontSize: '0.85rem' }}
                    />

                    <label className="form-label small text-danger fw-bold mb-1 mt-3 d-flex align-items-center gap-2">
                      <Ban size={14} /> Indirizzi MAI di consegna (uno per riga)
                    </label>
                    <textarea
                      className="form-control bg-black text-light border-secondary font-monospace"
                      rows="2"
                      placeholder="Es. VIA DEL RAME 2, 06134 PERUGIA (PG)"
                      value={(data.indirizzi_vietati || []).join('\n')}
                      onChange={(e) => updateSupplier(name, 'indirizzi_vietati', e.target.value.split('\n'))}
                      style={{ fontSize: '0.85rem' }}
                    />
                    <div className="form-text text-secondary" style={{ fontSize: '0.75rem' }}>
                      Controllo esatto fatto in Python dopo l'estrazione, non una richiesta al modello:
                      se legge uno di questi indirizzi il campo viene svuotato e il documento finisce in CHECK.
                      Vale sempre, anche a regola non attiva. Basta la parte stabile (via e civico).
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {filteredSuppliers.length === 0 && (
              <div className="text-center py-5 text-secondary">
                Nessun fornitore trovato con questi criteri.
              </div>
            )}
          </div>

          <Paginazione {...pagine} etichetta="fornitori" />
        </div>
      </div>
    </div>
  );
}
