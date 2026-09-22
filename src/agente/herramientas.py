"""Las herramientas del agente.

Este es el único archivo del AgentKit que tocamos: en el original vive acá
la herramienta de clima, de ejemplo. Mundo Gráfico no la necesita, así que
`HERRAMIENTAS` pasa a salir de `mundografico.herramientas` — todo lo
específico del negocio (catálogo, agenda, pedidos, Chatwoot) vive en ese
paquete aparte, sin tocar una sola línea más del kit. Es lo que permite
traer mejoras del original (`git pull upstream master`) sin pelearse con
este archivo: el diff siempre va a ser este mismo, chiquito y estable.

`agente.py` solo necesita `HERRAMIENTAS` de acá — el resto del kit no sabe
ni le importa qué hay adentro.
"""

from __future__ import annotations

from mundografico.herramientas import HERRAMIENTAS

__all__ = ["HERRAMIENTAS"]
