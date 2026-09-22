"""La herramienta de traspaso a una persona."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._contexto import conversacion_de, obtener as contexto


@tool
def pasar_a_humano(motivo: str, config: RunnableConfig) -> str:
    """Deriva la conversación a una persona del equipo. A partir de acá el
    bot deja de responder en esta conversación hasta que alguien del
    equipo la retome.

    Usala cuando: te piden hablar con una persona, hay un reclamo o una
    queja, piden algo que no podés resolver vos (un diseño a medida, una
    excepción de precio o de plazo), o cuando notás que la persona se está
    por ir sin cerrar por algo que un vendedor de carne y hueso sí podría
    destrabar.

    Args:
        motivo: en una frase, por qué se deriva. Lo lee el equipo como nota
            interna — la persona nunca ve este texto.
    """
    conversacion = conversacion_de(config)
    ctx = contexto()

    ctx.chatwoot.nota_privada(conversacion, f"🤖 Derivado por el bot: {motivo}")
    ctx.chatwoot.agregar_etiqueta(conversacion, ctx.etiqueta_humano)

    return (
        "Ya avisé al equipo, en un momento te responde una persona. "
        "No voy a contestar más en esta conversación mientras tanto."
    )
