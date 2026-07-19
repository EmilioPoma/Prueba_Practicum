"""
5_subir_a_mongo_generico.py
────────────────────
PASO 5 (opcional) del flujo: sube los documentos ya aplanados
(JSONObtenidos/resultado_<pdf>.json) a una base de datos MongoDB.

Requiere el driver oficial:
    pip install pymongo

Uso como script:
    # Sube TODOS los resultado_*.json que haya en JSONObtenidos
    python 5_subir_a_mongo_generico.py

    # Sube un archivo puntual
    python 5_subir_a_mongo_generico.py JSONObtenidos/resultado_DSOF_1067-O20F21.json

    # Apuntando a otro servidor / base / colección
    python 5_subir_a_mongo_generico.py --uri "mongodb+srv://usuario:clave@cluster.mongodb.net" \
        --db planes_docentes --coleccion asignaturas

    # También se puede pasar la URI por variable de entorno en vez de
    # escribirla en la línea de comandos (recomendado si tiene contraseña):
    #   export MONGODB_URI="mongodb+srv://usuario:clave@cluster.mongodb.net"
    #   python 5_subir_a_mongo_generico.py

Uso como clase (ej. integrado en main.py como paso final):
    from subir_a_mongodb import MongoUploader

    with MongoUploader(base_datos="planes_docentes", coleccion="asignaturas") as uploader:
        uploader.subir_archivo("JSONObtenidos/resultado_DSOF_1067-O20F21.json")
"""

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
