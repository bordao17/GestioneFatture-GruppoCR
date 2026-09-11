"""I mattoni HTML condivisi dalle tre mail.

Vincoli, gli stessi che avevano i nodi Code di n8n e che non sono cambiati
cambiando linguaggio:
  - TABELLE e stili inline, niente flex/grid e niente <div> portanti: la mail
    deve reggere anche Outlook, che di CSS moderno non sa nulla. Le @media in
    fondo servono solo ai client che le supportano (Gmail, Apple Mail).
  - TUTTO cio' che viene da un documento passa da esc(): sono ragioni sociali
    lette da una scansione o da un XML di terzi, e una & o una < romperebbero
    il markup.

Le tre mail condividono il guscio (intestazione, pulsante, pie' di pagina) e
non l'ho fatto per risparmiare righe: sono tre messaggi dello stesso sistema e
devono somigliarsi, altrimenti chi li riceve non li riconosce a colpo d'occhio.
"""

from src.comune.configurazione import valore
from src.comune.tempo import adesso

# Gli stessi colori degli stati in dashboard (etichetteDdt.js / etichetteFatture.js):
# verde = a posto, ambra = aspetta una persona, rosso = manca qualcosa, blu = da fare.
VERDE = "#16a34a"
AMBRA = "#f59e0b"
ROSSO = "#dc2626"
BLU = "#2563eb"
GRIGIO = "#6b7280"

MANCANTE = '<span style="color:#b91c1c; font-style:italic;">non letto</span>'

_CELLA = "padding:0 32px 14px 32px;"


def esc(v):
    """Il testo reso innocuo per l'HTML. Da usare su OGNI valore che viene da un documento."""
    return (str("" if v is None else v)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def valore_o_mancante(v):
    """Il campo, oppure la scritta rossa "non letto" se il modello non l'ha estratto."""
    return esc(v) if str(v or "").strip() else MANCANTE


def plurale(n, singolare, plurale_):
    return singolare if n == 1 else plurale_


def riga(contenuto, padding=_CELLA):
    """Una riga della tabella-contenitore: e' l'unico modo di impilare blocchi in una mail."""
    return f'<tr><td style="{padding}" class="padding-laterale">{contenuto}</td></tr>'


def testo_piccolo(contenuto):
    return riga(f'<div style="font-size:12px; color:{GRIGIO};">{contenuto}</div>')


def titolo_sezione(testo, spiegazione):
    """Intestazione di un elenco: dice quanti sono e, sotto, come si chiude quella coda."""
    return riga(
        f'<div style="font-size:12px; font-weight:700; color:#374151; '
        f'text-transform:uppercase; letter-spacing:.5px;">{testo}</div>'
        f'<div style="font-size:12px; color:{GRIGIO}; padding:2px 0 8px 0;">{spiegazione}</div>',
        padding="padding:6px 32px 4px 32px;",
    )


def scheda(colore, contenuto, sfondo="#f9fafb"):
    """Il riquadro con la barretta colorata a sinistra: una pratica, un documento, un avviso."""
    return riga(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse; border-left:3px solid {colore}; background:{sfondo};">'
        f'<tr><td style="padding:11px 14px;">{contenuto}</td></tr></table>'
    )


def barra(segmenti):
    """Barra proporzionale: celle di tabella con width in percentuale, non un <div>."""
    totale = sum(n for n, _ in segmenti)
    if totale <= 0:
        return ""

    celle = "".join(
        f'<td width="{round(n / totale * 100)}%" style="background:{colore}; height:8px; '
        f'font-size:0; line-height:0;">&nbsp;</td>'
        for n, colore in segmenti if n > 0
    )
    return riga(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse; border-radius:4px; overflow:hidden;">'
        f'<tr>{celle}</tr></table>',
        padding="padding:0 32px 18px 32px;",
    )


def conteggi(voci):
    """La fila dei numeroni in cima: [(etichetta, numero, colore), ...]."""
    larghezza = round(100 / max(1, len(voci)))
    celle = "".join(
        f'<td width="{larghezza}%" align="center" style="padding:10px 4px;">'
        f'<div style="font-size:26px; font-weight:700; color:{colore};">{numero}</div>'
        f'<div style="font-size:11px; color:{GRIGIO}; text-transform:uppercase; '
        f'letter-spacing:.5px;">{etichetta}</div></td>'
        for etichetta, numero, colore in voci
    )
    return riga(
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;"><tr>{celle}</tr></table>',
        padding="padding:0 32px 18px 32px;",
    )


def troncamento(totale, mostrati, cosa="voci"):
    """La riga "e altre N": oltre un certo numero la mail smette di essere leggibile
    e la dashboard e' il posto giusto per guardarle."""
    if totale <= mostrati:
        return ""
    return testo_piccolo(f"e altre {totale - mostrati} {cosa}: aprirle dalla dashboard.")


def pagina(titolo, sottotitolo, corpo, anteprima=""):
    """Il guscio completo del messaggio, dal <!DOCTYPE> al pulsante finale."""
    url = esc(valore("URL_DASHBOARD"))
    data_ora = adesso().strftime("%d/%m/%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titolo)}</title>
<style>
  @media only screen and (max-width:600px) {{
    .padding-laterale {{ padding-left:18px !important; padding-right:18px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; background:#f3f4f6;">
<!-- Riga di anteprima nella lista dei messaggi, invisibile nel corpo -->
<div style="display:none; max-height:0; overflow:hidden; opacity:0;">{esc(anteprima)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse; background:#f3f4f6; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="border-collapse:collapse; width:600px; max-width:100%; background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden;">
        <tr>
          <td style="padding:24px 32px 16px 32px;" class="padding-laterale">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:19px; font-weight:700; color:#111827;">{esc(titolo)}</div>
                  <div style="font-size:13px; color:{GRIGIO}; padding-top:4px;">{sottotitolo}</div>
                </td>
                <td align="right" style="color:#9ca3af; font-size:12px; white-space:nowrap; vertical-align:top;">{data_ora}</td>
              </tr>
            </table>
          </td>
        </tr>
        {corpo}
        <tr>
          <td align="center" style="padding:12px 32px 26px 32px;" class="padding-laterale">
            <table role="presentation" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#111827; border-radius:5px;">
                  <a href="{url}" style="display:inline-block; padding:11px 24px; font-size:13px; font-weight:600; color:#ffffff; text-decoration:none;">Apri la dashboard</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:14px 32px; background:#f9fafb; border-top:1px solid #e5e7eb;" class="padding-laterale">
            <div style="font-size:11px; color:#9ca3af; line-height:1.5;">
              Notifica automatica di GestioneFatture &middot; GruppoCR.
              Orari e destinatari si cambiano dalla sezione Configurazione della dashboard.
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""
