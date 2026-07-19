# Referencia de scripts

| Script | Entrada | Salida |
|--------|---------|--------|
| `main.py` | PDF detectado o por argumento | corre los pasos 1 a 5 sobre `JSONObtenidos/<nombre_pdf>.json` |
| `0_detectar_pdf.py` | — | auxiliar (no se ejecuta solo) |
| `1_extraer_pdf_opendataloader.py` | PDF detectado o por argumento | `JSONObtenidos/<nombre_pdf>.json`, `<nombre_pdf>.md`, `<nombre_pdf>_images/` |
| `2_filtrar_contenido_sin_tablas.py` | `JSONObtenidos/<nombre_pdf>.json` | el mismo archivo, sobrescrito |
| `3_construir_documento_final_ordenado.py` | PDF + `JSONObtenidos/<nombre_pdf>.json` | el mismo archivo, sobrescrito |
| `4_aplanar_para_mongo_generico.py` | entrada y salida por argumento | JSON clave:valor con su metadata |
| `5_subir_a_mongo_generico.py` | JSON final (por argumento o toda una carpeta) | documento insertado en MongoDB |

## `main.py`

Es el orquestador del flujo. Corre los cinco pasos seguidos para un mismo
PDF y termina subiendo el resultado a MongoDB. Detecta el PDF igual que los
demás scripts, y acepta estas opciones:

- `--metadata`: JSON en línea o ruta a un archivo con overrides de metadata.
- `--sin-mongo`: hace los pasos 1 al 4 y no sube nada.
- `--mongo-uri`, `--mongo-db`, `--mongo-coleccion`: para apuntar a otro
  servidor, base o colección de los que trae por defecto (`planes_docentes` y
  `asignaturas`).

Un detalle de implementación: como los archivos de los pasos empiezan con un
número, no se pueden importar con la sintaxis normal de Python (un nombre de
módulo no puede empezar por un dígito). Por eso los carga con
`importlib.import_module()`. El paso 5 además se importa de forma diferida,
así quien use `--sin-mongo` no necesita tener pymongo instalado.

## `0_detectar_pdf.py`

Es lo que hace que el flujo sirva para cualquier PDF sin tocar el código.
`detectar_pdf()` usa el argumento de línea de comandos si se le pasó uno; si
no, busca los `.pdf` de la carpeta actual: con uno solo lo toma directo, con
varios muestra un menú numerado, y si no hay ninguno lanza un
FileNotFoundError. `nombre_base()` le quita la ruta y la extensión al
archivo, y ese nombre es el que se usa para el JSON de trabajo.

## `1_extraer_pdf_opendataloader.py` — Paso 1

La función `extraer_pdf(pdf_path, base)` crea la carpeta `JSONObtenidos/` si
no existe y llama a `opendataloader_pdf.convert()` con
`format="markdown,json"`. Necesita Java en el PATH. Genera el JSON crudo, la
versión en Markdown y la carpeta de imágenes del PDF.

## `2_filtrar_contenido_sin_tablas.py` — Paso 2

La función `filtrar_contenido(base)` abre el JSON del paso 1, se queda solo
con los elementos heading, paragraph y list, y sobrescribe el mismo archivo
con la forma `{"file_name": ..., "kids": [...]}`. Si el archivo no existe,
avisa que primero hay que correr el paso de extracción.

## `3_construir_documento_final_ordenado.py` — Paso 3

La función `construir_documento_final(pdf_path, base)` hace cuatro cosas:

1. Recorre el PDF con pdfplumber y por cada tabla que encuentra
   (`page.find_tables()`) guarda su id con el formato `T{página}_{n}`, sus
   filas limpias (sin celdas vacías) y su posición, convertida con
   `y_top = page.height - top`.
2. Carga el texto del paso 2 y elimina el que está duplicado dentro de alguna
   tabla de su misma página, comparando en tres niveles: celda exacta, texto
   concatenado de la tabla, y dentro de una celda.
3. Une texto y tablas y ordena todo por página, Y descendente y X ascendente.
4. Sobrescribe el mismo archivo con `{"file_name", "total_elements",
   "elements"}`, sin los campos auxiliares de posición, e imprime un resumen
   con el conteo por tipo de elemento.

## `4_aplanar_para_mongo_generico.py` — Paso 4

Se usa así: `python 4_aplanar_para_mongo_generico.py entrada.json salida.json`,
y acepta `--metadata` para fijar campos a mano. Sus funciones principales:

- `preparar_tablas()` reconstruye las tablas que quedaron cortadas por los
  saltos de página (título duplicado, título colgante, matriz cortada).
- `is_matrix_table()` decide si una tabla es matriz (con encabezados de
  columna) o formulario. `parse_matrix_table()` produce registros y hereda
  las celdas combinadas de la fila anterior (rowspan); `parse_form_table()`
  aplica la regla padre-hijo, donde una fila de una celda es el título del
  bloque.
- `transformar()` recorre todos los elementos y arma la jerarquía de
  secciones. Usa el patrón de "letra mayúscula y punto" para saber qué
  encabezado abre una sección nueva de la raíz y cuál es subsección, y agrupa
  bajo `portada` todo lo que viene antes de la primera sección con letra.
- `construir_metadata()` arma el bloque de metadata combinando los overrides
  que se pasen con la auto-detección desde el contenido del documento.
- `clean_key()` normaliza las claves (snake_case, sin tildes ni símbolos) y
  `add_unique()` acumula en lista en vez de sobrescribir cuando una clave se
  repite.

El archivo de salida queda con la forma `{"metadata": {...}, ...secciones}`.

## `5_subir_a_mongo_generico.py` — Paso 5

Define la clase `MongoUploader`, que se puede usar con `with` para que cierre
la conexión sola. Sus métodos:

- `verificar_conexion()` hace un ping al servidor y lanza un error claro si
  no responde.
- `subir_documento()` inserta el documento; si se le pasa una clave única
  hace un upsert en vez de insertar, para no duplicar.
- `subir_archivo()` carga un JSON del disco y lo sube, usando
  `metadata.archivo_origen` como clave única.
- `subir_carpeta()` sube todos los archivos que calcen con un patrón dentro
  de una carpeta.

Como script acepta un archivo puntual o ninguno (en cuyo caso sube todos los
que encuentre), y las opciones `--uri`, `--db`, `--coleccion` y
`--sin-actualizar` (esta última fuerza a insertar siempre uno nuevo en vez de
reemplazar el existente).

La URI de conexión se resuelve en este orden: la que se pase por argumento,
la variable de entorno `MONGODB_URI`, y como último recurso
`mongodb://localhost:27017/`.
