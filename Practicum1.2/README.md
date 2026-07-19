# Practicum 1.2 — Extracción estructurada de PDF a JSON para MongoDB

Este proyecto toma un PDF académico (el plan docente o el diseño de una
asignatura), extrae todo su contenido, lo limpia, lo ordena según como se lee
el documento, lo convierte en un solo JSON de tipo clave:valor y finalmente
lo sube a MongoDB.

Para la extracción inicial usamos la librería
[`opendataloader_pdf`](https://pypi.org/project/opendataloader-pdf/) (que
necesita Java instalado), para las tablas usamos
[`pdfplumber`](https://github.com/jsvine/pdfplumber), que da la posición
exacta de cada tabla en la página, y para la subida a la base de datos
usamos [`pymongo`](https://pypi.org/project/pymongo/).

Todo el flujo se puede correr de una sola vez con `main.py`, o paso por paso
si se quiere revisar cada etapa por separado.

## Cómo se guardan los resultados

Algo importante de entender antes de ver el proceso: el flujo trabaja con
**un solo archivo JSON por PDF**, que se va sobrescribiendo en cada paso en
lugar de ir creando un archivo nuevo cada vez. Ese archivo es
`JSONObtenidos/<nombre_pdf>.json` y va cambiando así:

```
paso 1  ->  contenido crudo que devuelve opendataloader_pdf
paso 2  ->  se sobrescribe: solo heading, paragraph y list
paso 3  ->  se sobrescribe: texto + tablas, ordenado por posición visual
paso 4  ->  se sobrescribe: documento aplanado final, con su metadata
paso 5  ->  ese mismo archivo se sube a MongoDB
```

La ventaja es que no quedan archivos intermedios regados por la carpeta, y
siempre se sabe cuál es el archivo de trabajo de cada PDF. La contra es que
si se quiere conservar el estado de un paso intermedio, hay que copiarlo
aparte antes de seguir.

En `JSONObtenidos/` de este repositorio están los JSON de los dos PDF que nos
facilitó el docente tutor, junto con su versión en Markdown y las imágenes
que se extrajeron de cada uno.

## Resultados obtenidos

Corrimos el flujo completo sobre los dos PDF que nos facilitó el docente
tutor. Estos son los documentos que quedaron en `JSONObtenidos/`:

| | `DSOF_1067-O20F21.pdf` | `PLAN_3952-DSOF_1067.pdf` |
|---|---|---|
| Secciones raíz (sin contar metadata) | 9 | 8 |
| Secciones que son lista de registros | 3 (`d_contenidos`, `f_procedimientos_de_evaluacion`, `h_elaboracion_y_aprobacion`) | 1 (`horario_de_clases`, dentro de la sección A) |
| Subsecciones anidadas | `g_bibliografia` con `basica` y `complementaria` | ninguna |
| Sección más grande | `a_datos_de_identificacion_de_la_asignatura`, con 14 campos | `d_planificacion_general_de_la_asignatura_primer_bimestre`, con 54 campos |

Un pedazo del resultado del DSOF, para que se vea a qué se llega:

```json
{
  "metadata": {
    "archivo_origen": "DSOF_1067-O20F21.pdf",
    "universidad": "UNIVERSIDAD TÉCNICA PARTICULAR DE LOJA",
    "modalidad": "Presencial",
    "lugar": "Loja – Ecuador",
    "anio_documento": "2020",
    "area_academica": "Técnica",
    "carrera": "Computación",
    "asignatura": "Introducción a la programación"
  },
  "a_datos_de_identificacion_de_la_asignatura": {
    "asignatura": "Introducción a la programación",
    "modalidad_de_estudio": "Presencial",
    "codigo": "DSOF_1067",
    "numero_de_credito_horas": { "credito": "3", "horas": "144" }
  }
}
```

Las claves quedan en snake_case, sin tildes ni símbolos, porque los puntos y
caracteres raros rompen las consultas con notación de puntos en Mongo. Los
valores no se tocan, conservan el texto tal como viene en el PDF.

En el PLAN se puede ver funcionando la lógica de tablas matriz. El horario de
clases quedó como una lista de registros, y el nombre del docente se repite
en cada uno porque en el PDF esa celda estaba combinada verticalmente:

```json
"horario_de_clases": [
  { "docente": "RENE ROLANDO ELIZALDE SOLANO", "paralelo": "A",
    "dia": "MIERCOLES", "horario": "03:00 PM-04:59 PM0 (CLAS)" },
  { "docente": "RENE ROLANDO ELIZALDE SOLANO", "paralelo": "A",
    "dia": "JUEVES", "horario": "03:00 PM-04:59 PM0 (PRAC)" }
]
```

### Sobre la auto-detección de la metadata

En el DSOF la metadata se llenó sola por completo, porque ese documento trae
la universidad, la modalidad, el lugar y el año en la carátula.

En el PLAN, en cambio, se detectaron el área académica, la carrera, la
asignatura y la fecha de elaboración, pero los campos `universidad`,
`modalidad`, `lugar` y `anio_documento` quedaron vacíos, porque su carátula
solo trae "PLAN DOCENTE DE LA ASIGNATURA" y "CARRERAS NUEVAS O REDISEÑADAS",
sin esos datos por ningún lado.

Ese es justamente el caso para el que sirve la opción `--metadata`: cuando el
documento no tiene la información, se la pasamos a mano en vez de dejar los
campos en blanco.

```bash
python main.py PLAN_3952-DSOF_1067.pdf --metadata "{\"universidad\": \"UNIVERSIDAD TÉCNICA PARTICULAR DE LOJA\", \"modalidad\": \"Presencial\", \"lugar\": \"Loja - Ecuador\", \"anio_documento\": \"2023\"}"
```

## Estructura del repositorio

```
Practicum1.2/
├── scripts/                       Código del flujo
│   ├── main.py                        Orquestador: corre todo de principio a fin
│   ├── 0_detectar_pdf.py              Auxiliar: detección/selección del PDF
│   ├── 1_extraer_pdf_opendataloader.py    Paso 1: extracción cruda
│   ├── 2_filtrar_contenido_sin_tablas.py  Paso 2: filtrar solo texto
│   ├── 3_construir_documento_final_ordenado.py  Paso 3: tablas + orden real
│   ├── 4_aplanar_para_mongo_generico.py   Paso 4: aplanado clave:valor + metadata
│   └── 5_subir_a_mongo_generico.py        Paso 5: subida a MongoDB
├── pdfs_entrada/                  PDFs de origen facilitados por el tutor
├── JSONObtenidos/                 Salidas generadas (JSON, Markdown, imágenes)
├── documentacion/                 Explicación ampliada del flujo y los scripts
├── requirements.txt
└── README.md
```

## Requisitos e instalación

1. Python 3.10 o superior. Se comprueba con `python --version` (en Ubuntu
   suele ser `python3 --version`).
2. Java (JRE 8 o superior) instalado y en el PATH, porque
   `opendataloader_pdf` lo usa internamente. Se comprueba con
   `java -version`. En Ubuntu se instala con `sudo apt install default-jre`;
   en Windows, con el instalador de la página de Java o Adoptium.
3. Un servidor MongoDB accesible, solo si se va a usar el paso 5. Puede ser
   local (`mongodb://localhost:27017/`) o remoto, por ejemplo un cluster de
   Atlas. Si no se tiene, el flujo igual funciona usando la opción
   `--sin-mongo`, que genera el JSON final pero no lo sube.
4. Las dependencias de Python:

```bash
pip install -r requirements.txt
```

Eso instala `opendataloader_pdf`, `pdfplumber` y `pymongo`. El resto de
librerías que usan los scripts (json, re, argparse, unicodedata, etc.) ya
vienen con Python.

## Proceso replicable

Antes de empezar: copiar el PDF a procesar y los scripts a una misma carpeta
de trabajo, porque los scripts buscan el `.pdf` en la carpeta actual. La
carpeta `JSONObtenidos/` se crea sola en el paso 1. Todos los comandos se
corren desde esa carpeta.

### Opción A: correr todo de una vez con main.py

Esta es la forma normal de usarlo. Un solo comando hace los cinco pasos y
sube el resultado a MongoDB:

```bash
python main.py
```

Si hay un solo PDF en la carpeta lo detecta solo. Si hay varios, muestra un
menú numerado para elegir. También se le puede pasar el archivo directamente:

```bash
python main.py PLAN_3952-DSOF_1067.pdf
```

Si no se tiene MongoDB corriendo, o simplemente no se quiere subir nada, se
usa la bandera `--sin-mongo`, que hace los pasos 1 al 4 y deja el JSON final
listo en `JSONObtenidos/`:

```bash
python main.py PLAN_3952-DSOF_1067.pdf --sin-mongo
```

Se le puede fijar metadata explícita, para los campos que el script no logre
detectar solo del documento:

```bash
python main.py PLAN_3952-DSOF_1067.pdf --metadata "{\"universidad\": \"UTPL\", \"lugar\": \"Loja - Ecuador\", \"anio_documento\": \"2020\"}"
```

Y se puede apuntar a otra base o colección de las que trae por defecto
(`planes_docentes` y `asignaturas`):

```bash
python main.py PLAN_3952-DSOF_1067.pdf --mongo-db PracticumPDF --mongo-coleccion PlanDsof
```

### Opción B: paso por paso

Cada script también se puede correr solo, que es útil para revisar qué queda
después de cada etapa. Hay que respetar el orden, porque cada paso lee lo que
dejó el anterior en el mismo archivo.

```bash
# Paso 1: extracción cruda del PDF
python 1_extraer_pdf_opendataloader.py

# Paso 2: se queda solo con heading, paragraph y list
python 2_filtrar_contenido_sin_tablas.py

# Paso 3: re-extrae las tablas y ordena todo por posición visual
python 3_construir_documento_final_ordenado.py

# Paso 4: aplana a clave:valor y agrega la metadata
python 4_aplanar_para_mongo_generico.py JSONObtenidos/PLAN_3952-DSOF_1067.json JSONObtenidos/PLAN_3952-DSOF_1067.json

# Paso 5: sube el resultado a MongoDB
python 5_subir_a_mongo_generico.py JSONObtenidos/PLAN_3952-DSOF_1067.json
```

Los pasos 1, 2 y 3 detectan el PDF igual que `main.py`. El paso 4 sí recibe
las rutas de entrada y salida como argumentos (se puede poner la misma ruta
en ambos para mantener el comportamiento de sobrescribir). El paso 5 recibe
el archivo a subir, o si no se le pasa ninguno, sube todos los que encuentre
en la carpeta.

### Qué se genera en cada paso

Paso 1: el JSON crudo `JSONObtenidos/<nombre_pdf>.json` con todo lo que la
librería detecta (headings, paragraphs, lists, tables, images), más una
versión en Markdown y una carpeta `<nombre_pdf>_images/` con las imágenes
del PDF.

Paso 2: el mismo JSON, pero ya solo con los elementos de texto. La consola
reporta cuántos elementos quedaron.

Paso 3: el mismo JSON, ahora con el texto y las tablas juntos y ordenados.
La consola muestra un resumen con el total de elementos y cuántos son de cada
tipo, además de cuántos duplicados se eliminaron.

Paso 4: el mismo JSON, convertido en el documento final clave:valor, con un
bloque `metadata` al inicio.

Paso 5: ese documento queda subido a la colección de MongoDB.

### Sobre la conexión a MongoDB

El paso 5 decide a qué servidor conectarse en este orden: primero la URI que
se le pase por argumento, luego la variable de entorno `MONGODB_URI`, y si no
hay ninguna de las dos, usa `mongodb://localhost:27017/`.

Si la URI tiene usuario y contraseña, lo recomendable es pasarla por variable
de entorno en vez de escribirla en la línea de comandos:

```bash
export MONGODB_URI="mongodb+srv://usuario:clave@cluster.mongodb.net"
python main.py PLAN_3952-DSOF_1067.pdf
```

Algo útil: si se vuelve a procesar el mismo PDF, el script no duplica el
documento en la base. Usa el campo `metadata.archivo_origen` para reconocer
que ya existe y lo reemplaza con la versión nueva.

## Cómo funciona (resumen)

La explicación completa está en
[`documentacion/flujo.md`](./documentacion/flujo.md). Acá va lo esencial.

El orden de lectura (paso 3). El problema es que opendataloader_pdf da la
posición del texto en coordenadas PDF (el origen está abajo a la izquierda y
la Y crece hacia arriba), mientras que pdfplumber da la posición de las
tablas al revés (origen arriba a la izquierda, `top` crece hacia abajo). La
solución fue convertir el bbox de cada tabla con
`y_top = page.height - top`, con lo que texto y tablas quedan en el mismo
sistema y se puede ordenar cada página de arriba hacia abajo. Así cada tabla
queda intercalada justo donde va en el documento.

Los duplicados (paso 3). A veces opendataloader_pdf reporta como párrafo o
heading un texto que en realidad es el contenido de una celda. Para no
duplicar, cada texto se compara contra las tablas de su misma página en tres
niveles: si coincide exacto con una celda, si está contenido en el texto
completo de la tabla, o si está contenido dentro de una celda.

Las tablas cortadas por página (paso 4). Los PDF cortan las tablas al cambiar
de página y pdfplumber las devuelve como tablas separadas. Antes de
interpretarlas, el script las reconstruye: descarta los títulos que se
repiten por el salto de página, pega el contenido que quedó separado de su
título (el caso típico es que un título como "Semana 6" queda solo al final
de una tabla y sus datos caen en la siguiente), y fusiona las tablas tipo
matriz que quedaron partidas, usando el número de columna.

La interpretación de tablas (paso 4). Hay dos casos. Si la tabla es una
matriz (con encabezados de columna de verdad, como el horario de clases), se
convierte en una lista de registros; cuando a una fila le falta la primera
columna es porque en el PDF esa celda estaba combinada con la de arriba
(rowspan, como pasa con la columna "Componente"), y se hereda el valor de la
fila anterior. Si la tabla es tipo formulario, se aplica la regla padre-hijo:
una fila de una sola celda (como "A. Datos básicos de la asignatura") es el
padre de las filas que siguen, y cada fila de dos celdas es un par
clave:valor.

Las secciones del documento (paso 4). Los documentos institucionales suelen
numerar sus secciones principales con una letra y un punto ("A. DATOS DE
IDENTIFICACIÓN", "G. BIBLIOGRAFÍA"). El script usa ese patrón para decidir
qué encabezado abre una sección nueva en la raíz y cuál es solo una
subsección de la sección activa (por ejemplo "Básica" y "Complementaria"
dentro de Bibliografía). Todo lo que aparece antes de la primera sección con
letra, o sea la carátula, se agrupa bajo la clave `portada`, porque el
formato de carátula cambia demasiado entre universidades como para adivinar
qué es cada línea.

La metadata (paso 4). Al documento final se le antepone un bloque `metadata`
con datos como universidad, carrera, área académica, modalidad, asignatura y
fecha. Esos campos se intentan detectar del propio contenido del documento, y
lo que no se pueda detectar se puede fijar a mano con la opción `--metadata`.
Esto es lo que permite que el flujo sirva para documentos de cualquier
universidad y no solo para los de la nuestra.

Las claves (paso 4). La función `clean_key()` normaliza solo las claves,
nunca los valores: quita tildes, cambia cualquier símbolo por guión bajo y
pasa todo a minúsculas. Y `add_unique()` evita perder datos: si una clave se
repite, en lugar de sobrescribir agrupa los valores en una lista.

## Notas de replicabilidad

- Los scripts se ejecutan desde la carpeta donde está el PDF; las rutas de
  salida (`JSONObtenidos/...`) son relativas a la carpeta actual.
- Como cada paso sobrescribe el mismo archivo, no se puede volver a correr un
  paso intermedio sobre un JSON que ya avanzó. Si hay que rehacer algo, lo
  más simple es correr el flujo otra vez desde el paso 1.
- Los archivos de los pasos empiezan con un número, y en Python eso no es un
  identificador válido para un `import` normal. Por eso `main.py` y los demás
  scripts los cargan con `importlib.import_module()` en lugar de la sintaxis
  habitual.
- El paso 1 falla si Java no está instalado o no está en el PATH.
- El paso 5 falla si no hay un servidor MongoDB accesible. Si solo se quiere
  el JSON final, hay que usar `--sin-mongo`.

## Código

Este es el código de cada script. Antes de cada bloque hay una explicación
corta de qué hace.

### `scripts/main.py`

El orquestador. Corre los cinco pasos seguidos para un mismo PDF y sube el
resultado a MongoDB al final. Maneja las banderas de línea de comandos
(`--metadata`, `--sin-mongo`, `--mongo-uri`, `--mongo-db`,
`--mongo-coleccion`) y va imprimiendo en qué paso va. Carga los módulos con
`importlib` porque sus nombres empiezan con número.

```python
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
```

### `scripts/0_detectar_pdf.py`

Auxiliar que usan los demás scripts. Si se pasa un PDF por argumento usa ese;
si no, busca los `.pdf` de la carpeta actual: si hay uno lo toma, si hay
varios muestra un menú y si no hay ninguno lanza un error. La función
`nombre_base()` devuelve el nombre del archivo sin extensión, que es lo que
se usa para nombrar el JSON de trabajo.

```python
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
```

### `scripts/1_extraer_pdf_opendataloader.py` — Paso 1

Crea la carpeta `JSONObtenidos/` si no existe y llama a
`opendataloader_pdf.convert()`, que genera el JSON crudo con todo el
contenido detectado, la versión Markdown y las imágenes del PDF. Se puede
correr solo o importarse como función desde `main.py`.

```python
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
```

### `scripts/2_filtrar_contenido_sin_tablas.py` — Paso 2

Lee el JSON del paso 1 y se queda solo con los elementos de texto: heading,
paragraph y list. Las tablas se descartan a propósito, porque en el paso 3 se
vuelven a extraer con pdfplumber, que las saca mejor. El resultado sobrescribe
el mismo archivo.

```python
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
```

### `scripts/3_construir_documento_final_ordenado.py` — Paso 3

Re-extrae las tablas con pdfplumber guardando su bounding box, limpia las
celdas vacías, elimina el texto duplicado (los tres niveles de comparación) y
ordena todos los elementos por página, Y descendente y X ascendente, que es
el orden en que se lee el documento. También sobrescribe el mismo archivo.

```python
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
```

### `scripts/4_aplanar_para_mongo_generico.py` — Paso 4

El paso con más lógica propia. Reconstruye las tablas que quedaron cortadas
por los saltos de página, interpreta cada tabla como matriz o como formulario
padre-hijo, arma las secciones del documento a partir de los encabezados con
letra, clasifica los párrafos en título o contenido, construye el bloque de
metadata y normaliza todas las claves para que funcionen en Mongo.

```python
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime


def clean_key(text) -> str:
    """Convierte texto crudo (celda/encabezado) en una clave de Mongo
    100% segura: sin tildes/diéresis/ñ especiales, sin puntos ni otros
    símbolos (rompen la notación de puntos de Mongo), sin espacios
    (todo en snake_case). Esto NUNCA se aplica a los valores, solo a
    las claves."""
    if text is None:
        return "campo"
    key = str(text).strip()
    key = unicodedata.normalize("NFKD", key)
    key = "".join(c for c in key if not unicodedata.combining(c))  # quita tildes
    key = re.sub(r"[^A-Za-z0-9]+", " ", key)  # cualquier símbolo (incluye '.') -> espacio
    key = re.sub(r"\s+", "_", key.strip())
    return key.lower() if key else "campo"


def add_unique(target: dict, key: str, value):
    """Agrega key:value; si la clave ya existe, la convierte en lista
    en vez de sobrescribirla. Si tanto el valor existente como el nuevo
    son listas, se concatenan (no se anida una lista dentro de otra)."""
    if key in target:
        if isinstance(target[key], list) and isinstance(value, list):
            target[key].extend(value)
        elif isinstance(target[key], list):
            target[key].append(value)
        else:
            target[key] = [target[key], value]
    else:
        target[key] = value


_EMBEDDED_KV = re.compile(r"^([^:：]{1,60}):\s*(.+)$", re.DOTALL)


def split_embedded_kv(text: str):
    """Separa el patrón 'Etiqueta: valor' cuando viene junto en un mismo
    texto (ej. 'Crédito: 3' o 'ÁREA ACADÉMICA: Técnica'). None si el
    texto termina en ':' sin nada después."""
    if not text:
        return None
    m = _EMBEDDED_KV.match(text.strip())
    if not m:
        return None
    etiqueta, valor = m.group(1).strip(), m.group(2).strip()
    if not etiqueta or not valor:
        return None
    return clean_key(etiqueta), valor


# ---------------------------------------------------------------------
# Detección de encabezado de NIVEL SUPERIOR (secciones principales del
# documento, ej. "A. DATOS DE IDENTIFICACIÓN...", "G. BIBLIOGRAFÍA").
# Estos documentos institucionales casi siempre enumeran sus secciones
# principales con una letra mayúscula seguida de un punto. Cualquier
# encabezado que NO siga ese patrón (ej. "Básica", "Complementaria"
# dentro de Bibliografía) se trata como SUBSECCIÓN de la sección activa,
# no como una sección nueva de la raíz del documento.
# ---------------------------------------------------------------------
_TOP_LEVEL_HEADING = re.compile(r"^[A-ZÁÉÍÓÚÑ]\.\s*\S")


# ---------------------------------------------------------------------
# Preparación de tablas: el PDF corta muchas tablas al cambiar de página.
# El título de una sección (ej. "Semana 6") suele quedar solo en una
# tabla, y su contenido real cae en la(s) tabla(s) siguientes SIN su
# propio título. Estas reglas reconstruyen la tabla completa antes de
# interpretarla.
# ---------------------------------------------------------------------

def _es_titulo_duplicado(actual, anterior):
    """La tabla 'actual' es una fila suelta cuyo texto repite EXACTO el
    título con el que terminó la tabla anterior (artefacto típico de
    salto de página): se descarta, no aporta nada nuevo."""
    filas_a = actual.get("rows") or []
    filas_p = anterior.get("rows") or []
    if len(filas_a) != 1 or not filas_p:
        return False
    celdas_a = filas_a[0].get("cells", [])
    celdas_p = filas_p[-1].get("cells", [])
    if len(celdas_a) != 1 or len(celdas_p) != 1:
        return False
    return clean_key(celdas_a[0].get("content")) == clean_key(celdas_p[0].get("content"))


def _tiene_titulo_colgante_confiable(table):
    """True solo si hay evidencia fuerte de que la tabla quedó cortada a
    mitad de un bloque título+contenido (y no es simplemente una lista de
    casilleros que termina en un ítem suelto, ni una tabla-matriz cuya
    última fila es un dato disperso y no un título).

    Evidencia fuerte = la tabla termina en una fila de 1 celda, Y ADEMÁS:
    - es la ÚNICA fila de la tabla (un título suelto, sin nada más), o
    - la fila justo antes tiene 2+ celdas (datos reales), señal de que
      el bloque título+contenido se interrumpió a mitad de camino.
    """
    rows = table.get("rows") or []
    if not rows or is_matrix_table(rows):
        return False
    if len(rows[-1].get("cells", [])) != 1:
        return False
    if len(rows) == 1:
        return True
    return len(rows[-2].get("cells", [])) >= 2


def _empieza_sin_titulo(table):
    """True si la primera fila de la tabla NO es un título (no tiene
    exactamente 1 celda): esta tabla no abre su propia sección."""
    rows = table.get("rows") or []
    return bool(rows) and len(rows[0].get("cells", [])) != 1


def _es_continuacion_de_matriz(table):
    """Tabla-matriz (ej. horarios) cortada por página: ninguna de sus
    celdas usa la columna 1 porque esa columna quedó vacía en el corte."""
    rows = table.get("rows") or []
    if not rows:
        return False
    return all(c.get("column_number") != 1 for r in rows for c in r.get("cells", []))


def preparar_tablas(elementos: list) -> list:
    resultado = []
    for e in elementos:
        es_tabla = isinstance(e, dict) and e.get("type") == "table"
        anterior = resultado[-1] if resultado and isinstance(resultado[-1], dict) else None
        anterior_es_tabla = anterior is not None and anterior.get("type") == "table"

        if es_tabla and anterior_es_tabla:
            if _es_titulo_duplicado(e, anterior):
                continue  # título repetido por el corte de página: se descarta

            if _tiene_titulo_colgante_confiable(anterior) and _empieza_sin_titulo(e):
                # Contenido sin título propio, y la tabla anterior quedó
                # con un título sin resolver: se pega como continuación.
                anterior["rows"] = (anterior.get("rows") or []) + (e.get("rows") or [])
                continue

            if _es_continuacion_de_matriz(e):
                nuevas_filas = e.get("rows") or []
                prev_rows = anterior.get("rows") or []
                fusionado = False
                if len(nuevas_filas) == 1 and prev_rows:
                    cols_previas = {c["column_number"]: c for c in prev_rows[-1].get("cells", [])}
                    for c in nuevas_filas[0].get("cells", []):
                        if c["column_number"] in cols_previas:
                            celda = cols_previas[c["column_number"]]
                            celda["content"] = f"{str(celda.get('content', '')).rstrip()}\n{c.get('content', '')}"
                            fusionado = True
                if not fusionado:
                    anterior["rows"] = prev_rows + nuevas_filas
                continue

        resultado.append(e)
    return resultado


def is_matrix_table(rows) -> bool:
    """Tabla-matriz (columnas reales, ej. horarios): la primera fila
    tiene 3+ celdas que no terminan en ':' (son encabezados de columna)."""
    if not rows:
        return False
    first_cells = rows[0].get("cells", [])
    if len(first_cells) < 3:
        return False
    if any(str(c.get("content", "")).rstrip().endswith(":") for c in first_cells):
        return False
    max_col = max((c.get("column_number", 1) for r in rows for c in r.get("cells", [])), default=1)
    return max_col > 2


def parse_matrix_table(rows):
    """Lista de registros usando column_number para emparejar cada celda
    con el encabezado real de su columna. Cuando a una fila le falta la
    PRIMERA columna (ej. 'Componente'), es porque en el PDF original esa
    celda estaba combinada (rowspan) con la fila de arriba: se hereda el
    valor de la fila anterior para esa y cualquier otra columna faltante,
    igual que se ve visualmente en la tabla del PDF."""
    headers = {c.get("column_number"): clean_key(c.get("content")) for c in rows[0].get("cells", [])}
    columnas = sorted(headers.keys())
    primera_columna = columnas[0] if columnas else None

    registros = []
    anterior = {}
    for row in rows[1:]:
        celdas = {c.get("column_number"): c.get("content") for c in row.get("cells", [])}
        es_continuacion = primera_columna is not None and primera_columna not in celdas
        registro = {}
        for col in columnas:
            nombre_col = headers[col]
            if col in celdas:
                add_unique(registro, nombre_col, celdas[col])
            elif es_continuacion and nombre_col in anterior:
                add_unique(registro, nombre_col, anterior[nombre_col])
        for col, valor in celdas.items():
            if col not in headers:
                add_unique(registro, f"columna_{col}", valor)
        registros.append(registro)
        anterior = registro
    return registros


def parse_row_into(row, target: dict):
    """Regla padre-hijo por fila: 2 celdas = clave:valor directo; 3+ =
    primera celda como mini-título y el resto en pares clave:valor (o
    separando 'Etiqueta: valor' si viene junto en una celda)."""
    cells = row.get("cells", [])
    n = len(cells)
    if n == 0:
        return
    if n == 1:
        target.setdefault("otros_elementos", []).append(cells[0].get("content"))
    elif n == 2:
        add_unique(target, clean_key(cells[0].get("content")), cells[1].get("content"))
    else:
        label = clean_key(cells[0].get("content"))
        resto = cells[1:]
        sub = {}
        i = 0
        while i < len(resto):
            embebido = split_embedded_kv(resto[i].get("content"))
            if embebido:
                add_unique(sub, embebido[0], embebido[1])
                i += 1
            elif i + 1 < len(resto):
                add_unique(sub, clean_key(resto[i].get("content")), resto[i + 1].get("content"))
                i += 2
            else:
                add_unique(sub, "valor_adicional", resto[i].get("content"))
                i += 1
        add_unique(target, label, sub)


def _tiene_hijos_antes_del_siguiente_titulo(rows, start_idx):
    j = start_idx
    found = False
    while j < len(rows) and len(rows[j].get("cells", [])) != 1:
        if len(rows[j].get("cells", [])) >= 2:
            found = True
        j += 1
    return found, j


def parse_form_table(rows):
    """Tabla tipo formulario: una fila de 1 celda es el PADRE de las
    filas que siguen (hasta la próxima fila de 1 celda), igual que en el
    ejemplo original ('A. Datos básicos...' como padre de 'Nombre de la
    asignatura' -> 'INTRODUCCION A LA PROGRAMACION')."""
    contenido = {}
    idx, n = 0, len(rows)
    while idx < n:
        row = rows[idx]
        cells = row.get("cells", [])
        if len(cells) == 1:
            label = clean_key(cells[0].get("content"))
            tiene_hijos, next_idx = _tiene_hijos_antes_del_siguiente_titulo(rows, idx + 1)
            if tiene_hijos:
                sub = {}
                for j in range(idx + 1, next_idx):
                    parse_row_into(rows[j], sub)
                add_unique(contenido, label, sub)
                idx = next_idx
            else:
                contenido.setdefault("otros_elementos", []).append(cells[0].get("content"))
                idx += 1
        else:
            parse_row_into(row, contenido)
            idx += 1
    return contenido


# ---------------------------------------------------------------------
# Manejo de secciones anidadas por PATH (lista de claves desde la raíz).
# Antes el código solo llevaba una clave de sección activa a nivel raíz,
# así que un subtítulo como "Básica" dentro de "G. Bibliografía" se
# creaba como sección nueva en la raíz en vez de anidarse dentro de
# "g_bibliografia". Ahora se navega/crea el árbol completo según el path.
# ---------------------------------------------------------------------

def get_container(root: dict, path: list) -> dict:
    """Devuelve (creándolo si falta) el dict ubicado en 'path' dentro de root."""
    d = root
    for k in path:
        nxt = d.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            d[k] = nxt
        d = nxt
    return d


def asegurar_seccion(root: dict, path: list) -> None:
    """Crea el esqueleto de dicts anidados para 'path' sin pisar contenido
    ya existente. Si algún tramo del path ya es una lista (tabla-matriz),
    no se sigue anidando dentro de ella."""
    d = root
    for k in path:
        actual = d.get(k)
        if not isinstance(actual, (dict, list)):
            d[k] = {}
            actual = d[k]
        if isinstance(actual, list):
            return
        d = actual


def set_or_merge(root: dict, path: list, data) -> None:
    """Coloca/fusiona 'data' (dict o list) en la posición 'path' del árbol.
    Si ya había algo ahí, fusiona en vez de sobrescribir (mismo criterio
    que antes: dict+dict fusiona claves, dict+list y list+dict se
    envuelven bajo 'registros' para no perder datos, list+list concatena)."""
    if not path:
        return
    parent = get_container(root, path[:-1])
    key = path[-1]
    existente = parent.get(key)

    if existente is None or existente == {}:
        parent[key] = data
        return

    if isinstance(existente, dict):
        if isinstance(data, dict):
            for k, v in data.items():
                add_unique(existente, k, v)
        else:
            add_unique(existente, "registros", data)
    elif isinstance(existente, list):
        if isinstance(data, list):
            existente.extend(data)
        elif isinstance(data, dict):
            nuevo = {"registros": existente}
            for k, v in data.items():
                add_unique(nuevo, k, v)
            parent[key] = nuevo
        else:
            existente.append(data)
    else:
        parent[key] = {"valor_previo": existente}
        set_or_merge(root, path, data)


def encontrar_lista_de_elementos(data):
    """Ubica la lista de elementos aunque no esté bajo la clave 'elements'."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("elements"), list):
            return data["elements"]
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "type" in v[0]:
                return v
    raise ValueError(
        "No pude encontrar la lista de elementos del documento. Esperaba "
        "una clave 'elements' (lista de objetos con 'type'), o directamente "
        "una lista de esos objetos en la raíz."
    )


_FIN_ORACION = (".", ",", ";")


def _clasificar_parrafo(texto: str, siguiente_tipo):
    """Distingue párrafo-TÍTULO (ej. 'Fechas importantes:') de
    párrafo-CONTENIDO (ej. una descripción larga). Termina en ':' ->
    título. Termina en '.', ',' o ';' -> contenido. Corto y justo antes
    de tabla/lista -> título que las agrupa. Otro caso -> contenido."""
    t = (texto or "").strip()
    if not t:
        return "vacio"
    if t.endswith(":"):
        return "titulo"
    if t.endswith(_FIN_ORACION):
        return "contenido"
    return "titulo" if len(t.split()) <= 10 and siguiente_tipo in ("table", "list") else "contenido"


def transformar(data) -> dict:
    elementos = preparar_tablas(encontrar_lista_de_elementos(data))

    root: dict = {}
    seccion_actual: list = []  # path (lista de claves) de la sección/subsección activa
    seccion_top: list = []     # path de la sección PRINCIPAL activa (1 solo nivel)
    contador_listas = 0
    visto_top_level = False    # True cuando ya se abrió la 1ra sección con letra (A., B., ...)

    def agregar_a_portada(texto: str) -> None:
        """Todo lo que aparece ANTES de la primera sección con letra (nombre
        de la universidad, modalidad, lugar, año, carrera, etc. en la
        carátula) se agrupa siempre bajo la clave fija 'portada', sin
        importar qué tan largo/corto sea el texto ni si parece un título:
        el formato de carátula varía demasiado entre universidades como
        para adivinar cuál línea es cuál por su forma."""
        nonlocal seccion_actual, seccion_top
        seccion_top = ["portada"]
        seccion_actual = ["portada"]
        asegurar_seccion(root, seccion_actual)
        embebido = split_embedded_kv(texto)
        if embebido:
            set_or_merge(root, seccion_actual, {embebido[0]: embebido[1]})
        else:
            texto_limpio = (texto or "").strip()
            if texto_limpio:
                set_or_merge(root, seccion_actual, {"texto": [texto_limpio]})

    def abrir_seccion(texto_titulo: str) -> None:
        """Abre una sección de nivel superior (A., B., C...) o, si ya hay
        una sección principal activa, una subsección que cuelga de ella
        (ej. 'Básica'/'Complementaria' dentro de 'G. Bibliografía')."""
        nonlocal seccion_actual, seccion_top, visto_top_level
        clave = clean_key(texto_titulo)
        if not clave:
            return
        es_top_level = bool(_TOP_LEVEL_HEADING.match((texto_titulo or "").strip()))

        if es_top_level or not seccion_top:
            nuevo_path = [clave]
            seccion_top = nuevo_path
            visto_top_level = True
        else:
            # Subsección: siempre cuelga directo de la sección principal
            # activa (hermana de cualquier otra subsección previa), nunca
            # anidada dentro de la última subsección abierta.
            nuevo_path = seccion_top + [clave]
        asegurar_seccion(root, nuevo_path)
        seccion_actual = nuevo_path

    def asegurar_seccion_por_defecto() -> None:
        nonlocal seccion_actual, seccion_top
        if not seccion_actual:
            seccion_actual = ["contenido"]
            seccion_top = seccion_actual
            asegurar_seccion(root, seccion_actual)

    for idx, e in enumerate(elementos):
        if not isinstance(e, dict):
            continue

        tipo = e.get("type")
        siguiente = elementos[idx + 1] if idx + 1 < len(elementos) else None
        siguiente_tipo = siguiente.get("type") if isinstance(siguiente, dict) else None

        try:
            if tipo == "heading":
                contenido_txt = e.get("content")
                if contenido_txt is None:
                    continue
                texto_limpio = (contenido_txt or "").strip()
                if _TOP_LEVEL_HEADING.match(texto_limpio):
                    abrir_seccion(contenido_txt)
                elif not visto_top_level:
                    agregar_a_portada(contenido_txt)
                else:
                    # Un heading tipo "ÁREA ACADÉMICA: Técnica" es en realidad
                    # un campo clave:valor de la sección actual, no un título
                    # nuevo de subsección.
                    embebido = split_embedded_kv(contenido_txt)
                    if embebido and seccion_actual:
                        set_or_merge(root, seccion_actual, {embebido[0]: embebido[1]})
                    else:
                        abrir_seccion(contenido_txt)

            elif tipo == "paragraph":
                contenido_txt = e.get("content")
                if contenido_txt is None:
                    continue
                if not visto_top_level:
                    agregar_a_portada(contenido_txt)
                else:
                    embebido = split_embedded_kv(contenido_txt)
                    if embebido:
                        asegurar_seccion_por_defecto()
                        set_or_merge(root, seccion_actual, {embebido[0]: embebido[1]})
                    elif _clasificar_parrafo(contenido_txt, siguiente_tipo) == "titulo":
                        abrir_seccion(contenido_txt)
                    else:
                        asegurar_seccion_por_defecto()
                        set_or_merge(root, seccion_actual, {"texto": contenido_txt})

            elif tipo == "table":
                rows = e.get("rows", [])
                titulo_en_tabla = None
                if rows and not is_matrix_table(rows) and len(rows[0].get("cells", [])) == 1:
                    texto_celda = rows[0]["cells"][0].get("content")
                    if _TOP_LEVEL_HEADING.match((texto_celda or "").strip()):
                        titulo_en_tabla = texto_celda

                if titulo_en_tabla:
                    # El título de la sección viene pegado en la primera fila
                    # de la tabla (ej. un "Plan Docente" donde "A. Datos
                    # básicos..." es la fila 1 de la tabla) en vez de venir
                    # como elemento 'heading' aparte.
                    abrir_seccion(titulo_en_tabla)
                    contenido = parse_form_table(rows[1:]) if len(rows) > 1 else {}
                else:
                    contenido = parse_matrix_table(rows) if is_matrix_table(rows) else parse_form_table(rows)

                if not visto_top_level:
                    seccion_top = ["portada"]
                    seccion_actual = ["portada"]
                    asegurar_seccion(root, seccion_actual)
                else:
                    asegurar_seccion_por_defecto()
                set_or_merge(root, seccion_actual, contenido)

            elif tipo == "list":
                contador_listas += 1
                items = [item.get("content") for item in e.get("items", [])]
                if not visto_top_level:
                    seccion_top = ["portada"]
                    seccion_actual = ["portada"]
                    asegurar_seccion(root, seccion_actual)
                else:
                    asegurar_seccion_por_defecto()
                set_or_merge(root, seccion_actual, {f"lista_{contador_listas}": items})

            else:
                if isinstance(e.get("rows"), list):
                    rows = e["rows"]
                    contenido = parse_matrix_table(rows) if is_matrix_table(rows) else parse_form_table(rows)
                    asegurar_seccion_por_defecto()
                    set_or_merge(root, seccion_actual, contenido)
                elif isinstance(e.get("items"), list):
                    contador_listas += 1
                    items = [i.get("content", i) if isinstance(i, dict) else i for i in e["items"]]
                    asegurar_seccion_por_defecto()
                    set_or_merge(root, seccion_actual, {f"lista_{contador_listas}": items})
                elif e.get("content") is not None:
                    if not visto_top_level:
                        agregar_a_portada(e["content"])
                    else:
                        abrir_seccion(e["content"])
        except Exception:
            continue

    return root


# ---------------------------------------------------------------------
# Metadata genérica: varía por universidad, así que se arma con overrides
# explícitos (--metadata) combinados con auto-detección desde la propia
# primera sección del documento (donde suele estar nombre/área/carrera).
# ---------------------------------------------------------------------

def construir_metadata(resultado: dict, archivo_origen: str, overrides: dict) -> dict:
    portada = resultado.get("portada", {})
    if not isinstance(portada, dict):
        portada = {}

    # La primera sección "real" es la primera clave que NO sea 'portada'
    # (que es donde suele estar el detalle estructurado: asignatura,
    # carrera, área académica, modalidad, fecha de elaboración...).
    secciones_reales = {k: v for k, v in resultado.items() if k != "portada"}
    primera_seccion = next(iter(secciones_reales.values()), {})
    if not isinstance(primera_seccion, dict):
        primera_seccion = {}

    # En la portada, cosas como el nombre de la universidad, la modalidad,
    # el lugar y el año suelen venir como líneas sueltas sin etiqueta clara
    # (se guardan en 'texto' como lista). Se intentan reconocer por patrón.
    textos_portada = portada.get("texto", [])
    if isinstance(textos_portada, str):
        textos_portada = [textos_portada]
    elif not isinstance(textos_portada, list):
        textos_portada = []

    universidad_detectada = ""
    modalidad_detectada = ""
    lugar_detectado = ""
    anio_detectado = ""
    for t in textos_portada:
        t = (t or "").strip()
        if not t:
            continue
        if not universidad_detectada and "universidad" in t.lower():
            universidad_detectada = t
        elif not modalidad_detectada and "modalidad" in t.lower():
            modalidad_detectada = t
        elif not anio_detectado and re.fullmatch(r"\d{4}", t):
            anio_detectado = t
        elif not lugar_detectado and ("–" in t or " - " in t or "-" in t):
            lugar_detectado = t

    fuente_portada = {
        "universidad": universidad_detectada,
        "modalidad": modalidad_detectada,
        "lugar": lugar_detectado,
        "anio_documento": anio_detectado,
        **{k: v for k, v in portada.items() if k != "texto"},
    }

    def auto(campo_metadata, *campos_alternativos, default=""):
        if overrides.get(campo_metadata):
            return overrides[campo_metadata]
        candidatos = (campo_metadata,) + campos_alternativos

        # 1) la primera sección real (donde casi siempre está lo importante)
        for campo in candidatos:
            if primera_seccion.get(campo):
                return primera_seccion[campo]

        # 2) cualquier otra sección del documento (ej. la fecha de
        #    elaboración puede estar en la última sección, no en la primera,
        #    según el formato/plantilla de cada universidad)
        for seccion in secciones_reales.values():
            if isinstance(seccion, dict):
                for campo in candidatos:
                    if seccion.get(campo):
                        return seccion[campo]

        # 3) la portada, como último recurso
        for campo in candidatos:
            if fuente_portada.get(campo):
                return fuente_portada[campo]
        return default

    metadata = {
        "archivo_origen": overrides.get("archivo_origen", os.path.basename(archivo_origen)),
        "fecha_procesamiento": overrides.get(
            "fecha_procesamiento", datetime.now().isoformat(timespec="seconds")
        ),
        "universidad": auto("universidad"),
        "modalidad": auto("modalidad", "modalidad_de_estudio"),
        "lugar": auto("lugar"),
        "anio_documento": auto("anio_documento"),
        "area_academica": auto("area_academica", "facultad"),
        "carrera": auto("carrera", "nombre_de_la_carrera"),
        "tipo_documento": overrides.get("tipo_documento", "programa_de_asignatura"),
        "asignatura": auto("asignatura", "programa_de_asignatura", "nombre_de_la_asignatura"),
        "fecha_de_elaboracion": auto("fecha_de_elaboracion"),
    }
    return metadata


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


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Aplana un JSON de sílabo/programa de asignatura (de cualquier "
        "universidad) a un único documento jerárquico listo para MongoDB."
    )
    parser.add_argument("entrada", nargs="?", default="entrada.json",
                         help="Ruta al JSON crudo (elementos extraídos del PDF).")
    parser.add_argument("salida", nargs="?", default="documento_para_mongo_generico.json",
                         help="Ruta del JSON de salida.")
    parser.add_argument("--metadata", dest="metadata_arg", default=None,
                         help="JSON en línea o ruta a archivo .json con overrides de "
                              'metadata, ej: \'{"universidad": "UTPL", "lugar": "Loja - Ecuador", '
                              '"anio_documento": "2020"}\'')
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    overrides = cargar_overrides(args.metadata_arg)

    with open(args.entrada, encoding="utf-8") as f:
        data = json.load(f)

    resultado = transformar(data)
    metadata = construir_metadata(resultado, args.entrada, overrides)
    salida = {"metadata": metadata, **resultado}

    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(args.salida)
```

### `scripts/5_subir_a_mongo_generico.py` — Paso 5

Sube el documento final a MongoDB con la clase `MongoUploader`. Verifica la
conexión antes de intentar nada, y usa `metadata.archivo_origen` como clave
para reemplazar el documento si ese PDF ya se había subido antes, en vez de
duplicarlo. Se puede usar para un archivo puntual o para todos los de una
carpeta.

```python
import argparse
import glob
import os
import sys
import json

from pymongo import MongoClient
from pymongo.errors import PyMongoError


class MongoUploader:
    """Sube documentos JSON (ya aplanados por 4_aplanar_para_mongo_generico.py)
    a una colección de MongoDB, evitando duplicados cuando el mismo PDF se
    vuelve a procesar (se identifica por metadata.archivo_origen)."""

    def __init__(
        self,
        uri: str = None,
        base_datos: str = "planes_docentes",
        coleccion: str = "asignaturas",
        timeout_ms: int = 5000,
    ):
        # Prioridad: uri explícita > variable de entorno MONGODB_URI > localhost
        self.uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
        self.nombre_base_datos = base_datos
        self.nombre_coleccion = coleccion

        self.cliente = MongoClient(self.uri, serverSelectionTimeoutMS=timeout_ms)
        self.db = self.cliente[self.nombre_base_datos]
        self.coleccion = self.db[self.nombre_coleccion]

    # -- soporte para "with MongoUploader(...) as uploader:" ----------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cerrar()

    def verificar_conexion(self) -> bool:
        """Hace un ping al servidor para confirmar que la conexión funciona.
        Lanza la excepción original si falla (con un mensaje más claro)."""
        try:
            self.cliente.admin.command("ping")
            return True
        except PyMongoError as e:
            raise ConnectionError(
                f"No se pudo conectar a MongoDB en '{self.uri}'. "
                f"Verifica que el servidor esté corriendo y la URI sea correcta.\n"
                f"Detalle: {e}"
            ) from e

    def subir_documento(self, documento: dict, clave_unica: str = None):
        """Inserta 'documento' en la colección. Si se da 'clave_unica'
        (normalmente metadata.archivo_origen), hace upsert: si ya existe un
        documento con ese archivo_origen, lo REEMPLAZA en vez de duplicarlo;
        si no existe, lo inserta. Devuelve el _id del documento."""
        if clave_unica:
            resultado = self.coleccion.replace_one(
                {"metadata.archivo_origen": clave_unica},
                documento,
                upsert=True,
            )
            if resultado.upserted_id is not None:
                return resultado.upserted_id
            existente = self.coleccion.find_one(
                {"metadata.archivo_origen": clave_unica}, {"_id": 1}
            )
            return existente["_id"] if existente else None

        resultado = self.coleccion.insert_one(documento)
        return resultado.inserted_id

    def subir_archivo(self, ruta_json: str, actualizar_si_existe: bool = True):
        """Carga un JSON ya aplanado desde disco y lo sube. Devuelve el _id
        del documento en MongoDB (o None si falló)."""
        with open(ruta_json, encoding="utf-8") as f:
            documento = json.load(f)

        clave_unica = None
        if actualizar_si_existe:
            clave_unica = documento.get("metadata", {}).get("archivo_origen")

        _id = self.subir_documento(documento, clave_unica=clave_unica)
        print(f"✔ Subido a MongoDB: {ruta_json} → _id={_id}")
        return _id

    def subir_carpeta(
        self,
        carpeta: str = "JSONObtenidos",
        patron: str = "resultado_*.json",
        actualizar_si_existe: bool = True,
    ) -> list:
        """Sube todos los archivos que calcen con 'patron' dentro de
        'carpeta' (por defecto, todos los resultado_<pdf>.json generados
        por main.py). Devuelve la lista de _id subidos."""
        rutas = sorted(glob.glob(os.path.join(carpeta, patron)))
        if not rutas:
            print(f"No se encontró ningún archivo '{patron}' en '{carpeta}'.")
            return []

        ids = []
        for ruta in rutas:
            try:
                ids.append(self.subir_archivo(ruta, actualizar_si_existe=actualizar_si_existe))
            except Exception as e:
                print(f"✗ Error subiendo {ruta}: {e}")
        return ids

    def cerrar(self) -> None:
        self.cliente.close()


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Sube documentos ya aplanados (resultado_*.json) a MongoDB."
    )
    parser.add_argument(
        "archivo", nargs="?", default=None,
        help="Ruta a un resultado_<pdf>.json puntual. Si se omite, sube TODOS "
             "los resultado_*.json encontrados en --carpeta.",
    )
    parser.add_argument(
        "--carpeta", default="JSONObtenidos",
        help="Carpeta donde buscar los resultado_*.json (por defecto: JSONObtenidos).",
    )
    parser.add_argument(
        "--uri", default=None,
        help="URI de conexión a MongoDB. Si no se da, usa la variable de entorno "
             "MONGODB_URI, o mongodb://localhost:27017/ como último recurso.",
    )
    parser.add_argument("--db", dest="base_datos", default="planes_docentes",
                         help="Nombre de la base de datos (por defecto: planes_docentes).")
    parser.add_argument("--coleccion", default="asignaturas",
                         help="Nombre de la colección (por defecto: asignaturas).")
    parser.add_argument(
        "--sin-actualizar", dest="actualizar", action="store_false",
        help="Si se pasa, siempre INSERTA un documento nuevo en vez de "
             "reemplazar uno existente con el mismo archivo_origen.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])

    with MongoUploader(uri=args.uri, base_datos=args.base_datos, coleccion=args.coleccion) as uploader:
        uploader.verificar_conexion()
        print(f"Conectado a MongoDB → base de datos '{args.base_datos}', colección '{args.coleccion}'")

        if args.archivo:
            uploader.subir_archivo(args.archivo, actualizar_si_existe=args.actualizar)
        else:
            ids = uploader.subir_carpeta(carpeta=args.carpeta, actualizar_si_existe=args.actualizar)
            print(f"\nTotal subidos: {len(ids)}")
```

---

La documentación ampliada está en
[`documentacion/flujo.md`](./documentacion/flujo.md) (explicación detallada
de cada paso) y en [`documentacion/scripts.md`](./documentacion/scripts.md)
(referencia de entradas y salidas de cada script).
