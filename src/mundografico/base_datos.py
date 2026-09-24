"""Conexión a Postgres y migraciones de Mundo Gráfico.

Un solo pool para todo el proceso: lo comparten las herramientas del agente
y las rutas del panel, así ninguna de las dos abre una conexión por pedido.

Las migraciones son archivos `.sql` en `migraciones/`, se aplican en orden
alfabético al arrancar el servidor (ver `servidor_mundografico.py`) y quedan
anotadas en `mundografico.schema_migraciones` — correr el servidor de nuevo
no repite un seed ni pisa datos que ya estén cargados.

Cada archivo de migración es SQL sin parámetros (nada de `%s`), a propósito:
así se puede mandar entero de una sola vez con `execute()`. Con parámetros,
psycopg no deja correr varias sentencias separadas por `;` en el mismo
`execute()` — es una limitación real de la librería, no un capricho nuestro.
"""

from __future__ import annotations

import logging
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

registro = logging.getLogger("mundografico.base_datos")

CARPETA_MIGRACIONES = Path(__file__).parent / "migraciones"

_pool: ConnectionPool | None = None


def iniciar_pool(dsn: str) -> ConnectionPool:
    """Arma el pool si todavía no existe. Es seguro llamarla más de una vez."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


def obtener_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError(
            "El pool de Postgres no se inició todavía: llamá a "
            "iniciar_pool(dsn) antes (lo hace aplicar_migraciones al arrancar)."
        )
    return _pool


def cerrar_pool() -> None:
    """Para el apagado prolijo del servidor y para los tests."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def aplicar_migraciones(dsn: str, incluir_demo: bool = False) -> list[str]:
    """Corre los `.sql` de `migraciones/` que todavía no se aplicaron.

    Devuelve los nombres de los archivos que se aplicaron recién ahora
    (lista vacía si ya estaba todo al día). Se llama una vez al arrancar.
    """
    pool = iniciar_pool(dsn)
    aplicadas: list[str] = []

    with pool.connection() as conexion:
        conexion.execute("CREATE SCHEMA IF NOT EXISTS mundografico")
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS mundografico.schema_migraciones (
                nombre      TEXT PRIMARY KEY,
                aplicada_en TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conexion.commit()

        ya_aplicadas = {
            fila["nombre"]
            for fila in conexion.execute(
                "SELECT nombre FROM mundografico.schema_migraciones"
            ).fetchall()
        }

        for archivo in sorted(CARPETA_MIGRACIONES.glob("*.sql")):
            if archivo.name == "003_demo.sql" and not incluir_demo:
                continue
            if archivo.name in ya_aplicadas:
                continue

            registro.info("Aplicando migración %s", archivo.name)
            try:
                conexion.execute(archivo.read_text(encoding="utf-8"))
                conexion.execute(
                    "INSERT INTO mundografico.schema_migraciones (nombre) "
                    "VALUES (%s)",
                    (archivo.name,),
                )
            except Exception:
                # Si una migración se rompe a la mitad, no queremos que
                # quede a medio aplicar y sin registrar: eso deja la base en
                # un estado que ni "ya está" ni "no se aplicó" describen bien.
                conexion.rollback()
                raise

            conexion.commit()
            aplicadas.append(archivo.name)

    return aplicadas
