import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Upload, PlayCircle, Loader2, Inbox, CloudOff, RefreshCw, Store } from 'lucide-react';

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
 *
 * Sui soli D.D.T. la barra chiede anche PER QUALE PUNTO VENDITA e' la pila di
 * fogli: una scansione e' la posta di un negozio solo, e chi la mette nello
 * scanner lo sa gia'. Dichiarandolo, ragione_sociale_consegna e
 * indirizzo_consegna smettono di essere una lettura del modello e diventano un
 * dato certo. La scelta non si ricorda da un'analisi all'altra, ed e' voluto:
 * un punto vendita rimasto selezionato dalla volta prima scriverebbe in
 * silenzio la consegna sbagliata su tutte le bolle del batch nuovo.
 *
 * Sui soli D.D.T. la barra controlla anche che il motore AI risponda, e finche'
 * non risponde non lascia nemmeno premere Analizza. NON vale per le fatture, e
 * non e' una dimenticanza: il flusso fatture e' tutto Python e non chiama mai
 * il modello, quindi li' un Ollama spento non cambia niente — un avviso
 * sarebbe solo rumore che insegna a ignorare gli avvisi.
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
  controllaMotore = false,   // solo i D.D.T.: le fatture non passano dal modello
  puntiVendita = null,       // solo i D.D.T.: null = non si chiede niente
}) {
  const input = useRef(null);
  const [inCaricamento, setInCaricamento] = useState(false);
  const [inAnalisi, setInAnalisi] = useState(false);
  const [inAttesa, setInAttesa] = useState(null);   // quanti file aspettano
  const [ultimo, setUltimo] = useState(null);
  // null = non lo sappiamo (endpoint irraggiungibile, backend vecchio): in quel
  // caso non si avvisa e non si blocca niente. Si blocca solo quando sappiamo
  // POSITIVAMENTE che il motore e' giu' — un controllo rotto non deve poter
  // impedire un lavoro che funzionerebbe.
  const [motore, setMotore] = useState(null);
  const [inVerifica, setInVerifica] = useState(false);
  // '' = non ancora scelto (Analizza resta bloccato), 'NESSUNO' = scelto di
  // proposito di non dichiararlo. Sono due cose diverse: la prima e' una
  // domanda senza risposta, la seconda una risposta.
  const [puntoVendita, setPuntoVendita] = useState('');

  const chiedePuntoVendita = Array.isArray(puntiVendita) && puntiVendita.length > 0;

  const verificaMotore = useCallback(async () => {
    if (!controllaMotore) return null;
    setInVerifica(true);
    try {
      const res = await axios.get(`${apiUrl}/api/motore`);
      setMotore(res.data);
      return res.data;
    } catch {
      setMotore(null);
      return null;
    } finally {
      setInVerifica(false);
    }
  }, [apiUrl, controllaMotore]);

  // Al montaggio, cosi' l'avviso c'e' gia' quando si arriva sulla sezione:
  // scoprire che la GPU e' spenta DOPO aver caricato dieci bolle e premuto
  // Analizza e' esattamente il giro che questo controllo serve a evitare.
  useEffect(() => { verificaMotore(); }, [verificaMotore]);

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
    // Il controllo al montaggio puo' avere minuti: la GPU e' condivisa e nel
    // frattempo qualcuno puo' averla spenta. Si richiede adesso, che costa
    // millisecondi contro i minuti che sta per impegnare. Il backend lo rifa'
    // comunque (503) — questo serve a non far partire il giro per niente.
    const stato = await verificaMotore();
    if (stato && !stato.pronto) {
      setUltimo({ tipo: 'danger', testo: stato.motivo });
      return;
    }

    setInAnalisi(true);
    setUltimo(null);
    try {
      const res = await axios.post(`${apiUrl}/api/${tipo}/scansiona`,
        chiedePuntoVendita && puntoVendita && puntoVendita !== 'NESSUNO'
          ? { punto_vendita: puntoVendita }
          : {});
      const falliti = res.data.falliti || [];
      // Le anomalie sul cedente non sono errori: la fattura e' stata archiviata
      // lo stesso (dal 2026-09-08 non si scarta piu' niente per il fornitore).
      // Vanno pero' dette qui, perche' e' il momento in cui qualcuno guarda.
      const segnalate = res.data.segnalate || [];
      // Le pagine gia' archiviate non sono un errore e non chiedono niente a
      // nessuno: si dicono perche' senza, i conteggi non tornerebbero con la
      // pila di fogli appena messa nello scanner.
      const duplicate = res.data.duplicati || [];
      // La discordanza sul punto vendita si dice QUI prima ancora che nella
      // tabella: e' l'unico momento in cui chi ha scelto il negozio nel menu
      // qui accanto e' ancora davanti allo schermo, e la sua ha senso contarla
      // sul batch — una pagina su venti e' un foglio di un'altra pila, venti su
      // venti sono venti bolle attribuite al negozio sbagliato.
      const discordanze = res.data.discordanze || [];
      const fatti = tipo === 'ddt'
        ? `${res.data.elaborati.length} documenti (${res.data.pagine_totali} pagine)`
        : `${res.data.totale} fatture`;
      // Si riscrive il punto vendita che il backend dice di aver applicato, non
      // quello scelto qui: e' l'unico modo di accorgersi che un codice non e'
      // stato trovato in anagrafica e la consegna non e' stata scritta.
      const pv = res.data.punto_vendita;

      setInAttesa(0);
      setUltimo({
        tipo: (falliti.length > 0 || segnalate.length > 0 || discordanze.length > 0)
          ? 'warning'
          : (duplicate.length > 0 ? 'info' : 'success'),
        testo: `Analizzati ${fatti}`
          + (pv ? ` per ${pv.dipendenza}` : '')
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
            : '')
          + (discordanze.length > 0
            ? ` ${discordanze.length} ${discordanze.length === 1 ? 'pagina parla' : 'pagine parlano'}`
              + ` di un altro punto vendita (${[...new Set(discordanze.map((d) => d.nome))].join(', ')}):`
              + ' sono in DA VERIFICARE, controlla di non aver scelto il negozio sbagliato.'
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
  const motoreGiu = motore !== null && !motore.pronto;
  const senzaPuntoVendita = chiedePuntoVendita && !puntoVendita;

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

        {chiedePuntoVendita && (
          <div className="d-flex align-items-center gap-2">
            <Store size={18} className="text-body-secondary flex-shrink-0" />
            <select
              className="form-select form-select-sm"
              style={{ minWidth: '15rem' }}
              value={puntoVendita}
              onChange={(e) => setPuntoVendita(e.target.value)}
              disabled={occupato}
              title="Il negozio a cui appartiene questa pila di fogli: ne riempie
                     la ragione sociale e l'indirizzo di consegna"
            >
              <option value="">Per quale punto vendita?</option>
              {puntiVendita.map((pv) => (
                <option key={pv.codice} value={pv.codice}>
                  {pv.dipendenza} — {pv.citta}
                </option>
              ))}
              {/* Una pila mista si analizza lo stesso, ma dicendolo: senza
                  questa voce l'unica via d'uscita sarebbe lasciare il menu
                  vuoto, che e' la stessa cosa che fa chi si e' distratto. */}
              <option value="NESSUNO">— Non dichiararlo (pila mista) —</option>
            </select>
          </div>
        )}

        <button
          type="button"
          className="btn btn-outline-secondary d-flex align-items-center gap-2"
          onClick={() => input.current?.click()}
          disabled={occupato}
          title={`Copia i file nella cartella in ingresso, senza analizzarli`}
        >
          {inCaricamento ? <Loader2 size={18} className="gira" /> : <Upload size={18} />}
          {etichettaCarica}
        </button>

        <button
          type="button"
          className="btn btn-primary d-flex align-items-center gap-2"
          onClick={analizza}
          disabled={occupato || motoreGiu || senzaPuntoVendita}
          title={motoreGiu
            ? motore.motivo
            : senzaPuntoVendita
              ? 'Scegli prima il punto vendita di questa scansione'
              : 'Elabora tutti i file fermi nella cartella in ingresso'}
        >
          {inAnalisi ? <Loader2 size={18} className="gira" /> : <PlayCircle size={18} />}
          {inAnalisi ? 'Analisi in corso...' : etichettaAnalizza}
          {inAttesa > 0 && <span className="badge rounded-pill bg-white text-primary">{inAttesa}</span>}
        </button>
      </div>

      {motoreGiu && (
        <div className="card-footer bg-transparent py-2 d-flex flex-wrap align-items-center gap-2">
          <CloudOff size={16} className="text-danger flex-shrink-0" />
          <small className="text-danger flex-grow-1">
            <strong>Motore AI non raggiungibile.</strong> {motore.motivo}
            {' '}I file caricati restano in coda: nessuno viene perso, l'analisi riparte da qui
            quando il motore torna su.
          </small>
          <button
            type="button"
            className="btn btn-sm btn-outline-danger d-flex align-items-center gap-1"
            onClick={verificaMotore}
            disabled={inVerifica}
            title="Ricontrolla adesso se il motore risponde"
          >
            <RefreshCw size={14} className={inVerifica ? 'gira' : undefined} />
            Ricontrolla
          </button>
        </div>
      )}

      {ultimo && (
        <div className={`card-footer bg-transparent py-2 text-${ultimo.tipo}`}>
          <small>{ultimo.testo}</small>
        </div>
      )}
    </div>
  );
}
