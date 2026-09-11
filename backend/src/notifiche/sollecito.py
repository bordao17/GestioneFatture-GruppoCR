"""Mail del mattino: che cosa e' fermo da troppi giorni.

Porting del nodo Code "Html Sollecito" di n8n (n8n_snippets/sollecito_attese_email.js).

PERCHE' ESISTE. Tutto il resto dell'abbinamento e' guidato da eventi che il
backend vede da solo (un D.D.T. estratto, corretto, unito) e che fanno ripartire
il ricontrollo. "In attesa da troppi giorni" e' invece un fatto TEMPORALE: alla
scadenza nel backend non succede niente, e se nessuno lo dice quella pratica
resta ferma per sempre.

LE SOGLIE SONO TRE e arrivano da fuori (le legge main.py da configurazione.py):
una per le fatture che aspettano una bolla, una per le bolle che aspettano una
fattura, una piu' corta per chi aspetta solo un click. Qui non se ne decide
nessuna: la mail le scrive e basta, cosi' il numero vive in un posto solo.

Quattro code, che si risolvono in quattro modi diversi — ed e' l'unica ragione
per cui vale la pena leggere questa mail invece di aprire la dashboard:
  da_confermare  il D.D.T. c'e' gia' ma con un numero letto male: si corregge a
                 mano, e da solo non si sbloccher&agrave; mai.
  attende_ddt    la bolla non e' stata scansionata: va cercata in magazzino, e
                 quando arriva la fattura si aggancia da sola.
  da_accoppiare  non manca niente: aspetta un click (ABBINA oppure ACCOPPIA).
  ddt_orfani     il lato speculare: una bolla in archivio di cui non e' mai
                 arrivata la fattura.

Se non c'e' niente da sollecitare componi() restituisce None e la mail non
parte: "nessuna fattura in attesa" verrebbe ignorata entro tre giorni, comprese
le volte in cui dice qualcosa.
"""

from src.notifiche.impaginazione import (
    AMBRA, BLU, GRIGIO, ROSSO, esc, pagina, plurale, scheda, titolo_sezione,
    troncamento,
)

MAX_RIGHE = 30

CIANO = "#0891b2"


def _riga_fattura(fattura, colore):
    """Una pratica che aspetta un DOCUMENTO: si elencano i numeri da cercare."""
    dati = fattura.get("dati", {})
    attesa = fattura.get("attesa", {})
    numeri = (attesa.get("numeri_da_confermare") if attesa.get("da_confermare")
              else attesa.get("numeri_mancanti")) or []

    elenco = ", ".join(f"<strong>{esc(n)}</strong>" for n in numeri) or "&mdash;"

    return scheda(
        colore,
        f'<div style="font-size:14px; font-weight:700; color:#111827;">'
        f'Fattura {esc(dati.get("numero_fattura"))} del {esc(dati.get("data_fattura"))}</div>'
        f'<div style="font-size:12px; color:{GRIGIO}; padding-bottom:6px;">'
        f'{esc(dati.get("fornitore"))} &nbsp;&bull;&nbsp; ferma da '
        f'<strong>{fattura.get("giorni_attesa", 0)}</strong> giorni &nbsp;&bull;&nbsp; '
        f'{attesa.get("abbinati", 0)}/{len(fattura.get("ddt") or [])} DDT trovati</div>'
        f'<div style="font-size:13px; color:#111827;">DDT {elenco}</div>'
    )


def _riga_click(fattura):
    """Una pratica che aspetta una PERSONA: qui non serve nessun numero, serve
    sapere QUALE dei due pulsanti premere. "Abbina" non e' "Accoppia"."""
    dati = fattura.get("dati", {})
    da_abbinare = fattura.get("motivo_attesa") == "da_abbinare"

    azione = ('I suoi D.D.T. non sono ancora stati cercati: premi <strong>ABBINA</strong> sulla riga.'
              if da_abbinare else
              'Tutti i D.D.T. sono stati trovati: premi <strong>ACCOPPIA</strong> per salvare il file unico.')

    return scheda(
        BLU if da_abbinare else CIANO,
        f'<div style="font-size:14px; font-weight:700; color:#111827;">'
        f'Fattura {esc(dati.get("numero_fattura"))} del {esc(dati.get("data_fattura"))}</div>'
        f'<div style="font-size:12px; color:{GRIGIO}; padding-bottom:6px;">'
        f'{esc(dati.get("fornitore"))} &nbsp;&bull;&nbsp; ferma da '
        f'<strong>{fattura.get("giorni_attesa", 0)}</strong> giorni</div>'
        f'<div style="font-size:13px; color:#111827;">{azione}</div>'
    )


def _riga_ddt(ddt):
    """Una bolla in archivio che nessuna fattura ha mai agganciato."""
    return scheda(
        GRIGIO,
        f'<div style="font-size:14px; font-weight:700; color:#111827;">'
        f'DDT {esc(ddt.get("numero_ddt"))} del {esc(ddt.get("data_ddt"))}</div>'
        f'<div style="font-size:12px; color:{GRIGIO};">{esc(ddt.get("fornitore"))} '
        f'&nbsp;&bull;&nbsp; consegna a {esc(ddt.get("ragione_sociale_consegna")) or "&mdash;"} '
        f'&nbsp;&bull;&nbsp; in archivio da <strong>{ddt.get("giorni_attesa", 0)}</strong> giorni</div>'
    )


def _sezione(titolo, spiegazione, voci, disegna):
    if not voci:
        return ""
    return (titolo_sezione(f"{titolo} ({len(voci)})", spiegazione)
            + "".join(disegna(v) for v in voci[:MAX_RIGHE])
            + troncamento(len(voci), MAX_RIGHE))


def componi(attese, da_accoppiare, ddt_orfani, giorni_fattura, giorni_click,
            giorni_ddt=None):
    """(oggetto, corpo_html), oppure None se non c'e' niente da sollecitare.

    giorni_ddt vale quanto giorni_fattura se non viene passato: era un numero
    solo fino al 2026-09-10, e chi chiama con la vecchia firma deve continuare a
    ricevere la mail di prima e non una senza il numero delle bolle.
    """
    if giorni_ddt is None:
        giorni_ddt = giorni_fattura

    attese = list(attese or [])
    da_accoppiare = list(da_accoppiare or [])
    ddt_orfani = list(ddt_orfani or [])

    da_confermare = [f for f in attese if (f.get("attesa") or {}).get("da_confermare")]
    attende_ddt = [f for f in attese if not (f.get("attesa") or {}).get("da_confermare")]

    if not attese and not da_accoppiare and not ddt_orfani:
        return None

    corpo = (
        _sezione(
            "Da confermare a mano",
            f"Ferme da oltre {giorni_fattura} giorni. Il D.D.T. risulta gi&agrave; in archivio ma "
            "con un numero diverso: va corretto dalla dashboard, da solo non si sblocca.",
            da_confermare, lambda f: _riga_fattura(f, AMBRA),
        )
        + _sezione(
            "DDT mai arrivati",
            f"Ferme da oltre {giorni_fattura} giorni. Le bolle non sono ancora state scansionate: "
            "quando arrivano, la fattura si aggancia da sola.",
            attende_ddt, lambda f: _riga_fattura(f, ROSSO),
        )
        + _sezione(
            "Aspettano solo un click",
            f"Ferme da oltre {giorni_click} giorni. Non manca nessun documento: bastano due clic "
            "in dashboard.",
            da_accoppiare, _riga_click,
        )
        + _sezione(
            "Bolle senza fattura",
            f"Scansionate da oltre {giorni_ddt} giorni e mai fatturate: o la fattura non &egrave; "
            "arrivata, o nessuno ne ha ancora chiesto l&apos;abbinamento.",
            ddt_orfani, _riga_ddt,
        )
    )

    totale = len(attese)
    sottotitolo = (
        f"{totale} {plurale(totale, 'fattura', 'fatture')} in attesa dei documenti di trasporto"
        + (f", {len(da_accoppiare)} da chiudere con un click" if da_accoppiare else "")
        + (f", {len(ddt_orfani)} {plurale(len(ddt_orfani), 'bolla', 'bolle')} senza fattura"
           if ddt_orfani else "")
        + "."
    )

    pezzi = []
    if attese:
        pezzi.append(f"{totale} {plurale(totale, 'fattura', 'fatture')} da oltre {giorni_fattura} giorni")
    if da_accoppiare:
        pezzi.append(f"{len(da_accoppiare)} da accoppiare")
    if ddt_orfani:
        pezzi.append(f"{len(ddt_orfani)} {plurale(len(ddt_orfani), 'bolla', 'bolle')} "
                     f"da oltre {giorni_ddt} giorni")

    oggetto = "Documenti fermi: " + ", ".join(pezzi)
    if da_confermare:
        oggetto += f" ({len(da_confermare)} da confermare a mano)"

    # Il titolo dice il numero solo quando ce n'e' uno solo da dire: con soglie
    # diverse sarebbe falso per meta' della mail, e ogni sezione ha gia' il suo.
    titolo = (f"Fermi da oltre {giorni_fattura} giorni"
              if giorni_fattura == giorni_ddt else "Fermi da troppo tempo")

    return oggetto, pagina(
        titolo,
        sottotitolo,
        corpo,
        anteprima=f"{totale} fatture in attesa, {len(ddt_orfani)} bolle senza fattura",
    )
