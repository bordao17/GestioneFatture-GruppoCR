"""Logica di classificazione dei documenti estratti in stato OK / CHECK / KO."""

CAMPI_OBBLIGATORI = ["fornitore", "numero_ddt", "data_ddt", "indirizzo_consegna"]


def determina_stato(dati_estratti, campi_obbligatori=CAMPI_OBBLIGATORI):
    """
    Decide lo stato del documento (OK / CHECK / KO) in base a:
    - quanti campi obbligatori sono stati effettivamente estratti (sul dato UNITO del gruppo)
    - se una qualsiasi pagina del gruppo ha segnalato bassa leggibilità

    Regole:
    - 0 campi trovati                         -> KO (documento non leggibile / vuoto)
    - tutti i campi trovati E leggibilità OK  -> OK
    - tutti gli altri casi (parziale, oppure
      completo ma con leggibilità bassa)      -> CHECK (va rivisto manualmente)
    """
    campi_trovati = sum(1 for campo in campi_obbligatori if dati_estratti.get(campo))
    leggibilita_bassa = bool(dati_estratti.get("leggibilita_bassa", False))

    if campi_trovati == 0:
        return "KO", campi_trovati
    elif campi_trovati == len(campi_obbligatori) and not leggibilita_bassa:
        return "OK", campi_trovati
    else:
        return "CHECK", campi_trovati