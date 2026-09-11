import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AlarmClock, Mail, Play, Send, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

/**
 * I tre lavori che partono da soli, e lo stato dell'invio mail.
 *
 * È la faccia visibile di quello che fino al 2026-09-09 era n8n: tre nodi
 * Schedule su un'altra porta, con un'altra interfaccia e un altro login. Gli
 * orari si impostano nei campi qui sotto (sono impostazioni come le altre);
 * questo pannello serve a rispondere alle due domande che i campi non possono:
 * **quando toccherà la prossima volta** e **com'è andata l'ultima**.
 *
 * I due pulsanti esistono per la stessa ragione: un lavoro notturno che non
 * funziona non lo scopre nessuno fino al mattino dopo. "Esegui adesso" passa
 * dalla stessa strada dell'esecuzione pianificata — se funziona a mano,
 * funzionerà di notte per le stesse ragioni.
 */

const QUANDO = new Intl.DateTimeFormat('it-IT', {
  weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});

const quando = (iso) => (iso ? QUANDO.format(new Date(iso)) : null);

export default function PannelloLavori({ apiUrl, versione = 0, onFatto, onAvviso }) {
  const [stato, setStato] = useState(null);
  const [inCorso, setInCorso] = useState(null);   // chiave del lavoro lanciato a mano
  const [prova, setProva] = useState(false);

  const carica = useCallback(async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/pianificazione`);
      setStato(res.data);
      return res.data;
    } catch (err) {
      setStato(null);
      return null;
    }
  }, [apiUrl]);

  // Si ricarica anche quando cambia `versione`, cioè dopo un salvataggio della
  // configurazione: toccato un orario, "prossima esecuzione" è già un'altra.
  useEffect(() => { carica(); }, [carica, versione]);

  // Polling solo mentre qualcosa gira: una scansione D.D.T. lanciata da qui
  // dura minuti, e nel frattempo il pannello deve dire che sta lavorando.
  useEffect(() => {
    if (!stato?.lavori?.some((l) => l.in_corso)) return undefined;
    const timer = setInterval(carica, 3000);
    return () => clearInterval(timer);
  }, [stato, carica]);

  const esegui = async (lavoro) => {
    setInCorso(lavoro.chiave);
    try {
      // Nessun timeout: una scansione di venti bolle sulla GPU condivisa può
      // durare parecchi minuti, e interromperla qui non la fermerebbe comunque.
      const res = await axios.post(`${apiUrl}/api/pianificazione/${lavoro.chiave}/esegui`, null, { timeout: 0 });
      onAvviso?.({ tipo: 'success', testo: `${lavoro.etichetta}: ${res.data.esito}` });
      onFatto?.(lavoro.chiave);
    } catch (err) {
      onAvviso?.({ tipo: 'danger', testo: err.response?.data?.detail || `${lavoro.etichetta} non riuscito.` });
    } finally {
      setInCorso(null);
      carica();
    }
  };

  const inviaProva = async () => {
    setProva(true);
    try {
      const res = await axios.post(`${apiUrl}/api/notifiche/prova`);
      onAvviso?.({ tipo: 'success', testo: `Mail di prova inviata a ${(res.data.destinatari || []).join(', ')}.` });
    } catch (err) {
      onAvviso?.({ tipo: 'danger', testo: err.response?.data?.detail || 'Invio non riuscito.' });
    } finally {
      setProva(false);
    }
  };

  if (!stato) return null;

  const notifiche = stato.notifiche || {};

  return (
    <div className="card shadow-sm mb-4">
      <div className="card-header d-flex justify-content-between align-items-center py-3 flex-wrap gap-2">
        <h6 className="mb-0 text-body d-flex align-items-center gap-2">
          <AlarmClock size={18} className="text-warning" /> Lavori automatici
          {!stato.attivo && <span className="badge bg-danger">pianificatore fermo</span>}
        </h6>
        <button
          className="btn btn-sm btn-outline-info d-flex align-items-center gap-2"
          onClick={inviaProva}
          disabled={prova || !notifiche.configurata}
          title={notifiche.configurata
            ? 'Manda una mail ai destinatari configurati'
            : 'Servono almeno il server SMTP e un destinatario'}
        >
          <Send size={15} /> {prova ? 'Invio…' : 'Invia mail di prova'}
        </button>
      </div>

      <div className="card-body">
        <div className="d-flex align-items-start gap-2 mb-3 small text-body-secondary">
          <Mail size={16} className="flex-shrink-0 mt-1" />
          {notifiche.configurata ? (
            <span>
              Le mail partono da <span className="text-body">{notifiche.mittente || '—'}</span> via{' '}
              <span className="text-body">{notifiche.server}:{notifiche.porta}</span> ({notifiche.sicurezza}) e
              arrivano a <span className="text-body">{(notifiche.destinatari || []).join(', ')}</span>.
            </span>
          ) : (
            <span>
              Nessuna mail configurata: i lavori girano lo stesso, ma nessuno riceve il riepilogo.
              Compila <code className="text-body-secondary">SMTP_HOST</code> e{' '}
              <code className="text-body-secondary">MAIL_DESTINATARI</code> qui sotto.
            </span>
          )}
        </div>

        {stato.lavori.map((lavoro) => {
          const attivo = lavoro.in_corso || inCorso === lavoro.chiave;

          return (
            <div className="row align-items-center py-2 border-top border-opacity-25" key={lavoro.chiave}>
              <div className="col-lg-4">
                <div className="text-body fw-semibold">{lavoro.etichetta}</div>
                {lavoro.orario ? (
                  <small className="text-body-secondary">
                    ogni giorno alle <span className="text-warning">{lavoro.orario}</span>
                    {lavoro.prossima && <> &bull; poi {quando(lavoro.prossima)}</>}
                  </small>
                ) : (
                  <small className="text-body-secondary">
                    non pianificato &mdash; scrivi un orario in{' '}
                    <code className="text-body-secondary">{lavoro.impostazione}</code>
                  </small>
                )}
              </div>

              <div className="col-lg-5">
                {attivo ? (
                  <small className="text-info d-flex align-items-center gap-2">
                    <Loader2 size={14} className="spinner-border-sm" /> in corso…
                  </small>
                ) : lavoro.ultima ? (
                  <small className={lavoro.errore ? 'text-danger' : 'text-body-secondary'}>
                    {lavoro.errore
                      ? <XCircle size={14} className="me-1" />
                      : <CheckCircle2 size={14} className="me-1 text-success" />}
                    {quando(lavoro.ultima)} &bull; {lavoro.esito} ({lavoro.durata}s)
                  </small>
                ) : (
                  <small className="text-body-secondary">mai eseguito da quando il backend è acceso</small>
                )}
              </div>

              <div className="col-lg-3 text-lg-end">
                <button
                  className="btn btn-sm btn-outline-warning d-flex align-items-center gap-2 ms-lg-auto"
                  onClick={() => esegui(lavoro)}
                  disabled={attivo || inCorso !== null}
                  title="Esegue subito, come farebbe all'ora prevista"
                >
                  <Play size={14} /> Esegui adesso
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
