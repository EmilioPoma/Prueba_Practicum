"""
4_aplanar_para_mongo_generico.py

Aplana el JSON extraído del PDF (sílabo / programa de asignatura) en UN
único diccionario jerárquico clave:valor, listo para subir a MongoDB.
Las CLAVES se normalizan (sin tildes, sin puntos, sin espacios,
snake_case) para que cualquier consulta con notación de puntos funcione
sin errores; los VALORES (el contenido real) se dejan intactos, con
tildes y formato original.

Pensado para funcionar con documentos de CUALQUIER universidad: los
metadatos (universidad, lugar, año, etc.) se pasan como overrides desde
la línea de comandos o se auto-detectan del propio contenido cuando es
posible; el resto de la estructura se infiere del documento, no está
hardcodeada a una universidad en particular.

Uso:
    python3 4_aplanar_para_mongo_generico.py entrada.json salida.json
    python3 4_aplanar_para_mongo_generico.py entrada.json salida.json \
        --metadata '{"universidad": "UTPL", "lugar": "Loja - Ecuador", "anio_documento": "2020"}'
    python3 4_aplanar_para_mongo_generico.py entrada.json salida.json --metadata overrides.json
"""

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
