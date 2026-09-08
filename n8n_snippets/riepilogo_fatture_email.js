// ============================================================================
// Nodo Code (n8n) - Mail di riepilogo abbinamento FATTURE -> DDT
// Va posizionato subito dopo l'HTTP Request che chiama POST /abbina-fattura.
// Modalita': "Run Once for All Items" (aggrega tutti i file del batch).
// Restituisce oggetto + corpo_html, cosi' nel nodo "Send Email":
//   Subject -> {{ $json.oggetto }}
//   HTML    -> {{ $json.corpo_html }}
//
// Copia versionata del nodo: l'originale vive dentro il database di n8n e da
// qui non e' leggibile. Se lo modifichi in n8n, riallinea anche questo file.
//
// COSA FA OGGI QUESTO RAMO. Dal 2026-09-08 leggere una fattura e cercarle i
// DDT sono due gesti distinti: /abbina-fattura archivia soltanto, quindi la
// mail non racconta piu' un abbinamento — dice CHE COSA E' ENTRATO e che
// aspetta un ABBINA in dashboard. Un abbinamento fatto di nascosto sarebbe
// esattamente cio' che si e' voluto togliere.
//
// Stati possibili di una fattura nella risposta del backend:
//   DA_ABBINARE  letta e archiviata, i suoi DDT non sono ancora stati cercati.
//                E' lo stato normale di tutto cio' che entra da qui.
//   DUPLICATA    gia' registrata: il ramo non svuota /FATTURE/da_leggere, quindi
//                a ogni rilancio i vecchi file ripassano di qui.
//   ABBINATA / IN_ATTESA / NON_ABBINATA restano gestiti per compatibilita': non
//                li produce piu' questa chiamata, ma il ricontrollo della coda.
//
// Le anomalie sul cedente (P.IVA assente o diversa da quella confermata in
// anagrafica) NON impediscono l'archiviazione: nessuna fattura viene piu'
// scartata per il fornitore, perche' chi carica un file ha gia' deciso che gli
// interessa. Arrivano in `segnalazioni` e finiscono in fondo alla mail.
// ============================================================================

const URL_DASHBOARD = 'http://localhost:3000';
const MAX_RIGHE_DDT = 25; // oltre, la mail diventa illeggibile: si rimanda alla dashboard

// I valori arrivano da una fattura di un fornitore: ragioni sociali con & o
// numeri documento con < romperebbero il markup. Tutto passa da qui.
const esc = (v) => String(v ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

// Su un item fallito n8n sostituisce il json con il solo errore: il nome del
// file si recupera solo risalendo all'item di partenza tramite pairedItem.
const nomeFile = (item) => {
  try {
    const indice = item.pairedItem?.item ?? item.pairedItem ?? 0;
    const origine = $('Leggi Fatture').all()[typeof indice === 'number' ? indice : 0];
    return origine?.binary?.data?.fileName || 'file sconosciuto';
  } catch (e) {
    return 'file sconosciuto';
  }
};

// Un file illeggibile non deve far saltare la mail: l'HTTP Request ha
// onError = continueRegularOutput, e qui l'errore diventa semplicemente una
// riga in piu' in fondo al messaggio.
const fatture = [];
const falliti = [];

for (const item of $input.all()) {
  const dati = item.json || {};

  if (dati.error || dati.status !== 'success') {
    const err = dati.error;
    const dettaglio = (typeof err === 'string' ? err : null)
      || err?.message || err?.detail || dati.message || 'errore sconosciuto';
    falliti.push({ file: dati.filename || nomeFile(item), motivo: dettaglio });
    continue;
  }

  for (const fattura of dati.fatture || []) {
    fatture.push({ ...fattura, file: dati.filename });
  }
}

const conta = (stato) => fatture.filter((f) => f.stato === stato).length;
const da_abbinare = conta('DA_ABBINARE');
const abbinate = conta('ABBINATA');
const in_attesa = conta('IN_ATTESA');
const non_abbinate = conta('NON_ABBINATA');
const duplicate = conta('DUPLICATA');
const segnalate = fatture.filter((f) => (f.segnalazioni || []).length > 0);

// Le duplicate non sono state elaborate: tenerle nel totale (e nella barra)
// farebbe sembrare un lavoro andato male un lavoro che non c'e' proprio stato.
const totale = da_abbinare + abbinate + in_attesa + non_abbinate;

const COLORI = {
  DA_ABBINARE: '#2563eb',
  ABBINATA: '#16a34a',
  IN_ATTESA: '#f59e0b',
  NON_ABBINATA: '#dc2626',
};

const ETICHETTE = {
  abbinato: ['#16a34a', 'abbinato'],
  probabile: ['#f59e0b', 'da confermare'],
  non_trovato: ['#dc2626', 'DDT non ancora arrivato'],
};

const perc = (n) => (totale > 0 ? Math.round((n / totale) * 100) : 0);

// --- Barra proporzionale ----------------------------------------------------
// Niente div ne' CSS moderno: celle di tabella con width in percentuale, la
// sola cosa che si vede uguale anche in Outlook.
const segmento = (n, colore) => (n > 0
  ? `<td width="${perc(n)}%" style="background:${colore}; height:8px; font-size:0; line-height:0;">&nbsp;</td>`
  : '');

const barra = totale > 0 ? `
  <tr>
    <td style="padding:0 32px 22px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-radius:4px; overflow:hidden;">
        <tr>
          ${segmento(da_abbinare, COLORI.DA_ABBINARE)}
          ${segmento(abbinate, COLORI.ABBINATA)}
          ${segmento(in_attesa, COLORI.IN_ATTESA)}
          ${segmento(non_abbinate, COLORI.NON_ABBINATA)}
        </tr>
      </table>
    </td>
  </tr>` : '';

const totali = `
  <tr>
    <td style="padding:0 32px 18px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <tr>
          ${[['Da abbinare', da_abbinare, COLORI.DA_ABBINARE],
             ['Pronte da accoppiare', abbinate, COLORI.ABBINATA],
             ['In attesa', in_attesa, COLORI.IN_ATTESA],
             ['Senza DDT', non_abbinate, COLORI.NON_ABBINATA]].map(([testo, n, colore]) => `
          <td width="25%" align="center" style="padding:10px 4px;">
            <div style="font-size:26px; font-weight:700; color:${colore};">${n}</div>
            <div style="font-size:11px; color:#6b7280; text-transform:uppercase; letter-spacing:.5px;">${testo}</div>
          </td>`).join('')}
        </tr>
      </table>
    </td>
  </tr>`;

// --- File passati ma non elaborati ------------------------------------------
// Una riga sola: e' una situazione normale, non un problema. Le duplicate sono
// la conseguenza attesa del fatto che la cartella non viene svuotata.
const scartate = duplicate ? `
  <tr>
    <td style="padding:0 32px 14px 32px; font-size:12px; color:#6b7280;" class="padding-laterale">
      ${duplicate} gi&agrave; registrat${duplicate === 1 ? 'a' : 'e'}
    </td>
  </tr>` : '';

// --- Anomalie sul cedente ---------------------------------------------------
// Non hanno bloccato niente: la fattura e' in archivio. Ma la P.IVA e' l'unica
// chiave esatta fra i due lati del sistema, quindi una che manca o che
// contraddice l'anagrafica va detta a qualcuno, non solo scritta nei log.
const blocco_segnalazioni = segnalate.length ? `
  <tr>
    <td style="padding:0 32px 14px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid #f59e0b; background:#fffbeb;">
        <tr>
          <td style="padding:12px 14px; font-size:13px; color:#92400e;">
            <strong>${segnalate.length} fattur${segnalate.length === 1 ? 'a' : 'e'} da controllare in anagrafica</strong>
            <div style="font-size:12px; padding-top:2px;">Archiviate lo stesso: il fornitore non filtra pi&ugrave; nulla. Va per&ograve; sistemata la P.IVA, altrimenti l&apos;abbinamento lavora alla cieca.</div>
            ${segnalate.map((f) => `<div style="font-size:12px; padding-top:6px;"><strong>${esc(f.numero_fattura)}</strong> — ${esc(f.fornitore)}<br>${(f.segnalazioni || []).map((s) => esc(s.messaggio)).join('<br>')}</div>`).join('')}
          </td>
        </tr>
      </table>
    </td>
  </tr>` : '';

// --- Dettaglio delle fatture che non si sono chiuse --------------------------
// Le ABBINATE non si elencano: sono quelle per cui non c'e' niente da fare.
const da_rivedere = fatture.filter((f) => f.stato === 'IN_ATTESA' || f.stato === 'NON_ABBINATA');
const troncato = da_rivedere.length > MAX_RIGHE_DDT;

const blocchi = da_rivedere.slice(0, MAX_RIGHE_DDT).map((fattura) => {
  // Una accompagnatoria non "cita" nessun DDT: la merce viaggia con la fattura,
  // che vale essa stessa da bolla. Il documento cercato tra le scansioni e' lei,
  // col suo numero — dirlo cambia cosa deve andare a cercare chi legge.
  const accompagnatoria = fattura.tipo === 'accompagnatoria';

  const righe = (fattura.ddt || []).map((ddt) => {
    const [colore, etichetta] = ETICHETTE[ddt.esito] || ['#6b7280', ddt.esito];
    return `
      <tr>
        <td style="padding:4px 0; font-size:13px; color:#111827;">
          ${accompagnatoria ? 'Documento' : 'DDT'} <strong>${esc(ddt.numero_ddt)}</strong> del ${esc(ddt.data_ddt)}
          <span style="color:${colore}; font-weight:600;">&nbsp;&bull;&nbsp;${etichetta}</span>
          <div style="font-size:12px; color:#6b7280;">${esc(ddt.motivo)}</div>
        </td>
      </tr>`;
  }).join('');

  const senza_ddt = (fattura.ddt || []).length === 0
    ? '<tr><td style="padding:4px 0; font-size:13px; color:#6b7280;">La fattura non cita alcun documento di trasporto e non riporta dati di trasporto: non c&apos;&egrave; nessuna bolla da attendere.</td></tr>'
    : '';

  // Le due attese non si risolvono nello stesso modo: quella per un DDT non
  // ancora scansionato si chiude da sola, quella per un numero letto male
  // aspetta che qualcuno lo corregga in dashboard.
  const attesa = fattura.attesa || {};
  const nota_attesa = fattura.stato === 'IN_ATTESA' ? `
            <div style="font-size:12px; color:#92400e; padding-top:6px;">
              ${attesa.da_confermare
                ? `${attesa.da_confermare} riferiment${attesa.da_confermare === 1 ? 'o' : 'i'} da confermare a mano: il DDT c'&egrave; gi&agrave;, ma con un numero diverso.`
                : accompagnatoria
                  ? 'In coda: la fattura accompagnatoria non &egrave; ancora stata scansionata tra i DDT.'
                  : 'In coda: verr&agrave; ricontrollata da sola a ogni nuova estrazione di DDT.'}
            </div>` : '';

  return `
  <tr>
    <td style="padding:0 32px 14px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid ${COLORI[fattura.stato] || '#6b7280'}; background:#f9fafb;">
        <tr>
          <td style="padding:12px 14px;">
            <div style="font-size:14px; font-weight:700; color:#111827;">
              Fattura ${esc(fattura.numero_fattura)} del ${esc(fattura.data_fattura)}
            </div>
            <div style="font-size:12px; color:#6b7280; padding-bottom:8px;">
              ${esc(fattura.fornitore)} &nbsp;&bull;&nbsp; ${fattura.ddt_abbinati}/${fattura.ddt_totali} DDT abbinati${accompagnatoria ? ' &nbsp;&bull;&nbsp; accompagnatoria' : ''}
            </div>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
              ${righe}${senza_ddt}
            </table>${nota_attesa}
          </td>
        </tr>
      </table>
    </td>
  </tr>`;
}).join('');

const nota_troncamento = troncato ? `
  <tr>
    <td style="padding:0 32px 14px 32px; font-size:12px; color:#6b7280;" class="padding-laterale">
      e altre ${da_rivedere.length - MAX_RIGHE_DDT} fatture in coda: aprirle dalla dashboard.
    </td>
  </tr>` : '';

const blocco_falliti = falliti.length ? `
  <tr>
    <td style="padding:0 32px 14px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border-left:3px solid #dc2626; background:#fef2f2;">
        <tr>
          <td style="padding:12px 14px; font-size:13px; color:#991b1b;">
            <strong>${falliti.length} file non elaborati</strong>
            ${falliti.map((f) => `<div style="font-size:12px; padding-top:4px;">${esc(f.file)} — ${esc(f.motivo)}</div>`).join('')}
          </td>
        </tr>
      </table>
    </td>
  </tr>` : '';

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
          <td style="padding:26px 32px 18px 32px;" class="padding-laterale">
            <div style="font-size:19px; font-weight:700; color:#111827;">Fatture elettroniche in ingresso</div>
            <div style="font-size:13px; color:#6b7280; padding-top:4px;">
              ${totale} fatt${totale === 1 ? 'ura archiviata' : 'ure archiviate'}${da_abbinare ? ' &mdash; i D.D.T. si cercano dalla dashboard, con Abbina tutte' : ''}
            </div>
          </td>
        </tr>
        ${barra}
        ${totali}
        ${scartate}
        ${blocco_segnalazioni}
        ${da_rivedere.length ? `
        <tr>
          <td style="padding:6px 32px 10px 32px; font-size:12px; font-weight:700; color:#374151; text-transform:uppercase; letter-spacing:.5px;" class="padding-laterale">
            Non ancora chiuse
          </td>
        </tr>` : ''}
        ${blocchi}
        ${nota_troncamento}
        ${blocco_falliti}
        <tr>
          <td align="center" style="padding:8px 32px 28px 32px;" class="padding-laterale">
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

const oggetto = totale === 0 && falliti.length === 0
  ? (duplicate
      ? `Fatture: nessuna nuova da elaborare (${duplicate} gia' registrate)`
      : 'Fatture: nessun file da elaborare')
  : `Fatture: ${totale} archiviate, ${da_abbinare} da abbinare`
    + (segnalate.length ? `, ${segnalate.length} da controllare` : '');

return [{
  json: {
    oggetto, corpo_html, totale, da_abbinare, abbinate, in_attesa, non_abbinate,
    duplicate, segnalate: segnalate.length, falliti: falliti.length,
  },
}];
