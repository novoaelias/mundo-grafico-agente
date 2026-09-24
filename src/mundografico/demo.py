"""Reposiciona los pedidos ficticios para ensayar la demo el día actual.

La migración 003 se aplica una sola vez. Sin este paso, el ejemplo de
capacidad queda anclado al día del primer deploy y deja de servir mañana.
Solo se ejecuta con MG_MODO_DEMO=true o desde preparar_demo.py.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import pedidos


def dias_de_demo(taller: dict, desde: date) -> list[date]:
    """Tres días hábiles consecutivos desde hoy, respetando feriados."""
    habiles = set(taller["dias_habiles"])
    feriados = set(taller.get("feriados") or [])
    dias = []
    for desplazamiento in range(60):
        dia = desde + timedelta(days=desplazamiento)
        if dia.isoweekday() in habiles and dia not in feriados:
            dias.append(dia)
            if len(dias) == 3:
                return dias
    raise ValueError("No hay tres días hábiles en los próximos 60 días para la demo.")


def preparar_demo(conexion, hoy: date) -> list[date]:
    """Restablece únicamente DEMO-001 a DEMO-005; nunca toca pedidos reales."""
    dias = dias_de_demo(pedidos.obtener_taller(conexion), hoy)
    fechas = {
        "DEMO-002": dias[0],
        "DEMO-001": dias[1],
        "DEMO-003": dias[1],
        "DEMO-004": dias[2],
        "DEMO-005": dias[2],
    }
    for numero, fecha in fechas.items():
        estado = "en_proceso" if numero == "DEMO-002" else "pendiente"
        fila = conexion.execute(
            """
            UPDATE mundografico.pedidos
            SET fecha_promesa = %s, estado = %s, estado_pago = 'a_cobrar',
                monto_cobrado = NULL, avisado_listo_en = NULL,
                entregado_en = NULL, pendiente_sheets = FALSE,
                actualizado_en = now()
            WHERE numero = %s RETURNING id, minutos_estimados
            """,
            (fecha, estado, numero),
        ).fetchone()
        if fila is None:
            raise ValueError(f"Falta {numero}. Activá MG_MODO_DEMO y aplicá 003_demo.sql.")
        conexion.execute(
            "DELETE FROM mundografico.asignacion_agenda WHERE pedido_id = %s",
            (fila["id"],),
        )
        conexion.execute(
            "INSERT INTO mundografico.asignacion_agenda (pedido_id, fecha, minutos) "
            "VALUES (%s, %s, %s)",
            (fila["id"], fecha, fila["minutos_estimados"]),
        )
    return dias
