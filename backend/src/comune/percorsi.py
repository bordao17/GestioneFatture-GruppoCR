"""
Percorsi delle cartelle di archivio: unico punto del backend in cui vivono.

Prima "/fatture_lette" era ripetuto in quattro moduli; da quando i flussi sono
due (DDT e fatture elettroniche) e ognuno ha il suo archivio, tenerli sparsi
significherebbe sbagliarne uno alla prossima modifica.

Struttura sul disco dell'host, montata in Docker con gli stessi nomi:
    DDT/da_leggere      scansioni in ingresso (le guarda n8n)
    DDT/lette           OK.json, CHECK.json, KO.json + i PDF in OK/, CHECK/, KO/
    FATTURE/da_leggere  fatture elettroniche in ingresso (.xml / .xml.p7m)
    FATTURE/lette       FATTURE.json, ATTESA.json e gli XML originali
    ACCOPPIATE          i file unici fattura+DDT confermati dall'operatore
"""

import os

CARTELLA_DDT = os.getenv("CARTELLA_DDT", "/DDT/lette")
CARTELLA_FATTURE = os.getenv("CARTELLA_FATTURE", "/FATTURE/lette")

# Le due cartelle in ingresso. Le guarda n8n, ma dal 2026-09-08 ci scrive e ci
# legge anche la dashboard: "Aggiungi documento" ci deposita i file e
# "Analizza" ci passa sopra. Sono percorsi, non un archivio: quello che sta
# qui dentro non e' ancora stato lavorato.
CARTELLA_DDT_INGRESSO = os.getenv("CARTELLA_DDT_INGRESSO", "/DDT/da_leggere")
CARTELLA_FATTURE_INGRESSO = os.getenv("CARTELLA_FATTURE_INGRESSO", "/FATTURE/da_leggere")

# Dove finisce il file unico fattura+DDT quando l'operatore conferma
# l'accoppiamento. E' l'unica cartella pensata per essere aperta a mano da una
# persona, quindi i file dentro hanno un nome leggibile (fornitore, numero,
# data) e non un UUID: gli archivi di lavoro restano in DDT/ e FATTURE/.
CARTELLA_ACCOPPIATE = os.getenv("CARTELLA_ACCOPPIATE", "/ACCOPPIATE")

# Nomi dei registri del flusso fatture: sono anche i valori che distinguono i
# due archivi in cartella_registro(), quindi non sono stringhe qualsiasi.
# FATTURE = pratiche chiuse (abbinate, o senza DDT da aspettare).
# ATTESA  = la coda: fatture i cui DDT non sono ancora tutti arrivati. Sono due
#           file separati per la stessa ragione per cui OK/CHECK/KO lo sono:
#           lo stato di una pratica e' il registro in cui si trova, e la coda
#           va riletta per intero a ogni nuovo DDT, quindi conviene sia corta.
REGISTRO_FATTURE = "FATTURE"
REGISTRO_ATTESA = "ATTESA"
REGISTRI_FATTURE = (REGISTRO_FATTURE, REGISTRO_ATTESA)


def cartella_registro(stato):
    """Archivio a cui appartiene un registro: OK/CHECK/KO ai DDT, FATTURE e ATTESA al loro."""
    return CARTELLA_FATTURE if stato in REGISTRI_FATTURE else CARTELLA_DDT
