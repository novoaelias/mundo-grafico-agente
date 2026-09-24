"""Registro de ventas en Google Sheets.

Cada pedido es una fila, identificada por su número en la columna A: si ya
existe esa fila se actualiza, si no se agrega. Así un pedido que pasa de
"pendiente" a "entregado" actualiza la MISMA fila en vez de duplicarla —
es lo que permite usar la hoja para controlar la plata después, como pidió
el dueño.

Que falten las credenciales, que la API de Google esté caída, o que la
hoja esté mal compartida: nada de eso puede impedir que se tome un
pedido. El pedido ya quedó guardado en Postgres antes de llegar acá (ver
`pedidos.crear_pedido`); todo lo de este archivo está pensado para fallar
en silencio y avisar por log. La columna `pendiente_sheets` de cada
pedido es la memoria de qué falta reintentar — `sincronizar_pendientes()`
es el reintento, y se llama tanto después de cada escritura (para que se
vea al toque) como cada tanto desde `servidor_mundografico.py` (por si la
API estuvo caída justo en el momento).

Los imports de gspread/google-auth van adentro de las funciones a
propósito, igual que hace `agente/modelos.py` con los SDK de cada
proveedor: si Sheets no está configurado, el servidor arranca igual
aunque esos paquetes no estén instalados.
"""

from __future__ import annotations

import json
import logging
import re
import threading

from . import pedidos as datos
from .config import ConfigSheets

registro = logging.getLogger("mundografico.sheets")

ENCABEZADOS = [
    "Número", "Fecha", "Cliente", "Teléfono", "Detalle", "Total",
    "Estado", "Pago", "Monto cobrado", "Entrega prometida", "Entregado",
]

_hoja_cacheada = None  # abrir la hoja tarda un viaje de red; no cambia entre pedidos
_candado_hoja = threading.Lock()


def sincronizar_pedido(config: ConfigSheets, pedido: dict) -> bool:
    """Escribe o actualiza la fila de este pedido.

    Devuelve True si se pudo escribir (para que quien llama apague
    `pendiente_sheets`) y False si no —sin credenciales configuradas, sin
    conexión, o cualquier otro error de la API—, sin levantar nunca una
    excepción hacia quien llama.
    """
    if not config.activo:
        return False

    try:
        # El bot y el reintento periódico comparten proceso. Sin el candado,
        # ambos pueden observar "no existe" y agregar dos filas iguales.
        with _candado_hoja:
            hoja = _abrir_hoja(config)
            fila = _fila_de(pedido)

            # gspread usa búsqueda de texto/regex; sin anclas, MG-0001 puede
            # coincidir con MG-00010 y terminar pisando otra venta.
            celda = hoja.find(re.compile(r"^" + re.escape(str(pedido["numero"])) + r"$"), in_column=1)
            if celda:
                hoja.update([fila], range_name=f"A{celda.row}:{_ultima_columna()}{celda.row}")
            else:
                hoja.append_row(fila)

        return True
    except Exception as e:
        registro.error(
            "No se pudo sincronizar el pedido %s con Sheets: %s",
            pedido.get("numero"), e,
        )
        return False


def sincronizar_pendientes(config: ConfigSheets, pool) -> int:
    """Reintenta todos los pedidos que quedaron sin escribir en Sheets.

    Devuelve cuántos se pudieron sincronizar recién ahora.
    """
    if not config.activo:
        return 0

    # La API de Google puede tardar varios segundos. Soltamos la conexión
    # antes de salir a la red para no retener una transacción del pool.
    with pool.connection() as conexion:
        pendientes = datos.pendientes_de_sheets(conexion)

    sincronizados = 0
    for pedido in pendientes:
        if sincronizar_pedido(config, pedido):
            with pool.connection() as conexion:
                datos.marcar_sincronizado_con_sheets(
                    conexion, pedido["id"], pedido.get("actualizado_en"),
                )
            sincronizados += 1

    return sincronizados


# ---------------------------------------------------------------------------


def _abrir_hoja(config: ConfigSheets):
    global _hoja_cacheada
    if _hoja_cacheada is not None:
        return _hoja_cacheada

    import gspread
    from google.oauth2.service_account import Credentials

    credenciales_dict = json.loads(config.credenciales_json)
    alcance = ["https://www.googleapis.com/auth/spreadsheets"]
    credenciales = Credentials.from_service_account_info(credenciales_dict, scopes=alcance)
    cliente = gspread.authorize(credenciales)

    libro = cliente.open_by_key(config.id_hoja)
    try:
        hoja = libro.worksheet(config.nombre_pestaña)
    except gspread.WorksheetNotFound:
        hoja = libro.add_worksheet(title=config.nombre_pestaña, rows=1000, cols=len(ENCABEZADOS))
        hoja.append_row(ENCABEZADOS)

    _hoja_cacheada = hoja
    return _hoja_cacheada


def _fila_de(pedido: dict) -> list:
    detalle_texto = "; ".join(
        f"{item['cantidad']:g} {item['unidad']} {item['nombre']}"
        for item in (pedido.get("detalle") or [])
    )
    return [
        pedido["numero"],
        _fecha_hora(pedido.get("creado_en")),
        pedido.get("cliente_nombre") or "",
        pedido.get("cliente_telefono") or "",
        detalle_texto,
        float(pedido["total"]),
        pedido["estado"],
        pedido["estado_pago"],
        float(pedido["monto_cobrado"]) if pedido.get("monto_cobrado") is not None else "",
        _fecha(pedido.get("fecha_promesa")),
        "sí" if pedido["estado"] == "entregado" else "",
    ]


def _fecha_hora(valor) -> str:
    return valor.strftime("%d/%m/%Y %H:%M") if valor else ""


def _fecha(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else ""


def _ultima_columna() -> str:
    from gspread.utils import rowcol_to_a1

    referencia = rowcol_to_a1(1, len(ENCABEZADOS))
    return "".join(c for c in referencia if c.isalpha())
