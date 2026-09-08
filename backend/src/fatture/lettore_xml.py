"""
Lettura delle fatture elettroniche italiane (FatturaPA), in chiaro (.xml) o
firmate CAdES (.xml.p7m).

A differenza del flusso DDT qui NON serve il modello: lo schema FatturaPA e'
fisso e i riferimenti ai documenti di trasporto sono gia' strutturati dentro
<DatiDDT>. Vale lo stesso principio del normalizzatore: se e' una regola
esatta si fa in Python, non si chiede a un 7B.

Le fatture di merce arrivano in due forme e vanno lette diversamente:
  - DIFFERITA: i documenti di trasporto sono elencati in <DatiDDT> (rapporto
    1 -> N con i DDT), che e' il caso di FATTURE/da_leggere/esempio.xml;
  - ACCOMPAGNATORIA: la merce viaggia con la fattura, che fa essa stessa da
    documento di trasporto. Non c'e' nessun <DatiDDT> perche' il "DDT" e' la
    fattura: c'e' invece <DatiTrasporto>, ed e' il numero della fattura a
    comparire sul documento scansionato (rapporto 1 -> 1).
La classificazione vera e' in abbinatore.classifica_fattura(): qui si estrae
solo cio' che le serve.
"""

import base64
import re
import xml.etree.ElementTree as ET

from src.comune.normalizzatore import normalizza_azienda, normalizza_data, normalizza_numero_ddt

MARCATORE_XML = b"<?xml"


# ==========================================
# Sbustamento del file firmato (.xml.p7m)
# ==========================================

def _sbusta_con_asn1crypto(dati):
    """Estrae l'eContent dalla busta CMS. None se la libreria manca o il file non e' CMS."""
    try:
        from asn1crypto import cms
    except ImportError:
        return None

    try:
        info = cms.ContentInfo.load(dati)
        if info["content_type"].native != "signed_data":
            return None
        contenuto = info["content"]["encap_content_info"]["content"]
        return contenuto.native if contenuto is not None else None
    except Exception:
        return None


def _sbusta_per_scansione(dati):
    """
    Fallback: ritaglia il payload XML cercandone i marcatori dentro il DER.

    Non e' elegante ma e' l'unico modo di non perdere un documento quando la
    busta e' codificata in modo inatteso (BER con OCTET STRING costruite, firme
    prodotte da tool non standard). Meglio un XML recuperato a forza bruta che
    una fattura scartata.
    """
    inizio = dati.find(MARCATORE_XML)
    if inizio == -1:
        return None

    fine = dati.rfind(b">")
    if fine <= inizio:
        return None

    return dati[inizio:fine + 1]


def estrai_xml(dati):
    """
    Restituisce i byte dell'XML a partire dal contenuto di un file .xml o .xml.p7m.

    Il riconoscimento e' sul contenuto e non sull'estensione: i file che
    arrivano dallo SdI hanno nomi poco affidabili (capita un .xml che dentro e'
    una busta firmata, e viceversa).
    """
    if not dati:
        return b""

    # Alcune buste arrivano in base64 (PEM o testo puro) invece che in DER.
    testa = dati.lstrip()[:64]
    if not testa.startswith(b"<") and not testa.startswith(b"\x30"):
        try:
            ripulito = re.sub(rb"-----[A-Z ]+-----|\s", b"", dati)
            decodificato = base64.b64decode(ripulito, validate=True)
            if decodificato:
                dati = decodificato
        except Exception:
            pass

    if dati.lstrip().startswith(b"<"):
        return dati

    return _sbusta_con_asn1crypto(dati) or _sbusta_per_scansione(dati) or b""


# ==========================================
# Navigazione dell'albero XML
# ==========================================

def _nome(elemento):
    """Nome del tag senza namespace: i file reali girano con p:, ns2: o senza nulla."""
    tag = elemento.tag
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _figli(elemento, nome):
    if elemento is None:
        return []
    return [figlio for figlio in elemento if _nome(figlio) == nome]


def _figlio(elemento, *percorso):
    """Scende lungo un percorso di tag ignorando i namespace. None se manca un anello."""
    corrente = elemento
    for nome in percorso:
        trovati = _figli(corrente, nome)
        if not trovati:
            return None
        corrente = trovati[0]
    return corrente


def _testo(elemento, *percorso):
    trovato = _figlio(elemento, *percorso) if percorso else elemento
    if trovato is None or trovato.text is None:
        return ""
    return trovato.text.strip()


def _anagrafica(blocco):
    """Denominazione, oppure Nome + Cognome per le ditte individuali."""
    anagrafica = _figlio(blocco, "DatiAnagrafici", "Anagrafica")
    if anagrafica is None:
        return ""

    denominazione = _testo(anagrafica, "Denominazione")
    if denominazione:
        return denominazione

    return " ".join(parte for parte in (_testo(anagrafica, "Nome"), _testo(anagrafica, "Cognome")) if parte)


def _partita_iva(blocco):
    """IdCodice senza il prefisso paese: sul DDT, se un giorno la leggeremo, non ci sara'."""
    id_fiscale = _figlio(blocco, "DatiAnagrafici", "IdFiscaleIVA")
    if id_fiscale is None:
        return ""
    return _testo(id_fiscale, "IdCodice")


# ==========================================
# Parsing della fattura
# ==========================================

def _riferimenti_ddt(dati_generali):
    """
    Lista dei DDT citati dalla fattura, deduplicata.

    <DatiDDT> e' ripetibile e nei tracciati reali viene emesso una volta per
    riga di dettaglio (con RiferimentoNumeroLinea): senza deduplica una fattura
    di 40 righe risulterebbe collegata a 40 DDT identici.
    """
    riferimenti = []
    visti = set()

    for blocco in _figli(dati_generali, "DatiDDT"):
        numero_grezzo = _testo(blocco, "NumeroDDT")
        data_grezza = _testo(blocco, "DataDDT")

        numero = normalizza_numero_ddt(numero_grezzo)
        data = normalizza_data(data_grezza)

        chiave = (numero, data)
        if not numero or chiave in visti:
            continue
        visti.add(chiave)

        riferimenti.append({
            "numero_ddt": numero,
            "data_ddt": data,
            "numero_ddt_xml": numero_grezzo,
        })

    return riferimenti


def _trasporto(dati_generali):
    """
    Sintesi di <DatiTrasporto>, quando c'e'.

    Non serve per abbinare ma per CLASSIFICARE: la presenza del blocco dice che
    la merce ha viaggiato accompagnata dalla fattura stessa (accompagnatoria).
    E' l'unico appiglio strutturale per distinguerla da una fattura di soli
    servizi, che non ha nessun DDT da aspettare: il TipoDocumento non basta,
    TD01 copre entrambi i casi.
    """
    blocco = _figlio(dati_generali, "DatiTrasporto")
    if blocco is None:
        return {}

    vettore = _figlio(blocco, "DatiAnagraficiVettore", "Anagrafica")
    denominazione = _testo(vettore, "Denominazione") if vettore is not None else ""

    data = _testo(blocco, "DataInizioTrasporto") or _testo(blocco, "DataOraConsegna")[:10]

    return {
        "vettore": normalizza_azienda(denominazione),
        "causale": _testo(blocco, "CausaleTrasporto"),
        "data_trasporto": normalizza_data(data),
    }


def _allegati(corpo):
    """Allegati della fattura. Il PDF di cortesia, se c'e', diventa la copertina del fascicolo."""
    allegati = []

    for blocco in _figli(corpo, "Allegati"):
        contenuto = _testo(blocco, "Attachment")
        if not contenuto:
            continue
        try:
            dati = base64.b64decode(re.sub(r"\s", "", contenuto), validate=False)
        except Exception:
            continue

        allegati.append({
            "nome": _testo(blocco, "NomeAttachment"),
            "formato": _testo(blocco, "FormatoAttachment").upper(),
            "dati": dati,
        })

    return allegati


def leggi_fattura(dati):
    """
    Parsa i byte di un file FatturaPA e restituisce UNA VOCE PER FATTURA.

    Un file puo' contenere piu' <FatturaElettronicaBody> (fattura a lotti):
    l'intestazione del cedente e' comune, il resto no.
    """
    xml = estrai_xml(dati)
    if not xml:
        raise ValueError("File non riconosciuto: non contiene un XML ne' una busta firmata leggibile")

    try:
        radice = ET.fromstring(xml)
    except ET.ParseError as errore:
        raise ValueError(f"XML non valido: {errore}")

    intestazione = _figlio(radice, "FatturaElettronicaHeader")
    cedente = _figlio(intestazione, "CedentePrestatore") if intestazione is not None else None
    cessionario = _figlio(intestazione, "CessionarioCommittente") if intestazione is not None else None

    fornitore_xml = _anagrafica(cedente)
    comune = {
        "fornitore": normalizza_azienda(fornitore_xml),
        "fornitore_xml": fornitore_xml,
        "partita_iva": _partita_iva(cedente),
        "cessionario": normalizza_azienda(_anagrafica(cessionario)),
        "partita_iva_cessionario": _partita_iva(cessionario),
    }

    fatture = []
    for corpo in _figli(radice, "FatturaElettronicaBody"):
        dati_generali = _figlio(corpo, "DatiGenerali")
        documento = _figlio(dati_generali, "DatiGeneraliDocumento")

        fatture.append({
            **comune,
            "numero_fattura": _testo(documento, "Numero"),
            "data_fattura": normalizza_data(_testo(documento, "Data")),
            "tipo_documento": _testo(documento, "TipoDocumento"),
            "importo_totale": _testo(documento, "ImportoTotaleDocumento"),
            "ddt": _riferimenti_ddt(dati_generali),
            "trasporto": _trasporto(dati_generali),
            "allegati": _allegati(corpo),
        })

    if not fatture:
        raise ValueError("XML privo di FatturaElettronicaBody: non e' una fattura elettronica")

    return fatture
