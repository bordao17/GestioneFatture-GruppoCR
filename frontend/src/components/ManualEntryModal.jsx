import React, { useState } from 'react';
import { FilePlus, Upload, X } from 'lucide-react';

const CAMPI_VUOTI = {
  fornitore: '',
  numero_ddt: '',
  data_ddt: '',
  ragione_sociale_consegna: '',
  indirizzo_consegna: ''
};

const FORMATI_AMMESSI = ['pdf', 'jpg', 'jpeg', 'png'];

export default function ManualEntryModal({ show, onClose, onSaved, apiUrl }) {
  const [dati, setDati] = useState(CAMPI_VUOTI);
  const [file, setFile] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [errore, setErrore] = useState(null);

  if (!show) return null;

  // I 4 campi che determinano lo stato del documento (vedi classificatore.py):
  // se manca anche solo uno, il documento finisce tra quelli da verificare.
  const campiCompleti = dati.fornitore && dati.numero_ddt && dati.data_ddt && dati.indirizzo_consegna;
  const puoSalvare = file && campiCompleti && !isSaving;

  const chiudi = () => {
    setDati(CAMPI_VUOTI);
    setFile(null);
    setErrore(null);
    onClose();
  };

  const handleFile = (e) => {
    const scelto = e.target.files[0];
    if (!scelto) return;

    const estensione = scelto.name.split('.').pop().toLowerCase();
    if (!FORMATI_AMMESSI.includes(estensione)) {
      setErrore('Formato non supportato: carica un PDF o un\'immagine (JPG, PNG).');
      setFile(null);
      return;
    }

    setErrore(null);
    setFile(scelto);
  };

  const handleSalva = async () => {
    setIsSaving(true);
    setErrore(null);

    try {
      const payload = new FormData();
      payload.append('file', file);
      Object.entries(dati).forEach(([campo, valore]) => payload.append(campo, valore));

      const risposta = await fetch(`${apiUrl}/api/documents/manuale`, {
        method: 'POST',
        body: payload
      });

      if (!risposta.ok) {
        const dettaglio = await risposta.json().catch(() => ({}));
        throw new Error(dettaglio.detail || 'Salvataggio non riuscito.');
      }

      chiudi();
      onSaved();
    } catch (err) {
      console.error('Errore inserimento manuale:', err);
      setErrore(err.message || 'Impossibile contattare il server.');
    } finally {
      setIsSaving(false);
    }
  };

  const campoTesto = (nome, etichetta, opzioni = {}) => (
    <>
      <label className="form-label small fw-bold text-secondary">
        {etichetta}
        {opzioni.facoltativo && <span className="text-muted fw-normal"> (facoltativo)</span>}
      </label>
      <input
        type="text"
        className="form-control bg-dark text-light border-secondary"
        value={dati[nome]}
        placeholder={opzioni.placeholder}
        onChange={(e) => setDati({ ...dati, [nome]: e.target.value })}
      />
    </>
  );

  return (
    <div className="modal show d-block" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }} tabIndex="-1">
      <div className="modal-dialog modal-lg modal-dialog-centered modal-dialog-scrollable">
        <div className="modal-content bg-dark text-light border-secondary shadow-lg">

          <div className="modal-header border-secondary py-3">
            <div className="d-flex align-items-center gap-2">
              <FilePlus size={22} className="text-success" />
              <div>
                <h5 className="modal-title fw-bold mb-0">Aggiunta Manuale</h5>
                <small className="text-secondary">
                  Allega il documento e trascrivi i dati: l'AI non viene interpellata.
                </small>
              </div>
            </div>
            <button type="button" className="btn-close btn-close-white" onClick={chiudi}></button>
          </div>

          <div className="modal-body p-4">
            {errore && (
              <div className="alert alert-danger bg-danger bg-opacity-10 border-danger text-danger small">
                {errore}
              </div>
            )}

            {/* Allegato */}
            <div className="mb-4">
              <label className="form-label small fw-bold text-secondary">Documento da allegare</label>
              <div className="d-flex align-items-center gap-3">
                <label className="btn btn-outline-info d-flex align-items-center gap-2 mb-0">
                  <Upload size={18} />
                  {file ? 'Cambia file' : 'Scegli file'}
                  <input
                    type="file"
                    className="d-none"
                    accept=".pdf,.jpg,.jpeg,.png"
                    onChange={handleFile}
                  />
                </label>

                {file ? (
                  <span className="d-flex align-items-center gap-2 text-light small">
                    <span className="text-truncate" style={{ maxWidth: '320px' }}>{file.name}</span>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-secondary border-0 p-1 d-flex"
                      onClick={() => setFile(null)}
                      title="Togli il file"
                    >
                      <X size={14} />
                    </button>
                  </span>
                ) : (
                  <span className="text-secondary small">Nessun file selezionato (PDF, JPG o PNG)</span>
                )}
              </div>
            </div>

            <hr className="border-secondary" />

            {/* Dati del documento */}
            <div className="mb-3">
              {campoTesto('fornitore', 'Fornitore')}
            </div>

            <div className="row mb-3">
              <div className="col-6">
                {campoTesto('numero_ddt', 'Numero D.D.T.')}
              </div>
              <div className="col-6">
                {campoTesto('data_ddt', 'Data D.D.T.', { placeholder: 'GG-MM-AAAA' })}
              </div>
            </div>

            <div className="mb-3">
              {campoTesto('ragione_sociale_consegna', 'Ragione Sociale Consegna', { facoltativo: true })}
            </div>

            <div className="mb-2">
              <label className="form-label small fw-bold text-secondary">Indirizzo di Consegna</label>
              <textarea
                rows="2"
                className="form-control bg-dark text-light border-secondary"
                value={dati.indirizzo_consegna}
                onChange={(e) => setDati({ ...dati, indirizzo_consegna: e.target.value })}
              />
            </div>

            {!campiCompleti && (
              <small className="text-secondary">
                Fornitore, numero, data e indirizzo di consegna servono per archiviare
                il documento come completato.
              </small>
            )}
          </div>

          <div className="p-3 border-top border-secondary text-end">
            <button className="btn btn-outline-secondary me-2 px-4" onClick={chiudi} disabled={isSaving}>
              Annulla
            </button>
            <button className="btn btn-success px-4 fw-bold" onClick={handleSalva} disabled={!puoSalvare}>
              {isSaving ? 'Salvataggio...' : 'Salva Documento'}
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}
