"""Herramientas de pedidos: cuándo puede estar listo un trabajo, darlo de
alta de verdad, y consultarlo después."""

from __future__ import annotations

import logging
from datetime import timedelta

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from .. import agenda, base_datos, horario, sheets
from .. import catalogo as motor
from .. import pedidos as datos
from ._contexto import conversacion_de, obtener as contexto

registro = logging.getLogger("mundografico.herramientas.pedidos")


@tool
def calcular_entrega(items: list[dict]) -> str:
    """Calcula para cuándo puede estar listo un trabajo, según la carga real del taller.

    Usala antes de comprometerte con una fecha de entrega: nunca prometas
    "hoy" ni ningún otro día de memoria. Esta herramienta mira los pedidos
    que ya están anotados y devuelve la fecha real, incluso si eso
    significa decir que hoy no se puede.

    Args:
        items: lo mismo que en `cotizar`: [{"producto": ..., "cantidad": ...}]
    """
    try:
        with base_datos.obtener_pool().connection() as conexion:
            productos = datos.productos_activos(conexion)
            cotizacion = motor.cotizar(productos, items)

            if not cotizacion.completa:
                return "No pude calcular una fecha para todo el trabajo. " + cotizacion.texto()

            taller = datos.obtener_taller(conexion)
            hoy = horario.hoy()
            comprometido = datos.comprometido_por_dia(conexion, hoy)

        ahora = horario.hora_actual()
        resultado = agenda.proxima_fecha(
            taller, comprometido, cotizacion.minutos_totales, desde=hoy, ahora=ahora,
        )
    except Exception:
        registro.exception("Falló calcular_entrega")
        return "No pude confirmar una fecha de entrega. Derivá la consulta al equipo."
    fecha_texto = horario.formatear_fecha(resultado.fecha_promesa)

    if resultado.entra_hoy and not resultado.se_reparte_en_varios_dias:
        return f"Lo tenemos listo hoy mismo, {fecha_texto}."

    motivo = agenda.motivo_por_el_que_no_entra_hoy(taller, comprometido, hoy, ahora)
    aclaracion = f" ({motivo})" if motivo else ""
    # El motivo anterior habla SOLO de hoy. Si mañana ya está completo,
    # explicitarlo evita que el agente atribuya a mañana el corte de hoy.
    manana = hoy + timedelta(days=1)
    contexto_manana = ""
    if manana < resultado.fecha_promesa:
        fecha_manana = horario.formatear_fecha(manana)
        if manana.isoweekday() not in taller["dias_habiles"] or manana in (taller.get("feriados") or []):
            contexto_manana = f" El {fecha_manana} no es día hábil."
        elif comprometido.get(manana, 0) >= taller["minutos_por_dia"]:
            contexto_manana = f" El {fecha_manana} el taller ya está completo."

    if resultado.se_reparte_en_varios_dias:
        return (
            f"Es un trabajo grande y no entra en un solo día de producción: "
            f"va a estar listo el {fecha_texto}{aclaracion}.{contexto_manana}"
        )

    return f"No llega para hoy{aclaracion}.{contexto_manana} Va a estar listo el {fecha_texto}."


@tool
def crear_pedido(items: list[dict], como_paga: str, config: RunnableConfig) -> str:
    """Da de alta un pedido nuevo en el sistema de Mundo Gráfico.

    Es el paso FINAL: llamala recién cuando la persona ya confirmó qué
    quiere, aceptó el precio y la fecha de entrega. No la uses solo para
    cotizar o para calcular una fecha — para eso están `cotizar` y
    `calcular_entrega`. El texto que devuelve esta herramienta ya incluye
    el número de pedido y la fecha de entrega definitiva: contestale eso
    a la persona, no vuelvas a calcular nada antes.

    Args:
        items: lo mismo que en `cotizar`: [{"producto": ..., "cantidad": ...}]
        como_paga: en una frase, cómo va a pagar según lo que se acordó en
            la charla (por ejemplo "paga todo al retirar" o "transfirió la
            seña del 50%, resto al retirar"). Seguí la política de pago
            vigente que te indica el prompt del sistema.
    """
    conversacion = conversacion_de(config)
    ctx = contexto()
    if ctx.negocio.politica_pago != "retiro":
        return (
            "Esta política requiere verificar el pago antes de confirmar. "
            "No puedo comprobar una seña o adelanto automáticamente; "
            "derivá la conversación a una persona del equipo."
        )
    contacto = ctx.chatwoot.datos_contacto(conversacion)

    try:
        with base_datos.obtener_pool().connection() as conexion:
            pedido = datos.crear_pedido(
                conexion,
                conversacion_id=conversacion,
                items=items,
                hoy=horario.hoy(),
                ahora=horario.hora_actual(),
                nombre_cliente=contacto["nombre"],
                telefono_cliente=contacto["telefono"],
                contacto_id=contacto["contacto_id"],
                notas=como_paga,
                estado_pago="a_cobrar",
                permitir_precios_provisorios=ctx.negocio.modo_demo,
            )
    except datos.PedidoInvalido as e:
        return str(e)
    except Exception:
        registro.exception("Falló crear_pedido antes de confirmar la transacción")
        return "No pude confirmar el pedido. Derivá la consulta al equipo antes de volver a intentarlo."

    # Google puede tardar o fallar. El pedido y su reserva de capacidad ya
    # quedaron confirmados antes de hacer cualquier pedido de red a Sheets.
    para_sheets = {
        **pedido,
        "cliente_nombre": pedido["cliente"]["nombre"],
        "cliente_telefono": pedido["cliente"]["telefono"],
    }
    if sheets.sincronizar_pedido(ctx.sheets, para_sheets):
        try:
            with base_datos.obtener_pool().connection() as conexion:
                datos.marcar_sincronizado_con_sheets(
                    conexion, pedido["id"], pedido.get("actualizado_en"),
                )
        except Exception:
            # La venta ya existe: no devolver un error que invite al modelo
            # a crearla otra vez. El reintento periódico resolverá la marca.
            registro.exception("Pedido %s creado; falló marcar Sheets sincronizado", pedido["numero"])

    fecha_texto = horario.formatear_fecha(pedido["agenda"].fecha_promesa)
    prefijo = "Pedido de demostración" if ctx.negocio.modo_demo else "Pedido"
    return (
        f"{prefijo} {pedido['numero']} anotado. "
        f"Total {motor.formato_dinero(float(pedido['total']))}. "
        f"Listo el {fecha_texto}."
    )


@tool
def estado_pedido(numero: str, config: RunnableConfig) -> str:
    """Consulta el estado de un pedido ya hecho.

    Si la persona te dio un número de pedido (por ejemplo "MG-0007"),
    pasalo en `numero`. Si no lo tiene o no te acordás de habérselo dado en
    esta charla, dejá `numero` vacío: se buscan los pedidos de esta misma
    conversación. Por privacidad, un número de otra conversación no alcanza
    para consultar el pedido: derivá al equipo para verificar identidad.

    Args:
        numero: el número de pedido, o "" si no se sabe.
    """
    conversacion = conversacion_de(config)
    numero = (numero or "").strip().upper()

    try:
        with base_datos.obtener_pool().connection() as conexion:
            if numero:
                pedido = datos.pedido_por_numero(conexion, numero, conversacion)
                encontrados = [pedido] if pedido else []
            else:
                encontrados = datos.pedidos_de_conversacion(conexion, conversacion)
    except Exception:
        registro.exception("Falló estado_pedido")
        return "No pude consultar el estado ahora. Derivá la consulta al equipo."

    if not encontrados:
        return (
            f"No encontré ningún pedido con el número {numero}."
            if numero else "No encontré ningún pedido en esta conversación."
        )

    return "\n---\n".join(_texto_de(p) for p in encontrados)


_ESTADOS_LEGIBLES = {
    "pendiente": "en cola, todavía no se empezó",
    "en_proceso": "en producción",
    "listo": "listo para retirar",
    "entregado": "ya entregado",
    "cancelado": "cancelado",
}


def _texto_de(pedido: dict) -> str:
    estado = _ESTADOS_LEGIBLES.get(pedido["estado"], pedido["estado"])
    return (
        f"Pedido {pedido['numero']}: {estado}. "
        f"Total {motor.formato_dinero(float(pedido['total']))}. "
        f"Fecha de entrega: {horario.formatear_fecha(pedido['fecha_promesa'])}."
    )
