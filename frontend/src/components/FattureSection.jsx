import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Search, X, RotateCw, Receipt, CheckCircle, Clock, Truck, ChevronDown, ChevronRight, Link2,
} from 'lucide-react';
import InvoiceTable from './InvoiceTable';
import BarraIngresso from './BarraIngresso';
import Paginazione, { usePaginazione } from './Paginazione';
import { conteggioDdt, daAccoppiare } from './etichetteFatture';

const FILTRI = [
  { valore: 'TUTTE', etichetta: 'Tutte', colore: 'light' },
  { valore: 'DA_ABBINARE', etichetta: 'Da abbinare', colore: 'primary' },
  { valore: 'IN_ATTESA', etichetta: 'In attesa', colore: 'warning' },
  { valore: 'DA_CONFERMARE', etichetta: 'Da confermare a mano', colore: 'info' },
  { valore: 'DA_ACCOPPIARE', etichetta: 'Da accoppiare', colore: 'warning' },
  { valore: 'ABBINATA', etichetta: 'Accoppiate', colore: 'success' },
  { valore: 'NON_ABBINATA', etichetta: 'Senza D.D.T.', colore: 'secondary' },
];

const normalizza = (valore) =>
  (valore ?? '').toString().toLowerCase().replace(/[/.]/g, '-').replace(/\s+/g, ' ').trim();

/**
 * Sezione Fatture: le fatture elettroniche e il loro abbinamento ai D.D.T.
 *
 * L'elenco arriva già unito da GET /api/fatture (chiuse + coda). Qui si aggiunge
 * solo il lato speculare dell'attesa — i D.D.T. che nessuna fattura ha ancora
 * agganciato — perché le due code si guardano insieme: se una bolla è ferma da
 * un mese, o la fattura non è mai arrivata o non è ancora stata caricata, e in
 * entrambi i casi la risposta sta altrove.
 */
export default function FattureSection({
  fatture, loading, onRicarica, onApri, onElimina, onApriDdt, onAccoppia, idInAccoppiamento, apiUrl,
  onErrore,
}) {
  const [filtro, setFiltro] = useState('TUTTE');
  const [ricerca, setRicerca] = useState('');
  const [isRicontrollo, setIsRicontrollo] = useState(false);
  const [isAbbinaTutte, setIsAbbinaTutte] = useState(false);
  const [esitoRicontrollo, setEsitoRicontrollo] = useState(null);

  const [ddtSoli, setDdtSoli] = useState([]);
  const [mostraDdtSoli, setMostraDdtSoli] = useState(false);

  useEffect(() => {
    // giorni=0 perché qui si vuole la coda intera: la soglia di
    // GIORNI_ATTESA_SOLLECITO serve alla mail, non alla dashboard.
    axios
      .get(`${apiUrl}/api/ddt/senza-fattura?giorni=0`)
      .then((res) => setDdtSoli(res.data.ddt || []))
      .catch(() => setDdtSoli([]));
  }, [apiUrl, fatture]);

  const conteggi = useMemo(() => {
    const base = {
      totali: fatture.length, abbinate: 0, attesa: 0, nonAbbinate: 0,
      daConfermare: 0, mancanti: 0, daAccoppiare: 0, daAbbinare: 0,
    };

    fatture.forEach((fattura) => {
      if (fattura.stato === 'ABBINATA') base.abbinate += 1;
      else if (fattura.stato === 'IN_ATTESA') base.attesa += 1;
      else if (fattura.stato === 'DA_ABBINARE') base.daAbbinare += 1;
      else base.nonAbbinate += 1;

      // Pronte ma non firmate: è l'unico numero che conta un'azione da fare,
      // e vale per qualsiasi stato — anche una fattura senza D.D.T. va
      // comunque archiviata dall'operatore.
      if (daAccoppiare(fattura)) base.daAccoppiare += 1;

      const { daConfermare, mancanti } = conteggioDdt(fattura);
      if (fattura.stato === 'IN_ATTESA') {
        if (daConfermare > 0) base.daConfermare += 1;
        else if (mancanti > 0) base.mancanti += 1;
      }
    });

    return base;
  }, [fatture]);

  const filtrate = useMemo(() => {
    const termine = normalizza(ricerca);

    return fatture
      .filter((fattura) => {
        if (filtro === 'DA_CONFERMARE') {
          return fattura.stato === 'IN_ATTESA' && conteggioDdt(fattura).daConfermare > 0;
        }
        if (filtro === 'DA_ACCOPPIARE') return daAccoppiare(fattura);
        // "Abbinate" vuol dire accoppiate davvero: una pratica pronta ma non
        // ancora firmata ha lo stesso stato e non è la stessa cosa.
        if (filtro === 'ABBINATA') return fattura.stato === 'ABBINATA' && !daAccoppiare(fattura);
        return filtro === 'TUTTE' || fattura.stato === filtro;
      })
      .filter((fattura) => {
        if (!termine) return true;
        const dati = fattura.dati || {};
        // Si cerca anche nei numeri D.D.T. citati: partire dalla bolla che si ha
        // in mano per risalire alla fattura è il caso d'uso più frequente.
        const numeriDdt = (fattura.ddt || []).map((r) => `${r.numero_ddt} ${r.numero_ddt_letto}`).join(' ');
        return [dati.numero_fattura, dati.fornitore, dati.partita_iva, dati.data_fattura, numeriDdt]
          .some((campo) => normalizza(campo).includes(termine));
      })
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [fatture, filtro, ricerca]);

  const pagine = usePaginazione(filtrate, `${filtro}|${ricerca}`);

  // Il pulsante globale. Diverso da "Ricontrolla coda": quello riguarda le
  // pratiche che un abbinamento ce l'hanno gia' e possono essersi sbloccate da
  // sole, questo prende anche le DA_ABBINARE, cioe' quelle su cui nessuno ha
  // ancora chiesto niente. Nessuna pratica si chiude: la firma resta un gesto
  // per fattura.
  const handleAbbinaTutte = async () => {
    setIsAbbinaTutte(true);
    setEsitoRicontrollo(null);
    try {
      const res = await axios.post(`${apiUrl}/api/fatture/abbina-tutte`);
      const sbloccate = res.data.sbloccate || [];
      setEsitoRicontrollo({
        tipo: sbloccate.length > 0 ? 'success' : 'secondary',
        testo: sbloccate.length > 0
          ? `${sbloccate.length} pratic${sbloccate.length === 1 ? 'a pronta' : 'he pronte'} da accoppiare: ${sbloccate.map((f) => f.numero_fattura || f.id).join(', ')}. Premi ACCOPPIA sulla riga per salvare il file unico.`
          : `Nessuna pratica completata: ${res.data.restano ?? 0} restano in coda. Servono nuovi D.D.T. o una correzione ai numeri letti male.`,
      });
      onRicarica();
    } catch (err) {
      setEsitoRicontrollo({ tipo: 'danger', testo: err.response?.data?.detail || 'Abbinamento non riuscito.' });
    } finally {
      setIsAbbinaTutte(false);
    }
  };

  const handleRicontrolla = async () => {
    setIsRicontrollo(true);
    setEsitoRicontrollo(null);
    try {
      const res = await axios.post(`${apiUrl}/api/fatture/ricontrolla`);
      const sbloccate = res.data.sbloccate || [];
      setEsitoRicontrollo({
        tipo: sbloccate.length > 0 ? 'success' : 'secondary',
        testo: sbloccate.length > 0
          ? `${sbloccate.length} pratic${sbloccate.length === 1 ? 'a chiusa' : 'he chiuse'}: ${sbloccate.map((f) => f.numero_fattura || f.id).join(', ')}`
          : `Nessuna novità: ${res.data.restano ?? 0} fattur${res.data.restano === 1 ? 'a resta' : 'e restano'} in coda. Servono nuovi D.D.T. o una correzione ai numeri letti male.`,
      });
      onRicarica();
    } catch {
      setEsitoRicontrollo({ tipo: 'danger', testo: 'Ricontrollo non riuscito: backend irraggiungibile.' });
    } finally {
      setIsRicontrollo(false);
    }
  };

  const cartaConteggio = (etichetta, valore, colore, Icona, titolo) => (
    <div className="col-md-3">
      <div className={`card bg-dark border-secondary shadow-sm h-100 border-start border-4 border-${colore}`} title={titolo}>
        <div className="card-body py-3 d-flex justify-content-between align-items-center">
          <div>
            <h6 className="text-secondary mb-1 text-uppercase fw-bold" style={{ fontSize: '0.75rem' }}>{etichetta}</h6>
            <h3 className={`mb-0 fw-bold text-${colore === 'primary' ? 'light' : colore}`}>{valore}</h3>
          </div>
          <Icona size={28} className={`text-${colore} opacity-50`} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="container-fluid px-4">
      <div className="row g-3 mb-4">
        {cartaConteggio('Fatture totali', conteggi.totali, 'primary', Receipt, 'Confermate e in coda insieme')}
        {cartaConteggio('Da abbinare', conteggi.daAbbinare, 'info', Search, 'Lette e archiviate, ma il confronto con i D.D.T. non è ancora stato chiesto')}
        {cartaConteggio('Da accoppiare', conteggi.daAccoppiare, 'warning', Link2, 'Pratiche che aspettano l’operatore: ABBINA cerca i D.D.T., ACCOPPIA crea il file unico')}
        {cartaConteggio('Accoppiate', conteggi.abbinate, 'success', CheckCircle, 'Confermate: il file unico fattura + D.D.T. è in ACCOPPIATE')}
      </div>

      <BarraIngresso
        apiUrl={apiUrl}
        tipo="fatture"
        accept=".xml,.p7m"
        etichettaCarica="Aggiungi fattura"
        etichettaAnalizza="Analizza fatture"
        descrizione="Cartella in ingresso FATTURE/da_leggere: le fatture vengono lette e archiviate, ma NON abbinate — l'abbinamento lo chiedi tu."
        onFatto={onRicarica}
        onErrore={onErrore}
      />

      {/* Le due code non si risolvono nello stesso modo: tenerle separate è
          l'unica ragione per cui vale la pena guardare questo riquadro. */}
      {conteggi.attesa > 0 && (
        <div className="row g-3 mb-4">
          <div className="col-md-6">
            <div className="alert bg-info bg-opacity-10 border border-info border-opacity-25 text-light h-100 mb-0 py-3">
              <h6 className="fw-bold text-info d-flex align-items-center gap-2">
                <Clock size={18} /> {conteggi.daConfermare} da confermare a mano
              </h6>
              <div className="small mb-0">
                Il D.D.T. c’è già ma il modello ne ha letto male il numero. Ricontrollare non serve: apri la
                fattura, vai al documento e correggi il numero — al salvataggio la pratica si chiude da sola.
              </div>
            </div>
          </div>
          <div className="col-md-6">
            <div className="alert bg-warning bg-opacity-10 border border-warning border-opacity-25 text-light h-100 mb-0 py-3">
              <h6 className="fw-bold text-warning d-flex align-items-center gap-2">
                <Truck size={18} /> {conteggi.mancanti} in attesa di bolle mai arrivate
              </h6>
              <div className="small mb-0">
                Nessun D.D.T. archiviato con quel numero: la bolla va cercata in magazzino e scansionata.
                Appena viene letta, l’abbinamento scatta da solo senza fare altro.
              </div>
            </div>
          </div>
        </div>
      )}

      {esitoRicontrollo && (
        <div className={`alert alert-${esitoRicontrollo.tipo} shadow-sm border-0 py-2 d-flex justify-content-between align-items-center`}>
          <span className="small">{esitoRicontrollo.testo}</span>
          <button className="btn-close btn-close-white btn-sm" onClick={() => setEsitoRicontrollo(null)} />
        </div>
      )}

      <div className="card bg-dark border-secondary shadow-sm mb-4">
        <div className="card-header border-secondary d-flex justify-content-between align-items-center py-3 gap-3 flex-wrap">
          <div className="input-group" style={{ maxWidth: '420px' }}>
            <span className="input-group-text bg-secondary border-secondary text-white">
              <Search size={18} />
            </span>
            <input
              type="text"
              className="form-control bg-black text-white border-secondary"
              placeholder="Cerca per n. fattura, fornitore, P.IVA o numero D.D.T.…"
              value={ricerca}
              onChange={(e) => setRicerca(e.target.value)}
            />
            {ricerca && (
              <button className="btn btn-outline-secondary text-white" onClick={() => setRicerca('')} title="Azzera">
                <X size={18} />
              </button>
            )}
          </div>

          <div className="d-flex align-items-center gap-2 flex-wrap">
            {FILTRI.map(({ valore, etichetta, colore }) => (
              <button
                key={valore}
                className={`btn btn-sm ${filtro === valore ? `btn-${colore}` : 'btn-outline-secondary'}`}
                onClick={() => setFiltro(valore)}
              >
                {etichetta}
              </button>
            ))}

            <button
              className="btn btn-sm btn-primary d-flex align-items-center gap-2 ms-2"
              onClick={handleAbbinaTutte}
              disabled={isAbbinaTutte || isRicontrollo}
              title="Cerca i D.D.T. di tutte le fatture in coda, comprese quelle appena caricate. Non chiude niente: la conferma resta per fattura."
            >
              <Link2 size={16} className={isAbbinaTutte ? 'fa-spin' : ''} />
              {isAbbinaTutte ? 'Abbinamento…' : 'Abbina tutte'}
            </button>

            <button
              className="btn btn-sm btn-outline-info d-flex align-items-center gap-2"
              onClick={handleRicontrolla}
              disabled={isRicontrollo || isAbbinaTutte || conteggi.attesa === 0}
              title="Riprova l'abbinamento di tutta la coda. Normalmente scatta da solo dopo ogni D.D.T.: serve dopo aver toccato l'anagrafica fornitori."
            >
              <RotateCw size={16} className={isRicontrollo ? 'fa-spin' : ''} />
              {isRicontrollo ? 'Ricontrollo…' : 'Ricontrolla coda'}
            </button>
          </div>
        </div>

        <div className="card-body p-0">
          {loading && fatture.length === 0 ? (
            <div className="text-center py-5 text-secondary">Caricamento fatture…</div>
          ) : (
            <>
              <InvoiceTable
                fatture={pagine.visibili}
                onApri={onApri}
                onElimina={onElimina}
                onAccoppia={onAccoppia}
                idInAccoppiamento={idInAccoppiamento}
              />
              <Paginazione {...pagine} etichetta="fatture" />
            </>
          )}
        </div>

        <div className="card-footer border-secondary text-secondary small py-2">
          {filtrate.length} di {fatture.length} fatture
        </div>
      </div>

      {/* L'attesa dall'altro lato: bolle archiviate che nessuna fattura cita. */}
      <div className="card bg-dark border-secondary shadow-sm mb-5">
        <button
          className="card-header border-secondary bg-transparent w-100 text-start d-flex justify-content-between align-items-center py-3 border-0"
          onClick={() => setMostraDdtSoli((v) => !v)}
        >
          <span className="fw-bold text-light d-flex align-items-center gap-2">
            {mostraDdtSoli ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            <Truck size={18} className="text-warning" />
            D.D.T. senza fattura
            <span className="badge bg-secondary">{ddtSoli.length}</span>
          </span>
          <span className="text-secondary small">
            Bolle archiviate che nessuna fattura ha ancora agganciato
          </span>
        </button>

        {mostraDdtSoli && (
          <div className="card-body p-0">
            {ddtSoli.length === 0 ? (
              <div className="text-center py-4 text-secondary small">
                Nessuna: ogni D.D.T. archiviato è già finito in un fascicolo.
              </div>
            ) : (
              <>
                <div className="px-4 pt-3 text-secondary small">
                  Da questo lato non c’è niente da correggere: una bolla si aggancia quando la sua fattura
                  viene caricata e qualcuno preme <strong>Abbina</strong>. Se aspetta da troppo, o la fattura
                  non è mai arrivata, oppure è in archivio e nessuno ne ha ancora chiesto l’abbinamento —
                  in quel caso la trovi qui sopra tra le <em>Da abbinare</em>. I <code>KO</code> non compaiono
                  qui: lì il numero non è stato letto affatto, quindi nessuna fattura potrebbe agganciarli.
                </div>

                <div className="table-responsive mt-3">
                  <table className="table table-dark table-striped table-hover align-middle mb-0">
                    <thead className="table-secondary">
                      <tr>
                        <th className="px-4 py-2 border-0">Fornitore</th>
                        <th className="py-2 border-0">N. D.D.T.</th>
                        <th className="py-2 border-0">Data</th>
                        <th className="py-2 border-0">Stato</th>
                        <th className="py-2 border-0">In attesa da</th>
                        <th className="px-4 py-2 text-end border-0">Azioni</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ddtSoli.map((ddt) => (
                        <tr key={ddt.id}>
                          <td className="px-4 text-white">{ddt.fornitore || <span className="text-warning fst-italic">Mancante</span>}</td>
                          <td className="font-monospace text-white fw-bold">{ddt.numero_ddt || '—'}</td>
                          <td className="font-monospace text-white">{ddt.data_ddt || '—'}</td>
                          <td>
                            <span className={`badge rounded-pill ${ddt.stato === 'OK' ? 'bg-success' : 'bg-warning text-dark'}`}>
                              {ddt.stato}
                            </span>
                          </td>
                          <td className="text-secondary">{ddt.giorni_attesa} giorn{ddt.giorni_attesa === 1 ? 'o' : 'i'}</td>
                          <td className="px-4 text-end">
                            <button className="btn btn-sm btn-outline-info" onClick={() => onApriDdt(ddt.id)}>
                              Apri il D.D.T.
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
