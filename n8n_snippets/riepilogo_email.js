// ============================================================================
// Nodo Code (n8n) - Mail di riepilogo elaborazione DDT
// Va posizionato subito dopo l'HTTP Request che chiama GET /riepilogo.
// Restituisce anche l'oggetto della mail, cosi' nel nodo "Send Email":
//   Subject -> {{ $json.oggetto }}
//   HTML    -> {{ $json.corpo_html }}
//
// Copia versionata del nodo: l'originale vive dentro il database di n8n e da
// qui non e' leggibile. Se lo modifichi in n8n, riallinea anche questo file.
// ============================================================================

const URL_DASHBOARD = 'http://localhost:3000';
const MAX_RIGHE_CHECK = 25; // oltre, la mail diventa illeggibile: si rimanda alla dashboard

const dati = $input.first().json;

const ok = Number(dati.ok) || 0;
const check = Number(dati.check) || 0;
const ko = Number(dati.ko) || 0;
const totale = Number(dati.totale) || ok + check + ko;

// I valori arrivano da una lettura del modello: possono contenere &, < o >
// e romperebbero il markup. Tutto cio' che entra nell'HTML passa da qui.
const esc = (v) => String(v ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const MANCANTE = '<span style="color:#b91c1c; font-style:italic;">non letto</span>';
const valore = (v) => (String(v ?? '').trim() ? esc(v) : MANCANTE);

// Gli stessi 4 campi su cui il backend decide OK/CHECK/KO (CAMPI_OBBLIGATORI).
const CAMPI = [
  ['fornitore', 'Fornitore'],
  ['numero_ddt', 'N. DDT'],
  ['data_ddt', 'Data'],
  ['indirizzo_consegna', 'Indirizzo di consegna'],
];

const perc = (n) => (totale > 0 ? Math.round((n / totale) * 100) : 0);

// --- Barra proporzionale OK / CHECK / KO ------------------------------------
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
          ${segmento(ok, '#16a34a')}
          ${segmento(check, '#f59e0b')}
          ${segmento(ko, '#dc2626')}
        </tr>
      </table>
    </td>
  </tr>` : '';

// --- Riquadri con i conteggi -------------------------------------------------
const riquadro = (numero, etichetta, coloreNumero, coloreTesto, sfondo, bordo) => `
  <td width="32%" class="riquadro" style="background:${sfondo}; border:1px solid ${bordo}; border-radius:8px; padding:16px 8px; text-align:center;">
    <div style="font-size:30px; font-weight:700; color:${coloreNumero}; line-height:1;">${numero}</div>
    <div style="margin-top:6px; font-size:11px; font-weight:600; letter-spacing:.6px; text-transform:uppercase; color:${coloreTesto};">${etichetta}</div>
  </td>`;

// --- Righe dei documenti da controllare -------------------------------------
const vociCheck = Array.isArray(dati.voci_check) ? dati.voci_check : [];

const righeCheck = vociCheck.slice(0, MAX_RIGHE_CHECK).map((voce, indice) => {
  const d = voce.dati || {};

  // Perche' e' finito in CHECK: e' l'informazione che serve davvero a chi apre
  // la mail, altrimenti deve aprire il documento per scoprirlo.
  const mancanti = CAMPI
    .filter(([campo]) => !String(d[campo] ?? '').trim())
    .map(([, nome]) => nome);

  let motivo;
  if (d.indirizzo_scartato) {
    motivo = `Indirizzo scartato perche' vietato per questo fornitore: ${esc(d.indirizzo_scartato)}`;
  } else if (mancanti.length) {
    motivo = `Non letto: ${esc(mancanti.join(', '))}`;
  } else if (d.leggibilita_bassa) {
    motivo = 'Campi completi, ma scansione di bassa qualita';
  } else {
    motivo = 'Da verificare';
  }

  const sfondo = indice % 2 === 0 ? '#ffffff' : '#fffdf6';
  const cella = 'padding:10px 14px; border-bottom:1px solid #f5e9c8; font-size:13px; color:#374151; vertical-align:top;';

  return `
    <tr style="background:${sfondo};">
      <td style="${cella}">
        <div style="font-weight:600; color:#111827;">${valore(d.fornitore)}</div>
        <div style="margin-top:2px; font-size:11px; color:#9ca3af;">${esc(voce.file_origine || '')}</div>
      </td>
      <td style="${cella} font-family:Consolas,Menlo,monospace; white-space:nowrap;">${valore(d.numero_ddt)}</td>
      <td style="${cella} white-space:nowrap;">${valore(d.data_ddt)}</td>
      <td style="${cella} color:#92400e;">${motivo}</td>
    </tr>`;
}).join('');

const nascosti = Math.max(0, vociCheck.length - MAX_RIGHE_CHECK);
const rigaNascosti = nascosti > 0 ? `
        <tr>
          <td colspan="4" style="padding:10px 14px; font-size:12px; color:#92400e; background:#fef3c7;">
            e altri ${nascosti} documenti da controllare: aprili dalla dashboard.
          </td>
        </tr>` : '';

const intestazione = (testo) => `
          <th align="left" style="padding:9px 14px; font-size:11px; font-weight:600; letter-spacing:.5px; text-transform:uppercase; color:#92400e; border-bottom:1px solid #fde68a;">${testo}</th>`;

const bloccoCheck = check > 0 ? `
  <tr>
    <td style="padding:0 32px 22px 32px;" class="padding-laterale">
      <div style="font-size:14px; font-weight:600; color:#92400e; margin-bottom:10px;">
        Da controllare manualmente (${check})
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; border:1px solid #fde68a; border-radius:8px; overflow:hidden;">
        <tr style="background:#fef3c7;">
          ${intestazione('Fornitore')}
          ${intestazione('N. DDT')}
          ${intestazione('Data')}
          ${intestazione('Motivo')}
        </tr>
        ${righeCheck}
        ${rigaNascosti}
      </table>
    </td>
  </tr>` : '';

const bloccoKo = ko > 0 ? `
  <tr>
    <td style="padding:0 32px 22px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fef2f2; border:1px solid #fecaca; border-radius:8px;">
        <tr>
          <td style="padding:16px 18px; font-size:13px; color:#991b1b; line-height:1.5;">
            <strong>${ko} document${ko === 1 ? 'o non letto' : 'i non letti'} (KO):</strong>
            il modello non ha estratto nessun campo, vanno compilati a mano dalla dashboard guardando la scansione.
          </td>
        </tr>
      </table>
    </td>
  </tr>` : '';

const bloccoTuttoBene = (totale > 0 && check === 0 && ko === 0) ? `
  <tr>
    <td style="padding:0 32px 22px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px;">
        <tr>
          <td style="padding:16px 18px; font-size:14px; color:#166534;">
            <strong>Nessun documento da rivedere.</strong> Tutti i DDT di questa elaborazione sono stati letti per intero.
          </td>
        </tr>
      </table>
    </td>
  </tr>` : '';

const bloccoVuoto = totale === 0 ? `
  <tr>
    <td style="padding:0 32px 22px 32px;" class="padding-laterale">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb; border:1px solid #e5e7eb; border-radius:8px;">
        <tr>
          <td style="padding:16px 18px; font-size:14px; color:#4b5563;">
            Nessun documento elaborato in questa esecuzione.
          </td>
        </tr>
      </table>
    </td>
  </tr>` : '';

const dataOra = new Date().toLocaleString('it-IT', { timeZone: 'Europe/Rome' });

const anteprima = totale === 0
  ? 'Nessun documento elaborato'
  : `${ok} letti correttamente, ${check} da controllare, ${ko} non letti`;

const oggetto = totale === 0
  ? 'Riepilogo DDT - nessun documento elaborato'
  : `Riepilogo DDT - ${ok} OK / ${check} da controllare / ${ko} KO`;

const html = `<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${esc(oggetto)}</title>
  <style>
    @media only screen and (max-width:620px) {
      .contenitore { width:100% !important; }
      .padding-laterale { padding-left:18px !important; padding-right:18px !important; }
      .riquadro { display:block !important; width:100% !important; margin-bottom:8px !important; }
    }
  </style>
</head>
<body style="margin:0; padding:0; background:#eef1f5;">

  <!-- Riga di anteprima nella lista dei messaggi, invisibile nel corpo -->
  <div style="display:none; max-height:0; overflow:hidden; opacity:0;">${esc(anteprima)}</div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f5; padding:28px 12px; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
    <tr>
      <td align="center">
        <table role="presentation" class="contenitore" width="620" cellpadding="0" cellspacing="0" style="width:620px; max-width:620px; background:#ffffff; border:1px solid #e2e6ec; border-radius:12px; overflow:hidden;">

          <!-- Intestazione -->
          <tr>
            <td style="background:#111827; padding:22px 32px;" class="padding-laterale">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <div style="color:#ffffff; font-size:17px; font-weight:600;">Riepilogo elaborazione D.D.T.</div>
                    <div style="color:#9ca3af; font-size:12px; margin-top:3px;">GestioneFatture &middot; GruppoCR</div>
                  </td>
                  <td align="right" style="color:#6b7280; font-size:12px; white-space:nowrap;">${esc(dataOra)}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Totale -->
          <tr>
            <td style="padding:26px 32px 12px 32px;" class="padding-laterale">
              <div style="font-size:11px; font-weight:600; letter-spacing:.7px; text-transform:uppercase; color:#9ca3af;">Documenti elaborati</div>
              <div style="font-size:38px; font-weight:700; color:#111827; line-height:1.1; margin-top:4px;">${totale}</div>
            </td>
          </tr>

          ${barra}

          <!-- Conteggi -->
          <tr>
            <td style="padding:0 32px 22px 32px;" class="padding-laterale">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  ${riquadro(ok, 'Letti OK', '#16a34a', '#166534', '#f0fdf4', '#bbf7d0')}
                  <td width="2%"></td>
                  ${riquadro(check, 'Da controllare', '#d97706', '#92400e', '#fffbeb', '#fde68a')}
                  <td width="2%"></td>
                  ${riquadro(ko, 'Non letti', '#dc2626', '#991b1b', '#fef2f2', '#fecaca')}
                </tr>
              </table>
            </td>
          </tr>

          ${bloccoCheck}
          ${bloccoKo}
          ${bloccoTuttoBene}
          ${bloccoVuoto}

          <!-- Pulsante -->
          <tr>
            <td align="center" style="padding:0 32px 26px 32px;" class="padding-laterale">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background:#2563eb; border-radius:6px;">
                    <a href="${URL_DASHBOARD}" style="display:inline-block; padding:12px 26px; font-size:14px; font-weight:600; color:#ffffff; text-decoration:none;">Apri la dashboard</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Pie' di pagina -->
          <tr>
            <td style="padding:16px 32px; background:#f9fafb; border-top:1px solid #e5e7eb;" class="padding-laterale">
              <div style="font-size:11px; color:#9ca3af; line-height:1.5;">
                Notifica automatica del flusso n8n &middot; i documenti restano nella dashboard,
                dove possono essere corretti, uniti o rianalizzati.
              </div>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;

return [{ json: { ...dati, oggetto, corpo_html: html } }];
