import React from 'react';
import { FileSearch, Trash2, Clock, Link2, Loader } from 'lucide-react';
import { statoPratica, azionePratica, tipoAbbinamento, formattaImporto, conteggioDdt } from './etichetteFatture';

/**
 * Elenco delle fatture elettroniche, chiuse e in coda insieme.
 *
 * I due registri (FATTURE.json e ATTESA.json) sono file separati lato backend,
 * ma per chi lavora sono un elenco solo: lo stato è già dentro la voce, come
 * per i D.D.T.
 */
export default function InvoiceTable({ fatture, onApri, onElimina, onAccoppia, idInAccoppiamento }) {
  const campoMancante = <span className="text-warning fst-italic">Mancante</span>;

  return (
    <div className="table-responsive">
      <table className="table table-striped table-hover align-middle mb-0">
        <thead className="table-secondary">
          <tr>
            <th className="px-4 py-3 border-0">Ricevuta il</th>
            <th className="py-3 border-0">N. Fattura</th>
            <th className="py-3 border-0">Data</th>
            <th className="py-3 border-0">Fornitore</th>
            <th className="py-3 border-0">Forma</th>
            <th className="py-3 border-0">Stato</th>
            <th className="py-3 border-0" title="D.D.T. agganciati con certezza sul totale citato dalla fattura">
              D.D.T.
            </th>
            <th className="py-3 border-0 text-end">Importo</th>
            <th className="px-4 py-3 text-end border-0">Azioni</th>
          </tr>
        </thead>
        <tbody className="border-top-0">
          {fatture.length === 0 ? (
            <tr>
              <td colSpan="9" className="text-center py-5 text-body-secondary">
                Nessuna fattura in questa categoria.
              </td>
            </tr>
          ) : (
            fatture.map((fattura) => {
              const dati = fattura.dati || {};
              const stato = statoPratica(fattura);
              // Due pulsanti diversi sulla stessa colonna: ABBINA cerca i
              // D.D.T. e non scrive niente, ACCOPPIA firma e crea il file
              // unico. Chiamarli allo stesso modo farebbe sembrare
              // irreversibile anche il primo.
              const azione = azionePratica(fattura);
              const inCorso = idInAccoppiamento === fattura.id;
              const forma = tipoAbbinamento(fattura.tipo_abbinamento);
              const { totali, abbinati, daConfermare, mancanti } = conteggioDdt(fattura);

              return (
                <tr key={fattura.id}>
                  <td className="px-4 text-body small text-nowrap">
                    {fattura.timestamp ? new Date(fattura.timestamp).toLocaleString('it-IT') : '—'}
                    {fattura.giorni_attesa > 0 && (
                      <span
                        className="badge bg-warning text-dark ms-2"
                        title="Giorni da cui questa pratica è ferma in coda"
                      >
                        <Clock size={11} className="me-1" />
                        {fattura.giorni_attesa}g
                      </span>
                    )}
                  </td>

                  <td className="font-monospace text-white fw-bold">
                    {dati.numero_fattura || campoMancante}
                  </td>

                  <td className="font-monospace text-white text-nowrap">{dati.data_fattura || '—'}</td>

                  <td className="text-white fw-medium">
                    {dati.fornitore || campoMancante}
                    {dati.partita_iva && (
                      <div className="text-body-secondary font-monospace" style={{ fontSize: '0.75rem' }}>
                        P.IVA {dati.partita_iva}
                      </div>
                    )}
                  </td>

                  <td>
                    <span className={`badge rounded-pill ${forma.badge}`} title={forma.spiegazione}>
                      {forma.etichetta}
                    </span>
                  </td>

                  <td>
                    <span className={`badge rounded-pill ${stato.badge}`} title={stato.spiegazione}>
                      {stato.etichetta}
                    </span>
                  </td>

                  <td className="text-nowrap">
                    {totali === 0 ? (
                      <span className="text-body-secondary small">nessuno</span>
                    ) : (
                      <>
                        <span className={`font-monospace fw-bold ${abbinati === totali ? 'text-success' : 'text-warning'}`}>
                          {abbinati}/{totali}
                        </span>
                        {daConfermare > 0 && (
                          <span className="badge bg-info text-dark ms-2" title="Trovati ma da confermare a mano">
                            {daConfermare} da confermare
                          </span>
                        )}
                        {mancanti > 0 && (
                          <span className="badge bg-danger ms-2" title="Nessun D.D.T. archiviato con questo numero">
                            {mancanti} mancant{mancanti === 1 ? 'e' : 'i'}
                          </span>
                        )}
                      </>
                    )}
                  </td>

                  <td className="text-end font-monospace text-white text-nowrap">
                    {formattaImporto(dati.importo_totale) || '—'}
                  </td>

                  <td className="px-4 text-end text-nowrap">
                    {/* Nessun pulsante sulle pratiche già firmate: il file
                        unico esiste, e rifare il confronto contraddirebbe un
                        documento consegnato. */}
                    {azione && (
                      <button
                        className={`btn btn-sm me-2 shadow-sm fw-bold ${azione === 'abbina' ? 'btn-primary' : 'btn-warning'}`}
                        onClick={() => onAccoppia(fattura)}
                        disabled={inCorso}
                        title={azione === 'abbina'
                          ? 'Cerca fra i D.D.T. archiviati quelli citati da questa fattura. Non scrive niente: mostra il risultato.'
                          : 'I D.D.T. sono stati trovati: apri e conferma per creare il file unico in ACCOPPIATE'}
                      >
                        {inCorso
                          ? <Loader size={16} className="me-1 spinner-border-sm" />
                          : <Link2 size={16} className="me-1" />}
                        {azione === 'abbina' ? 'ABBINA' : 'ACCOPPIA'}
                      </button>
                    )}
                    <button
                      className="btn btn-sm btn-outline-info me-2 shadow-sm"
                      onClick={() => onApri(fattura)}
                      title="Apri il fascicolo PDF e il dettaglio degli abbinamenti"
                    >
                      <FileSearch size={16} className="me-1" /> Apri
                    </button>
                    <button
                      className="btn btn-sm btn-outline-danger shadow-sm"
                      onClick={() => onElimina(fattura)}
                      title="Elimina la fattura, il fascicolo e l'XML archiviato"
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
