"""Herramientas de catálogo: qué hay y cuánto sale."""

from __future__ import annotations

from langchain_core.tools import tool

from .. import base_datos
from .. import catalogo as motor
from .. import pedidos as datos


@tool
def buscar_producto(consulta: str) -> str:
    """Busca en el catálogo de Mundo Gráfico productos parecidos a lo que pide la persona.

    Usala cuando no estés seguro de cómo se llama el producto en el
    catálogo, o cuando la persona pidió algo genérico (por ejemplo
    "necesito unos carteles") y conviene confirmar cuál de las opciones es
    antes de cotizar.

    Args:
        consulta: lo que la persona pidió, en sus palabras. Por ejemplo
            "banners", "tarjetas de presentación", "algo para pegar en la pared".
    """
    with base_datos.obtener_pool().connection() as conexion:
        productos = datos.productos_activos(conexion)

    encontrados = motor.buscar_producto(productos, consulta)
    if not encontrados:
        return f"No encontré nada parecido a '{consulta}' en el catálogo."

    lineas = [
        f"- {p['nombre']} ({motor.formato_dinero(float(p['precio_unitario']))} por {p['unidad']})"
        for p in encontrados
    ]
    return "Encontré esto en el catálogo:\n" + "\n".join(lineas)


@tool
def cotizar(items: list[dict]) -> str:
    """Cotiza uno o varios productos del catálogo de Mundo Gráfico.

    Usala SIEMPRE que tengas que decir un precio: nunca inventes ni
    calcules un precio de memoria ni sumes vos mismo — esta herramienta es
    la única fuente de verdad de cuánto sale cada cosa, incluidos los
    descuentos por cantidad.

    Args:
        items: lista de lo que se quiere cotizar. Por ejemplo:
            [{"producto": "lona banner", "cantidad": 3},
             {"producto": "tarjetas personales", "cantidad": 200}]
            `producto` es el nombre tal como lo dijo la persona (no hace
            falta que sea exacto: se busca el más parecido en el
            catálogo). `cantidad` es un número: para lonas y plotteo son
            metros cuadrados, para tarjetas/volantes/folletos/stickers son
            unidades sueltas (no "cientos": si piden 200 tarjetas, cantidad
            es 200), para el resto son unidades sueltas.
    """
    with base_datos.obtener_pool().connection() as conexion:
        productos = datos.productos_activos(conexion)

    resultado = motor.cotizar(productos, items)
    return resultado.texto()
