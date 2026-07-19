"""
3_construir_documento_final_ordenado.py
────────────────────────────────────────
PASO 3 del flujo.

Re-extrae tablas con pdfplumber (con bounding box real), elimina
párrafos/headings que son duplicados de celdas de tabla, y ordena
todo por posición visual (Y, X) en cada página.

ENTRADA/SALIDA: <pdf detectado> + JSONObtenidos/<nombre_pdf>.json

Este paso LEE y SOBRESCRIBE el mismo archivo <nombre_pdf>.json que
vienen arrastrando los pasos 1 y 2 (en vez de crear uno nuevo).

También se puede importar y usar como función desde otro script (ver
main.py), sin necesidad de volver a detectar/seleccionar el PDF.
"""

import json
import os
from collections import Counter

import pdfplumber
# '0_detectar_pdf.py' empieza con un número, así que no se puede
# importar con la sintaxis normal "from 0_detectar_pdf import ..."
# (no es un identificador válido en Python). Se carga con importlib.
from importlib import import_module as _import_module
_paso0 = _import_module("0_detectar_pdf")
detectar_pdf = _paso0.detectar_pdf
nombre_base = _paso0.nombre_base


def norm(t):
    return " ".join(str(t).lower().replace("\n", " ").split())


def construir_documento_final(pdf_path: str, base: str) -> str:
    """Reconstruye el documento completo (texto + tablas) ordenado por
    posición visual y SOBRESCRIBE JSONObtenidos/<base>.json con el
    resultado. Devuelve la ruta de ese archivo (sin cambios)."""
    print(f"PDF: {pdf_path}")

    # ── Re-extraer tablas con bbox ────────────────────────────────────
    tablas_con_bbox = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            for table_idx, tabla in enumerate(page.find_tables(), start=1):

                x0, top, x1, bottom = tabla.bbox
                y1_pdf = page.height - top
                y0_pdf = page.height - bottom

                filas_limpias = []
                for fila_num, fila in enumerate(tabla.extract(), start=1):
                    celdas = [
                        {"column_number": i, "content": str(v).strip()}
                        for i, v in enumerate(fila, start=1)
                        if v and str(v).strip()
                    ]
                    if celdas:
                        filas_limpias.append({"row_number": fila_num, "cells": celdas})

                tablas_con_bbox.append({
                    "type": "table",
                    "id": f"T{page_idx}_{table_idx}",
                    "page_number": page_idx,
                    "table_number": table_idx,
                    "y_top": y1_pdf,
                    "y_bottom": y0_pdf,
                    "x0": x0,
                    "rows": filas_limpias
                })

    print(f"Tablas extraídas: {len(tablas_con_bbox)}")

    # ── Cargar texto (el mismo archivo que traen los pasos 1 y 2) ───────
    ruta = os.path.join("JSONObtenidos", f"{base}.json")
    if not os.path.isfile(ruta):
        raise FileNotFoundError(
            f"No se encontró {ruta}.\n"
            f"Ejecuta primero los pasos de extracción y filtrado."
        )

    with open(ruta, "r", encoding="utf-8") as f:
        contenido = json.load(f)

    elementos_texto = contenido["kids"]
    print(f"Elementos de texto: {len(elementos_texto)}")

    # ── Índices para detección de duplicados (3 niveles) ────────────────
    celdas_exactas = {}
    texto_concat_pagina = {}
    celdas_individuales = {}

    for t in tablas_con_bbox:
        p = t["page_number"]
        celdas_exactas.setdefault(p, set())
        texto_concat_pagina.setdefault(p, [])
        celdas_individuales.setdefault(p, [])
        concat = ""
        for row in t["rows"]:
            for cell in row["cells"]:
                cn = norm(cell["content"])
                if cn:
                    celdas_exactas[p].add(cn)
                    celdas_individuales[p].append(cn)
                    concat += " " + cn
        texto_concat_pagina[p].append(concat.strip())

    def es_duplicado(elem):
        tipo = elem.get("type")
        content = elem.get("content", "").strip()
        page = elem.get("page number") or 0
        if tipo not in ("paragraph", "heading") or not content:
            return False
        cn = norm(content)
        if cn in celdas_exactas.get(page, set()):
            return True
        if len(cn) >= 5:
            for tc in texto_concat_pagina.get(page, []):
                if cn in tc:
                    return True
        for c in celdas_individuales.get(page, []):
            if cn in c:
                return True
        return False

    # ── Serializar texto sobreviviente ──────────────────────────────────
    nodos_texto = []
    eliminados = 0

    for elem in elementos_texto:
        tipo = elem.get("type")
        bb = elem.get("bounding box", [0, 0, 0, 0])

        if tipo in ("paragraph", "heading"):
            if es_duplicado(elem):
                eliminados += 1
                continue
            nodos_texto.append({
                "type": tipo,
                "id": elem.get("id"),
                "page_number": elem.get("page number"),
                "content": elem.get("content", "").strip(),
                "y_top": bb[3],
                "y_bottom": bb[1],
                "x0": bb[0]
            })

        elif tipo == "list":
            items = [
                {"content": item.get("content", "").strip()}
                for item in elem.get("list items", [])
                if item.get("content", "").strip()
            ]
            if items:
                nodos_texto.append({
                    "type": "list",
                    "id": elem.get("id"),
                    "page_number": elem.get("page number"),
                    "items": items,
                    "y_top": bb[3],
                    "y_bottom": bb[1],
                    "x0": bb[0]
                })

    print(f"Duplicados eliminados: {eliminados}")

    # ── Unir + ordenar por posición visual ──────────────────────────────
    todos_ordenados = sorted(
        nodos_texto + tablas_con_bbox,
        key=lambda e: (e["page_number"], -e["y_top"], e["x0"])
    )

    elementos_finales = [
        {k: v for k, v in e.items() if k not in ("y_top", "y_bottom", "x0")}
        for e in todos_ordenados
    ]

    resultado = {
        "file_name": contenido["file_name"],
        "total_elements": len(elementos_finales),
        "elements": elementos_finales
    }

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=4)

    tipos = Counter(e["type"] for e in elementos_finales)
    print()
    print("=" * 50)
    print(f"  {ruta} sobrescrito (documento ordenado)")
    print("=" * 50)
    print(f"  Total: {len(elementos_finales)}")
    for t, c in sorted(tipos.items()):
        print(f"    {t:<12} : {c}")
    print("=" * 50)

    return ruta


if __name__ == "__main__":
    _pdf_path = detectar_pdf()
    _base = nombre_base(_pdf_path)
    construir_documento_final(_pdf_path, _base)
