"""Lo que las herramientas necesitan y no pueden recibir por parámetro.

LangGraph instancia las `@tool` como funciones sueltas —las llama el
modelo, no nosotros— así que no hay forma de pasarles un cliente de
Chatwoot o la configuración del negocio por constructor. Este módulo es el
lugar donde vive eso, cargado una sola vez al arrancar el servidor con
`inicializar()` (ver `servidor_mundografico.py`).

El pool de Postgres no vive acá: ya es un singleton de `base_datos.py`
(`base_datos.obtener_pool()`), y duplicarlo acá solo sumaría una forma más
de que los dos queden desincronizados.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig

from ..chatwoot_api import ClienteChatwoot
from ..config import ConfigNegocio


@dataclass
class Contexto:
    chatwoot: ClienteChatwoot
    negocio: ConfigNegocio
    etiqueta_humano: str


_contexto: Contexto | None = None


def inicializar(
    *,
    chatwoot_url: str,
    chatwoot_token: str,
    chatwoot_cuenta_id: str,
    etiqueta_humano: str,
    negocio: ConfigNegocio,
) -> Contexto:
    """Arma el contexto compartido. Se llama una sola vez, al arrancar."""
    global _contexto
    _contexto = Contexto(
        chatwoot=ClienteChatwoot(chatwoot_url, chatwoot_token, chatwoot_cuenta_id),
        negocio=negocio,
        etiqueta_humano=(etiqueta_humano or "humano").strip().lower(),
    )
    return _contexto


def obtener() -> Contexto:
    if _contexto is None:
        raise RuntimeError(
            "Las herramientas de Mundo Gráfico no se inicializaron todavía: "
            "llamá a herramientas.inicializar(...) antes de levantar el agente."
        )
    return _contexto


def _reemplazar_para_tests(contexto: Contexto) -> None:
    """Puerta trasera para los tests: no la use nada que no sea un test."""
    global _contexto
    _contexto = contexto


def conversacion_de(config: RunnableConfig) -> str:
    """El thread_id que LangGraph inyecta en `config`: el id de conversación
    de Chatwoot. Es lo que une "con quién habla el bot" con "de quién es
    este pedido" — ver agente/canales/chatwoot.py del kit."""
    conversacion = (config.get("configurable") or {}).get("thread_id")
    if not conversacion:
        raise RuntimeError(
            "Falta thread_id en el config: no se puede identificar la conversación."
        )
    return str(conversacion)
