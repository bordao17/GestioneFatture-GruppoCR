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
            doc_attivo = pagina
        else:
            stesso_fornitore = (fornitore == doc_attivo.get("fornitore", "")) or is_fornitore_invalido
            stesso_numero = (numero_ddt == doc_attivo.get("numero_ddt", "")) or is_numero_invalido

            if stesso_fornitore and stesso_numero:
                for key, value in pagina.items():
                    # Unisce i campi mancanti
                    if doc_attivo.get(key, "").lower() == "dato mancante" and value.lower() != "dato mancante":
                        doc_attivo[key] = value
                    # Se ci sono nuove note_layout, le aggiunge
                    elif key == "note_layout" and value and not doc_attivo.get("note_layout"):
                        doc_attivo["note_layout"] = value
            else:
                documenti_finali.append(doc_attivo)
                doc_attivo = pagina

    if doc_attivo:
        documenti_finali.append(doc_attivo)

    return documenti_finali