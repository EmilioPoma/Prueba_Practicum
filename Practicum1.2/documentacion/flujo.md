# Explicación detallada del flujo

Este documento explica el porqué de cada paso. La meta final es llegar a un
solo documento clave:valor, con su metadata, que se pueda subir directo a
MongoDB.

El flujo completo es:

```
PDF -> (1) JSON crudo -> (2) solo texto -> (3) documento ordenado -> (4) clave:valor + metadata -> (5) MongoDB
```

Los pasos 1 al 4 trabajan sobre el mismo archivo
`JSONObtenidos/<nombre_pdf>.json`, sobrescribiéndolo cada vez, y el paso 5
toma ese archivo ya terminado y lo sube a la base de datos. Todo esto lo
encadena `main.py`, aunque cada paso también se puede correr por separado.

## Paso 1 — Extracción cruda

La librería opendataloader_pdf (que por dentro corre en Java) analiza el PDF
y devuelve un árbol JSON con todo lo que detecta: heading, paragraph, list,
table, image, cada uno con su página y su bounding box. También genera una
versión en Markdown y extrae las imágenes a una carpeta aparte.

¿Por qué no quedarse con este JSON y ya? Por dos razones. Primero, sus tablas
no siempre respetan la estructura visual real del PDF. Y segundo, el orden en
que entrega los elementos no siempre coincide con el orden en que se lee el
documento. Por eso existen los pasos 2 y 3.

## Paso 2 — Filtrar solo el texto

De todo el JSON crudo se conservan solo heading, paragraph y list. Las tablas
se descartan a propósito: en el paso 3 se vuelven a extraer con pdfplumber,
que da mejor estructura de filas y columnas y, sobre todo, la posición exacta
de cada tabla en la página.

## Paso 3 — Tablas reales y orden de lectura

### El problema de las coordenadas

Las dos fuentes usan sistemas de coordenadas distintos:

- opendataloader_pdf entrega el texto con su bounding box en coordenadas PDF:
  el origen está abajo a la izquierda y la Y crece hacia arriba.
- pdfplumber (con `find_tables`) entrega cada tabla en su propio sistema: el
  origen está arriba a la izquierda y el valor `top` crece hacia abajo.

La conversión que une los dos mundos es una sola línea:

```
y_top = page.height - top      # borde superior de la tabla, en coords PDF
```

Con todo en el mismo sistema, se ordena cada página de arriba hacia abajo
(Y descendente) y, si dos elementos están a la misma altura, de izquierda a
derecha (X ascendente):

```python
sorted(elementos, key=lambda e: (e["page_number"], -e["y_top"], e["x0"]))
```

Con eso se reconstruye el orden de lectura real: cada tabla queda intercalada
exactamente entre el texto que la precede y el que la sigue en el PDF.

### Los duplicados, en tres niveles

opendataloader_pdf a veces reporta como párrafo o heading un texto que en
realidad es el contenido de una celda. Para no repetir información, cada
texto se compara contra las tablas de su misma página en tres niveles:

1. coincidencia exacta con una celda (normalizando espacios y mayúsculas);
2. contención dentro del texto concatenado de toda la tabla;
3. contención dentro de una celda individual.

## Paso 4 — Aplanado clave:valor con metadata

Es el paso con más lógica propia. Trabaja en varias fases.

### Fase A — Reconstruir las tablas cortadas por página

Los PDF cortan las tablas al cambiar de página, y pdfplumber las devuelve
como si fueran tablas separadas. Antes de interpretarlas, el script las
reconstruye con tres reglas:

- Título duplicado: si una "tabla" es una sola fila de una celda cuyo texto
  repite exacto el título con el que terminó la tabla anterior (un artefacto
  típico del salto de página), se descarta.
- Título colgante: si la tabla anterior terminó en una fila-título de una
  celda (por ejemplo "Semana 6") y la tabla siguiente no abre con un título
  propio, sus filas se pegan a la anterior, porque ese contenido pertenecía
  al título que quedó colgando.
- Matriz cortada: si en la nueva tabla ninguna celda usa la columna 1, es la
  continuación de una tabla tipo matriz (como el horario de clases). Se
  fusiona usando el número de columna; si es una sola fila, su texto se
  concatena a las celdas correspondientes de la última fila anterior.

### Fase B — Interpretar cada tabla

Hay dos tipos de tabla, y el script los detecta solo:

- Tabla matriz (`is_matrix_table`): la primera fila tiene 3 o más celdas que
  no terminan en dos puntos, o sea que son encabezados de columna (el caso
  del horario de clases). Se convierte en una lista de registros
  {encabezado: valor}, usando el número de columna para emparejar cada celda
  con su columna real. Cuando a una fila le falta la primera columna es
  porque en el PDF esa celda estaba combinada verticalmente con la de arriba
  (rowspan, como pasa con la columna "Componente"); en ese caso se hereda el
  valor de la fila anterior, igual que se ve en el PDF.
- Tabla formulario (`parse_form_table`): todas las demás. Se aplica la regla
  padre-hijo: una fila de una sola celda (por ejemplo "A. Datos básicos de la
  asignatura") es el padre de las filas que siguen, hasta la próxima fila de
  una celda. Dentro de cada bloque, una fila de dos celdas es un par
  clave:valor directo; con tres o más celdas, la primera funciona como
  mini-título y el resto se agrupa en pares. Una celda marcada con "x" o "✓"
  significa que esa opción está seleccionada, y se guarda la etiqueta.

### Fase C — Armar las secciones del documento

Los documentos institucionales casi siempre enumeran sus secciones
principales con una letra mayúscula y un punto: "A. DATOS DE
IDENTIFICACIÓN", "G. BIBLIOGRAFÍA". El script usa ese patrón (`_TOP_LEVEL_HEADING`)
para decidir la jerarquía:

- Si un encabezado calza con ese patrón, abre una sección nueva en la raíz
  del documento.
- Si no calza pero ya hay una sección principal abierta, se toma como
  subsección de esa sección (por ejemplo "Básica" y "Complementaria" dentro
  de "G. Bibliografía"). Las subsecciones siempre cuelgan de la sección
  principal activa, nunca una dentro de otra.
- Todo lo que aparece antes de la primera sección con letra, es decir la
  carátula, se agrupa bajo una clave fija llamada `portada`. Esto se hace así
  a propósito: el formato de carátula cambia demasiado entre universidades
  como para adivinar por la forma del texto qué línea es el nombre de la
  universidad, cuál la carrera y cuál el año.

También hay un caso especial: a veces el título de la sección no viene como
un elemento heading aparte, sino pegado como primera fila de una tabla. El
script lo detecta y abre la sección igual, usando el resto de las filas como
su contenido.

### Fase D — El texto

- Un heading con el patrón "Etiqueta: valor" (como "ÁREA ACADÉMICA: Técnica")
  no es un título nuevo, es un campo de la sección actual, y así se guarda.
- Un párrafo se clasifica según su forma: si termina en dos puntos es un
  título de sección (como "Fechas importantes:"); si termina en punto, coma o
  punto y coma es contenido; si es corto (10 palabras o menos) y viene justo
  antes de una tabla o lista, se toma como el título que las agrupa; y en
  cualquier otro caso es contenido.
- Las listas se guardan como `lista_N: [items]` dentro de la sección actual.

### Fase E — La metadata

Al documento final se le antepone un bloque `metadata` con campos como
universidad, modalidad, lugar, año, área académica, carrera, asignatura y
fecha de elaboración, más el nombre del archivo de origen y la fecha en que
se procesó.

Esos campos se arman combinando dos fuentes: los overrides que se pasen con
la opción `--metadata`, que tienen prioridad, y la auto-detección desde el
propio contenido del documento. La auto-detección busca en este orden: primero
en la primera sección real (que es donde suele estar el detalle de la
asignatura), luego en cualquier otra sección del documento (porque la fecha de
elaboración, por ejemplo, puede estar al final según la plantilla), y como
último recurso en la portada.

Esta parte es la que hace que el flujo sirva para documentos de cualquier
universidad, porque nada queda hardcodeado a un formato en particular.

Al correrlo sobre nuestros dos PDF se vio bien la diferencia. En el DSOF la
metadata se llenó sola por completo, porque su carátula trae el nombre de la
universidad, la modalidad, el lugar y el año. En el PLAN se detectaron el
área académica, la carrera, la asignatura y la fecha, pero universidad,
modalidad, lugar y año quedaron vacíos, simplemente porque el documento no
los trae en ninguna parte. Ese es el caso para el que existe `--metadata`:
cuando el dato no está en el PDF, no hay forma de deducirlo y hay que
pasarlo a mano.

### Claves seguras y sin pérdida de datos

- `clean_key()` normaliza solo las claves, nunca los valores: quita tildes,
  reemplaza cualquier símbolo por guión bajo (los puntos rompen la notación
  seccion.campo de Mongo) y deja todo en snake_case en minúsculas.
- `add_unique()` evita sobrescribir: si una clave se repite, convierte el
  valor en una lista y va acumulando.

## Paso 5 — Subida a MongoDB

El último paso toma el JSON ya terminado y lo inserta en una colección de
MongoDB, usando la clase `MongoUploader`.

Lo primero que hace es un ping al servidor para confirmar que la conexión
funciona, y si falla lanza un error con un mensaje claro en vez de quedarse
colgado. La URI se resuelve en este orden: la que se pase por argumento, la
variable de entorno `MONGODB_URI`, y si no hay ninguna, `localhost:27017`.

Para no llenar la base de duplicados cuando se reprocesa el mismo PDF, la
subida se hace con un upsert usando `metadata.archivo_origen` como clave: si
ya existe un documento con ese mismo archivo de origen, lo reemplaza con la
versión nueva; si no existe, lo inserta.
