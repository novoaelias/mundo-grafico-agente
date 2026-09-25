"""Mundo Gráfico completo: el webhook de Chatwoot del kit + el panel interno.

    python servidor_mundografico.py

Es el mismo servidor que `webhook_chatwoot.py`, con dos agregados:

    1. Antes de levantar nada, se aplican las migraciones de Postgres y se
       inicializan las herramientas (`mundografico.herramientas.inicializar`)
       con el cliente de Chatwoot y la configuración del negocio.
    2. Al FastAPI que arma `agente.web.webhook.crear_app()` se le suma el
       router del panel (`/panel/...`) y sus archivos estáticos.

No se toca `webhook_chatwoot.py`: ese sigue siendo el arranque "solo el
webhook" del kit original, útil para un `git diff` limpio contra upstream.
Este archivo es el que corre de verdad en el servidor (es lo que arranca
el Dockerfile).

Antes de arrancar, además de las variables de Chatwoot del .env.example,
hacen falta las de Mundo Gráfico — ver la sección correspondiente ahí
mismo (POSTGRES_DSN, PANEL_USUARIO, PANEL_CLAVE, etc.).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agente.consola import preparar  # noqa: E402

preparar()  # antes de imprimir nada, para que las tildes no rompan Windows

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from agente import ErrorDeConfiguracion  # noqa: E402
from agente import Config as ConfigAgente  # noqa: E402
from agente.web.webhook import crear_app  # noqa: E402
from mundografico.canal import ChatwootMundoGrafico  # noqa: E402
from mundografico import base_datos, demo, herramientas, horario, panel, sheets  # noqa: E402
from mundografico.chatwoot_api import ClienteChatwoot  # noqa: E402
from mundografico.config import Config as ConfigNegocio  # noqa: E402
from mundografico.config import ErrorDeConfiguracion as ErrorDeConfiguracionMG  # noqa: E402

AMBAR = "\033[38;5;214m"
GRIS = "\033[90m"
ROJO = "\033[91m"
FIN = "\033[0m"

# Cada cuánto se reintenta escribir en Sheets los pedidos que quedaron
# pendientes (porque la API estuvo caída, o sin credenciales cuando se
# creó el pedido). El intento "al toque" pasa por herramientas/pedidos.py
# y panel/rutas.py — esto es solo la red de seguridad para lo que se les
# escapó a esos dos.
INTERVALO_REINTENTO_SHEETS = 5 * 60


def construir_app(config_agente: ConfigAgente, config_mg: ConfigNegocio) -> FastAPI:
    """Arma el FastAPI completo: migraciones + herramientas + webhook + panel.

    Separado de `main()` para poder probarlo con configs de prueba, sin
    levantar un servidor de verdad (ver tests/test_mundografico_servidor.py).
    """
    aplicadas = base_datos.aplicar_migraciones(
        config_mg.postgres_dsn, incluir_demo=config_mg.negocio.modo_demo,
    )
    if config_mg.negocio.modo_demo:
        with base_datos.obtener_pool().connection() as conexion:
            demo.preparar_demo(conexion, horario.hoy())

    herramientas.inicializar(
        chatwoot_url=config_agente.chatwoot_url,
        chatwoot_token=config_agente.chatwoot_token,
        chatwoot_cuenta_id=config_agente.chatwoot_cuenta_id,
        etiqueta_humano=config_agente.chatwoot_etiqueta_humano,
        negocio=config_mg.negocio,
        sheets=config_mg.sheets,
    )

    canal = ChatwootMundoGrafico(
        url=config_agente.chatwoot_url,
        token=config_agente.chatwoot_token,
        cuenta_id=config_agente.chatwoot_cuenta_id,
        etiqueta_humano=config_agente.chatwoot_etiqueta_humano,
    )
    app = crear_app(config_agente, canal=canal)

    @app.get("/panel", include_in_schema=False)
    async def abrir_panel() -> RedirectResponse:
        # FastAPI redirige automáticamente /panel a /panel/ usando el esquema
        # interno HTTP del proxy; una ruta explícita conserva HTTPS en el navegador.
        return RedirectResponse(url="/panel/pedidos")

    app.mount(
        "/panel/estaticos",
        StaticFiles(directory=str(panel.CARPETA_ESTATICOS)),
        name="panel-estaticos",
    )

    cliente_chatwoot_panel = ClienteChatwoot(
        url=config_agente.chatwoot_url,
        token=config_agente.chatwoot_token,
        cuenta_id=config_agente.chatwoot_cuenta_id,
    )
    app.include_router(panel.crear_router(
        config_mg, cliente_chatwoot_panel, config_agente.chatwoot_etiqueta_humano,
    ))

    app.state.migraciones_aplicadas = aplicadas
    return app


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config_agente = ConfigAgente.desde_entorno()
        config_mg = ConfigNegocio.desde_entorno()
    except (ErrorDeConfiguracion, ErrorDeConfiguracionMG, ValueError) as e:
        print(f"{ROJO}{e}{FIN}")
        return 1

    print(f"{AMBAR}Aplicando migraciones de Postgres...{FIN}")
    app = construir_app(config_agente, config_mg)

    aplicadas = app.state.migraciones_aplicadas
    print(f"{GRIS}   {', '.join(aplicadas) if aplicadas else '(ya estaba todo al día)'}{FIN}")

    if config_mg.sheets.activo:
        threading.Thread(
            target=_reintentar_sheets_periodicamente,
            args=(config_mg,),
            daemon=True,
            name="reintento-sheets",
        ).start()

    puerto = _puerto()

    print(f"\n{AMBAR}Mundo Gráfico escuchando{FIN} - puerto {puerto}")
    print(f"{GRIS}   {config_agente.proveedor} - {config_agente.modelo}{FIN}")
    print(f"{GRIS}   Sheets: {'activo' if config_mg.sheets.activo else 'apagado'}{FIN}")
    print(f"{GRIS}   POST /chatwoot/<token>   ·   GET /salud   ·   GET /panel{FIN}\n")

    uvicorn.run(app, host="0.0.0.0", port=puerto, log_level="info")
    return 0


def _reintentar_sheets_periodicamente(config_mg: ConfigNegocio) -> None:
    """Corre en un hilo aparte durante toda la vida del proceso.

    Nada de asyncio acá: sincronizar_pendientes() ya es sincrónico (usa
    gspread, que es bloqueante), así que un hilo de toda la vida alcanza
    y evita pelearse con el lifespan que ya arma agente/web/webhook.py.
    """
    registro = logging.getLogger("mundografico.sheets")
    while True:
        time.sleep(INTERVALO_REINTENTO_SHEETS)
        try:
            cantidad = sheets.sincronizar_pendientes(
                config_mg.sheets, base_datos.obtener_pool(),
            )
            if cantidad:
                registro.info("Reintento periódico: %d pedido(s) sincronizados con Sheets", cantidad)
        except Exception as e:
            registro.error("Falló el reintento periódico de Sheets: %s", e)


def _puerto() -> int:
    return int(os.getenv("PUERTO", "8000"))


if __name__ == "__main__":
    raise SystemExit(main())
