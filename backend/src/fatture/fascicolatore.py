"""
Costruzione del PDF unico (fascicolo) fattura + DDT abbinati.

Ordine delle pagine:
  1. pagina di riepilogo generata qui (indice del fascicolo: cosa si e'
     abbinato e cosa no — la fattura e' un XML, senza questa pagina il
     fascicolo non direbbe da dove arriva);
  2. copia di cortesia della fattura, se il fornitore l'ha allegata all'XML;
  3. i PDF dei DDT, nell'ordine in cui la fattura li cita.
"""

import os

import fitz

from src.comune.registro import percorso_pdf_documento

# A4 in punti PDF.
LARGHEZZA_PAGINA = 595
ALTEZZA_PAGINA = 842
MARGINE = 56

ESITI_DA_ALLEGARE = ("abbinato", "probabile")


def primo_pdf_allegato(allegati):
    """Byte del primo allegato PDF della fattura, se presente."""
    for allegato in allegati or []:
        if allegato.get("formato") == "PDF" and allegato.get("dati", b"").startswith(b"%PDF"):
            return allegato["dati"]
    return None


def _riga(pagina, testo, y, dimensione=10, grassetto=False):
    """Scrive una riga e restituisce la y successiva."""
    pagina.insert_text(
        (MARGINE, y), testo,
        fontsize=dimensione,
        fontname="hebo" if grassetto else "helv",
    )
    return y + dimensione + 4


def pagina_riepilogo(documento, fattura, righe):
    """Prima pagina del fascicolo: dati di testata della fattura e stato dei DDT."""
    pagina = documento.new_page(width=LARGHEZZA_PAGINA, height=ALTEZZA_PAGINA)
    y = MARGINE

    y = _riga(pagina, f"FATTURA {fattura.get('numero_fattura', '')}", y, 16, grassetto=True)
    y = _riga(pagina, f"del {fattura.get('data_fattura', '')}", y, 11)
    y += 10

    y = _riga(pagina, "FORNITORE", y, 9, grassetto=True)
    y = _riga(pagina, fattura.get("fornitore_xml") or fattura.get("fornitore", ""), y)
    if fattura.get("partita_iva"):
        y = _riga(pagina, f"P.IVA {fattura['partita_iva']}", y)
    y += 8

    y = _riga(pagina, "CLIENTE", y, 9, grassetto=True)
    y = _riga(pagina, fattura.get("cessionario", ""), y)
    y += 8

    if fattura.get("importo_totale"):
        y = _riga(pagina, f"Importo totale documento: {fattura['importo_totale']} EUR", y)
        y += 8

    y += 6

    # In una accompagnatoria non c'e' nessun DDT "citato": il documento di
    # trasporto e' la fattura stessa, ritrovata tra le scansioni col suo numero.
    # Scriverlo qui evita che chi apre il fascicolo cerchi una bolla che non
    # esiste.
    accompagnatoria = any(riga.get("origine") == "numero_fattura" for riga in righe)
    if accompagnatoria:
        y = _riga(pagina, "FATTURA ACCOMPAGNATORIA", y, 9, grassetto=True)
        y = _riga(pagina, "La merce viaggia con la fattura: il documento allegato e' la sua scansione.", y, 9)
        y += 2
    else:
        y = _riga(pagina, f"DOCUMENTI DI TRASPORTO CITATI ({len(righe)})", y, 9, grassetto=True)
        y += 2

    for riga in righe:
        etichetta = {
            "abbinato": "OK",
            "probabile": "DA VERIFICARE",
            "non_trovato": "NON TROVATO",
        }.get(riga["esito"], riga["esito"].upper())

        titolo = "DOCUMENTO" if riga.get("origine") == "numero_fattura" else "DDT"
        y = _riga(pagina, f"{titolo} {riga['numero_ddt']} del {riga['data_ddt']}  [{etichetta}]", y, 10, grassetto=True)
        y = _riga(pagina, f"    {riga['motivo']}", y, 9)
        y += 4

        if y > ALTEZZA_PAGINA - MARGINE:  # riepiloghi lunghi: si continua sotto
            pagina = documento.new_page(width=LARGHEZZA_PAGINA, height=ALTEZZA_PAGINA)
            y = MARGINE

    return documento


def costruisci_fascicolo(fattura, righe, percorso_dest):
    """
    Genera il PDF unico e restituisce (numero_pagine, id_ddt_allegati).

    I DDT non trovati non fermano la costruzione: il fascicolo parziale e'
    comunque il modo piu' comodo per capire cosa manca.
    """
    documento = fitz.open()
    allegati = []

    try:
        pagina_riepilogo(documento, fattura, righe)

        # Un PDF illeggibile non deve mai far saltare il fascicolo: sia la copia
        # di cortesia sia i PDF dei DDT sono file che arrivano da fuori, e il
        # riepilogo con i DDT restanti vale comunque piu' di un errore 500.
        copia_cortesia = primo_pdf_allegato(fattura.get("allegati"))
        if copia_cortesia:
            try:
                with fitz.open(stream=copia_cortesia, filetype="pdf") as pdf_fattura:
                    documento.insert_pdf(pdf_fattura)
            except Exception as errore:
                print(f"⚠️ Copia di cortesia della fattura non allegabile, ignorata: {errore}")

        for riga in righe:
            if riga["esito"] not in ESITI_DA_ALLEGARE or not riga.get("documento_id"):
                continue

            percorso = percorso_pdf_documento(riga["stato_ddt"], riga["documento_id"])
            if not percorso or not os.path.exists(percorso):
                print(f"⚠️ PDF mancante per il DDT {riga['documento_id']}, non allegato al fascicolo")
                continue

            try:
                with fitz.open(percorso) as pdf_ddt:
                    documento.insert_pdf(pdf_ddt)
            except Exception as errore:
                print(f"⚠️ PDF del DDT {riga['documento_id']} non allegabile, ignorato: {errore}")
                continue

            allegati.append(riga["documento_id"])

        os.makedirs(os.path.dirname(percorso_dest), exist_ok=True)
        documento.save(percorso_dest)
        return documento.page_count, allegati
    finally:
        documento.close()
