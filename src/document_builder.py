def elabora_pagine_in_documenti(dati_pagine):
    documenti_finali = []
    doc_attivo = None

    for pagina in dati_pagine:
        if not pagina:
            continue
        
        fornitore = pagina.get("fornitore", "").strip()
        numero_ddt = pagina.get("numero_ddt", "").strip()

        is_fornitore_invalido = (not fornitore or fornitore.lower() == "dato mancante")
        is_numero_invalido = (not numero_ddt or numero_ddt.lower() == "dato mancante")

        if doc_attivo is None:
            # Apriamo il primo documento del PDF
            doc_attivo = pagina
        else:
            # Controlliamo se è lo stesso fornitore e numero del documento in elaborazione
            stesso_fornitore = (fornitore == doc_attivo.get("fornitore", "")) or is_fornitore_invalido
            stesso_numero = (numero_ddt == doc_attivo.get("numero_ddt", "")) or is_numero_invalido

            if stesso_fornitore and stesso_numero:
                # È la CONTINUAZIONE del documento precedente (es. Pagina 2)
                # Integra i dati che prima erano mancanti (se ne trova di nuovi)
                for key, value in pagina.items():
                    if doc_attivo.get(key, "").lower() == "dato mancante" and value.lower() != "dato mancante":
                        doc_attivo[key] = value
            else:
                # NUOVO DOCUMENTO! Salviamo quello vecchio e partiamo col nuovo
                documenti_finali.append(doc_attivo)
                doc_attivo = pagina

    # Salviamo l'ultimo documento rimasto in memoria
    if doc_attivo:
        documenti_finali.append(doc_attivo)

    return documenti_finali