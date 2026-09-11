"""Mail di fine scansione delle fatture elettroniche: che cosa e' entrato.

Porting del nodo Code "Html Fatture" di n8n (n8n_snippets/riepilogo_fatture_email.js).

Questa mail non racconta un abbinamento, racconta un INGRESSO: leggere una
fattura e cercarle i D.D.T. sono due gesti distinti, quindi tutto cio' che passa
di qui e' DA_ABBINARE e i D.D.T. si cercano dalla dashboard con "Abbina tutte".
Gli altri stati restano gestiti perche' li produce il ricontrollo della coda.

Le anomalie sul cedente (P.IVA assente, o diversa da quella confermata in
anagrafica) non hanno impedito niente: la fattura e' in archivio. Sono pero'
l'unica cosa in questa mail su cui qualcuno debba davvero intervenire, e per
questo hanno un blocco loro.
"""

from src.notifiche.impaginazione import (
    AMBRA, BLU, GRIGIO, ROSSO, VERDE, barra, conteggi, esc, pagina, plurale,
    riga, scheda, testo_piccolo, troncamento,
)

MAX_RIGHE = 25

COLORI_STATO = {
    "DA_ABBINARE": BLU,
    "ABBINATA": VERDE,
    "IN_ATTESA": AMBRA,
    "NON_ABBINATA": ROSSO,
}

# Cosa e' successo a un singolo riferimento DDT. Le stesse parole della
# dashboard (etichetteFatture.js): la mail e la schermata devono chiamare le
# cose allo stesso modo, o sembrano due sistemi diversi.
ESITI = {
    "abbinato": (VERDE, "abbinato"),
    "probabile": (AMBRA, "da confermare"),
    "non_trovato": (ROSSO, "DDT non ancora arrivato"),
    "da_abbinare": (BLU, "non ancora cercato"),
}


def _blocco_fattura(fattura):
    """Una pratica non ancora chiusa, con i suoi riferimenti uno per uno."""
    stato = fattura.get("stato", "")
    accompagnatoria = fattura.get("tipo") == "accompagnatoria"
    righe_ddt = fattura.get("ddt") or []

    voci = []
    for ddt in righe_ddt:
        colore, etichetta = ESITI.get(ddt.get("esito"), (GRIGIO, esc(ddt.get("esito", ""))))
        voci.append(
            f'<tr><td style="padding:4px 0; font-size:13px; color:#111827;">'
            f'{"Documento" if accompagnatoria else "DDT"} <strong>{esc(ddt.get("numero_ddt"))}</strong> '
            f'del {esc(ddt.get("data_ddt"))}'
            f'<span style="color:{colore}; font-weight:600;">&nbsp;&bull;&nbsp;{etichetta}</span>'
            f'<div style="font-size:12px; color:{GRIGIO};">{esc(ddt.get("motivo", ""))}</div>'
            f'</td></tr>'
        )

    if not righe_ddt:
        voci.append(
            f'<tr><td style="padding:4px 0; font-size:13px; color:{GRIGIO};">'
            'La fattura non cita alcun documento di trasporto e non riporta dati di trasporto: '
            'non c&apos;&egrave; nessuna bolla da attendere.</td></tr>'
        )

    # Le due attese non si risolvono nello stesso modo, ed e' la sola cosa utile
    # da dire qui: una si chiude da sola, l'altra aspetta una correzione a mano.
    nota = ""
    if stato == "IN_ATTESA":
        da_confermare = (fattura.get("attesa") or {}).get("da_confermare")
        if da_confermare:
            testo = (f'{da_confermare} {plurale(da_confermare, "riferimento", "riferimenti")} '
                     'da confermare a mano: il DDT c&apos;&egrave; gi&agrave;, ma con un numero diverso.')
        elif accompagnatoria:
            testo = 'In coda: la fattura accompagnatoria non &egrave; ancora stata scansionata tra i D.D.T.'
        else:
            testo = 'In coda: verr&agrave; ricontrollata da sola a ogni nuova estrazione di D.D.T.'
        nota = f'<div style="font-size:12px; color:#92400e; padding-top:6px;">{testo}</div>'

    return scheda(
        COLORI_STATO.get(stato, GRIGIO),
        f'<div style="font-size:14px; font-weight:700; color:#111827;">'
        f'Fattura {esc(fattura.get("numero_fattura"))} del {esc(fattura.get("data_fattura"))}</div>'
        f'<div style="font-size:12px; color:{GRIGIO}; padding-bottom:8px;">'
        f'{esc(fattura.get("fornitore"))} &nbsp;&bull;&nbsp; '
        f'{fattura.get("ddt_abbinati", 0)}/{fattura.get("ddt_totali", 0)} DDT abbinati'
        f'{" &nbsp;&bull;&nbsp; accompagnatoria" if accompagnatoria else ""}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-collapse:collapse;">{"".join(voci)}</table>{nota}'
    )


def componi(esito):
    """(oggetto, corpo_html) da cio' che restituisce la scansione delle fatture.

    esito: l'uscita di POST /api/fatture/scansiona — fatture, falliti.
    """
    fatture = esito.get("fatture") or []
    falliti = esito.get("falliti") or []

    def conta(stato):
        return sum(1 for f in fatture if f.get("stato") == stato)

    da_abbinare = conta("DA_ABBINARE")
    abbinate = conta("ABBINATA")
    in_attesa = conta("IN_ATTESA")
    non_abbinate = conta("NON_ABBINATA")
    duplicate = conta("DUPLICATA")
    segnalate = [f for f in fatture if f.get("segnalazioni")]

    # Le duplicate restano fuori dal totale: non sono un lavoro andato male,
    # sono un lavoro che non c'e' proprio stato.
    totale = da_abbinare + abbinate + in_attesa + non_abbinate

    corpo = [
        barra([(da_abbinare, BLU), (abbinate, VERDE), (in_attesa, AMBRA), (non_abbinate, ROSSO)]),
        conteggi([("Da abbinare", da_abbinare, BLU),
                  ("Pronte da accoppiare", abbinate, VERDE),
                  ("In attesa", in_attesa, AMBRA),
                  ("Senza DDT", non_abbinate, ROSSO)]),
    ]

    if duplicate:
        corpo.append(testo_piccolo(
            f'{duplicate} gi&agrave; {plurale(duplicate, "registrata", "registrate")} '
            '(la deduplica &egrave; su P.IVA + numero + data: nessuna pratica doppia).'
        ))

    if segnalate:
        dettagli = "".join(
            f'<div style="font-size:12px; padding-top:6px;"><strong>{esc(f.get("numero_fattura"))}</strong> '
            f'&mdash; {esc(f.get("fornitore"))}<br>'
            + "<br>".join(esc(s.get("messaggio", "")) for s in f.get("segnalazioni", []))
            + '</div>'
            for f in segnalate
        )
        corpo.append(scheda(
            AMBRA,
            f'<div style="font-size:13px; color:#92400e;">'
            f'<strong>{len(segnalate)} {plurale(len(segnalate), "fattura", "fatture")} '
            f'da controllare in anagrafica</strong>'
            '<div style="font-size:12px; padding-top:2px;">Archiviate lo stesso: il fornitore non '
            'filtra nulla. Va per&ograve; sistemata la P.IVA, che &egrave; l&apos;unica chiave esatta '
            'fra i due lati del sistema.</div>'
            f'{dettagli}</div>',
            sfondo="#fffbeb",
        ))

    # Le pronte da accoppiare non si elencano: per quelle non c'e' niente da capire.
    da_rivedere = [f for f in fatture if f.get("stato") in ("IN_ATTESA", "NON_ABBINATA")]
    if da_rivedere:
        corpo.append(riga(
            '<div style="font-size:12px; font-weight:700; color:#374151; text-transform:uppercase; '
            'letter-spacing:.5px;">Non ancora chiuse</div>',
            padding="padding:6px 32px 10px 32px;",
        ))
        corpo.extend(_blocco_fattura(f) for f in da_rivedere[:MAX_RIGHE])
        corpo.append(troncamento(len(da_rivedere), MAX_RIGHE, "fatture in coda"))

    if falliti:
        elenco = "".join(
            f'<div style="font-size:12px; padding-top:4px;">{esc(f.get("file", ""))} '
            f'&mdash; {esc(f.get("motivo", ""))}</div>'
            for f in falliti
        )
        corpo.append(scheda(
            ROSSO,
            f'<div style="font-size:13px; color:#991b1b;">'
            f'<strong>{len(falliti)} file non elaborati</strong>{elenco}'
            '<div style="font-size:12px; padding-top:6px;">Sono rimasti in FATTURE/da_leggere.</div></div>',
            sfondo="#fef2f2",
        ))

    if not totale and not falliti:
        corpo.append(testo_piccolo(
            "Nessuna fattura nuova da leggere." if duplicate else "Nessun file da leggere."
        ))

    sottotitolo = (
        f"{totale} {plurale(totale, 'fattura archiviata', 'fatture archiviate')}"
        + (" &mdash; i D.D.T. si cercano dalla dashboard, con <strong>Abbina tutte</strong>"
           if da_abbinare else "")
    )

    if totale == 0 and not falliti:
        oggetto = (f"Fatture: nessuna nuova da elaborare ({duplicate} gia' registrate)"
                   if duplicate else "Fatture: nessun file da elaborare")
    else:
        oggetto = f"Fatture: {totale} archiviate, {da_abbinare} da abbinare"
        if segnalate:
            oggetto += f", {len(segnalate)} da controllare"

    return oggetto, pagina(
        "Fatture elettroniche in ingresso",
        sottotitolo,
        "".join(corpo),
        anteprima=f"{totale} archiviate, {da_abbinare} da abbinare",
    )
