"""
1_extraer_pdf_opendataloader.py
─────────────────────────────────
PASO 1 del flujo.

Usa la librería `opendataloader_pdf` (requiere Java instalado) para leer
el PDF y generar un JSON con TODO el contenido detectado por la
herramienta: headings, paragraphs, lists, tables, images, etc.

ENTRADA:  <pdf detectado o seleccionado>
SALIDA:   JSONObtenidos/<nombre_pdf>.json
          JSONObtenidos/<nombre_pdf>.md

También se puede importar y usar como función desde otro script (ver
main.py), sin necesidad de volver a detectar/seleccionar el PDF.
"""

import os
import opendataloader_pdf
# '0_detectar_pdf.py' empieza con un número, así que no se puede
# importar con la sintaxis normal "from 0_detectar_pdf import ..."
# (no es un identificador válido en Python). Se carga con importlib.
from importlib import import_module as _import_module
_paso0 = _import_module("0_detectar_pdf")
detectar_pdf = _paso0.detectar_pdf
nombre_base = _paso0.nombre_base


def extraer_pdf(pdf_path: str, base: str) -> str:
    """Convierte 'pdf_path' a JSON con opendataloader_pdf.
    Devuelve la ruta al JSON crudo generado (JSONObtenidos/<base>.json)."""
    os.makedirs("JSONObtenidos", exist_ok=True)

    print(f"Procesando: {pdf_path}")

    opendataloader_pdf.convert(
        input_path=[pdf_path],
        output_dir="JSONObtenidos",
        format="markdown,json"
    )

    ruta_json = os.path.join("JSONObtenidos", f"{base}.json")
    print(f"Extracción completada → {ruta_json}")
    return ruta_json


if __name__ == "__main__":
    _pdf_path = detectar_pdf()
    _base = nombre_base(_pdf_path)
    extraer_pdf(_pdf_path, _base)
