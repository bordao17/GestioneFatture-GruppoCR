import React, { useRef, useState } from 'react';
import axios from 'axios';
import { Upload, PlayCircle, Loader2, Inbox } from 'lucide-react';

/**
 * I due pulsanti della cartella in ingresso: deposita i file, poi analizzali.
 *
 * Uno solo per D.D.T. e fatture, perché il gesto è identico e cambiano solo le
 * estensioni ammesse e i due endpoint. Le cartelle sono le stesse su cui lavora
 * la scansione pianificata (DDT/da_leggere e FATTURE/da_leggere): questi
 * pulsanti non aprono un secondo canale, fanno adesso ciò che di notte
 * succederebbe da solo.
 *
 * Caricare e analizzare restano DUE gesti: si mettono in coda dieci bolle in
 * pochi secondi e si fa partire l'analisi (minuti, sulla GPU condivisa) una
 * volta sola, guardando la barra di avanzamento.
 */
export default function BarraIngresso({
  apiUrl,
  tipo,               // 'ddt' | 'fatture'
  accept,
  etichettaCarica,
  etichettaAnalizza,
  descrizione,
  onFatto,            // (esito) => void, per ricaricare gli elenchi
  onErrore,
}) {
  const input = useRef(null);
  const [inCaricamento, setInCaricamento] = useState(false);
  const [inAnalisi, setInAnalisi] = useState(false);
  const [inAttesa, setInAttesa] = useState(null);   // quanti file aspettano
  const [ultimo, setUltimo] = useState(null);

  const carica = async (files) => {
    if (!files || files.length === 0) return;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append('files', f));

    setInCaricamento(true);
    setUltimo(null);
    try {
      const res = await axios.post(`${apiUrl}/api/${tipo}/carica`, form);
      setInAttesa(res.data.in_attesa);
      const scartati = res.data.scartati || [];
      setUltimo({
        tipo: scartati.length > 0 ? 'warning' : 'success',
        testo: `${res.data.caricati.length} file in coda`
          + (scartati.length > 0 ? ` — ${scartati.length} scartati (formato non ammesso)` : '')
          + '. Premi Analizza per elaborarli.',
      });
    } catch (err) {
      onErrore?.(err.response?.data?.detail || 'Caricamento non riuscito.');
    } finally {
      setInCaricamento(false);
      if (input.current) input.current.value = '';   // riselezionare lo stesso file deve funzionare
    }
  };

  const analizza = async () => {
    setInAnalisi(true);
    setUltimo(null);
    try {
      const res = await axios.post(`${apiUrl}/api/${tipo}/scansiona`);
      const falliti = res.data.falliti || [];
      // Le anomalie sul cedente non sono errori: la fattura e' stata archiviata
      // lo stesso (dal 2026-09-08 non si scarta piu' niente per il fornitore).
      // Vanno pero' dette qui, perche' e' il momento in cui qualcuno guarda.
      const segnalate = res.data.segnalate || [];
      // Le pagine gia' archiviate non sono un errore e non chiedono niente a
      // nessuno: si dicono perche' senza, i conteggi non tornerebbero con la
      // pila di fogli appena messa nello scanner.
      const duplicate = res.data.duplicati || [];
      const fatti = tipo === 'ddt'
        ? `${res.data.elaborati.length} documenti (${res.data.pagine_totali} pagine)`
        : `${res.data.totale} fatture`;

      setInAttesa(0);
      setUltimo({
        tipo: (falliti.length > 0 || segnalate.length > 0)
          ? 'warning'
          : (duplicate.length > 0 ? 'info' : 'success'),
        testo: `Analizzati ${fatti}`
          + (falliti.length > 0
            ? ` — ${falliti.length} non elaborati, restano in cartella: ${falliti.map((f) => f.file).join(', ')}`
            : '.')
          + (duplicate.length > 0
            ? ` ${duplicate.length} ${duplicate.length === 1 ? 'pagina già archiviata' : 'pagine già archiviate'}, `
              + 'saltate senza rileggerle.'
            : '')
          + (segnalate.length > 0
            ? ` ${segnalate.length} con anomalie sul fornitore (archiviate lo stesso): `
              + segnalate.map((s) => `${s.numero_fattura} — ${s.messaggi.join(' ')}`).join(' · ')
            : ''),
      });
      onFatto?.(res.data);
    } catch (err) {
      onErrore?.(err.response?.data?.detail || 'Analisi non riuscita.');
    } finally {
      setInAnalisi(false);
    }
  };

  const occupato = inCaricamento || inAnalisi;

  return (
    <div className="card shadow-sm mb-3">
      <div className="card-body py-3 d-flex flex-wrap align-items-center gap-3">
        <div className="d-flex align-items-center gap-2 text-body-secondary flex-grow-1">
          <Inbox size={18} />
          <small>{descrizione}</small>
        </div>

        <input
          ref={input}
          type="file"
          accept={accept}
          multiple
          className="d-none"
          onChange={(e) => carica(e.target.files)}
        />

        <button
          type="button"
          className="btn btn-outline-secondary d-flex align-items-center gap-2"
          onClick={() => input.current?.click()}
          disabled={occupato}
          title={`Copia i file nella cartella in ingresso, senza analizzarli`}
        >
          {inCaricamento ? <Loader2 size={18} className="fa-spin" /> : <Upload size={18} />}
          {etichettaCarica}
        </button>

        <button
          type="button"
          className="btn btn-primary d-flex align-items-center gap-2"
          onClick={analizza}
          disabled={occupato}
          title="Elabora tutti i file fermi nella cartella in ingresso"
        >
          {inAnalisi ? <Loader2 size={18} className="fa-spin" /> : <PlayCircle size={18} />}
          {inAnalisi ? 'Analisi in corso...' : etichettaAnalizza}
          {inAttesa > 0 && <span className="badge rounded-pill bg-white text-primary">{inAttesa}</span>}
        </button>
      </div>

      {ultimo && (
        <div className={`card-footer bg-transparent py-2 text-${ultimo.tipo}`}>
          <small>{ultimo.testo}</small>
        </div>
      )}
    </div>
  );
}
