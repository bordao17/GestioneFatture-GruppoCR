import React, { useEffect, useState } from 'react';
import { FileText, PanelLeftClose, PanelLeftOpen, Sun, Moon } from 'lucide-react';
import { SEZIONI } from './sezioni';

// La navigazione del gestionale: una colonna a sinistra, richiudibile.
//
// Era una navbar in alto, che e' la forma giusta per un sito e quella sbagliata
// per un gestionale: le sezioni sono quattro e cresceranno (ogni anagrafica
// nuova e' una voce), e in orizzontale ogni voce in piu' toglie spazio ai
// pulsanti globali finche' non si comincia a nasconderli dietro i breakpoint.
// In verticale una voce in piu' costa 40 px di una colonna che e' gia' alta
// quanto lo schermo, e le tabelle — che sono il contenuto vero — ci guadagnano
// l'altezza che la navbar si prendeva.
//
// Lo stato aperta/chiusa vive QUI e non in App.jsx: e' l'unica cosa in questo
// componente che non riguarda nessun altro (la larghezza la gestisce il flex,
// quindi il contenuto non ha bisogno di saperlo). Si ricorda fra una sessione e
// l'altra perche' chi lavora su un portatile la tiene chiusa sempre, e
// ritrovarla aperta a ogni apertura sarebbe un gesto da rifare ogni giorno.
const CHIAVE_BARRA = 'gestionale-barra-aperta';

function statoIniziale() {
  try {
    return localStorage.getItem(CHIAVE_BARRA) !== 'no';
  } catch {
    return true;
  }
}

export default function Sidebar({ vista, onVista, badge = {}, tema, onCambiaTema }) {
  const [aperta, setAperta] = useState(statoIniziale);

  useEffect(() => {
    try {
      localStorage.setItem(CHIAVE_BARRA, aperta ? 'si' : 'no');
    } catch {
      // Preferenza persa alla chiusura: la barra funziona lo stesso.
    }
  }, [aperta]);

  const scura = tema === 'dark';

  return (
    <aside className={`barra-laterale bg-body-tertiary border-end ${aperta ? '' : 'ridotta'}`}>

      {/* 1. Marchio e pulsante per richiudere */}
      <div className="d-flex align-items-center gap-2 px-3 py-3 border-bottom">
        
        {/* Nota: ho tolto "bg-primary text-white" se il tuo logo ha già i suoi colori o è trasparente. 
            Se invece il tuo logo è bianco e vuoi il quadratino blu dietro, rimettili! */}
        <div className="marchio d-flex align-items-center justify-content-center flex-shrink-0">
          <img 
            src="/logo.png" 
            alt="Logo Gestionale" 
            style={{ width: '45px', height: '45px', objectFit: 'contain' }} 
          />
        </div>

        <div className="solo-estesa flex-grow-1 lh-sm">
          <div className="fw-semibold small">Gestione D.D.T.</div>
          <div className="text-body-secondary" style={{ fontSize: '0.72rem' }}>&amp; Fatture elettroniche</div>
        </div>
        <button
          type="button"
          className="btn btn-sm btn-link text-body-secondary p-1 solo-estesa flex-shrink-0"
          onClick={() => setAperta(false)}
          title="Riduci il menu"
          aria-label="Riduci il menu"
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* 2. Le sezioni */}
      <nav className="flex-grow-1 overflow-y-auto overflow-x-hidden p-2">
        <ul className="nav flex-column gap-1 mb-0">
          {SEZIONI.map(({ id, etichetta, icona: Icona, titolo }) => {
            const attiva = vista === id;
            const daFare = badge[id] || 0;

            return (
              <li className="nav-item" key={id}>
                <button
                  type="button"
                  className={`voce-menu ${attiva ? 'attiva' : ''}`}
                  onClick={() => onVista(id)}
                  // Con la barra ridotta il title e' l'unica etichetta rimasta,
                  // quindi porta il nome della sezione oltre alla descrizione.
                  title={aperta ? titolo : `${etichetta} — ${titolo}`}
                  aria-current={attiva ? 'page' : undefined}
                >
                  <Icona size={20} className="flex-shrink-0" />
                  <span className="etichetta-menu flex-grow-1 text-truncate">{etichetta}</span>
                  {daFare > 0 && (
                    <span
                      className={`badge rounded-pill ${attiva ? 'bg-white text-primary' : 'bg-warning text-dark'}`}
                      title="Righe che aspettano un intervento"
                    >
                      {daFare}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* 3. In fondo: tema, riapertura e firma */}
      <div className="border-top p-2 d-flex flex-column gap-1">
        <button
          type="button"
          className="voce-menu"
          onClick={onCambiaTema}
          title={scura ? 'Passa al tema chiaro' : 'Passa al tema scuro'}
        >
          {scura ? <Sun size={20} className="flex-shrink-0" /> : <Moon size={20} className="flex-shrink-0" />}
          <span className="etichetta-menu flex-grow-1 text-truncate">
            {scura ? 'Tema chiaro' : 'Tema scuro'}
          </span>
        </button>

        {/* Il pulsante per riaprire c'e' SOLO da ridotta: da aperta sta in cima
            accanto al marchio, dove ci si aspetta di trovarlo. */}
        {!aperta && (
          <button
            type="button"
            className="voce-menu"
            onClick={() => setAperta(true)}
            title="Espandi il menu"
            aria-label="Espandi il menu"
          >
            <PanelLeftOpen size={20} className="flex-shrink-0" />
            <span className="etichetta-menu flex-grow-1 text-truncate">Espandi</span>
          </button>
        )}

        <div className="solo-estesa text-body-secondary px-2 pt-2 pb-1" style={{ fontSize: '0.82rem' }}>
          Author: Lorenzo Bordi
        </div>
      </div>
    </aside>
  );
}
