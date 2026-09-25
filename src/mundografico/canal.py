"""Adaptación mínima del canal de Chatwoot para adjuntos sin texto legible."""

from __future__ import annotations

import re

from agente.canales.base import MensajeEntrante
from agente.canales.chatwoot import Chatwoot


class ChatwootMundoGrafico(Chatwoot):
    def __init__(self, *args, modo_demo: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.modo_demo = modo_demo

    def enviar(self, conversacion: str, mensajes: list[str]) -> None:
        # El modelo recibió la advertencia del precio provisorio en la
        # herramienta, pero en una prueba real la omitió al responder. La
        # aclaración sale desde el canal para que no dependa del modelo.
        texto = " ".join(mensajes)
        hay_precio_o_pedido = re.search(r"\$\s*[\d.,]+|MG-\d+", texto)
        ya_aclarado = re.search(r"demo|demostraci|provisori|de ejemplo", texto, re.I)
        if self.modo_demo and hay_precio_o_pedido and not ya_aclarado:
            mensajes = [
                "⚠️ Esta es una demo: el precio y la forma de pago todavía "
                "no están confirmados por Mundo Gráfico.",
                *mensajes,
            ]
        super().enviar(conversacion, mensajes)

    def _etiquetas_de(self, id_conversacion) -> list[str]:
        """Si faltan etiquetas en el webhook y falla la consulta, el bot espera.

        Responder sobre una conversación ya tomada por una persona sería
        peor que dejar un mensaje en la bandeja pendiente de atención.
        """
        if not id_conversacion:
            return [self.etiqueta_humano]
        try:
            respuesta = self._api("GET", f"conversations/{id_conversacion}/labels")
            etiquetas = respuesta.get("payload")
            return etiquetas if isinstance(etiquetas, list) else [self.etiqueta_humano]
        except Exception:
            return [self.etiqueta_humano]

    def traducir(self, evento: dict) -> MensajeEntrante | None:
        mensaje = super().traducir(evento)
        if evento.get("event") != "message_created" or not evento.get("attachments"):
            return mensaje

        conversacion = (evento.get("conversation") or {}).get("id")
        if not conversacion:
            return mensaje

        texto = mensaje.texto if mensaje else ""
        aviso = (
            "[El cliente adjuntó un archivo. No podés verlo ni escucharlo. "
            "Pedile que describa por escrito lo que necesita antes de cotizar.]"
        )
        return MensajeEntrante(
            texto=f"{texto}\n{aviso}".strip(),
            conversacion=str(conversacion),
            identificador=str(evento.get("id") or ""),
            datos=evento,
        )
