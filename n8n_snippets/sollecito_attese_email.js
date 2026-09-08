// ============================================================================
// Nodo Code (n8n) - Mail di sollecito di CIO' CHE E' FERMO
// Va posizionato dopo i due HTTP Request in catena:
//   GET /api/fatture/attese      (fatture a cui manca una bolla)
//   GET /api/ddt/senza-fattura   (bolle a cui manca una fattura)
// I due nodi si leggono per nome, non dall'input: in n8n l'output dell'ultimo
// sostituisce quello del precedente.
// Modalita': "Run Once for All Items".
// Restituisce oggetto + corpo_html, cosi' nel nodo "Send Email":
//   Subject -> {{ $json.oggetto }}
//   HTML    -> {{ $json.corpo_html }}
//
// Copia versionata del nodo: l'originale vive dentro il database di n8n e da
// qui non e' leggibile. Se lo modifichi in n8n, riallinea anche questo file.
//
// PERCHE' QUESTO RAMO ESISTE. Tutto il resto dell'abbinamento e' guidato da
// eventi che il backend vede da solo (un DDT estratto, corretto, unito) e che
// fanno ripartire il ricontrollo senza n8n. "In attesa da piu' di 30 giorni"
// e' invece un trigger TEMPORALE: nessun evento del backend scatta al
// trentesimo giorno, e uno scheduler dentro FastAPI sarebbe un secondo
// orologio in una casa che ne ha gia' uno.
//
// Le soglie NON sono scritte qui: le decide il backend (sezione Configurazione,
// o docker-compose come ripiego). L'HTTP Request chiama /api/fatture/attese
// senza parametri, e la risposta ne porta DUE, perche' le attese non sono tutte
// uguali: GIORNI_ATTESA_SOLLECITO (30) per una fattura a cui manca una bolla
// che qualcuno deve andare a cercare in magazzino, GIORNI_ATTESA_ACCOPPIAMENTO
// (7, piu' corto) per una pratica che aspetta solo un click in dashboard.
//
// Se non c'e' niente da sollecitare il nodo restituisce ZERO item: cosi' il
// nodo Email successivo non parte e non arriva la mail "nessuna fattura in
// attesa", che dopo tre giorni verrebbe ignorata anche quando dice qualcosa.
// ============================================================================

const URL_DASHBOARD = 'http://localhost:3000';
const MAX_RIGHE = 30;

const esc = (v) => String(v ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const leggi = (nodo) => {
  try {
    return $(nodo).first()?.json || {};
  } catch (e) {
    return {}; // il ramo puo' girare anche senza il secondo nodo
  }
};

const risposta = leggi('Fatture In Attesa');
const risposta_ddt = leggi('DDT Senza Fattura');
const soglia = risposta.soglia_giorni ?? risposta.soglia_predefinita ?? 30;

// Le due code non si risolvono nello stesso modo, ed e' l'unica ragione per cui
// vale la pena leggere questa mail invece di aprire la dashboard:
//   - da_confermare: il DDT c'e' gia' in archivio ma con un numero diverso da
//     quello della fattura (una cifra letta male dal modello). Si chiude con un
//     click in dashboard, e ricontrollarla in automatico non servira' mai.
//   - attende_ddt: la bolla non e' ancora stata scansionata. Va cercata in
//     magazzino; quando arriva, la fattura si chiude da sola.
//   - ddt_orfani: il lato speculare, una bolla scansionata da un mese di cui
//     non e' mai arrivata la fattura (o e' arrivata da un fornitore non
//     mai caricata in FATTURE/da_leggere).
// - da_accoppiare: qui non manca NIENTE. La fattura e' in archivio e i suoi
//   DDT o sono gia' tutti agganciati o non sono ancora stati cercati: aspetta
//   solo che qualcuno prema ABBINA o ACCOPPIA. E' la coda piu' facile da
//   dimenticare, proprio perche' non ha bisogno di nessun documento nuovo, e
//   ha una soglia sua piu' corta.
const da_confermare = risposta.da_confermare || [];
const attende_ddt = risposta.attende_ddt || [];
const da_accoppiare = risposta.da_accoppiare || [];
const ddt_orfani = risposta_ddt.ddt || [];
const soglia_click = risposta.soglia_accoppiamento ?? soglia;
const totale = da_confermare.length + attende_ddt.length;

if (totale === 0 && ddt_orfani.length === 0 && da_accoppiare.length === 0) {
  return [];
}

const riga = (fattura, colore) => {
  const dati = fattura.dati || {};
  const attesa = fattura.attesa || {};
  const numeri = (attesa.da_confermare ? attesa.numeri_da_confermare : attesa.numeri_mancanti) || [];

  return `
  <tr>
    <td style="padding:0 32px 10px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid ${colore}; background:#f9fafb;">
        <tr>
          <td style="padding:11px 14px;">
            <div style="font-size:14px; font-weight:700; color:#111827;">
              Fattura ${esc(dati.numero_fattura)} del ${esc(dati.data_fattura)}
            </div>
            <div style="font-size:12px; color:#6b7280; padding-bottom:6px;">
              ${esc(dati.fornitore)} &nbsp;&bull;&nbsp; ferma da <strong>${fattura.giorni_attesa}</strong> giorni
              &nbsp;&bull;&nbsp; ${attesa.abbinati || 0}/${(fattura.ddt || []).length} DDT trovati
            </div>
            <div style="font-size:13px; color:#111827;">
              DDT ${numeri.map((n) => `<strong>${esc(n)}</strong>`).join(', ') || '&mdash;'}
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>`;
};

const sezione = (titolo, spiegazione, voci, colore) => (voci.length ? `
  <tr>
    <td style="padding:6px 32px 4px 32px;" class="padding-laterale">
      <div style="font-size:12px; font-weight:700; color:#374151; text-transform:uppercase; letter-spacing:.5px;">${titolo} (${voci.length})</div>
      <div style="font-size:12px; color:#6b7280; padding:2px 0 8px 0;">${spiegazione}</div>
    </td>
  </tr>
  ${voci.slice(0, MAX_RIGHE).map((f) => riga(f, colore)).join('')}
  ${voci.length > MAX_RIGHE ? `
  <tr>
    <td style="padding:0 32px 10px 32px; font-size:12px; color:#6b7280;" class="padding-laterale">
      e altre ${voci.length - MAX_RIGHE}: aprirle dalla dashboard.
    </td>
  </tr>` : ''}` : '');

// Nessun numero di DDT da elencare: quello che manca e' il gesto, quindi la
// riga dice QUALE dei due pulsanti serve. "Abbina" non e' "Accoppia".
const riga_click = (fattura) => {
  const dati = fattura.dati || {};
  const da_abbinare = fattura.motivo_attesa === 'da_abbinare';
  const colore = da_abbinare ? '#2563eb' : '#0891b2';
  return `
  <tr>
    <td style="padding:0 32px 10px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid ${colore}; background:#f9fafb;">
        <tr>
          <td style="padding:11px 14px;">
            <div style="font-size:14px; font-weight:700; color:#111827;">
              Fattura ${esc(dati.numero_fattura)} del ${esc(dati.data_fattura)}
            </div>
            <div style="font-size:12px; color:#6b7280; padding-bottom:6px;">
              ${esc(dati.fornitore)} &nbsp;&bull;&nbsp; ferma da <strong>${fattura.giorni_attesa}</strong> giorni
            </div>
            <div style="font-size:13px; color:#111827;">
              ${da_abbinare
                ? 'I suoi D.D.T. non sono ancora stati cercati: premi <strong>ABBINA</strong> sulla riga.'
                : 'Tutti i D.D.T. sono stati trovati: premi <strong>ACCOPPIA</strong> per salvare il file unico.'}
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>`;
};

const sezione_click = (voci) => (voci.length ? `
  <tr>
    <td style="padding:6px 32px 4px 32px;" class="padding-laterale">
      <div style="font-size:12px; font-weight:700; color:#374151; text-transform:uppercase; letter-spacing:.5px;">Aspettano solo un click (${voci.length})</div>
      <div style="font-size:12px; color:#6b7280; padding:2px 0 8px 0;">Ferme da oltre ${soglia_click} giorni. Non manca nessun documento: bastano due clic in dashboard.</div>
    </td>
  </tr>
  ${voci.slice(0, MAX_RIGHE).map(riga_click).join('')}
  ${voci.length > MAX_RIGHE ? `
  <tr>
    <td style="padding:0 32px 10px 32px; font-size:12px; color:#6b7280;" class="padding-laterale">
      e altre ${voci.length - MAX_RIGHE}: aprirle dalla dashboard.
    </td>
  </tr>` : ''}` : '');

const riga_ddt = (ddt) => `
  <tr>
    <td style="padding:0 32px 10px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid #6b7280; background:#f9fafb;">
        <tr>
          <td style="padding:11px 14px;">
            <div style="font-size:14px; font-weight:700; color:#111827;">
              DDT ${esc(ddt.numero_ddt)} del ${esc(ddt.data_ddt)}
            </div>
            <div style="font-size:12px; color:#6b7280;">
              ${esc(ddt.fornitore)} &nbsp;&bull;&nbsp; consegna a ${esc(ddt.ragione_sociale_consegna) || '&mdash;'}
              &nbsp;&bull;&nbsp; in archivio da <strong>${ddt.giorni_attesa}</strong> giorni
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>`;

const sezione_ddt = (voci) => (voci.length ? `
  <tr>
    <td style="padding:6px 32px 4px 32px;" class="padding-laterale">
      <div style="font-size:12px; font-weight:700; color:#374151; text-transform:uppercase; letter-spacing:.5px;">Bolle senza fattura (${voci.length})</div>
      <div style="font-size:12px; color:#6b7280; padding:2px 0 8px 0;">Scansionate da oltre ${soglia} giorni e mai fatturate: o la fattura non &egrave; arrivata, o nessuno ne ha ancora chiesto l&apos;abbinamento.</div>
    </td>
  </tr>
  ${voci.slice(0, MAX_RIGHE).map(riga_ddt).join('')}
  ${voci.length > MAX_RIGHE ? `
  <tr>
    <td style="padding:0 32px 10px 32px; font-size:12px; color:#6b7280;" class="padding-laterale">
      e altre ${voci.length - MAX_RIGHE}: aprirle dalla dashboard.
    </td>
  </tr>` : ''}` : '');

const corpo_html = `<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  @media only screen and (max-width:600px) {
    .padding-laterale { padding-left:18px !important; padding-right:18px !important; }
  }
</style>
</head>
<body style="margin:0; padding:0; background:#f3f4f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; background:#f3f4f6;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="border-collapse:collapse; width:600px; max-width:100%; background:#ffffff; border-radius:6px;">
        <tr>
          <td style="padding:26px 32px 8px 32px;" class="padding-laterale">
            <div style="font-size:19px; font-weight:700; color:#111827;">Fermi da oltre ${soglia} giorni</div>
            <div style="font-size:13px; color:#6b7280; padding-top:4px;">
              ${totale} fattur${totale === 1 ? 'a' : 'e'} in attesa dei documenti di trasporto${da_accoppiare.length ? `, ${da_accoppiare.length} da chiudere con un click` : ''}${ddt_orfani.length ? `, ${ddt_orfani.length} boll${ddt_orfani.length === 1 ? 'a' : 'e'} senza fattura` : ''}.
            </div>
          </td>
        </tr>
        <tr><td style="padding:10px 32px 0 32px;" class="padding-laterale"><hr style="border:0; border-top:1px solid #e5e7eb; margin:0;"></td></tr>
        ${sezione('Da confermare a mano', 'Il DDT risulta gi&agrave; in archivio ma con un numero diverso: va confermato dalla dashboard, da solo non si sblocca.', da_confermare, '#f59e0b')}
        ${sezione('DDT mai arrivati', 'Le bolle non sono ancora state scansionate. Quando arrivano, la fattura si chiude da sola.', attende_ddt, '#dc2626')}
        ${sezione_click(da_accoppiare)}
      ${sezione_ddt(ddt_orfani)}
        <tr>
          <td align="center" style="padding:12px 32px 28px 32px;" class="padding-laterale">
            <a href="${URL_DASHBOARD}" style="display:inline-block; padding:11px 22px; background:#111827; color:#ffffff; font-size:13px; font-weight:600; text-decoration:none; border-radius:4px;">
              Apri la dashboard
            </a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>`;

const oggetto = `Documenti fermi da oltre ${soglia} giorni: ${totale} fatture`
  + (da_accoppiare.length ? `, ${da_accoppiare.length} da accoppiare` : '')
  + (ddt_orfani.length ? `, ${ddt_orfani.length} bolle` : '')
  + (da_confermare.length ? ` (${da_confermare.length} da confermare a mano)` : '');

return [{
  json: {
    oggetto, corpo_html, soglia, soglia_click, totale,
    da_confermare: da_confermare.length,
    attende_ddt: attende_ddt.length,
    da_accoppiare: da_accoppiare.length,
    ddt_senza_fattura: ddt_orfani.length,
  },
}];
