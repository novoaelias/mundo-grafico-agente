"""Todo lo que toca Postgres: catálogo, taller, clientes y pedidos.

Es la capa fina que junta la lógica pura (`catalogo.py`, `agenda.py`) con la
base real. Las herramientas del agente y las rutas del panel llaman acá, y
acá es el único lugar del proyecto que sabe escribir SQL.

Cada función recibe una `conexion` de psycopg ya abierta (se la pasa quien
llama, normalmente sacándola del pool con
`with base_datos.obtener_pool().connection() as conexion:`), para que quien
necesite varias operaciones atómicas —como crear un pedido, que toca tres
tablas— las pueda envolver en una sola transacción.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg import Connection
from psycopg.types.json import Json

from . import agenda, catalogo

ESTADOS_ACTIVOS = ("pendiente", "en_proceso")


class PedidoInvalido(Exception):
    """El pedido que se quiere crear no tiene nada cotizable."""


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


def productos_activos(conexion: Connection) -> list[dict]:
    return conexion.execute(
        "SELECT * FROM mundografico.productos WHERE activo ORDER BY categoria, nombre"
    ).fetchall()


def todos_los_productos(conexion: Connection) -> list[dict]:
    """Activos e inactivos: lo que ve el panel para poder reactivar algo."""
    return conexion.execute(
        "SELECT * FROM mundografico.productos ORDER BY categoria, nombre"
    ).fetchall()


def actualizar_producto(conexion: Connection, producto_id: int, cambios: dict[str, Any]) -> dict:
    """Actualiza los campos editables desde el panel.

    Un precio de ejemplo solo se confirma cuando el panel manda
    `precio_provisorio=False` explícitamente. Guardar otro dato del producto
    no puede convertir por accidente una tarifa ficticia en real.
    """
    columnas_editables = {
        "nombre", "categoria", "unidad", "precio_unitario", "cantidad_minima",
        "escalas", "minutos_preparacion", "minutos_por_unidad", "activo",
        "alias", "precio_provisorio",
    }
    a_aplicar = {k: v for k, v in cambios.items() if k in columnas_editables}
    if not a_aplicar:
        raise ValueError("No hay ningún campo válido para actualizar.")

    if "escalas" in a_aplicar:
        # Sin este envoltorio, psycopg adapta una lista de Python como
        # ARRAY de Postgres, no como jsonb: con la lista vacía de hoy no
        # se nota (guarda '{}', que como jsonb es un objeto vacío, no un
        # array, pero como acá siempre se lee con `or []` da lo mismo) —
        # el día que esto tenga tramos de verdad ([{"desde":..., ...}]),
        # sin el Json() psycopg no sabe adaptar una lista de diccionarios
        # y revienta.
        a_aplicar["escalas"] = _a_jsonb(a_aplicar["escalas"])

    columnas = ", ".join(f"{c} = %({c})s" for c in a_aplicar)
    fila = conexion.execute(
        f"""
        UPDATE mundografico.productos
        SET {columnas}, actualizado_en = now()
        WHERE id = %(id)s
        RETURNING *
        """,
        {**a_aplicar, "id": producto_id},
    ).fetchone()

    if fila is None:
        raise ValueError(f"No existe el producto {producto_id}.")

    return fila


def crear_producto(conexion: Connection, datos: dict[str, Any]) -> dict:
    fila = conexion.execute(
        """
        INSERT INTO mundografico.productos
            (nombre, alias, categoria, unidad, precio_unitario, cantidad_minima,
             escalas, minutos_preparacion, minutos_por_unidad, precio_provisorio)
        VALUES
            (%(nombre)s, %(alias)s, %(categoria)s, %(unidad)s, %(precio_unitario)s,
             %(cantidad_minima)s, %(escalas)s, %(minutos_preparacion)s,
             %(minutos_por_unidad)s, %(precio_provisorio)s)
        RETURNING *
        """,
        {
            "nombre": datos["nombre"],
            "alias": datos.get("alias") or [],
            "categoria": datos.get("categoria") or "general",
            "unidad": datos.get("unidad") or "unidad",
            "precio_unitario": datos["precio_unitario"],
            "cantidad_minima": datos.get("cantidad_minima") or 1,
            "escalas": _a_jsonb(datos.get("escalas") or []),
            "minutos_preparacion": datos.get("minutos_preparacion") or 0,
            "minutos_por_unidad": datos.get("minutos_por_unidad") or 0,
            "precio_provisorio": datos.get("precio_provisorio", False),
        },
    ).fetchone()
    return fila


# ---------------------------------------------------------------------------
# Taller y agenda
# ---------------------------------------------------------------------------


def obtener_taller(conexion: Connection) -> dict:
    fila = conexion.execute("SELECT * FROM mundografico.taller WHERE id = 1").fetchone()
    return {
        "minutos_por_dia": fila["minutos_por_dia"],
        "dias_habiles": list(fila["dias_habiles"]),
        "hora_corte_mismo_dia": fila["hora_corte_mismo_dia"],
        "feriados": list(fila["feriados"]),
    }


def actualizar_taller(conexion: Connection, cambios: dict[str, Any]) -> dict:
    columnas_editables = {"minutos_por_dia", "dias_habiles", "hora_corte_mismo_dia", "feriados"}
    a_aplicar = {k: v for k, v in cambios.items() if k in columnas_editables}
    if not a_aplicar:
        raise ValueError("No hay ningún campo válido para actualizar.")
    if "minutos_por_dia" in a_aplicar and a_aplicar["minutos_por_dia"] <= 0:
        raise ValueError("La capacidad diaria debe ser mayor a cero.")
    if "dias_habiles" in a_aplicar and not a_aplicar["dias_habiles"]:
        raise ValueError("Elegí al menos un día hábil para el taller.")

    columnas = ", ".join(f"{c} = %({c})s" for c in a_aplicar)
    conexion.execute(f"UPDATE mundografico.taller SET {columnas} WHERE id = 1", a_aplicar)
    return obtener_taller(conexion)


def comprometido_por_dia(conexion: Connection, desde: date) -> dict[date, int]:
    """Minutos ya reservados por día, sumando solo pedidos activos.

    Un pedido 'listo', 'entregado' o 'cancelado' no compite más por lugar
    en la agenda: ya salió del taller (o nunca va a usarlo).
    """
    filas = conexion.execute(
        """
        SELECT a.fecha, SUM(a.minutos) AS minutos
        FROM mundografico.asignacion_agenda a
        JOIN mundografico.pedidos p ON p.id = a.pedido_id
        WHERE p.estado = ANY(%s) AND a.fecha >= %s
        GROUP BY a.fecha
        """,
        (list(ESTADOS_ACTIVOS), desde),
    ).fetchall()
    return {fila["fecha"]: fila["minutos"] for fila in filas}


def carga_de_hoy(conexion: Connection, hoy: date) -> dict:
    """Para la barra de carga del panel: cuánto hay comprometido hoy."""
    taller = obtener_taller(conexion)
    usado = comprometido_por_dia(conexion, hoy).get(hoy, 0)
    return {
        "usado": usado,
        "total": taller["minutos_por_dia"],
        "porcentaje": min(100, round(100 * usado / taller["minutos_por_dia"])) if taller["minutos_por_dia"] else 0,
    }


# ---------------------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------------------


def obtener_o_crear_cliente(
    conexion: Connection, conversacion_id: str, nombre: str = "", telefono: str = "",
    contacto_id: str = "",
) -> dict:
    fila = conexion.execute(
        "SELECT * FROM mundografico.clientes WHERE conversacion_id = %s",
        (conversacion_id,),
    ).fetchone()

    if fila is not None:
        # Si ahora sabemos algo que antes no (por ejemplo, el nombre lo
        # dijo recién en este mensaje), lo completamos sin pisar lo que
        # ya había con un dato vacío.
        cambios = {}
        if nombre and not fila["nombre"]:
            cambios["nombre"] = nombre
        if telefono and not fila["telefono"]:
            cambios["telefono"] = telefono
        if contacto_id and not fila["contacto_id"]:
            cambios["contacto_id"] = contacto_id

        if cambios:
            columnas = ", ".join(f"{c} = %({c})s" for c in cambios)
            fila = conexion.execute(
                f"""
                UPDATE mundografico.clientes SET {columnas}, actualizado_en = now()
                WHERE id = %(id)s RETURNING *
                """,
                {**cambios, "id": fila["id"]},
            ).fetchone()

        return fila

    return conexion.execute(
        """
        INSERT INTO mundografico.clientes (conversacion_id, nombre, telefono, contacto_id)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (conversacion_id, nombre, telefono, contacto_id),
    ).fetchone()


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------


def crear_pedido(
    conexion: Connection,
    conversacion_id: str,
    items: list[dict],
    hoy: date,
    ahora=None,
    nombre_cliente: str = "",
    telefono_cliente: str = "",
    contacto_id: str = "",
    notas: str = "",
    estado_pago: str = "a_cobrar",
    permitir_precios_provisorios: bool = False,
) -> dict:
    """Cotiza, calcula la fecha y guarda el pedido, todo en una transacción.

    No confía en ninguna cotización dicha antes en la charla: vuelve a
    calcular precio y fecha con el catálogo y la agenda de ESTE momento.
    Entre que el bot dijo un precio y la persona confirma pueden pasar
    minutos u horas, y en el medio pudo entrar otro pedido que ya ocupó
    el lugar de hoy.

    `pg_advisory_xact_lock` evita que dos pedidos que llegan al mismo
    tiempo reserven el mismo hueco de agenda: sin el candado, los dos
    leerían "hoy hay 60 minutos libres" a la vez y los dos los usarían.
    Se libera solo, al terminar la transacción.

    `estado_pago` lo decide quien llama (la herramienta `crear_pedido`,
    según `POLITICA_PAGO` del .env) — esta función no sabe nada de
    políticas de negocio, solo guarda el estado que le pasan. Sin un
    cobro real integrado todavía, es una foto de lo que se acordó en la
    charla, no una verificación de que el pago entró de verdad.
    """
    conexion.execute("SELECT pg_advisory_xact_lock(%s)", (_LLAVE_AGENDA,))

    productos = productos_activos(conexion)
    cotizacion = catalogo.cotizar(productos, items)

    if not cotizacion.completa:
        raise PedidoInvalido(
            "No se puede tomar el pedido completo. " + cotizacion.texto()
        )

    if not permitir_precios_provisorios and any(
        item.precio_provisorio for item in cotizacion.items
    ):
        raise PedidoInvalido(
            "Hay precios de ejemplo sin confirmar con Mundo Gráfico. "
            "Pedí intervención humana antes de tomar este pedido."
        )

    taller = obtener_taller(conexion)
    comprometido = comprometido_por_dia(conexion, hoy)
    resultado_agenda = agenda.proxima_fecha(
        taller, comprometido, cotizacion.minutos_totales, desde=hoy, ahora=ahora,
    )

    cliente = obtener_o_crear_cliente(
        conexion, conversacion_id, nombre_cliente, telefono_cliente, contacto_id,
    )

    numero = _siguiente_numero(conexion)
    detalle = [
        {
            "producto_id": item.producto_id,
            "nombre": item.nombre,
            "cantidad": item.cantidad,
            "unidad": item.unidad,
            "precio_unitario": item.precio_unitario,
            "subtotal": item.subtotal,
        }
        for item in cotizacion.items
    ]

    pedido = conexion.execute(
        """
        INSERT INTO mundografico.pedidos
            (numero, cliente_id, conversacion_id, detalle, total,
             minutos_estimados, fecha_promesa, notas, estado_pago)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            numero, cliente["id"], conversacion_id, _a_jsonb(detalle),
            cotizacion.total, cotizacion.minutos_totales,
            resultado_agenda.fecha_promesa, notas, estado_pago,
        ),
    ).fetchone()

    for fecha, minutos in resultado_agenda.minutos_por_dia.items():
        conexion.execute(
            "INSERT INTO mundografico.asignacion_agenda (pedido_id, fecha, minutos) "
            "VALUES (%s, %s, %s)",
            (pedido["id"], fecha, minutos),
        )

    _registrar_evento(conexion, pedido["id"], "creado", {"detalle": detalle, "total": cotizacion.total})

    return {
        **pedido,
        "cliente": cliente,
        "cotizacion": cotizacion,
        "agenda": resultado_agenda,
    }


def pedido_con_cliente(conexion: Connection, pedido_id: int) -> dict | None:
    """Un pedido con el nombre/teléfono del cliente ya resuelto.

    Lo usa el panel para redibujar una sola fila después de una acción
    (marcar listo, entregar): las funciones de cambio de estado devuelven
    la fila de `pedidos` sola, sin el join, porque son las que también usa
    el flujo de las herramientas, donde ese dato no hace falta.
    """
    return conexion.execute(
        """
        SELECT p.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM mundografico.pedidos p
        JOIN mundografico.clientes c ON c.id = p.cliente_id
        WHERE p.id = %s
        """,
        (pedido_id,),
    ).fetchone()


def pedido_por_numero(
    conexion: Connection, numero: str, conversacion_id: str | None = None,
) -> dict | None:
    """La consulta del bot se restringe a la conversación del cliente."""
    if conversacion_id is not None:
        return conexion.execute(
            "SELECT * FROM mundografico.pedidos "
            "WHERE numero = %s AND conversacion_id = %s",
            (numero, conversacion_id),
        ).fetchone()
    return conexion.execute(
        "SELECT * FROM mundografico.pedidos WHERE numero = %s", (numero,)
    ).fetchone()


def pedidos_de_conversacion(conexion: Connection, conversacion_id: str) -> list[dict]:
    return conexion.execute(
        """
        SELECT * FROM mundografico.pedidos
        WHERE conversacion_id = %s
        ORDER BY creado_en DESC
        """,
        (conversacion_id,),
    ).fetchall()


def listar_pedidos(conexion: Connection, estado: str | None = None) -> list[dict]:
    """Para el panel: todos los pedidos, o filtrados por estado, con el
    nombre del cliente ya resuelto (evita el N+1 de pedirlo aparte)."""
    if estado:
        return conexion.execute(
            """
            SELECT p.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
            FROM mundografico.pedidos p
            JOIN mundografico.clientes c ON c.id = p.cliente_id
            WHERE p.estado = %s
            ORDER BY p.fecha_promesa, p.creado_en
            """,
            (estado,),
        ).fetchall()

    return conexion.execute(
        """
        SELECT p.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM mundografico.pedidos p
        JOIN mundografico.clientes c ON c.id = p.cliente_id
        ORDER BY p.fecha_promesa, p.creado_en
        """
    ).fetchall()


def marcar_listo(conexion: Connection, pedido_id: int) -> dict:
    pedido = conexion.execute(
        """
        UPDATE mundografico.pedidos
        SET estado = 'listo', actualizado_en = now(),
            pendiente_sheets = TRUE
        WHERE id = %s AND estado IN ('pendiente', 'en_proceso')
        RETURNING *
        """,
        (pedido_id,),
    ).fetchone()

    if pedido is None:
        raise ValueError(f"El pedido {pedido_id} no existe o ya no está en producción.")

    _registrar_evento(conexion, pedido_id, "cambio_estado", {"a": "listo"})
    return pedido


def registrar_aviso_enviado(conexion: Connection, pedido_id: int) -> dict:
    """Anota el envío solo después de una respuesta exitosa de Chatwoot."""
    pedido = conexion.execute(
        """
        UPDATE mundografico.pedidos
        SET avisado_listo_en = now(), actualizado_en = now()
        WHERE id = %s AND estado = 'listo' AND avisado_listo_en IS NULL
        RETURNING *
        """,
        (pedido_id,),
    ).fetchone()
    if pedido is None:
        raise ValueError(f"El pedido {pedido_id} no está listo o ya fue avisado.")
    _registrar_evento(conexion, pedido_id, "aviso_enviado", {})
    return pedido


def marcar_entregado(conexion: Connection, pedido_id: int, monto_cobrado: Decimal | float) -> dict:
    try:
        monto = Decimal(str(monto_cobrado))
    except InvalidOperation as e:
        raise ValueError("El monto cobrado no es válido.") from e
    pedido_actual = conexion.execute(
        "SELECT total, estado FROM mundografico.pedidos WHERE id = %s FOR UPDATE",
        (pedido_id,),
    ).fetchone()
    if pedido_actual is None or pedido_actual["estado"] != "listo":
        raise ValueError(f"El pedido {pedido_id} tiene que estar listo antes de entregarse.")
    if not monto.is_finite() or monto < 0 or monto > pedido_actual["total"]:
        raise ValueError("El monto cobrado debe estar entre cero y el total del pedido.")

    estado_pago = "pagado" if monto == pedido_actual["total"] else ("señado" if monto > 0 else "a_cobrar")
    pedido = conexion.execute(
        """
        UPDATE mundografico.pedidos
        SET estado = 'entregado', estado_pago = %s, monto_cobrado = %s,
            entregado_en = now(), actualizado_en = now(), pendiente_sheets = TRUE
        WHERE id = %s AND estado = 'listo'
        RETURNING *
        """,
        (estado_pago, monto, pedido_id),
    ).fetchone()

    if pedido is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")

    _registrar_evento(conexion, pedido_id, "cambio_estado", {"a": "entregado", "monto_cobrado": float(monto)})
    return pedido


def cambiar_estado_pago(conexion: Connection, pedido_id: int, estado_pago: str) -> dict:
    pedido = conexion.execute(
        """
        UPDATE mundografico.pedidos
        SET estado_pago = %s, actualizado_en = now(), pendiente_sheets = TRUE
        WHERE id = %s
        RETURNING *
        """,
        (estado_pago, pedido_id),
    ).fetchone()

    if pedido is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")

    _registrar_evento(conexion, pedido_id, "cambio_pago", {"a": estado_pago})
    return pedido


def cancelar_pedido(conexion: Connection, pedido_id: int, motivo: str = "") -> dict:
    """Cancela y libera el lugar que tenía reservado en la agenda."""
    pedido = conexion.execute(
        """
        UPDATE mundografico.pedidos
        SET estado = 'cancelado', actualizado_en = now(), pendiente_sheets = TRUE
        WHERE id = %s AND estado IN ('pendiente', 'en_proceso', 'listo')
        RETURNING *
        """,
        (pedido_id,),
    ).fetchone()

    if pedido is None:
        raise ValueError(f"El pedido {pedido_id} no se puede cancelar en su estado actual.")

    # No se borra asignacion_agenda: es historial. comprometido_por_dia ya
    # filtra por estado activo, así que un pedido cancelado deja de pesar
    # en la agenda sin necesidad de tocar esa tabla.
    _registrar_evento(conexion, pedido_id, "cambio_estado", {"a": "cancelado", "motivo": motivo})
    return pedido


def pendientes_de_sheets(conexion: Connection) -> list[dict]:
    """Pedidos que todavía no se pudieron escribir en Google Sheets."""
    return conexion.execute(
        """
        SELECT p.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM mundografico.pedidos p
        JOIN mundografico.clientes c ON c.id = p.cliente_id
        WHERE p.pendiente_sheets
        ORDER BY p.creado_en
        """
    ).fetchall()


def marcar_sincronizado_con_sheets(
    conexion: Connection, pedido_id: int, actualizado_en=None,
) -> None:
    """No borra un cambio de estado que ocurrió mientras Google respondía."""
    if actualizado_en is None:
        conexion.execute(
            "UPDATE mundografico.pedidos SET pendiente_sheets = FALSE WHERE id = %s",
            (pedido_id,),
        )
    else:
        conexion.execute(
            "UPDATE mundografico.pedidos SET pendiente_sheets = FALSE "
            "WHERE id = %s AND actualizado_en = %s",
            (pedido_id, actualizado_en),
        )


# ---------------------------------------------------------------------------
# Ayudantes
# ---------------------------------------------------------------------------

# Una llave arbitraria y fija para el candado de agenda. Solo importa que
# sea siempre la misma (todo el mundo compite por el mismo recurso: "la
# agenda del taller") y que no choque con otro uso de advisory locks en la
# misma base — con un número de 63 bits al azar alcanza de sobra.
_LLAVE_AGENDA = 8_453_190_027


def _siguiente_numero(conexion: Connection) -> str:
    numero = conexion.execute(
        "SELECT nextval('mundografico.numero_pedido_seq') AS n"
    ).fetchone()["n"]
    return f"MG-{numero:04d}"


def _registrar_evento(conexion: Connection, pedido_id: int, tipo: str, detalle: dict) -> None:
    conexion.execute(
        "INSERT INTO mundografico.eventos_pedido (pedido_id, tipo, detalle) VALUES (%s, %s, %s)",
        (pedido_id, tipo, _a_jsonb(detalle)),
    )


def _a_jsonb(valor: Any) -> Json:
    """psycopg necesita que un dict/list se marque como Json para ir a una
    columna jsonb; sin esto lo manda como texto plano y Postgres lo rechaza."""
    return Json(valor)
