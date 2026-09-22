"""Las rutas del panel interno: pedidos, catálogo y taller.

Pensado para HTMX: la mayoría de las acciones (marcar listo, cambiar un
precio) devuelven el fragmento HTML de la fila que cambió, no la página
entera — así el trabajador ve el efecto al toque, sin recargar nada.

Nota sobre el alcance de esta demo: la edición de catálogo cubre nombre,
categoría, unidad, precio, mínimo y tiempos. Las escalas de precio por
cantidad (`productos.escalas`) se muestran pero no se editan desde acá
todavía — armar una UI para agregar/quitar tramos de una lista JSON es una
pantalla en sí misma, y no es lo que hace falta para la demo. Se editan a
mano en la base mientras tanto.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import base_datos, horario, sheets
from .. import catalogo as motor
from .. import pedidos as datos
from ..chatwoot_api import ClienteChatwoot
from ..config import Config
from .auth import requerir_acceso

registro = logging.getLogger("mundografico.panel")

CARPETA = Path(__file__).parent
CARPETA_ESTATICOS = CARPETA / "estaticos"

ESTADOS_PEDIDO = ("pendiente", "en_proceso", "listo", "entregado", "cancelado")
DIAS_SEMANA = (
    (1, "lunes"), (2, "martes"), (3, "miércoles"), (4, "jueves"),
    (5, "viernes"), (6, "sábado"), (7, "domingo"),
)


def crear_router(config: Config, chatwoot: ClienteChatwoot) -> APIRouter:
    """Arma el router del panel, cerrado sobre `config` y `chatwoot`.

    Mismo patrón que `agente/web/webhook.py`: las dependencias se reciben
    armadas (facilita pasar dobles de prueba) en vez de que cada ruta las
    arme por su cuenta.
    """
    router = APIRouter(prefix="/panel", dependencies=[Depends(requerir_acceso(config.panel))])
    plantillas = Jinja2Templates(directory=str(CARPETA / "plantillas"))
    plantillas.env.filters["plata"] = lambda m: motor.formato_dinero(float(m))
    plantillas.env.filters["fecha"] = horario.formatear_fecha

    # -- Pedidos -----------------------------------------------------------------

    @router.get("/")
    def inicio():
        return RedirectResponse(url="/panel/pedidos")

    @router.get("/pedidos")
    def ver_pedidos(request: Request, estado: str = ""):
        with base_datos.obtener_pool().connection() as conexion:
            lista = datos.listar_pedidos(conexion, estado or None)
            carga = datos.carga_de_hoy(conexion, horario.hoy())

        return plantillas.TemplateResponse(
            request, "pedidos.html",
            {
                "pedidos": lista, "carga": carga, "estado_filtro": estado,
                "estados": ESTADOS_PEDIDO, "hoy": horario.hoy(), "negocio": config.negocio,
                "seccion": "pedidos",
            },
        )

    def _fila(request: Request, pedido: dict):
        # `hoy` hace falta acá también: esta misma plantilla se devuelve
        # sola después de una acción (HTMX), no solo dentro de la lista
        # completa, y sin esto perdería el resaltado de "vence hoy".
        return plantillas.TemplateResponse(
            request, "fragmentos/fila_pedido.html", {"pedido": pedido, "hoy": horario.hoy()}
        )

    @router.post("/pedidos/{pedido_id}/listo")
    def marcar_listo(pedido_id: int, request: Request):
        with base_datos.obtener_pool().connection() as conexion:
            datos.marcar_listo(conexion, pedido_id)
            pedido = datos.pedido_con_cliente(conexion, pedido_id)
            _sincronizar_sheets(config, conexion, pedido)

        _avisar_listo(chatwoot, config, pedido)
        return _fila(request, pedido)

    @router.post("/pedidos/{pedido_id}/entregado")
    def marcar_entregado(pedido_id: int, request: Request, monto_cobrado: float = Form(...)):
        with base_datos.obtener_pool().connection() as conexion:
            datos.marcar_entregado(conexion, pedido_id, monto_cobrado)
            pedido = datos.pedido_con_cliente(conexion, pedido_id)
            _sincronizar_sheets(config, conexion, pedido)

        return _fila(request, pedido)

    @router.post("/pedidos/{pedido_id}/cancelar")
    def cancelar(pedido_id: int, request: Request, motivo: str = Form("")):
        with base_datos.obtener_pool().connection() as conexion:
            datos.cancelar_pedido(conexion, pedido_id, motivo)
            pedido = datos.pedido_con_cliente(conexion, pedido_id)
            _sincronizar_sheets(config, conexion, pedido)

        return _fila(request, pedido)

    # -- Catálogo -----------------------------------------------------------------

    @router.get("/catalogo")
    def ver_catalogo(request: Request):
        with base_datos.obtener_pool().connection() as conexion:
            productos = datos.todos_los_productos(conexion)

        return plantillas.TemplateResponse(
            request, "catalogo.html", {"productos": productos, "seccion": "catalogo"}
        )

    @router.post("/catalogo/nuevo")
    def crear_producto(
        request: Request,
        nombre: str = Form(...),
        categoria: str = Form("general"),
        unidad: str = Form("unidad"),
        precio_unitario: float = Form(...),
        cantidad_minima: float = Form(1),
        minutos_preparacion: int = Form(0),
        minutos_por_unidad: float = Form(0),
    ):
        with base_datos.obtener_pool().connection() as conexion:
            datos.crear_producto(conexion, {
                "nombre": nombre, "categoria": categoria, "unidad": unidad,
                "precio_unitario": precio_unitario, "cantidad_minima": cantidad_minima,
                "minutos_preparacion": minutos_preparacion,
                "minutos_por_unidad": minutos_por_unidad,
                # Un producto que carga a mano el dueño no es un precio de
                # ejemplo: nace ya confirmado.
                "precio_provisorio": False,
            })
            productos = datos.todos_los_productos(conexion)

        return plantillas.TemplateResponse(
            request, "fragmentos/tabla_catalogo.html", {"productos": productos}
        )

    @router.post("/catalogo/{producto_id}")
    def actualizar_producto(
        producto_id: int,
        request: Request,
        nombre: str = Form(...),
        categoria: str = Form("general"),
        unidad: str = Form("unidad"),
        precio_unitario: float = Form(...),
        cantidad_minima: float = Form(1),
        minutos_preparacion: int = Form(0),
        minutos_por_unidad: float = Form(0),
        activo: str = Form(""),
    ):
        with base_datos.obtener_pool().connection() as conexion:
            producto = datos.actualizar_producto(conexion, producto_id, {
                "nombre": nombre, "categoria": categoria, "unidad": unidad,
                "precio_unitario": precio_unitario, "cantidad_minima": cantidad_minima,
                "minutos_preparacion": minutos_preparacion,
                "minutos_por_unidad": minutos_por_unidad,
                "activo": _es_verdadero(activo),
            })

        return plantillas.TemplateResponse(
            request, "fragmentos/fila_producto.html", {"producto": producto}
        )

    # -- Taller -----------------------------------------------------------------

    @router.get("/taller")
    def ver_taller(request: Request):
        with base_datos.obtener_pool().connection() as conexion:
            taller = datos.obtener_taller(conexion)

        return plantillas.TemplateResponse(
            request, "taller.html",
            {"taller": taller, "dias_semana": DIAS_SEMANA, "seccion": "taller"},
        )

    @router.post("/taller")
    def actualizar_taller(
        request: Request,
        minutos_por_dia: int = Form(...),
        hora_corte_mismo_dia: str = Form(...),
        dias_habiles: list[int] = Form([]),
        feriados: str = Form(""),
    ):
        from datetime import time as _time

        with base_datos.obtener_pool().connection() as conexion:
            taller = datos.actualizar_taller(conexion, {
                "minutos_por_dia": minutos_por_dia,
                # Se convierte a `time` en vez de mandar el string tal cual:
                # así no depende de que Postgres le adivine el tipo a un
                # parámetro de texto contra una columna TIME.
                "hora_corte_mismo_dia": _time.fromisoformat(hora_corte_mismo_dia),
                "dias_habiles": dias_habiles,
                "feriados": _parsear_fechas(feriados),
            })

        return plantillas.TemplateResponse(
            request, "fragmentos/formulario_taller.html",
            {"taller": taller, "dias_semana": DIAS_SEMANA, "guardado": True},
        )

    return router


# -- Ayudantes ----------------------------------------------------------------


def _sincronizar_sheets(config: Config, conexion, pedido: dict) -> None:
    """Best-effort: si sale bien apaga `pendiente_sheets`, si no lo deja
    prendido para que lo agarre el reintento periódico
    (`servidor_mundografico.py`) o el próximo cambio de estado de este
    mismo pedido."""
    if sheets.sincronizar_pedido(config.sheets, pedido):
        datos.marcar_sincronizado_con_sheets(conexion, pedido["id"])


def _avisar_listo(chatwoot: ClienteChatwoot, config: Config, pedido: dict) -> None:
    """El mensaje automático al cliente. Que Chatwoot esté caído no puede
    tirar abajo la acción de marcar el pedido como listo: el trabajador ya
    hizo lo suyo, y el aviso se puede reintentar o mandar a mano."""
    texto = (
        f"¡Hola! Tu pedido {pedido['numero']} de {config.negocio.nombre} ya está "
        f"listo. Podés pasar a retirarlo cuando quieras "
        f"({config.negocio.direccion})."
    )
    try:
        chatwoot.enviar_mensaje(pedido["conversacion_id"], texto)
    except Exception as e:
        registro.error("No se pudo avisar el pedido %s: %s", pedido["numero"], e)


def _es_verdadero(valor: str) -> bool:
    return (valor or "").strip().lower() in ("1", "true", "on", "si", "sí")


def _parsear_fechas(texto: str) -> list:
    """"24/12/2026, 01/01/2027" → [date(2026,12,24), date(2027,1,1)].

    Acepta además fechas ISO (2026-12-24) por si alguien pega la lista
    desde otro lado. Una fecha que no se puede leer se ignora en vez de
    romper el guardado entero: peor es perder toda la configuración del
    taller por una coma de más.
    """
    from datetime import datetime

    fechas = []
    for parte in texto.replace("\n", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        for formato in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                fechas.append(datetime.strptime(parte, formato).date())
                break
            except ValueError:
                continue
    return fechas
