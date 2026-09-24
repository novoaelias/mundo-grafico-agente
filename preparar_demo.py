"""Reposiciona los pedidos ficticios antes de la presentación.

    python preparar_demo.py

Usa POSTGRES_DSN y solo funciona con MG_MODO_DEMO=true.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from mundografico import base_datos, demo, horario  # noqa: E402
from mundografico.config import Config  # noqa: E402


def main() -> int:
    config = Config.desde_entorno()
    if not config.negocio.modo_demo:
        print("Activá MG_MODO_DEMO=true antes de preparar datos ficticios.")
        return 1
    try:
        base_datos.aplicar_migraciones(config.postgres_dsn, incluir_demo=True)
        with base_datos.obtener_pool().connection() as conexion:
            dias = demo.preparar_demo(conexion, horario.hoy())
    finally:
        base_datos.cerrar_pool()
    print("Demo preparada para:", ", ".join(d.isoformat() for d in dias))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
