"""Las herramientas de Mundo Gráfico: lo que el bot puede hacer además de
conversar.

`src/agente/herramientas.py` (el archivo del kit) importa `HERRAMIENTAS`
desde acá en vez de definir las suyas — es la única línea que conecta el
AgentKit con todo lo nuestro.

Antes de que el agente reciba el primer mensaje hay que llamar a
`inicializar()` una sola vez (lo hace `servidor_mundografico.py`), para que
las herramientas tengan con qué hablarle a Chatwoot y sepan la
configuración del negocio.
"""

from __future__ import annotations

from ._contexto import inicializar
from .humano import pasar_a_humano
from .pedidos import calcular_entrega, crear_pedido, estado_pedido
from .productos import buscar_producto, cotizar

# El orden importa un poco para la lectura del modelo (las tools van todas
# en el mismo prompt), así que van en el orden natural de una venta:
# buscar → cotizar → calcular fecha → cerrar → consultar después → derivar.
HERRAMIENTAS = [
    buscar_producto,
    cotizar,
    calcular_entrega,
    crear_pedido,
    estado_pedido,
    pasar_a_humano,
]

__all__ = ["HERRAMIENTAS", "inicializar"]
