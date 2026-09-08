import os
import fitz

from src.comune.configurazione import valore

# Fattore di zoom del rendering: 2.5 ≈ 180 DPI. Alzarlo (es. 3.5 ≈ 250 DPI) dà al
# modello vision più pixel sui caratteri piccoli — utile sui numeri DDT dove si
# perde una cifra — al costo di più tempo per pagina. Si legge a ogni pagina e
# non all'import: è regolabile dalla dashboard, quindi può cambiare mentre il
# processo gira.

def converti_pdf_in_immagini(pdf_path, cartella_output="temp_images"):
    if not os.path.exists(cartella_output):
        os.makedirs(cartella_output)

    immagini_create = []
    doc = fitz.open(pdf_path)
    
    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        zoom = valore("PDF_RENDER_ZOOM")
        matrice = fitz.Matrix(zoom, zoom)
        pix = pagina.get_pixmap(matrix=matrice)
        
        nome_img = os.path.join(cartella_output, f"pagina_{num_pagina + 1}.png")
        pix.save(nome_img)
        
        immagini_create.append(nome_img)
        
    return immagini_create