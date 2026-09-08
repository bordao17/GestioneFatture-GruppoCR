import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Download, FileWarning, ExternalLink, Info, Link2, Check, Lock, AlertTriangle } from 'lucide-react';
import {
  statoPratica, daAccoppiare, esitoRiga, tipoAbbinamento, formattaImporto, conteggioDdt,
} from './etichetteFatture';

/**
 * Fascicolo di una fattura elettronica: PDF a sinistra, abbinamenti a destra.
 *
 * La fattura è un XML e non si può mostrare a schermo così com'è: il PDF viene
 * chiesto a GET /api/pdf-fattura/{id}.pdf, che per una pratica chiusa serve il
 * fascicolo archiviato e per una ancora in coda lo costruisce al momento (la
 * pagina di riepilogo, la copia di cortesia allegata all'XML e i PDF dei D.D.T.
 * già trovati). Il PDF si scarica come blob invece di puntarci l'iframe apposta
 * per due motivi: si può leggere l'header X-Fascicolo-Anteprima, che distingue
 * i due casi, e si può mostrare un'attesa mentre il fascicolo viene assemblato.
 *
 * I dati NON sono modificabili: vengono da un documento fiscale firmato, e
 * l'unica cosa che si corregge da questa parte è il D.D.T. letto male — per
 * quello c'è il pulsante che porta al documento nella sezione D.D.T.
 *
 * È anche il posto in cui si firma l'accoppiamento, in due tempi che sono due
 * pulsanti diversi: ABBINA cerca i D.D.T. fra quelli archiviati e non scrive
 * niente, ACCOPPIA congela il risultato in un file unico dentro ACCOPPIATE.
 * Una fattura appena caricata è DA_ABBINARE e mostra solo il primo: firmarla
 * prima di aver guardato cosa si aggancia produrrebbe un fascicolo vuoto.
 * Nessuna pratica si chiude da sola: un abbinamento è il confronto fra un XML
 * esatto e dei numeri letti da una fotografia, quindi resta una proposta
 * finché una persona non l'ha guardata.
 */
export default function InvoiceModal({
  fattura, apiUrl, onClose, onApriDdt, onElimina, onAccoppia, onConferma,
  isAccoppiando, isConfermando,
}) {
  const [pdfUrl, setPdfUrl] = useState(null);
  const [anteprima, setAnteprima] = useState(false);
  const [caricamento, setCaricamento] = useState(true);
  const [errorePdf, setErrorePdf] = useState(null);

  const idFattura = fattura?.id;
  // Rifare la ricerca dei D.D.T. non cambia l'id, quindi il modale non si
  // rimonta: l'anteprima va rigenerata guardando l'istante dell'ultimo
  // ricalcolo, altrimenti resterebbe il PDF senza le bolle appena agganciate.
  const ultimoControllo = fattura?.ultimo_controllo;

  useEffect(() => {
    if (!idFattura) return undefined;

    let annullato = false;
    let urlCreato = null;

    axios
      .get(`${apiUrl}/api/pdf-fattura/${idFattura}.pdf`, { responseType: 'blob' })
      .then((risposta) => {
        if (annullato) return;
        urlCreato = URL.createObjectURL(risposta.data);
        setPdfUrl(urlCreato);
        setAnteprima(risposta.headers['x-fascicolo-anteprima'] === '1');
      })
      .catch(() => {
        if (!annullato) setErrorePdf('Fascicolo non disponibile: il backend non è riuscito a costruirlo.');
      })
      .finally(() => {
        if (!annullato) setCaricamento(false);
      });

    return () => {
      annullato = true;
      if (urlCreato) URL.revokeObjectURL(urlCreato);
    };
  }, [apiUrl, idFattura, ultimoControllo]);

  if (!fattura) return null;

  const dati = fattura.dati || {};
  const righe = fattura.ddt || [];
  const stato = statoPratica(fattura);
  const forma = tipoAbbinamento(fattura.tipo_abbinamento);
  const { totali, abbinati } = conteggioDdt(fattura);

  const daFirmare = daAccoppiare(fattura);
  // Il confronto non e' ancora stato chiesto: qui l'unico gesto sensato e'
  // cercare i D.D.T. Firmare adesso salverebbe un fascicolo senza bolle.
  const daAbbinare = fattura.stato === 'DA_ABBINARE';
  const completa = fattura.stato === 'ABBINATA';
  const occupato = isAccoppiando || isConfermando;

  const scarica = () => {
    if (!pdfUrl) return;
    const pulisci = (v, sostituto = '') =>
      (v || sostituto).toString().replace(/[/\\:*?"<>|]/g, '-').replace(/\s+/g, '_');

    const link = document.createElement('a');
    link.href = pdfUrl;
    link.download = `Fascicolo_${pulisci(dati.fornitore, 'FornitoreIgnoto')}_${pulisci(dati.numero_fattura, 'SenzaNumero')}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const campo = (etichetta, valore, monospace = false) => (
    <div className="mb-3">
      <label className="form-label small fw-bold text-secondary mb-1">{etichetta}</label>
      <div className={`form-control bg-black border-secondary text-light ${monospace ? 'font-monospace' : ''}`}>
        {valore || <span className="text-secondary fst-italic">non presente</span>}
      </div>
    </div>
  );

  return (
    <div className="modal show d-block" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }} tabIndex="-1">
      <div className="modal-dialog modal-xl modal-dialog-centered modal-fullscreen-lg-down">
        <div className="modal-content bg-dark text-light border-secondary shadow-lg" style={{ height: '90vh' }}>

          <div className="modal-header border-secondary py-3">
            <div>
              <h5 className="modal-title fw-bold d-flex align-items-center gap-2">
                Fattura {dati.numero_fattura || '(senza numero)'}
                <span className={`badge rounded-pill ${stato.badge}`}>{stato.etichetta}</span>
                <span className={`badge rounded-pill ${forma.badge}`}>{forma.etichetta}</span>
              </h5>
              <small className="text-secondary">
                {dati.fornitore || 'fornitore sconosciuto'} · File: {fattura.file_origine || '—'}
              </small>
            </div>
            <button type="button" className="btn-close btn-close-white" onClick={onClose}></button>
          </div>

          <div className="modal-body p-0 overflow-hidden">
            <div className="row g-0 h-100">

              {/* Sinistra: il fascicolo PDF, generato dall'XML su richiesta */}
              <div className="col-lg-7 h-100 bg-black border-end border-secondary d-flex flex-column">
                <div className="p-2 border-bottom border-secondary d-flex justify-content-between align-items-center bg-dark gap-2">
                  <span className="small fw-bold text-secondary text-uppercase ps-2">
                    Fascicolo (fattura + D.D.T.)
                  </span>
                  <button
                    className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-2"
                    onClick={scarica}
                    disabled={!pdfUrl}
                    title="Scarica il fascicolo PDF"
                  >
                    <Download size={16} /> Scarica PDF
                  </button>
                </div>

                {anteprima && (
                  <div className="alert alert-warning bg-warning bg-opacity-10 border-0 border-bottom border-warning text-warning small mb-0 rounded-0 py-2 px-3 d-flex align-items-center gap-2">
                    <FileWarning size={16} className="flex-shrink-0" />
                    <span>
                      <strong>Anteprima provvisoria.</strong> La pratica non è ancora stata accoppiata: questo
                      fascicolo è stato costruito adesso con i D.D.T. trovati finora e non esiste su disco.
                      Il file unico nasce quando confermi qui sotto.
                    </span>
                  </div>
                )}

                <div className="flex-grow-1 d-flex align-items-center justify-content-center" style={{ minHeight: 0 }}>
                  {caricamento && (
                    <div className="text-center text-secondary">
                      <div className="spinner-border text-info mb-3" role="status" />
                      <div className="small">Costruzione del fascicolo dall’XML…</div>
                    </div>
                  )}

                  {!caricamento && errorePdf && (
                    <div className="text-center text-danger px-4">
                      <FileWarning size={32} className="mb-2" />
                      <div className="small">{errorePdf}</div>
                    </div>
                  )}

                  {!caricamento && pdfUrl && (
                    <iframe
                      src={`${pdfUrl}#toolbar=0&navpanes=0`}
                      className="w-100 h-100 border-0"
                      title="Fascicolo fattura"
                    />
                  )}
                </div>
              </div>

              {/* Destra: i dati letti dall'XML e gli abbinamenti */}
              <div className="col-lg-5 h-100 d-flex flex-column bg-dark">
                <div className="p-2 border-bottom border-secondary text-center small fw-bold text-secondary text-uppercase">
                  Dati della fattura elettronica
                </div>

                <div className="flex-grow-1 overflow-auto p-4">
                  <div className="alert bg-info bg-opacity-10 border border-info border-opacity-25 text-light small d-flex gap-2 py-2">
                    <Info size={16} className="text-info flex-shrink-0 mt-1" />
                    <span>
                      {forma.spiegazione} I campi arrivano dall’XML firmato e non si correggono da qui:
                      quando un abbinamento non torna, l’errore è quasi sempre nella lettura del D.D.T.
                    </span>
                  </div>

                  <div className="row">
                    <div className="col-6">{campo('Numero', dati.numero_fattura, true)}</div>
                    <div className="col-6">{campo('Data', dati.data_fattura, true)}</div>
                  </div>

                  {campo('Fornitore (cedente)', dati.fornitore)}

                  <div className="row">
                    <div className="col-6">{campo('P.IVA cedente', dati.partita_iva, true)}</div>
                    <div className="col-6">{campo('Tipo documento', dati.tipo_documento, true)}</div>
                  </div>

                  {campo('Cliente (cessionario)', dati.cessionario)}
                  {campo('Importo totale', formattaImporto(dati.importo_totale), true)}

                  {/* Anomalie sul cedente rilevate al caricamento. Non hanno
                      impedito l'archiviazione — dal 2026-09-08 il fornitore non
                      filtra piu' niente — ma restano scritte sulla pratica,
                      perche' una P.IVA che non torna e' l'unica chiave esatta
                      fra i due lati del sistema, ed e' qui che si guarda. */}
                  {(fattura.segnalazioni || []).length > 0 && (
                    <div className="alert bg-warning bg-opacity-10 border border-warning border-opacity-25 text-light small d-flex gap-2 py-2">
                      <AlertTriangle size={16} className="text-warning flex-shrink-0 mt-1" />
                      <div>
                        <strong className="d-block mb-1">Da controllare in anagrafica</strong>
                        {(fattura.segnalazioni || []).map((s, i) => (
                          <div key={i}>{s.messaggio}</div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Abbinamenti ai D.D.T. */}
                  <hr className="border-secondary my-4" />

                  {daFirmare && (() => {
                    const colore = daAbbinare ? 'primary' : (completa ? 'success' : 'warning');
                    const testo = daAbbinare
                      ? 'La fattura è stata letta e archiviata, ma i suoi D.D.T. non sono ancora stati cercati. Premi Abbina qui sotto: il confronto non scrive niente nell’archivio, propone soltanto.'
                      : (completa
                        ? 'Tutti i D.D.T. citati sono stati trovati. Controllali qui sotto e conferma: il file unico fattura + D.D.T. verrà salvato nella cartella ACCOPPIATE.'
                        : 'L’abbinamento non è completo. Puoi cercare di nuovo (i D.D.T. arrivati nel frattempo verranno agganciati) oppure confermare così com’è: nel file unico finiranno solo i documenti trovati.');

                    return (
                      <div className={`alert bg-${colore} bg-opacity-10 border border-${colore} border-opacity-25 text-light small d-flex gap-2 py-2 mb-0`}>
                        <Link2 size={16} className={`text-${colore} flex-shrink-0 mt-1`} />
                        <span>{testo}</span>
                      </div>
                    );
                  })()}

                  <div className="d-flex justify-content-between align-items-center mb-3">
                    <h6 className="fw-bold text-light mb-0">Documenti di trasporto</h6>
                    {totali > 0 && (
                      daAbbinare
                        ? <span className="badge bg-primary text-white">{totali} da cercare</span>
                        : (
                          <span className={`badge ${abbinati === totali ? 'bg-success' : 'bg-warning text-dark'}`}>
                            {abbinati} di {totali} agganciati
                          </span>
                        )
                    )}
                  </div>

                  {righe.length === 0 && (
                    <div className="text-secondary small fst-italic">
                      La fattura non cita nessun documento di trasporto.
                    </div>
                  )}

                  {righe.map((riga, indice) => {
                    const esito = esitoRiga(riga.esito);

                    return (
                      <div
                        key={`${riga.numero_ddt}-${indice}`}
                        className={`card bg-black border-${esito.colore} border-opacity-50 mb-3`}
                      >
                        <div className="card-body p-3">
                          <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
                            <div>
                              <div className="font-monospace fw-bold text-light">
                                {riga.numero_ddt || '(senza numero)'}
                              </div>
                              <div className="text-secondary" style={{ fontSize: '0.78rem' }}>
                                {riga.data_ddt ? `del ${riga.data_ddt}` : 'senza data'}
                                {riga.origine === 'numero_fattura' && ' · numero della fattura stessa'}
                              </div>
                            </div>
                            <span className={`badge rounded-pill ${esito.badge} flex-shrink-0`}>
                              {esito.etichetta}
                            </span>
                          </div>

                          <div className="text-secondary small mb-2">{riga.motivo}</div>

                          {riga.documento_id && (
                            <div className="bg-dark rounded p-2 mb-2 small">
                              <div className="text-secondary" style={{ fontSize: '0.75rem' }}>
                                D.D.T. archiviato ({riga.stato_ddt})
                              </div>
                              <div className="text-light">
                                <span className="font-monospace fw-bold">{riga.numero_ddt_letto || '—'}</span>
                                {riga.data_ddt_letta && <span className="font-monospace"> · {riga.data_ddt_letta}</span>}
                              </div>
                              <div className="text-secondary">{riga.fornitore_letto}</div>
                              {riga.gia_abbinato && (
                                <div className="text-warning" style={{ fontSize: '0.75rem' }}>
                                  Già citato dalla fattura {riga.gia_abbinato}
                                </div>
                              )}
                            </div>
                          )}

                          {esito.azione && (
                            <div className={`text-${esito.colore} mb-2`} style={{ fontSize: '0.78rem' }}>
                              {esito.azione}
                            </div>
                          )}

                          {riga.documento_id && (
                            <button
                              className={`btn btn-sm btn-outline-${esito.colore} d-flex align-items-center gap-2`}
                              onClick={() => onApriDdt(riga.documento_id)}
                              title="Apri il D.D.T. nella sua sezione: salvando la correzione la coda viene ricontrollata da sola"
                            >
                              <ExternalLink size={14} /> Apri il D.D.T.
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="p-3 border-top border-secondary bg-dark d-flex justify-content-between align-items-center gap-2 flex-wrap">
                  <button
                    className="btn btn-outline-danger px-3 text-nowrap"
                    onClick={() => onElimina(fattura)}
                    disabled={occupato}
                    title="Elimina la fattura, il file unico e l'XML archiviato"
                  >
                    Elimina
                  </button>

                  <div className="d-flex align-items-center gap-2 flex-wrap">
                    {/* Su una pratica già firmata non si rifà nessun confronto:
                        il file unico è stato consegnato, e ricalcolarlo
                        significherebbe contraddire un documento che esiste. */}
                    {!daFirmare && (
                      <span className="text-success small d-flex align-items-center gap-1 me-2">
                        <Lock size={14} />
                        Accoppiata{fattura.completata ? ` il ${new Date(fattura.completata).toLocaleDateString('it-IT')}` : ''}
                      </span>
                    )}

                    {daFirmare && (
                      <button
                        className={`btn ${daAbbinare ? 'btn-primary px-4 fw-bold' : 'btn-outline-warning px-3'} text-nowrap d-flex align-items-center gap-2`}
                        onClick={() => onAccoppia(fattura)}
                        disabled={occupato}
                        title="Cerca i D.D.T. fra quelli archiviati adesso. Non scrive niente: propone soltanto."
                      >
                        {isAccoppiando
                          ? <span className="spinner-border spinner-border-sm" />
                          : <Link2 size={16} />}
                        {isAccoppiando ? 'Ricerca…' : (daAbbinare ? 'Abbina' : 'Cerca di nuovo i D.D.T.')}
                      </button>
                    )}

                    {/* Finche' nessuno ha chiesto il confronto non c'e' niente
                        da firmare: il pulsante compare dopo il primo Abbina. */}
                    {daFirmare && !daAbbinare && (
                      <button
                        className={`btn btn-${completa ? 'success' : 'warning'} px-4 fw-bold text-nowrap d-flex align-items-center gap-2`}
                        onClick={() => onConferma(fattura)}
                        disabled={occupato}
                        title="Salva il file unico fattura + D.D.T. nella cartella ACCOPPIATE e chiudi la pratica"
                      >
                        {isConfermando
                          ? <span className="spinner-border spinner-border-sm" />
                          : <Check size={16} />}
                        {isConfermando ? 'Salvataggio…' : 'Conferma accoppiamento'}
                      </button>
                    )}

                    <button className="btn btn-primary px-4 fw-bold text-nowrap" onClick={onClose} disabled={occupato}>
                      Chiudi
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
