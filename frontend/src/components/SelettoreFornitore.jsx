import React, { useState, useEffect, useMemo, useRef } from 'react';
import axios from 'axios';
import { Search, KeyRound, Tags, X, AlertCircle } from 'lucide-react';

/**
 * Sceglie un fornitore dall'anagrafica e ne riporta nome e P.IVA sul documento.
 *
 * Serve al caso in cui il fornitore sul D.D.T. non si riesce proprio a leggere:
 * la bolla resta in CHECK con il campo vuoto, ma chi la rivede molto spesso sa
 * comunque di chi e' — dal timbro, dagli articoli, dalla firma. Prima l'unica
 * strada era riscrivere il nome a mano, e un nome riscritto a mano non e'
 * innocuo: il nome del fornitore e' META' DELLA CHIAVE con cui una fattura
 * ritrova le sue bolle (`abbinatore.stesso_fornitore`), e li' i nomi
 * alternativi non vengono consultati. "LEVONI" battuto al posto di "LEVONI SPA"
 * costa un abbinamento che resta in coda a chiedere una conferma.
 *
 * Pescando dall'anagrafica si scrive per costruzione il nome canonico, lo
 * stesso che `applica_nome_canonico()` avrebbe scritto se il modello avesse
 * letto il nome. E la P.IVA viene dietro gratis, che e' l'altra meta' del
 * lavoro: e' un dato che l'anagrafica ha gia' e che nessuno deve ribattere.
 *
 * L'anagrafica si rilegge all'apertura invece di riceverla come prop: e' una
 * GET sola, e una lista arrivata dall'alto sarebbe quella di quando la
 * dashboard e' stata caricata — cioe' prima delle voci censite proprio dalla
 * scansione che stiamo rivedendo.
 */
export default function SelettoreFornitore({ apiUrl, onScegli, onClose }) {
  const [fornitori, setFornitori] = useState({});
  const [ricerca, setRicerca] = useState('');
  const [errore, setErrore] = useState(null);
  const [caricando, setCaricando] = useState(true);
  const campoRicerca = useRef(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await axios.get(`${apiUrl}/api/fornitori`);
        if (vivo) setFornitori(res.data || {});
      } catch (err) {
        if (vivo) setErrore("Anagrafica non raggiungibile: il fornitore si può ancora scrivere a mano.");
      } finally {
        if (vivo) setCaricando(false);
      }
    })();
    return () => { vivo = false; };
  }, [apiUrl]);

  useEffect(() => { campoRicerca.current?.focus(); }, []);

  const alias = (data) => Array.isArray(data.nomi_alternativi) ? data.nomi_alternativi.filter(Boolean) : [];

  // Le voci marcate "mai un fornitore" (cliente, gruppo d'acquisto, vettore)
  // restano FUORI: sono l'elenco di chi non deve mai finire in questo campo, ed
  // e' esattamente l'errore che filtra_fornitore_vietato() passa il tempo a
  // rimediare. Offrirle qui sarebbe un modo per rifarlo a mano.
  const voci = useMemo(() => Object.entries(fornitori)
    .filter(([, data]) => data?.mai_fornitore !== true)
    .sort(([a], [b]) => a.localeCompare(b, 'it', { sensitivity: 'base', numeric: true })),
    [fornitori]);

  const esclusi = Object.values(fornitori).filter(d => d?.mai_fornitore === true).length;

  // Si cerca anche sui nomi alternativi e sulla P.IVA: chi rivede la bolla ha
  // spesso in mano proprio il nome "sbagliato" (quello corto, quello della
  // controllata estera), che e' il motivo per cui gli alias esistono.
  const trovati = useMemo(() => {
    const q = ricerca.trim().toLowerCase();
    if (!q) return voci;
    return voci.filter(([nome, data]) =>
      nome.toLowerCase().includes(q)
      || (data.partita_iva || '').includes(q)
      || alias(data).some(a => a.toLowerCase().includes(q)));
  }, [voci, ricerca]);

  const scegli = (nome, data) => {
    onScegli({
      nome,
      partita_iva: data.partita_iva || '',
      partita_iva_confermata: data.partita_iva_confermata !== false,
    });
  };

  return (
    <div
      className="modal show d-block"
      style={{ backgroundColor: 'rgba(0,0,0,0.6)', zIndex: 1060 }}
      tabIndex="-1"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
    >
      <div className="modal-dialog modal-dialog-centered modal-dialog-scrollable">
        <div className="modal-content shadow-lg">

          <div className="modal-header py-3">
            <div>
              <h6 className="modal-title fw-bold mb-0">Scegli il fornitore dall&apos;anagrafica</h6>
              <small className="text-body-secondary">
                Ne riporta il nome esatto e la partita IVA sul documento.
              </small>
            </div>
            <button type="button" className="btn-close" onClick={onClose} aria-label="Chiudi" />
          </div>

          <div className="px-3 pt-3">
            <div className="position-relative">
              <Search className="position-absolute top-50 translate-middle-y text-body-secondary ms-3" size={18} />
              <input
                ref={campoRicerca}
                type="text"
                className="form-control ps-5"
                placeholder="Cerca per nome, nome alternativo o partita IVA…"
                value={ricerca}
                onChange={(e) => setRicerca(e.target.value)}
              />
            </div>
          </div>

          <div className="modal-body pt-3" style={{ maxHeight: '55vh' }}>
            {errore && (
              <div className="alert alert-warning d-flex align-items-center gap-2 py-2 small">
                <AlertCircle size={16} className="flex-shrink-0" /> {errore}
              </div>
            )}

            {caricando && <div className="text-body-secondary small px-1">Lettura anagrafica…</div>}

            {!caricando && trovati.length === 0 && !errore && (
              <div className="text-body-secondary small px-1">
                Nessun fornitore corrisponde a <strong>{ricerca}</strong>.
                Se è un fornitore nuovo, scrivi il nome direttamente nel campo: verrà censito da solo.
              </div>
            )}

            <div className="list-group list-group-flush">
              {trovati.map(([nome, data]) => {
                const daConfermare = !!data.partita_iva && data.partita_iva_confermata === false;
                return (
                  <button
                    key={nome}
                    type="button"
                    className="list-group-item list-group-item-action px-2 py-2"
                    onClick={() => scegli(nome, data)}
                  >
                    <div className="d-flex justify-content-between align-items-start gap-2">
                      <span className="fw-semibold text-body">{nome}</span>
                      {data.partita_iva ? (
                        <span className={`badge d-flex align-items-center gap-1 flex-shrink-0 ${daConfermare
                          ? 'bg-primary bg-opacity-25 text-primary border border-primary border-opacity-50'
                          : 'bg-success bg-opacity-25 text-success border border-success border-opacity-50'}`}>
                          <KeyRound size={12} />
                          <span className="font-monospace">{data.partita_iva}</span>
                        </span>
                      ) : (
                        <span className="badge bg-body-secondary text-body-secondary flex-shrink-0">senza P.IVA</span>
                      )}
                    </div>
                    {alias(data).length > 0 && (
                      <div className="text-body-secondary d-flex align-items-center gap-1 mt-1" style={{ fontSize: '0.72rem' }}>
                        <Tags size={11} /> {alias(data).join(' · ')}
                      </div>
                    )}
                    {daConfermare && (
                      <div className="text-primary mt-1" style={{ fontSize: '0.72rem' }}>
                        P.IVA ancora da confermare: viene riportata lo stesso, ma va convalidata.
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="modal-footer py-2 d-flex justify-content-between">
            <small className="text-body-secondary">
              {esclusi > 0 && (
                <>
                  {esclusi} voc{esclusi === 1 ? 'e' : 'i'} marcat{esclusi === 1 ? 'a' : 'e'} <em>mai un fornitore</em>
                  {' '}(clienti, gruppi d&apos;acquisto, vettori) non compaiono qui.
                </>
              )}
            </small>
            <button className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-1" onClick={onClose}>
              <X size={14} /> Annulla
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
