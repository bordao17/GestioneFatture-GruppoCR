"""Salvataggio delle immagini elaborate come PDF (singola pagina o multi-pagina)."""

from PIL import Image


def salva_pdf_multipagina(percorso_dest, immagini_paths, risoluzione=150.0):
    """Combina una o più immagini in un unico PDF (multi-pagina se necessario)."""
    pagine = [Image.open(p).convert("RGB") for p in immagini_paths]
    try:
        pagine[0].save(
            percorso_dest, "PDF", resolution=risoluzione,
            save_all=True, append_images=pagine[1:]
        )
    finally:
        for p in pagine:
            p.close()