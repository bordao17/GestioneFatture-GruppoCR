import React, { useMemo, useState } from 'react';
import { Download, Sparkles, Receipt, KeyRound, Check, Lock, BookUser } from 'lucide-react';
import { STATI_DDT, ORDINE_STATI, infoStato } from './etichetteDdt';
import SelettoreFornitore from './SelettoreFornitore';

export default function ComparisonModal({ selectedDoc, editData, setEditData, onClose, onSave, isSaving, onReanalyze, isReanalyzing, onCambiaStato, isCambiandoStato, onConfermaPiva, isConfermandoPiva, apiUrl, onApriFattura }) {
  const [isDownloading, setIsDownloading] = useState(false);
  // Il selettore dell'anagrafica: un secondo modale sopra questo, aperto solo
  // su richiesta. Non si apre da solo nemmeno a campo vuoto — chi rivede il
  // documento sta guardando il PDF, e un pannello che compare da se' gli
  // coprirebbe proprio quello.
  const [selettoreAperto, setSelettoreAperto] = useState(false);

  // Il cache-buster va calcolato SOLO al cambio di documento (o dopo una
  // rianalisi, che riscrive il PDF). Calcolato nel corpo del componente
  // cambiava a ogni render: con il polling di /api/elaborazione ogni 2 secondi
  // l'iframe si ricaricava di continuo mentre si rivedeva il documento.
  // useMemo sta prima del return anticipato: gli hook non possono essere
  // condizionali.
  const idDocumento = selectedDoc?.id;
  const timestampRianalisi = selectedDoc?.rianalisi;
  const pdfUrlWithCache = useMemo(
    () => `${apiUrl}/api/pdf/${idDocumento}.pdf?t=${Date.now()}#toolbar=0&navpanes=0`,
    [apiUrl, idDocumento, timestampRianalisi]
  );

  if (!selectedDoc) return null;

  const pdfUrl = `${apiUrl}/api/pdf/${selectedDoc.id}.pdf`;

  // Lo stato della P.IVA non sta sul documento ma in anagrafica: lo calcola il
  // backend in lettura (annota_stato_piva). Una volta confermata la chiave e'
  // decisa e qui il campo si blocca: si conferma UNA volta, con il PDF a
  // fianco, poi si corregge solo dall'anagrafica.
  const pivaConfermata = selectedDoc.partita_iva_confermata === true;

  // Funzione che scarica il file bypassando le restrizioni
  const handleDownloadPDF = async () => {
    try {
      setIsDownloading(true);
      const response = await fetch(pdfUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      
      // 1. Recuperiamo Fornitore e Data (usiamo "Ignoto" se il campo è vuoto)
      let nomeFornitore = editData.fornitore || 'FornitoreIgnoto';
      let dataDocumento = editData.data_ddt || 'DataIgnota';

      // 2. Puliamo le stringhe da caratteri illegali per i file di Windows/Mac e sostituiamo gli spazi con underscore
      nomeFornitore = nomeFornitore.replace(/[\/\\:*?"<>|]/g, '').replace(/\s+/g, '_');
      dataDocumento = dataDocumento.replace(/[\/\\:*?"<>|]/g, '-').replace(/\s+/g, '_');

      // 3. Creiamo il nome finale. Il prefisso e' DDT_ e non Fattura_: adesso
      //    esistono anche i fascicoli veri delle fatture elettroniche, e due
      //    file "Fattura_ROSSI_..." che sono cose diverse finirebbero nella
      //    stessa cartella.
      const nomeFileFinale = `DDT_${nomeFornitore}_${dataDocumento}.pdf`;
      
      const link = document.createElement('a');
      link.href = url;
      link.download = nomeFileFinale;
      document.body.appendChild(link);
      link.click();
      
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Errore durante il download del PDF:", error);
      alert("Impossibile scaricare il file in questo momento.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="modal show d-block" style={{ backgroundColor: 'rgba(0,0,0,0.7)' }} tabIndex="-1">
      <div className="modal-dialog modal-xl modal-dialog-centered modal-fullscreen-lg-down">
        <div className="modal-content shadow-lg" style={{ height: '90vh' }}>
          
          <div className="modal-header py-3">
            <div>
              <h5 className="modal-title fw-bold">Validazione Documento</h5>
              <small className="text-body-secondary">
                File: {selectedDoc.file_origine}
              </small>
            </div>
            <button type="button" className="btn-close btn-close-white" onClick={onClose}></button>
          </div>
          
          <div className="modal-body p-0 overflow-hidden">
            <div className="row g-0 h-100">
              
              {/* Sinistra: Anteprima PDF */}
              <div className="col-lg-7 h-100 bg-body-secondary border-end d-flex flex-column">
                
                {/* Header del PDF con il bottone di download */}
                <div className="p-2 border-bottom d-flex justify-content-between align-items-center bg-body-tertiary">
                  <span className="small fw-bold text-body-secondary text-uppercase ps-2">
                    Documento Scansionato
                  </span>
                  <button 
                    className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-2" 
                    onClick={handleDownloadPDF}
                    disabled={isDownloading}
                    title="Scarica il file PDF rinominato"
                  >
                    <Download size={16} /> 
                    {isDownloading ? 'Scaricamento...' : 'Scarica PDF'}
                  </button>
                </div>
                
                <div className="flex-grow-1" style={{ minHeight: 0 }}>
                  <iframe 
                    src={pdfUrlWithCache} 
                    className="w-100 h-100 border-0"
                    title="Anteprima PDF"
                  />
                </div>
              </div>

              {/* Destra: Form Dati */}
              <div className="col-lg-5 h-100 d-flex flex-column bg-body-tertiary">
                <div className="p-2 border-bottom text-center small fw-bold text-body-secondary text-uppercase">
                  Dati Estratti
                </div>
                
                <div className="flex-grow-1 overflow-auto p-4">
                  {/* Un D.D.T. non cambia stato quando finisce in un fascicolo:
                      resta dov'era, e senza questa riga niente direbbe che una
                      fattura lo cita gia'. Correggerne il numero adesso rifa'
                      partire l'abbinamento, quindi vale la pena saperlo. */}
                  {selectedDoc.fattura?.numero_fattura && (
                    <div className="alert bg-success bg-opacity-10 border border-success border-opacity-25 text-body small d-flex justify-content-between align-items-center gap-2 py-2 mb-4">
                      <span>
                        Agganciato alla fattura <strong>{selectedDoc.fattura.numero_fattura}</strong>
                        {selectedDoc.fattura.data_fattura && ` del ${selectedDoc.fattura.data_fattura}`}
                      </span>
                      <button
                        className="btn btn-sm btn-outline-success d-flex align-items-center gap-1 flex-shrink-0"
                        onClick={() => onApriFattura?.(selectedDoc.fattura.id_fattura)}
                      >
                        <Receipt size={14} /> Fascicolo
                      </button>
                    </div>
                  )}

                  {selectedDoc.status === 'KO' && (
                    <div className="alert alert-danger bg-danger bg-opacity-10 border-danger text-danger small mb-4">
                      <strong>Estrazione Fallita:</strong> Compila manualmente i dati guardando il PDF.
                    </div>
                  )}

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-body-secondary">Fornitore</label>
                    <div className="input-group">
                      <input
                        type="text"
                        className={`form-control ${!editData.fornitore ? 'border-warning' : ''}`}
                        value={editData.fornitore || ''}
                        onChange={(e) => setEditData({...editData, fornitore: e.target.value})}
                      />
                      {/* Battuto a mano, il nome e' un campo come un altro; preso
                          dall'anagrafica e' la chiave con cui la fattura
                          ritrovera' questa bolla. Il pulsante c'e' sempre, anche
                          a campo pieno: serve anche a sostituire un nome letto
                          male con quello canonico. */}
                      <button
                        type="button"
                        className={`btn ${editData.fornitore ? 'btn-outline-secondary' : 'btn-warning'} d-flex align-items-center gap-1 text-nowrap`}
                        onClick={() => setSelettoreAperto(true)}
                        disabled={isSaving || isReanalyzing}
                        title="Scegli il fornitore dall'anagrafica: ne riporta il nome esatto e la partita IVA"
                      >
                        <BookUser size={15} /> Anagrafica
                      </button>
                    </div>
                    {/* Senza questa riga il campo sembrerebbe semplicemente non
                        letto, e chi rivede cercherebbe sul PDF un nome che il
                        modello aveva trovato eccome: solo che era il cliente. */}
                    {/* Il nome sul PDF e quello nel campo possono non
                        coincidere: se il fornitore e riconosciuto in anagrafica
                        vince il nome principale, perche e quello con cui le
                        fatture lo cercano. Senza questa riga sembrerebbe una
                        lettura sbagliata. */}
                    {editData.fornitore_letto && (
                      <div className="form-text text-info" style={{ fontSize: '0.75rem' }}>
                        Sul documento c&apos;&egrave; scritto <code>{editData.fornitore_letto}</code>:
                        riconosciuto in anagrafica, tenuto il nome principale.
                      </div>
                    )}
                    {editData.fornitore_scartato && (
                      <div className="form-text text-warning" style={{ fontSize: '0.75rem' }}>
                        Il modello aveva letto <code>{editData.fornitore_scartato}</code>, marcato in
                        anagrafica come <strong>mai un fornitore</strong> (cliente, gruppo d&apos;acquisto
                        o vettore): scritto qui il nome di chi emette la bolla.
                      </div>
                    )}
                    {!editData.fornitore && (
                      <div className="form-text text-warning" style={{ fontSize: '0.75rem' }}>
                        Senza fornitore la bolla resta in CHECK e nessuna fattura può agganciarla.
                        Se non riesci a leggerlo sul PDF ma sai di chi è, prendilo da
                        <strong> Anagrafica</strong>: scrive il nome esatto, quello con cui le fatture
                        lo cercano, e porta dietro la partita IVA.
                      </div>
                    )}
                  </div>
                  
                  {/* La P.IVA e' la chiave che lega il D.D.T. alla fattura, ed
                      e' l'unico campo verificabile da solo (11 cifre con
                      carattere di controllo). Il modello la legge solo per i
                      fornitori che non ce l'hanno ancora: qui, con il PDF a
                      fianco, si controlla e si conferma una volta per tutte —
                      da quel momento la mette l'anagrafica e nessuno la
                      rilegge piu'. */}
                  <div className="mb-3">
                    <label className="form-label small fw-bold text-body-secondary">Partita IVA fornitore</label>
                    {pivaConfermata ? (
                      <>
                        <div className="input-group">
                          <input
                            type="text"
                            className="form-control text-body-secondary font-monospace"
                            value={editData.partita_iva || selectedDoc.partita_iva_anagrafica || ''}
                            readOnly
                            disabled
                          />
                          <span className="input-group-text bg-success bg-opacity-25 border-success text-success d-flex align-items-center gap-1">
                            <Lock size={14} /> Confermata
                          </span>
                        </div>
                        <div className="form-text text-body-secondary" style={{ fontSize: '0.75rem' }}>
                          Già confermata in anagrafica per <strong>{editData.fornitore || 'questo fornitore'}</strong>:
                          da qui non si tocca più. Si corregge dalla sezione <strong>Fornitori</strong>.
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="input-group">
                          <input
                            type="text"
                            className="form-control font-monospace"
                            value={editData.partita_iva || ''}
                            onChange={(e) => setEditData({...editData, partita_iva: e.target.value.replace(/\D/g, '')})}
                            placeholder="11 cifre"
                            maxLength={11}
                          />
                          <button
                            type="button"
                            className="btn btn-outline-primary d-flex align-items-center gap-1"
                            onClick={() => onConfermaPiva?.(editData.partita_iva)}
                            disabled={!/^\d{11}$/.test(editData.partita_iva || '') || isConfermandoPiva || isSaving || isReanalyzing}
                            title="Salva questa partita IVA in anagrafica come confermata: dai prossimi D.D.T. verrà usata questa"
                          >
                            {isConfermandoPiva ? <span className="spinner-border spinner-border-sm" /> : <><KeyRound size={15} /> <Check size={15} /></>}
                            Conferma
                          </button>
                        </div>
                        <div className="form-text text-info" style={{ fontSize: '0.75rem' }}>
                          Letta dal documento e ancora da confermare: controllala sul PDF qui a fianco,
                          correggila se sbagliata, poi conferma. È l'unica volta che serve farlo.
                        </div>
                      </>
                    )}
                    {editData.partita_iva_scartata && (
                      <div className="form-text text-warning" style={{ fontSize: '0.75rem' }}>
                        Sul documento il modello aveva letto <code>{editData.partita_iva_scartata}</code>:
                        scartata perché è di un&apos;altra azienda — o l&apos;anagrafica ne ha già una
                        confermata per questo fornitore, o quel numero risulta di qualcun altro
                        (spesso è la P.IVA del cliente, stampata sulla bolla accanto a quella giusta).
                      </div>
                    )}
                  </div>

                  <div className="row mb-3">
                    <div className="col-6">
                      <label className="form-label small fw-bold text-body-secondary">Numero D.D.T.</label>
                      <input
                        type="text"
                        className="form-control"
                        value={editData.numero_ddt || ''}
                        onChange={(e) => setEditData({...editData, numero_ddt: e.target.value})}
                      />
                    </div>
                    <div className="col-6">
                      <label className="form-label small fw-bold text-body-secondary">Data D.D.T.</label>
                      <input
                        type="text"
                        className="form-control"
                        value={editData.data_ddt || ''}
                        onChange={(e) => setEditData({...editData, data_ddt: e.target.value})}
                        placeholder="GG-MM-AAAA"
                      />
                    </div>
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-body-secondary">Ragione Sociale Consegna</label>
                    <input
                      type="text"
                      className="form-control"
                      value={editData.ragione_sociale_consegna || ''}
                      onChange={(e) => setEditData({...editData, ragione_sociale_consegna: e.target.value})}
                    />
                  </div>

                  <div className="mb-3">
                    <label className="form-label small fw-bold text-body-secondary">Indirizzo di Consegna</label>
                    <textarea
                      rows="3"
                      className="form-control"
                      value={editData.indirizzo_consegna || ''}
                      onChange={(e) => setEditData({...editData, indirizzo_consegna: e.target.value})}
                    />
                  </div>
                </div>

                <div className="p-3 border-top bg-body-tertiary d-flex flex-column gap-3">
                  {/* Lo stato lo calcola determina_stato() contando i campi
                      letti, ma solo chi guarda il PDF sa se il documento vale
                      qualcosa: una bolla con tutti i campi pieni ma sbagliati
                      resta OK, un retro bianco non ha modo di finire in errore.
                      Da qui si scavalca la classificazione. */}
                  <div>
                    <label className="form-label small fw-bold text-body-secondary">Stato del documento</label>
                    <div className="btn-group w-100" role="group" aria-label="Stato del documento">
                      {ORDINE_STATI.map((stato) => {
                        const info = STATI_DDT[stato];
                        const attivo = selectedDoc.status === stato;
                        return (
                          <button
                            key={stato}
                            type="button"
                            className={`btn btn-sm ${attivo ? `btn-${info.colore} fw-bold` : `btn-outline-${info.colore}`}`}
                            onClick={() => !attivo && onCambiaStato?.(stato)}
                            disabled={isCambiandoStato || isReanalyzing || isSaving}
                            aria-pressed={attivo}
                            title={info.spiegazione}
                          >
                            {info.etichetta}
                          </button>
                        );
                      })}
                    </div>
                    <div className="form-text text-body-secondary">
                      {isCambiandoStato
                        ? 'Spostamento in corso...'
                        : selectedDoc.stato_manuale
                          ? `Stato impostato a mano il ${new Date(selectedDoc.stato_manuale).toLocaleString('it-IT')}: lo sposta subito, i dati restano questi.`
                          : `Attualmente ${infoStato(selectedDoc.status).etichetta.toLowerCase()} per il classificatore. Spostarlo non modifica i dati estratti.`}
                    </div>
                  </div>

                  <button
                    className="btn btn-outline-info w-100 d-flex align-items-center justify-content-center gap-2"
                    onClick={onReanalyze}
                    disabled={isReanalyzing || isSaving || isCambiandoStato}
                    title="Rimanda il PDF al modello AI e sostituisci i dati con la nuova lettura"
                  >
                    {isReanalyzing
                      ? <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                      : <Sparkles size={16} />}
                    {isReanalyzing ? 'Rianalisi in corso...' : 'Rianalizza con AI'}
                  </button>

                  <div className="d-flex justify-content-end align-items-center gap-2">
                    <button className="btn btn-outline-secondary px-4 text-nowrap" onClick={onClose} disabled={isReanalyzing || isCambiandoStato}>
                      Annulla
                    </button>
                    <button className="btn btn-primary px-4 fw-bold text-nowrap" onClick={onSave} disabled={isSaving || isReanalyzing || isCambiandoStato}>
                      {isSaving ? 'Salvataggio...' : 'Salva e Approva'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Il selettore sta DENTRO questo modale, sopra di esso: chiudendolo si
          torna al documento con il PDF ancora a fianco, che e' il punto —
          quello che si sceglie qui va controllato li'. La scelta riempie solo
          la bozza, come ogni altra correzione: si salva con "Salva e Approva". */}
      {selettoreAperto && (
        <SelettoreFornitore
          apiUrl={apiUrl}
          onClose={() => setSelettoreAperto(false)}
          onScegli={({ nome, partita_iva }) => {
            setEditData({
              ...editData,
              fornitore: nome,
              // La P.IVA si riporta solo se l'anagrafica ce l'ha: scrivere ""
              // cancellerebbe un numero che il modello aveva letto bene, e un
              // campo svuotato in silenzio e' peggio di un campo da riempire.
              ...(partita_iva ? { partita_iva } : {}),
            });
            setSelettoreAperto(false);
          }}
        />
      )}
    </div>
  );
}