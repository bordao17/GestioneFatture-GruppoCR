"""Logica di classificazione dei documenti estratti in stato OK / CHECK / KO."""

CAMPI_OBBLIGATORI = ["fornitore", "numero_ddt", "data_ddt", "indirizzo_consegna"]


def determina_stato(dati_estratti, campi_obbligatori=CAMPI_OBBLIGATORI):
    """
    Decide lo stato del documento (OK / CHECK / KO) in base a:
    - quanti campi obbligatori sono stati effettivamente estratti (sul dato UNITO del gruppo)
    - se una qualsiasi pagina del gruppo ha segnalato bassa leggibilità
    - se il fornitore è marcato CRITICO in anagrafica

    Regole:
    - 0 campi trovati                         -> KO (documento non leggibile / vuoto)
    - tutti i campi trovati, leggibilità OK
      e fornitore non critico                 -> OK
    - tutti gli altri casi (parziale, oppure
      completo ma con leggibilità bassa o
      fornitore critico)                      -> CHECK (va rivisto manualmente)

    "fornitore_critico" arriva nei dati come "leggibilita_bassa": lo scrive la
    pipeline (annota_fornitore_critico), questa funzione lo legge senza sapere
    da dove viene e resta pura. Ha cinque chiamanti, uno per pagina e due per
    accorpamento: una lettura dell'anagrafica qui dentro sarebbe una query a
    Postgres per ciascuno.

    Non tocca il KO: lì il fornitore non è stato letto affatto, quindi non c'è
    modo di sapere che era critico — e un KO non va spostato da nessun
    automatismo. La criticità sposta solo OK -> CHECK.
    """
    campi_trovati = sum(1 for campo in campi_obbligatori if dati_estratti.get(campo))
    leggibilita_bassa = bool(dati_estratti.get("leggibilita_bassa", False))
    fornitore_critico = bool(dati_estratti.get("fornitore_critico", False))

    if campi_trovati == 0:
        return "KO", campi_trovati
    elif (campi_trovati == len(campi_obbligatori)
            and not leggibilita_bassa and not fornitore_critico):
        return "OK", campi_trovati
    else:
        return "CHECK", campi_trovati