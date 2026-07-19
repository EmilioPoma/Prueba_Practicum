import sys
import glob
import os


def detectar_pdf():
    # Si se pasa un PDF por argumento
    if len(sys.argv) > 1:
        ruta = sys.argv[1]

        if not os.path.isfile(ruta):
            raise FileNotFoundError(
                f"No existe el archivo: {ruta}"
            )

        return ruta

    # Buscar PDFs en la carpeta actual
    pdfs = glob.glob("*.pdf")

    if len(pdfs) == 0:
        raise FileNotFoundError(
            "No se encontró ningún archivo PDF."
        )

    if len(pdfs) == 1:
        print(f"PDF detectado: {pdfs[0]}")
        return pdfs[0]

    # Hay varios PDFs
    print("\nPDFs encontrados:\n")

    for i, pdf in enumerate(pdfs, start=1):
        print(f"{i}. {pdf}")

    while True:
        try:
            opcion = int(
                input("\nSeleccione el PDF a procesar: ")
            )

            if 1 <= opcion <= len(pdfs):
                return pdfs[opcion - 1]

            print(
                f"Ingrese un número entre 1 y {len(pdfs)}"
            )

        except ValueError:
            print("Ingrese un número válido")


def nombre_base(ruta_pdf):
    return os.path.splitext(
        os.path.basename(ruta_pdf)
    )[0]