"""Le route HTTP, un modulo per entita' del dominio.

main.py era arrivato a 1726 righe e conteneva quattro cose diverse: l'avvio
dell'applicazione, gli aiutanti condivisi, i due corpi di elaborazione e
trentasei route. Qui sotto ognuna sta nel modulo della sua entita', con la
stessa divisione che vale in src/ e nel frontend — per FLUSSO, non per layer:

    supporto.py      gli aiutanti che piu' di un router chiama (nessuna route)
    lavorazione.py   elabora_ddt() ed elabora_fattura(), due chiamanti ciascuno
    fornitori.py     /api/fornitori*
    documenti.py     /api/documents*, /api/pdf, /api/elaborazione, /riepilogo,
                     /estrai-ddt
    fatture.py       /abbina-fattura, /api/fatture*, /api/ddt/senza-fattura,
                     /api/pdf-fattura
    ingresso.py      /api/ddt/carica|scansiona, /api/fatture/carica|scansiona,
                     /api/ingresso, piu' i tre lavori del pianificatore
    impostazioni.py  /api/pianificazione*, /api/notifiche/prova,
                     /api/configurazione

Due cose che il taglio NON ha cambiato, e che non vanno cambiate dopo:

1. I percorsi sono rimasti assoluti e completi. Nessun router ha un prefix, e
   non e' una dimenticanza: con un prefix="/api/fatture" il percorso di una
   route si leggerebbe meta' qui e meta' in main.py, e /abbina-fattura o
   /api/ddt/senza-fattura non ci starebbero comunque dentro. Cercare
   "/api/fatture/attese" nel repo deve continuare a trovare una riga sola.

2. L'ordine conta ancora. FastAPI risolve le route nell'ordine in cui sono
   registrate, quindi conta sia l'ordine DENTRO un modulo (/api/fatture/attese
   prima di /api/fatture/{id_fattura}) sia l'ordine degli include_router in
   main.py, che e' scritto li' con la sua ragione.
"""
