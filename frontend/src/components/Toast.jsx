import React, { useEffect } from 'react';
import { X } from 'lucide-react';

/**
 * Avviso passeggero in basso a destra.
 *
 * Serve soprattutto a una cosa: dire che una correzione fatta su un D.D.T. ha
 * chiuso una fattura ferma in coda. È un effetto che avviene nel backend a ogni
 * salvataggio (il ricontrollo delle attese) e che senza questo avviso resterebbe
 * invisibile — la fattura sparirebbe dalla coda e basta, in un'altra sezione.
 */
export default function Toast({ avviso, onClose, durata = 8000 }) {
  useEffect(() => {
    if (!avviso) return undefined;
    const timer = setTimeout(onClose, durata);
    return () => clearTimeout(timer);
  }, [avviso, onClose, durata]);

  if (!avviso) return null;

  return (
    <div
      className="position-fixed bottom-0 end-0 p-4"
      style={{ zIndex: 2000, maxWidth: '480px' }}
    >
      <div className={`alert alert-${avviso.tipo || 'info'} shadow-lg border-0 d-flex justify-content-between align-items-start gap-3 mb-0`}>
        <div>
          {avviso.titolo && <div className="fw-bold mb-1">{avviso.titolo}</div>}
          <div className="small">{avviso.testo}</div>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-link text-reset p-0 flex-shrink-0"
          onClick={onClose}
          aria-label="Chiudi"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
