"""Mail di fine scansione dei D.D.T.: quante bolle sono entrate e quali vanno riviste.

Porting del nodo Code "Html Riepilogo" di n8n (n8n_snippets/riepilogo_email.js),
con due cose in piu' che di la' non si potevano avere: i file che la scansione
non e' riuscita a leggere (senza, una scansione notturna fallita a meta' non lo
direbbe a nessuno) e le pratiche fattura diventate pronte da accoppiare grazie
alle bolle appena estratte.

Per ogni voce CHECK la mail dice PERCHE' e' finita li'. E' l'unica ragione per
cui vale la pena leggerla invece di aprire subito la dashboard.
"""

from src.ddt.classificatore import CAMPI_OBBLIGATORI
from src.notifiche.impaginazione import (
    AMBRA, GRIGIO, ROSSO, VERDE, barra, conteggi, esc, pagina, plurale, riga,
    scheda, testo_piccolo, troncamento, valore_o_mancante,
)

# Oltre questa soglia la mail diventa un elenco che nessuno legge: il resto si
# guarda in dashboard, dove per giunta si puo' correggere.
MAX_RIGHE = 25

# Gli stessi 4 campi su cui il backend decide OK/CHECK/KO, presi da dove sono
# decisi: se un giorno ne aggiungiamo uno, la mail lo dice senza ritocchi.
ETICHETTE_CAMPI = {
    "fornitore": "Fornitore",
    "numero_ddt": "N. DDT",
    "data_ddt": "Data",
    "indirizzo_consegna": "Indirizzo di consegna",
}


def _motivo_check(dati):
    """Perche' questo documento e' finito in CHECK, in una riga."""
    if dati.get("indirizzo_scartato"):
        return ("Indirizzo scartato perche' vietato per questo fornitore: "
                + esc(dati["indirizzo_scartato"]))

    mancanti = [ETICHETTE_CAMPI.get(campo, campo)
                for campo in CAMPI_OBBLIGATORI if not str(dati.get(campo) or "").strip()]
    if mancanti:
        return "Non letto: " + esc(", ".join(mancanti))

    if dati.get("leggibilita_bassa"):
        return "Campi completi, ma scansione di bassa qualita"

    # Dopo i campi mancanti e la leggibilita', perche' quelle due dicono cosa
    # c'e' da fare; questa dice solo che il documento va riletto comunque. Se
    # non si dicesse, un CHECK con tutti i campi pieni e la scansione buona
    # sembrerebbe finito li' per errore.
    if dati.get("fornitore_critico"):
        return "Fornitore critico: sempre da ricontrollare"

    return "Da verificare"


def _tabella_check(voci):
    intestazioni = "".join(
        f'<th align="left" style="padding:9px 14px; font-size:11px; font-weight:600; '
        f'letter-spacing:.5px; text-transform:uppercase; color:#92400e; '
        f'border-bottom:1px solid #fde68a;">{testo}</th>'
        for testo in ("Fornitore", "N. DDT", "Data", "Motivo")
    )

    cella = ("padding:10px 14px; border-bottom:1px solid #f5e9c8; font-size:13px; "
             "color:#374151; vertical-align:top;")
    righe = []
    for indice, voce in enumerate(voci[:MAX_RIGHE]):
        dati = voce.get("dati", {})
        sfondo = "#ffffff" if indice % 2 == 0 else "#fffdf6"
        righe.append(
            f'<tr style="background:{sfondo};">'
            f'<td style="{cella}">'
            f'<div style="font-weight:600; color:#111827;">{valore_o_mancante(dati.get("fornitore"))}</div>'
            f'<div style="margin-top:2px; font-size:11px; color:#9ca3af;">{esc(voce.get("file_origine", ""))}</div>'
            f'</td>'
            f'<td style="{cella} font-family:Consolas,Menlo,monospace; white-space:nowrap;">'
            f'{valore_o_mancante(dati.get("numero_ddt"))}</td>'
            f'<td style="{cella} white-space:nowrap;">{valore_o_mancante(dati.get("data_ddt"))}</td>'
            f'<td style="{cella} color:#92400e;">{_motivo_check(dati)}</td>'
            f'</tr>'
        )

    nascosti = len(voci) - MAX_RIGHE
    if nascosti > 0:
        righe.append(
            f'<tr><td colspan="4" style="padding:10px 14px; font-size:12px; color:#92400e; '
            f'background:#fef3c7;">e altri {nascosti} documenti da controllare: '
            f'aprili dalla dashboard.</td></tr>'
        )

    return riga(
        f'<div style="font-size:14px; font-weight:600; color:#92400e; margin-bottom:10px;">'
        f'Da controllare manualmente ({len(voci)})</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse; border:1px solid #fde68a; border-radius:8px; overflow:hidden;">'
        f'<tr style="background:#fef3c7;">{intestazioni}</tr>{"".join(righe)}</table>'
    )


def componi(riepilogo, sbloccate=(), falliti=(), duplicati=()):
    """(oggetto, corpo_html) della mail di riepilogo di una scansione D.D.T.

    riepilogo: l'uscita di calcola_riepilogo() — ok, check, ko, totale, voci_check.
    sbloccate: le fatture diventate pronte da accoppiare (fatture_sbloccate).
    falliti:   i file che la scansione non ha saputo leggere [{file, motivo}].
    duplicati: le pagine saltate perche' gia' archiviate
               [{file_origine, pagina, id_originale, stato_originale}].
    """
    ok = int(riepilogo.get("ok", 0))
    check = int(riepilogo.get("check", 0))
    ko = int(riepilogo.get("ko", 0))
    totale = int(riepilogo.get("totale", ok + check + ko))
    voci_check = riepilogo.get("voci_check") or []

    corpo = [
        barra([(ok, VERDE), (check, AMBRA), (ko, ROSSO)]),
        conteggi([("Letti OK", ok, VERDE),
                  ("Da controllare", check, AMBRA),
                  ("Non letti", ko, ROSSO)]),
    ]

    if check:
        corpo.append(_tabella_check(voci_check))

    if ko:
        corpo.append(scheda(
            ROSSO,
            f'<div style="font-size:13px; color:#991b1b;">'
            f'<strong>{ko} {plurale(ko, "documento non letto", "documenti non letti")} (KO):</strong> '
            f'il modello non ha estratto nessun campo. Vanno compilati a mano dalla dashboard, '
            f'guardando la scansione.</div>',
            sfondo="#fef2f2",
        ))

    # I file che non sono nemmeno arrivati all'estrazione. In una scansione
    # notturna e' l'informazione piu' importante di tutte: il file e' rimasto
    # nella cartella in ingresso (quelli falliti non si rimuovono) e nessuno
    # sarebbe li' a vederlo.
    if falliti:
        elenco = "".join(
            f'<div style="font-size:12px; padding-top:4px;">{esc(f.get("file", ""))} '
            f'&mdash; {esc(f.get("motivo", ""))}</div>'
            for f in falliti
        )
        corpo.append(scheda(
            ROSSO,
            f'<div style="font-size:13px; color:#991b1b;"><strong>{len(falliti)} file non elaborati</strong>'
            f'{elenco}<div style="font-size:12px; padding-top:6px;">Sono rimasti in '
            f'DDT/da_leggere: si riprovano dopo aver capito perche&apos;.</div></div>',
            sfondo="#fef2f2",
        ))

    # Le pagine gia' viste, saltate prima di arrivare al modello. Non e' un
    # errore e non richiede nessun intervento: si dice perche' altrimenti i
    # conteggi qui sopra non tornerebbero con la pila di fogli che qualcuno ha
    # messo nello scanner, e chi legge penserebbe a un'estrazione mancata.
    if duplicati:
        elenco = "".join(
            f'<div style="font-size:12px; padding-top:4px;">'
            f'{esc(d.get("file_origine", ""))} &mdash; pagina {esc(str(d.get("pagina", "")))}, '
            f'gia&apos; archiviata come <span style="font-family:Consolas,Menlo,monospace;">'
            f'{esc(str(d.get("id_originale", ""))[:8])}</span> '
            f'({esc(d.get("stato_originale", ""))})</div>'
            for d in duplicati[:MAX_RIGHE]
        )
        corpo.append(scheda(
            GRIGIO,
            f'<div style="font-size:13px; color:#374151;">'
            f'<strong>{len(duplicati)} {plurale(len(duplicati), "pagina gia&apos; archiviata", "pagine gia&apos; archiviate")}</strong>'
            f'{elenco}<div style="font-size:12px; padding-top:6px;">Non sono state rilette '
            f'e non hanno creato nessun documento nuovo: erano identiche a una pagina '
            f'gia&apos; in archivio.</div></div>',
        ))
        corpo.append(troncamento(len(duplicati), MAX_RIGHE, "pagine duplicate"))

    if sbloccate:
        elenco = "".join(
            f'<div style="font-size:12px; padding-top:4px;">Fattura '
            f'<strong>{esc(s.get("numero_fattura", ""))}</strong> &mdash; {esc(s.get("fornitore", ""))}</div>'
            for s in sbloccate
        )
        corpo.append(scheda(
            VERDE,
            f'<div style="font-size:13px; color:#166534;">'
            f'<strong>{len(sbloccate)} {plurale(len(sbloccate), "pratica pronta", "pratiche pronte")} '
            f'da accoppiare</strong> grazie a queste bolle{elenco}'
            f'<div style="font-size:12px; padding-top:6px;">Manca solo la firma: '
            f'ACCOPPIA sulla riga, nella sezione Fatture.</div></div>',
            sfondo="#f0fdf4",
        ))

    if totale and not check and not ko:
        corpo.append(scheda(
            VERDE,
            '<div style="font-size:14px; color:#166534;"><strong>Nessun documento da rivedere.</strong> '
            'Tutti i D.D.T. di questa scansione sono stati letti per intero.</div>',
            sfondo="#f0fdf4",
        ))

    if not totale and not falliti and not duplicati:
        corpo.append(testo_piccolo("Nessun documento elaborato in questa esecuzione."))

    if totale == 0 and duplicati:
        # Caso tutto suo: i fogli sono passati, ma erano gia' tutti in archivio.
        # Dire "nessun documento elaborato" e basta manderebbe a cercare un guasto
        # che non c'e'.
        oggetto = f"Riepilogo D.D.T. - {len(duplicati)} pagine gia' archiviate"
        sottotitolo = "Nessun documento nuovo: erano tutte pagine gia&apos; viste"
    elif totale == 0:
        oggetto = "Riepilogo D.D.T. - nessun documento elaborato"
        sottotitolo = "Nessuna scansione da leggere in DDT/da_leggere"
    else:
        oggetto = f"Riepilogo D.D.T. - {ok} OK / {check} da controllare / {ko} KO"
        sottotitolo = (f"{totale} {plurale(totale, 'documento elaborato', 'documenti elaborati')}"
                       + (f", {check} da rivedere" if check else ""))

    if falliti:
        oggetto += f" ({len(falliti)} non elaborati)"

    return oggetto, pagina(
        "Riepilogo elaborazione D.D.T.",
        sottotitolo,
        "".join(corpo),
        anteprima=f"{ok} letti correttamente, {check} da controllare, {ko} non letti",
    )
