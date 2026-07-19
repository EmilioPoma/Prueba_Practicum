"""
2_filtrar_contenido_sin_tablas.py
─────────────────────────────────
PASO 2 del flujo.

Toma el JSON crudo de opendataloader_pdf y se queda únicamente con los
elementos de tipo "heading", "paragraph" y "list".

ENTRADA/SALIDA: JSONObtenidos/<nombre_pdf>.json

Este paso LEE y SOBRESCRIBE el mismo archivo que generó el paso 1 (en vez
de crear uno nuevo): el JSON de <nombre_pdf>.json va cambiando de
contenido a medida que avanza cada paso del flujo, hasta terminar siendo
el resultado final en el paso 4.

También se puede importar y usar como función desde otro script (ver
main.py), sin necesidad de volver a detectar/seleccionar el PDF.
"""

import json
import os
# '0_detectar_pdf.py' empieza con un número, así que no se puede
# importar con la sintaxis normal "from 0_detectar_pdf import ..."
# (no es un identificador válido en Python). Se carga con importlib.
from importlib import import_module as _import_module
_paso0 = _import_module("0_detectar_pdf")
detectar_pdf = _paso0.detectar_pdf
nombre_base = _paso0.nombre_base


def filtrar_contenido(base: str) -> str:
    """Filtra heading/paragraph/list del JSON crudo de opendataloader_pdf
    correspondiente a 'base' y SOBRESCRIBE ese mismo archivo con el
    resultado filtrado. Devuelve la ruta del archivo (sin cambios)."""
    ruta = os.path.join("JSONObtenidos", f"{base}.json")

    if not os.path.isfile(ruta):
        raise FileNotFoundError(
            f"No se encontró {ruta}.\n"
            f"Ejecuta primero el paso de extracción del PDF."
        )

    print(f"Leyendo: {ruta}")

    with open(ruta, "r", encoding="utf-8") as f:
        documento = json.load(f)

    elementos_filtrados = [
        elem for elem in documento["kids"]
        if elem.get("type") in ("heading", "paragraph", "list")
    ]

    nuevo_json = {
        "file_name": documento["file name"],
        "kids": elementos_filtrados
    }

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(nuevo_json, f, ensure_ascii=False, indent=4)

    print(f"Filtrado: {len(elementos_filtrados)} elementos → {ruta} (sobrescrito)")
    return ruta


if __name__ == "__main__":
    _pdf_path = detectar_pdf()
    _base = nombre_base(_pdf_path)
    filtrar_contenido(_base)
