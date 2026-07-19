"""
main.py
─────────
Ejecuta TODO el flujo para un solo PDF, de principio a fin, y sube el
resultado a MongoDB automáticamente (no hace falta correr ningún otro
script por separado):

  0. Detecta/selecciona el PDF a procesar
  1. Extrae el contenido crudo del PDF (opendataloader_pdf)
  2. Filtra solo heading / paragraph / list
  3. Reconstruye tablas con pdfplumber y ordena todo por posición visual
  4. Aplana el resultado a un único documento jerárquico, agregando
     metadata (universidad, lugar, año, etc.)
  5. Sube ese resultado final a MongoDB

Todo el proceso usa UN SOLO archivo JSON por PDF, que se va sobrescribiendo
en cada paso (en vez de ir generando un archivo nuevo por paso):

    JSONObtenidos/<nombre_pdf>.json
        paso 1 → contenido crudo de opendataloader_pdf
        paso 2 → sobrescrito: solo heading/paragraph/list
        paso 3 → sobrescrito: texto + tablas, ordenado por posición visual
        paso 4 → sobrescrito: documento aplanado final + metadata
        paso 5 → ese mismo archivo se sube a MongoDB

Uso:
    python main.py
        → detecta el PDF automáticamente en la carpeta actual
          (o pide elegir si hay varios .pdf), lo procesa completo y lo
          sube a MongoDB

    python main.py ruta/al/archivo.pdf
        → procesa ese PDF puntual y lo sube a MongoDB

    python main.py ruta/al/archivo.pdf --metadata "{\"universidad\": \"UTPL\", \"lugar\": \"Loja - Ecuador\", \"anio_documento\": \"2020\"}"
        → además fija metadata explícita (los campos que no se den se
          intentan auto-detectar del propio contenido del documento)

    python main.py ruta/al/archivo.pdf --mongo-db PracticumPDF --mongo-coleccion PlanDsof
        → sube a una base/colección puntual en vez de las de por defecto

    python main.py ruta/al/archivo.pdf --sin-mongo
        → solo genera el JSON final, sin subirlo a MongoDB (por si no
          tienes pymongo instalado o el servidor no está disponible)
"""

import argparse
import json
import os
import sys
from importlib import import_module

# Los módulos de los pasos empiezan con un número, así que no se pueden
# importar con la sintaxis normal "import 0_detectar_pdf..." (no es un
# identificador válido en Python). Se cargan con importlib en su lugar.
paso0 = import_module("0_detectar_pdf")
paso1 = import_module("1_extraer_pdf_opendataloader")
paso2 = import_module("2_filtrar_contenido_sin_tablas")
paso3 = import_module("3_construir_documento_final_ordenado")
paso4 = import_module("4_aplanar_para_mongo_generico")

detectar_pdf = paso0.detectar_pdf
nombre_base = paso0.nombre_base
transformar = paso4.transformar
construir_metadata = paso4.construir_metadata


def cargar_overrides(metadata_arg):
    """'metadata_arg' puede ser un JSON en línea ('{"universidad": "..."}')
    o la ruta a un archivo .json con los overrides."""
    if not metadata_arg:
        return {}
    candidato = metadata_arg.strip()
    if candidato.startswith("{"):
        return json.loads(candidato)
    with open(candidato, encoding="utf-8") as f:
        return json.load(f)


def procesar_pdf(pdf_path: str, overrides: dict, mongo_config: dict = None) -> str:
    """Corre los pasos 1 a 4 completos para 'pdf_path'. Los 4 pasos leen y
    van SOBRESCRIBIENDO el mismo archivo JSONObtenidos/<nombre_pdf>.json
    (en vez de ir creando un archivo nuevo por paso), hasta que termina
    siendo el resultado final. Salvo que 'mongo_config' sea None, ese
    resultado se sube además a MongoDB como paso 5 (comportamiento por
    defecto). Devuelve la ruta del JSON final."""
    base = nombre_base(pdf_path)
    ruta_json = os.path.join("JSONObtenidos", f"{base}.json")

    print(f"\n{'=' * 60}")
    print(f"  Procesando: {pdf_path}")
    print(f"  Archivo de trabajo: {ruta_json}")
    print(f"{'=' * 60}\n")

    print("→ Paso 1/5: extrayendo contenido del PDF...")
    paso1.extraer_pdf(pdf_path, base)

    print("\n→ Paso 2/5: filtrando heading/paragraph/list...")
    paso2.filtrar_contenido(base)

    print("\n→ Paso 3/5: reconstruyendo tablas y ordenando por posición visual...")
    paso3.construir_documento_final(pdf_path, base)

    print("\n→ Paso 4/5: aplanando a documento único para MongoDB...")
    with open(ruta_json, encoding="utf-8") as f:
        data = json.load(f)

    resultado = transformar(data)
    metadata = construir_metadata(resultado, pdf_path, overrides)
    salida = {"metadata": metadata, **resultado}

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"✔ JSON final (mismo archivo, ya transformado) → {ruta_json}\n")

    if mongo_config is not None:
        print("→ Paso 5/5: subiendo el resultado a MongoDB...")
        # Import diferido: si alguien corre con --sin-mongo, no hace falta
        # tener pymongo instalado para el resto del flujo.
        paso5 = import_module("5_subir_a_mongo_generico")

        with paso5.MongoUploader(
            uri=mongo_config.get("uri"),
            base_datos=mongo_config.get("base_datos", "planes_docentes"),
            coleccion=mongo_config.get("coleccion", "asignaturas"),
        ) as uploader:
            uploader.verificar_conexion()
            uploader.subir_archivo(ruta_json)
        print(f"✔ Subido a MongoDB → base '{mongo_config.get('base_datos', 'planes_docentes')}', "
              f"colección '{mongo_config.get('coleccion', 'asignaturas')}'\n")
    else:
        print("(--sin-mongo: no se subió a MongoDB)\n")

    return ruta_json


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Procesa un PDF de principio a fin: extracción, filtrado, "
                    "reconstrucción de tablas, aplanado y subida a MongoDB."
    )
    parser.add_argument(
        "pdf", nargs="?", default=None,
        help="Ruta al PDF a procesar. Si se omite, se detecta automáticamente "
             "en la carpeta actual (o se pide elegir si hay varios)."
    )
    parser.add_argument(
        "--metadata", dest="metadata_arg", default=None,
        help="JSON en línea o ruta a archivo .json con overrides de metadata, "
             'ej: \'{"universidad": "UTPL", "lugar": "Loja - Ecuador", '
             '"anio_documento": "2020"}\''
    )
    parser.add_argument(
        "--sin-mongo", dest="sin_mongo", action="store_true",
        help="No subir el resultado a MongoDB, solo generar el JSON final."
    )
    parser.add_argument(
        "--mongo-uri", dest="mongo_uri", default=None,
        help="URI de conexión a MongoDB (por defecto usa la variable de entorno "
             "MONGODB_URI, o mongodb://localhost:27017/)."
    )
    parser.add_argument(
        "--mongo-db", dest="mongo_db", default="planes_docentes",
        help="Nombre de la base de datos en MongoDB (por defecto: planes_docentes)."
    )
    parser.add_argument(
        "--mongo-coleccion", dest="mongo_coleccion", default="asignaturas",
        help="Nombre de la colección en MongoDB (por defecto: asignaturas)."
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    pdf_path = args.pdf if args.pdf else detectar_pdf()
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"No existe el archivo: {pdf_path}")

    overrides = cargar_overrides(args.metadata_arg)

    # Por defecto SIEMPRE sube a MongoDB (paso 5); --sin-mongo lo desactiva.
    mongo_config = None
    if not args.sin_mongo:
        mongo_config = {
            "uri": args.mongo_uri,
            "base_datos": args.mongo_db,
            "coleccion": args.mongo_coleccion,
        }

    procesar_pdf(pdf_path, overrides, mongo_config=mongo_config)
