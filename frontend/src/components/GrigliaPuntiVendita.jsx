import React, { useMemo, useState } from 'react';
import { Store, ChevronDown, ChevronRight, Truck, FileText, HelpCircle, Inbox } from 'lucide-react';
import { infoStato } from './etichetteDdt';

/**
 * Le bolle appena lette, disposte come sarebbero su una scrivania: una cartella
 * per punto vendita, e dentro ogni cartella un mazzetto per fornitore.
 *
 * Serve DOPO una scansione, ed è un modo di guardare diverso da quello della
 * tabella: la tabella risponde a "com'è andata la lettura" (è divisa per
 * OK/CHECK/KO), questa risponde a "cosa è arrivato e da chi", che è la domanda
 * di chi la merce l'ha ricevuta. Le due convivono senza sostituirsi.
 *
 * SI DISEGNA DAI DOCUMENTI, NON DALL'ANAGRAFICA. Un punto vendita senza bolle
 * non compare: una griglia di trentuno cartelle di cui ventotto vuote
 * costringerebbe a cercare le tre che contano, ed è esattamente il contrario
 * del motivo per cui esiste. Per la stessa ragione l'anagrafica serve solo a
 * scrivere per esteso il nome di un codice.
 *
 * I documenti arrivano da App.jsx già pronti: nessun fetch qui dentro, come per
 * il resto della sezione.
 *
 * LE CARTELLE NASCONO CHIUSE (dal 2026-09-15, secondo giro). Con trenta negozi
 * aperti tutti insieme la griglia tornava a essere un elenco lungo quanto la
 * tabella: qui dentro si guarda un negozio alla volta, e chiusa la cartella
 * dice comunque le due cose per cui la si guarda — quante bolle e com'è andata
 * la lettura. Fa eccezione la cartella UNICA, che si apre da sola: una
 * scansione è la posta di un solo punto vendita, e chiedere un click per
 * aprire l'unica cosa presente sarebbe un click per niente. Senza `h-100` sulla
 * card, aprirne una non allunga a vuoto le altre due della stessa riga.
 *
 * Dal 2026-09-15 non è più un pannello richiudibile in fondo alla pagina ma il
 * contenuto della card della tabella, al posto di quella, quando si preme il
 * pulsante in fondo ai tre tab: due modi di guardare lo stesso elenco vanno
 * alternati, non impilati uno sotto l'altro — sotto la paginazione della
 * tabella nessuno scorreva, e la griglia sembrava un secondo archivio.
 */

// I documenti archiviati prima del 2026-09-14 non hanno nessun punto vendita, e
// non è un errore da nascondere: sono la maggioranza dell'archivio e vanno
// guardati come gli altri. La cartella è una sola, e sta in fondo.
const NON_DICHIARATO = '__nessuno__';

export default function GrigliaPuntiVendita({ documents, puntiVendita = [], onEdit }) {
  // Quale cartella (punto vendita) è aperta, e dentro quella quale mazzetto
  // (fornitore): uno alla volta, perché aprirne cinque riempirebbe lo schermo
  // di righe e toglierebbe alla griglia il colpo d'occhio che è la sua unica
  // ragione di esistere. Chiusa, la cartella dice comunque quanto contiene e
  // com'è andata la lettura: sono i due numeri per cui la si guarda.
  const [cartellaAperta, setCartellaAperta] = useState(null);
  const [mazzetto, setMazzetto] = useState(null);

  // Il nome per esteso di un codice punto vendita. Il documento porta già
  // punto_vendita_nome, ma un negozio può essere stato rinominato dopo:
  // l'anagrafica è la versione di oggi e vince, il nome sul documento resta il
  // ripiego per quando il codice non c'è più in anagrafica.
  const nomiPerCodice = useMemo(() => {
    const mappa = {};
    puntiVendita.forEach((pv) => { mappa[pv.codice] = pv; });
    return mappa;
  }, [puntiVendita]);

  const cartelle = useMemo(() => {
    const perPuntoVendita = new Map();

    documents.forEach((doc) => {
      const dati = doc.dati || {};
      const codice = dati.punto_vendita || NON_DICHIARATO;

      if (!perPuntoVendita.has(codice)) {
        perPuntoVendita.set(codice, { codice, documenti: [], fornitori: new Map() });
      }
      const cartella = perPuntoVendita.get(codice);
      cartella.documenti.push(doc);

      // Un KO non ha nemmeno il fornitore letto: raggrupparli sotto la stringa
      // vuota li renderebbe indistinguibili da un fornitore senza nome.
      const fornitore = (dati.fornitore || '').trim() || 'Fornitore non letto';
      if (!cartella.fornitori.has(fornitore)) cartella.fornitori.set(fornitore, []);
      cartella.fornitori.get(fornitore).push(doc);
    });

    return Array.from(perPuntoVendita.values())
      .map((cartella) => {
        const anagrafica = nomiPerCodice[cartella.codice];
        const daiDocumenti = cartella.documenti[0]?.dati?.punto_vendita_nome;
        return {
          ...cartella,
          nome: cartella.codice === NON_DICHIARATO
            ? 'Senza punto vendita'
            : (anagrafica?.dipendenza || daiDocumenti || `Codice ${cartella.codice}`),
          citta: anagrafica?.citta || '',
          societa: anagrafica?.ragione_sociale || '',
          fornitori: Array.from(cartella.fornitori.entries())
            .map(([nome, docs]) => ({ nome, docs }))
            // Prima chi ha consegnato di più: in una cartella con venti
            // fornitori è l'ordine in cui si guarda davvero.
            .sort((a, b) => b.docs.length - a.docs.length || a.nome.localeCompare(b.nome, 'it')),
        };
      })
      .sort((a, b) => {
        // I non dichiarati in fondo: sono un residuo storico, non una cartella
        // di lavoro, e in cima ruberebbero il posto a quelle che contano.
        if (a.codice === NON_DICHIARATO) return 1;
        if (b.codice === NON_DICHIARATO) return -1;
        return a.nome.localeCompare(b.nome, 'it');
      });
  }, [documents, nomiPerCodice]);

  // Una scansione e' la posta di UN punto vendita: quando la cartella e' una
  // sola, chiederle un click per aprirla sarebbe un click per niente. Derivata
  // e non salvata nello stato, cosi' non serve nessun effetto che la rincorra.
  const aperta = cartellaAperta ?? (cartelle.length === 1 ? cartelle[0].codice : null);

  const apriChiudi = (codice) => {
    setCartellaAperta(aperta === codice ? '' : codice);
    setMazzetto(null);  // il mazzetto di una cartella chiusa non vuol dire niente
  };

  const conteggi = (docs) => {
    const per = { OK: 0, CHECK: 0, KO: 0 };
    docs.forEach((d) => { if (per[d.status] !== undefined) per[d.status] += 1; });
    return per;
  };

  // Qui la griglia e' stata CHIESTA da chi ha premuto il pulsante: un
  // componente che non rende niente sembrerebbe un pulsante rotto. Finche'
  // stava in fondo alla pagina il null era giusto, adesso no.
  if (cartelle.length === 0) {
    return (
      <div className="text-center text-body-secondary py-5">
        <Inbox size={32} className="mb-2" />
        <div>Nessun documento da raccogliere: con questa ricerca non c'e' niente da mostrare.</div>
      </div>
    );
  }

  return (
    <>
      <div className="d-flex align-items-center gap-2 mb-3">
        <Store size={18} className="text-body-secondary" />
        <span className="fw-bold text-body">Per punto vendita</span>
        <span className="badge rounded-pill bg-body-secondary text-body">
          {cartelle.length} {cartelle.length === 1 ? 'cartella' : 'cartelle'}
        </span>
        <small className="text-body-secondary ms-auto">
          Le stesse bolle della tabella, raccolte per negozio e per fornitore.
        </small>
      </div>

      <div className="row row-cols-1 row-cols-md-2 row-cols-xxl-3 g-3">
        {cartelle.map((cartella) => {
          const per = conteggi(cartella.documenti);
          const nonDichiarata = cartella.codice === NON_DICHIARATO;
          const espansa = aperta === cartella.codice;

          return (
            <div className="col" key={cartella.codice}>
              <div className={`card ${nonDichiarata ? 'border-secondary border-opacity-50' : ''}`}>
                {/* Tutta l'intestazione e' il pulsante che apre la cartella: un
                    bersaglio grande, perche' e' il gesto principale di questa
                    vista. I fornitori restano chiusi finche' non si chiede
                    ESPRESSAMENTE questo negozio — trenta cartelle aperte tutte
                    insieme sono un elenco lungo quanto la tabella, cioe' il
                    contrario del colpo d'occhio per cui la griglia esiste. */}
                <button
                  type="button"
                  className="card-body pb-2 text-start w-100 border-0 bg-transparent"
                  onClick={() => apriChiudi(cartella.codice)}
                  aria-expanded={espansa}
                  title={espansa ? 'Chiudi la cartella' : 'Apri la cartella e vedi i fornitori'}
                >
                  <div className="d-flex align-items-start gap-2 mb-1">
                    {espansa
                      ? <ChevronDown size={18} className="text-body-secondary flex-shrink-0 mt-1" />
                      : <ChevronRight size={18} className="text-body-secondary flex-shrink-0 mt-1" />}
                    {nonDichiarata
                      ? <HelpCircle size={18} className="text-body-secondary flex-shrink-0 mt-1" />
                      : <Store size={18} className="text-primary flex-shrink-0 mt-1" />}
                    <div className="flex-grow-1">
                      <div className="fw-bold text-body">{cartella.nome}</div>
                      <small className="text-body-secondary">
                        {nonDichiarata
                          ? 'Scansionate senza dichiarare il negozio'
                          : [cartella.societa, cartella.citta].filter(Boolean).join(' · ')}
                      </small>
                    </div>
                    <span className="badge rounded-pill bg-primary">{cartella.documenti.length}</span>
                  </div>

                  <div className="d-flex flex-wrap align-items-center gap-1 mb-2">
                    {['OK', 'CHECK', 'KO'].filter((s) => per[s] > 0).map((s) => (
                      <span key={s} className={`badge ${infoStato(s).badge}`}>
                        {per[s]} {infoStato(s).etichetta}
                      </span>
                    ))}
                    {/* Chiusa, la cartella deve dire quanto c'e' dentro:
                        altrimenti aprirla e' l'unico modo di sapere se vale
                        la pena aprirla. */}
                    <small className="text-body-secondary ms-auto d-inline-flex align-items-center gap-1">
                      <Truck size={12} />
                      {cartella.fornitori.length}
                      {cartella.fornitori.length === 1 ? ' fornitore' : ' fornitori'}
                    </small>
                  </div>
                </button>

                {espansa && (
                <ul className="list-group list-group-flush">
                  {cartella.fornitori.map((f) => {
                    const chiave = `${cartella.codice}|${f.nome}`;
                    const espanso = mazzetto === chiave;
                    return (
                      <li className="list-group-item px-3 py-2 bg-transparent" key={chiave}>
                        <button
                          type="button"
                          className="btn btn-link p-0 text-decoration-none d-flex align-items-center gap-2 w-100 text-start"
                          onClick={() => setMazzetto(espanso ? null : chiave)}
                        >
                          {espanso ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <Truck size={14} className="text-body-secondary flex-shrink-0" />
                          <span className="small text-body flex-grow-1 text-truncate">{f.nome}</span>
                          <span className="badge rounded-pill bg-body-secondary text-body">
                            {f.docs.length}
                          </span>
                        </button>

                        {espanso && (
                          <div className="mt-2 ps-4 d-flex flex-column gap-1">
                            {f.docs.map((doc) => (
                              <button
                                type="button"
                                key={doc.id}
                                className="btn btn-sm btn-outline-secondary d-flex align-items-center gap-2 text-start"
                                onClick={() => onEdit?.(doc)}
                                title="Apri il documento"
                              >
                                <FileText size={13} className="flex-shrink-0" />
                                <span className="flex-grow-1 text-truncate">
                                  {doc.dati?.numero_ddt || 'senza numero'}
                                  {doc.dati?.data_ddt ? ` · ${doc.dati.data_ddt}` : ''}
                                </span>
                                <span className={`badge ${infoStato(doc.status).badge}`}>
                                  {doc.status}
                                </span>
                              </button>
                            ))}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
