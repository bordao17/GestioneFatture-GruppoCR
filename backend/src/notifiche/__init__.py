"""Le mail che prima componeva e spediva n8n.

Non e' un terzo flusso del dominio: e' il POSTINO. Fino al 2026-09-09 lo
faceva n8n, con tre nodi Code che tenevano l'HTML dentro il suo database (non
leggibile, non diffabile, riallineato a mano su una copia in n8n_snippets/).
Il contenuto di quelle mail pero' veniva tutto da qui — conteggi, code, motivi
dell'attesa — quindi n8n stava aggiungendo un secondo posto in cui sbagliare
per un lavoro che il backend sapeva gia' fare.

Tre messaggi, che sono i tre momenti in cui qualcuno vuole sapere qualcosa
senza aprire la dashboard:
  riepilogo_ddt      com'e' andata una scansione di bolle (quante da rivedere e perche')
  riepilogo_fatture  che cosa e' entrato da FATTURE/da_leggere
  sollecito          che cosa e' fermo da troppi giorni — l'unico guidato dal tempo

Le mail sono un di piu' e non un ingranaggio: senza SMTP configurato
invia_silenzioso() non fa niente e nessuna pipeline se ne accorge.
"""
