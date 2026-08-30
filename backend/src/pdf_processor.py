import os
import fitz

# Fattore di zoom del rendering: 2.5 ≈ 180 DPI. Alzarlo (es. 3.5 ≈ 250 DPI) dà al
# modello vision più pixel sui caratteri piccoli — utile sui numeri DDT dove si
# perde una cifra — al costo di più tempo per pagina. Regolabile senza rebuild.
ZOOM_RENDER = float(os.getenv("PDF_RENDER_ZOOM", "2.5"))

def converti_pdf_in_immagini(pdf_path, cartella_output="temp_images"):
    if not os.path.exists(cartella_output):
        os.makedirs(cartella_output)

    immagini_create = []
    doc = fitz.open(pdf_path)
    
    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        matrice = fitz.Matrix(ZOOM_RENDER, ZOOM_RENDER)
        pix = pagina.get_pixmap(matrix=matrice)
        
        nome_img = os.path.join(cartella_output, f"pagina_{num_pagina + 1}.png")
        pix.save(nome_img)
        
        immagini_create.append(nome_img)
        
    return immagini_create