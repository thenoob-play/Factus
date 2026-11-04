"""Aplica en orden las migraciones SQL de backend/crudDataBase/migraciones.

Uso:
    python -m scripts.migrar                 # base configurada en MYSQL_DB
    python -m scripts.migrar --db factus_test --crear
    python -m scripts.migrar --estado        # muestra qué versiones están aplicadas

Cada archivo se aplica una sola vez y queda registrado en `schema_migrations`.
Soporta `DELIMITER` (necesario para triggers). En MySQL el DDL hace commit
implícito: si una migración falla a mitad, restaura el respaldo antes de reintentar.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.crudDataBase.configDataBase.conf import settings  # noqa: E402

MIGRACIONES_DIR = ROOT / "backend" / "crudDataBase" / "migraciones"
_NOMBRE_DB = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def dividir_sentencias(sql: str) -> list[str]:
    """Divide un script en sentencias respetando `DELIMITER`, comillas y comentarios."""
    sentencias: list[str] = []
    delimitador = ";"
    actual: list[str] = []
    for linea in sql.splitlines():
        limpia = linea.strip()
        match = re.match(r"^DELIMITER\s+(\S+)\s*$", limpia, re.IGNORECASE)
        if match:
            delimitador = match.group(1)
            continue
        if not actual and (not limpia or limpia.startswith("--")):
            continue
        actual.append(linea)
        if limpia.endswith(delimitador):
            sentencia = "\n".join(actual).rstrip()
            sentencia = sentencia[: -len(delimitador)].strip()
            if sentencia:
                sentencias.append(sentencia)
            actual = []
    resto = "\n".join(actual).strip()
    if resto:
        sentencias.append(resto)
    return sentencias


def conectar(database: str | None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def aplicar(database: str, crear: bool = False, verbose: bool = True) -> list[str]:
    if not _NOMBRE_DB.match(database):
        raise ValueError("Nombre de base de datos inválido.")
    if crear:
        with conectar(None) as conn, conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )

    aplicadas: list[str] = []
    with conectar(database) as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version varchar(100) NOT NULL PRIMARY KEY,
              aplicado_en datetime NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cur.execute("SELECT version FROM schema_migrations")
        hechas = {row[0] for row in cur.fetchall()}

        for archivo in sorted(MIGRACIONES_DIR.glob("*.sql")):
            version = archivo.stem
            if version in hechas:
                continue
            if verbose:
                print(f"→ Aplicando {archivo.name} ...")
            for sentencia in dividir_sentencias(archivo.read_text(encoding="utf-8")):
                cur.execute(sentencia)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            aplicadas.append(version)
    if verbose:
        print("Sin migraciones pendientes." if not aplicadas else f"Aplicadas: {', '.join(aplicadas)}")
    return aplicadas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=settings.DB_NAME, help="Base de datos destino.")
    parser.add_argument("--crear", action="store_true", help="Crea la base si no existe.")
    parser.add_argument("--estado", action="store_true", help="Solo muestra el estado.")
    args = parser.parse_args()

    if args.estado:
        with conectar(args.db) as conn, conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE 'schema_migrations'")
            hechas = set()
            if cur.fetchone():
                cur.execute("SELECT version FROM schema_migrations")
                hechas = {row[0] for row in cur.fetchall()}
        for archivo in sorted(MIGRACIONES_DIR.glob("*.sql")):
            marca = "✔" if archivo.stem in hechas else "·"
            print(f"{marca} {archivo.name}")
        return

    aplicar(args.db, crear=args.crear)


if __name__ == "__main__":
    main()
