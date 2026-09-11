import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Save, RotateCcw, Sliders, AlertTriangle, Info } from 'lucide-react';
import PannelloLavori from './PannelloLavori';

// La stessa di configurazione.py: il backend manda questa al posto della
// password SMTP e la riconosce quando torna indietro. Un valore che non esce
// mai dal server non puo' finire nella cache del browser.
const MASCHERA = '••••••';

/**
 * Sezione Configurazione: le impostazioni che si cambiano senza ricostruire.
 *
 * Fino a ieri OLLAMA_HOST, il modello e le soglie dei solleciti stavano solo
 * nel docker-compose: cambiarne una voleva dire aprire un YAML sul server e
 * rifare `docker compose up -d`. Sono però proprio le leve che si provano più
 * spesso, quindi ora vivono anche in un file su volume che vince sull'ambiente.
 *
 * Il campo VUOTO non è un errore ed è metà del senso di questa schermata:
 * significa "torna al valore del docker-compose". È anche la via di fuga se una
 * modifica fatta di qui rompe qualcosa — per questo l'origine di ogni valore è
 * scritta accanto al campo.
 */
export default function ConfigSection({ apiUrl, onErrore, onAvviso, onRicarica }) {
  const [impostazioni, setImpostazioni] = useState([]);
  const [bozza, setBozza] = useState({});
  const [caricamento, setCaricamento] = useState(true);
  const [salvataggio, setSalvataggio] = useState(false);
  const [esito, setEsito] = useState(null);
  // Cresce a ogni salvataggio: toccato un orario, il pannello dei lavori deve
  // ricalcolare la prossima esecuzione invece di mostrare quella di prima.
  const [versione, setVersione] = useState(0);

  const carica = useCallback(async () => {
    setCaricamento(true);
    try {
      const res = await axios.get(`${apiUrl}/api/configurazione`);
      const voci = res.data.impostazioni || [];
      setImpostazioni(voci);
      // Nel form si mostra il valore attuale qualunque sia la sua origine: chi
      // apre la pagina vuole vedere cosa sta girando, non un campo vuoto.
      setBozza(Object.fromEntries(voci.map((i) => [i.chiave, String(i.valore ?? '')])));
      setEsito(null);
    } catch (err) {
      onErrore?.('Impossibile leggere la configurazione dal backend.');
    } finally {
      setCaricamento(false);
    }
  }, [apiUrl, onErrore]);

  useEffect(() => { carica(); }, [carica]);

  const modificate = useMemo(
    () => impostazioni.filter((i) => String(i.valore ?? '') !== (bozza[i.chiave] ?? '')).map((i) => i.chiave),
    [impostazioni, bozza],
  );

  const gruppi = useMemo(() => {
    const per = new Map();
    impostazioni.forEach((i) => {
      if (!per.has(i.gruppo)) per.set(i.gruppo, []);
      per.get(i.gruppo).push(i);
    });
    return Array.from(per.entries());
  }, [impostazioni]);

  const salva = async () => {
    setSalvataggio(true);
    setEsito(null);
    try {
      const res = await axios.put(`${apiUrl}/api/configurazione`, bozza);
      const voci = res.data.impostazioni || [];
      setImpostazioni(voci);
      setBozza(Object.fromEntries(voci.map((i) => [i.chiave, String(i.valore ?? '')])));
      setVersione((v) => v + 1);
      setEsito({
        tipo: (res.data.scartate || []).length > 0 ? 'warning' : 'success',
        testo: (res.data.scartate || []).length > 0
          ? `Salvato, ma ${res.data.scartate.join(', ')} è stato scartato: valore non valido o fuori intervallo.`
          : 'Configurazione salvata. Ha effetto subito, senza riavviare il backend.',
      });
    } catch (err) {
      setEsito({ tipo: 'danger', testo: err.response?.data?.detail || 'Salvataggio non riuscito.' });
    } finally {
      setSalvataggio(false);
    }
  };

  /**
   * Il campo giusto per il tipo dell'impostazione.
   *
   * Non è cosmesi: un orario scritto a mano si sbaglia (`8:00`, `20.30`, `8`) e
   * il backend lo scarterebbe in silenzio dal punto di vista di chi guarda,
   * mentre un `<input type="time">` non può produrre una forma sbagliata. Stesso
   * discorso per le tre sicurezze SMTP, che sono un elenco chiuso.
   */
  const campo = (impostazione, valore, cambiata, cambia) => {
    const classe = `form-control bg-black text-white ${cambiata ? 'border-warning' : 'border-secondary'}`;

    if (impostazione.tipo === 'scelta') {
      return (
        <select
          id={impostazione.chiave}
          className={`form-select bg-black text-white ${cambiata ? 'border-warning' : 'border-secondary'}`}
          value={valore}
          onChange={(e) => cambia(e.target.value)}
        >
          {(impostazione.opzioni || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    }

    // Il segreto arriva già mascherato dal backend e torna indietro tale e
    // quale, a dire "lascia com'è": la dashboard rimanda sempre la bozza
    // intera, quindi senza la maschera salvare un orario cancellerebbe la
    // password SMTP. Svuotare il campo la cancella davvero, come per gli altri.
    const segreto = impostazione.segreto;
    const tipo = segreto ? 'password'
      : impostazione.tipo === 'orario' ? 'time'
      : impostazione.tipo === 'testo' ? 'text' : 'number';

    return (
      <input
        id={impostazione.chiave}
        type={tipo}
        step={impostazione.tipo === 'decimale' ? '0.1' : '1'}
        min={impostazione.minimo}
        max={impostazione.massimo}
        autoComplete={segreto ? 'new-password' : 'off'}
        className={classe}
        value={valore}
        placeholder={segreto ? 'nessuna password' : `predefinito: ${impostazione.default || '(vuoto)'}`}
        onChange={(e) => cambia(e.target.value)}
        onFocus={segreto ? (e) => { if (e.target.value === MASCHERA) cambia(''); } : undefined}
      />
    );
  };

  const badgeOrigine = (origine) => {
    if (origine === 'dashboard') return { classe: 'bg-info text-dark', testo: 'da questa pagina' };
    if (origine === 'ambiente') return { classe: 'bg-secondary text-white', testo: 'da docker-compose' };
    return { classe: 'bg-dark border border-secondary text-secondary', testo: 'valore predefinito' };
  };

  if (caricamento) {
    return <div className="container-fluid px-4 text-center py-5 text-secondary">Caricamento configurazione…</div>;
  }

  return (
    <div className="container-fluid px-4">
      <div className="card bg-dark border-secondary shadow-sm mb-4">
        <div className="card-header border-secondary d-flex justify-content-between align-items-center py-3 flex-wrap gap-2">
          <h5 className="mb-0 text-light d-flex align-items-center gap-2">
            <Sliders size={20} className="text-primary" /> Configurazione
          </h5>

          <div className="d-flex align-items-center gap-2">
            {modificate.length > 0 && (
              <span className="badge bg-warning text-dark d-flex align-items-center gap-1">
                <AlertTriangle size={14} /> {modificate.length} modifiche non salvate
              </span>
            )}
            <button
              className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-2"
              onClick={carica}
              disabled={salvataggio}
              title="Rilegge dal backend e annulla le modifiche non salvate"
            >
              <RotateCcw size={16} /> Annulla
            </button>
            <button
              className="btn btn-sm btn-success d-flex align-items-center gap-2"
              onClick={salva}
              disabled={salvataggio || modificate.length === 0}
            >
              <Save size={16} /> {salvataggio ? 'Salvataggio…' : 'Salva'}
            </button>
          </div>
        </div>

        <div className="card-body">
          <PannelloLavori
            apiUrl={apiUrl}
            versione={versione}
            onAvviso={onAvviso}
            onFatto={onRicarica}
          />

          <div className="alert bg-info bg-opacity-10 border border-info border-opacity-25 text-light py-2 d-flex gap-2 align-items-start">
            <Info size={18} className="text-info flex-shrink-0 mt-1" />
            <small className="mb-0">
              I valori salvati qui <strong>vincono sul docker-compose</strong> e hanno effetto subito, senza
              riavviare il backend. <strong>Svuotare un campo</strong> non è un errore: fa tornare al valore
              del compose, ed è la via d’uscita se una modifica fatta da qui non funziona.
            </small>
          </div>

          {esito && (
            <div className={`alert alert-${esito.tipo} py-2 d-flex justify-content-between align-items-center`}>
              <span className="small">{esito.testo}</span>
              <button className="btn-close btn-close-white btn-sm" onClick={() => setEsito(null)} />
            </div>
          )}

          {gruppi.map(([gruppo, voci]) => (
            <div key={gruppo} className="mb-4">
              <h6 className="text-secondary text-uppercase fw-bold border-bottom border-secondary pb-2 mb-3">
                {gruppo}
              </h6>

              {voci.map((impostazione) => {
                const origine = badgeOrigine(impostazione.origine);
                const cambiata = modificate.includes(impostazione.chiave);

                return (
                  <div className="row align-items-start mb-3" key={impostazione.chiave}>
                    <div className="col-lg-4">
                      <label className="form-label text-light mb-1 fw-semibold" htmlFor={impostazione.chiave}>
                        {impostazione.etichetta}
                      </label>
                      <div className="d-flex align-items-center gap-2">
                        <code className="text-secondary" style={{ fontSize: '0.75rem' }}>{impostazione.chiave}</code>
                        <span className={`badge ${origine.classe}`} style={{ fontSize: '0.65rem' }}>
                          {origine.testo}
                        </span>
                      </div>
                    </div>

                    <div className="col-lg-3">
                      {campo(impostazione, bozza[impostazione.chiave] ?? '', cambiata,
                        (v) => setBozza((prec) => ({ ...prec, [impostazione.chiave]: v })))}
                      {impostazione.minimo !== undefined && (
                        <small className="text-secondary">
                          ammesso da {impostazione.minimo} a {impostazione.massimo}
                        </small>
                      )}
                      {impostazione.tipo === 'orario' && (
                        <small className="text-secondary">vuoto = non pianificato</small>
                      )}
                      {impostazione.segreto && cambiata && !bozza[impostazione.chiave] && (
                        <small className="text-warning">verr&agrave; rimossa al salvataggio</small>
                      )}
                    </div>

                    <div className="col-lg-5">
                      <small className="text-secondary">{impostazione.aiuto}</small>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
