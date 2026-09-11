"""L'invio SMTP: unico punto del backend che parla con un server di posta.

Le credenziali stanno nella sezione Configurazione (file su volume, ripiego sul
docker-compose) e si leggono con valore() a ogni invio, mai in una costante di
modulo: cambiare il server SMTP dalla dashboard deve avere effetto subito, che
e' tutto il motivo per cui quella schermata esiste.

REGOLA: un errore di posta non deve mai far fallire cio' che stava andando
bene. Le pipeline chiamano invia_silenzioso(), che registra il problema nei log
e restituisce un esito; solo i due pulsanti espliciti della dashboard (prova di
invio, sollecito adesso) usano invia() e vedono l'eccezione.
"""

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from src.comune.configurazione import valore

# Un server di posta che non risponde non deve tenere fermo il thread del
# pianificatore per minuti: dopo mezzo minuto la mail e' persa, e va bene cosi'.
TIMEOUT = 30


def destinatari():
    """Gli indirizzi configurati, separati da virgola o punto e virgola."""
    grezzo = str(valore("MAIL_DESTINATARI") or "")
    return [pezzo.strip() for pezzo in grezzo.replace(";", ",").split(",") if pezzo.strip()]


def mittente():
    """Il From: quello configurato, altrimenti l'utente SMTP."""
    return str(valore("MAIL_MITTENTE") or "").strip() or str(valore("SMTP_UTENTE") or "").strip()


def configurata():
    """Vero se c'e' abbastanza per provarci: un server e almeno un destinatario."""
    return bool(str(valore("SMTP_HOST") or "").strip()) and bool(destinatari())


def descrizione():
    """Lo stato delle notifiche per la dashboard, senza mai la password."""
    return {
        "configurata": configurata(),
        "server": str(valore("SMTP_HOST") or "").strip(),
        "porta": valore("SMTP_PORTA"),
        "sicurezza": valore("SMTP_SICUREZZA"),
        "mittente": mittente(),
        "destinatari": destinatari(),
    }


def _connessione():
    host = str(valore("SMTP_HOST") or "").strip()
    porta = int(valore("SMTP_PORTA"))
    sicurezza = str(valore("SMTP_SICUREZZA") or "starttls").lower()

    if sicurezza == "ssl":
        return smtplib.SMTP_SSL(host, porta, timeout=TIMEOUT)

    server = smtplib.SMTP(host, porta, timeout=TIMEOUT)
    if sicurezza == "starttls":
        server.starttls()
        server.ehlo()
    return server


def invia(oggetto, corpo_html, a=None):
    """Spedisce una mail HTML. Solleva se qualcosa non va.

    Da usare solo dove l'errore ha un posto dove finire (un pulsante che
    aspetta una risposta). Tutto il resto passa da invia_silenzioso().
    """
    a = a or destinatari()
    if not configurata():
        raise RuntimeError("SMTP non configurato: manca il server o i destinatari "
                           "(sezione Configurazione).")
    if not a:
        raise RuntimeError("Nessun destinatario configurato.")

    messaggio = EmailMessage()
    messaggio["Subject"] = oggetto
    messaggio["From"] = formataddr(("GestioneFatture GruppoCR", mittente() or a[0]))
    messaggio["To"] = ", ".join(a)

    # Il corpo testuale non e' un di piu': senza, i filtri antispam trattano
    # peggio il messaggio e chi legge da terminale o da notifica vede il vuoto.
    messaggio.set_content(
        f"{oggetto}\n\nApri la dashboard: {valore('URL_DASHBOARD')}\n"
        "(questa mail richiede un client che mostri l'HTML)"
    )
    messaggio.add_alternative(corpo_html, subtype="html")

    utente = str(valore("SMTP_UTENTE") or "").strip()
    password = str(valore("SMTP_PASSWORD") or "")

    with _connessione() as server:
        if utente and password:
            server.login(utente, password)
        server.send_message(messaggio)

    print(f"📧 Mail inviata a {', '.join(a)}: {oggetto}")
    return {"inviata": True, "destinatari": a, "oggetto": oggetto}


def invia_silenzioso(oggetto, corpo_html, motivo=""):
    """Come invia(), ma un problema di posta resta un problema di posta.

    Una scansione andata a buon fine non deve diventare un errore perche' il
    server SMTP e' spento, e una casella non configurata non e' un guasto: e'
    semplicemente un sistema senza notifiche.
    """
    if not configurata():
        return {"inviata": False, "motivo": "notifiche non configurate"}

    try:
        return invia(oggetto, corpo_html)
    except Exception as e:
        print(f"⚠️ Mail non inviata ({motivo or oggetto}): {e}")
        return {"inviata": False, "motivo": str(e)}
