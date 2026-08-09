import os
import fitz

def converti_pdf_in_immagini(pdf_path, cartella_output="temp_images"):
    if not os.path.exists(cartella_output):
        os.makedirs(cartella_output)

    immagini_create = []
    doc = fitz.open(pdf_path)
    
    for num_pagina in range(len(doc)):
        pagina = doc.load_page(num_pagina)
        # Matrice 2.5 = ~180 DPI, buona leggibilità su scansioni scadenti
        matrice = fitz.Matrix(2.5, 2.5)
        pix = pagina.get_pixmap(matrix=matrice)
        
        nome_img = os.path.join(cartella_output, f"pagina_{num_pagina + 1}.png")
        pix.save(nome_img)
        
        immagini_create.append(nome_img)
        
    return immagini_create