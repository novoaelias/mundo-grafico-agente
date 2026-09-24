"""Adaptación mínima del canal de Chatwoot para adjuntos sin texto legible."""

from __future__ import annotations

from agente.canales.base import MensajeEntrante
from agente.canales.chatwoot import Chatwoot


class ChatwootMundoGrafico(Chatwoot):
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
