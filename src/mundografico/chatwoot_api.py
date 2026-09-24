"""Cliente propio de la API de Chatwoot.

El canal del kit (`agente/canales/chatwoot.py`) solo sabe traducir mensajes
y contestar: es lo único que el agente necesita para conversar. Acá hace
falta más — leer el contacto, poner una etiqueta, dejar una nota interna —
así que en vez de tocar el canal del kit (y arriesgar el próximo
`git pull upstream`), este es un cliente aparte con el mismo patrón: solo
`urllib` de la biblioteca estándar, sin sumar una dependencia nueva.

Sí, `_api()` queda duplicado con el del canal del kit. Es a propósito: son
quince líneas contra el acoplarse a un método privado (con el guión bajo
que es) de un archivo que no es nuestro.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

registro = logging.getLogger("mundografico.chatwoot_api")

ESPERA_DE_RED = 20


class ErrorDeChatwoot(Exception):
    """Chatwoot contestó algo que no esperábamos."""


class ClienteChatwoot:
    def __init__(self, url: str, token: str, cuenta_id: str | int) -> None:
        if not url or not token:
            raise ValueError(
                "Faltan CHATWOOT_URL o CHATWOOT_TOKEN en el .env."
            )
        self.url = url.rstrip("/")
        self.token = token
        self.cuenta_id = str(cuenta_id)

    # -- Lo que se pregunta ------------------------------------------------------

    def datos_contacto(self, conversacion_id: str) -> dict:
        """Nombre y teléfono de quien habla en esa conversación.

        Se le pregunta a Chatwoot en vez de confiar en lo que trajo el
        webhook: así funciona igual en Telegram, WhatsApp o el widget web,
        sin depender de qué campos manda cada canal en el evento crudo.

        Si Chatwoot no contesta, se devuelve todo vacío: quien llama decide
        si eso alcanza para seguir (crear el pedido igual, sin nombre) o no.
        """
        try:
            datos = self._api("GET", f"conversations/{conversacion_id}")
        except Exception as e:
            registro.warning(
                "No se pudo leer el contacto de la conversación %s: %s",
                conversacion_id, e,
            )
            return {"nombre": "", "telefono": "", "contacto_id": ""}

        contacto = (datos.get("meta") or {}).get("sender") or {}
        return {
            "nombre": (contacto.get("name") or "").strip(),
            "telefono": (contacto.get("phone_number") or "").strip(),
            "contacto_id": str(contacto.get("id") or ""),
        }

    def etiquetas(self, conversacion_id: str) -> list[str]:
        # El POST reemplaza TODA la lista. Si el GET falla, devolver []
        # borraría etiquetas del equipo al agregar una nueva.
        respuesta = self._api("GET", f"conversations/{conversacion_id}/labels")
        etiquetas = respuesta.get("payload")
        if not isinstance(etiquetas, list):
            raise ErrorDeChatwoot("Chatwoot no devolvió la lista de etiquetas.")
        return etiquetas

    # -- Lo que se hace ------------------------------------------------------------

    def agregar_etiqueta(self, conversacion_id: str, etiqueta: str) -> None:
        """Suma una etiqueta sin pisar las que ya tenía la conversación.

        La API de Chatwoot no tiene "agregar una sola": el POST de labels
        reemplaza la lista entera. Por eso primero se lee la actual y se
        manda la unión — perder una etiqueta que ya tenía el equipo
        (por ejemplo "urgente") sería peor que no poner la nuestra.
        """
        actuales = self.etiquetas(conversacion_id)
        if etiqueta in actuales:
            return

        self._api(
            "POST",
            f"conversations/{conversacion_id}/labels",
            {"labels": [*actuales, etiqueta]},
        )

    def quitar_etiqueta(self, conversacion_id: str, etiqueta: str) -> None:
        """Devuelve el control al bot sin borrar las demás etiquetas."""
        actuales = self.etiquetas(conversacion_id)
        if etiqueta not in actuales:
            return
        self._api(
            "POST",
            f"conversations/{conversacion_id}/labels",
            {"labels": [actual for actual in actuales if actual != etiqueta]},
        )

    def nota_privada(self, conversacion_id: str, texto: str) -> None:
        """Deja una nota interna: la ve el equipo, nunca la persona."""
        self._api(
            "POST",
            f"conversations/{conversacion_id}/messages",
            {"content": texto, "message_type": "outgoing", "private": True},
        )

    def enviar_mensaje(self, conversacion_id: str, texto: str) -> None:
        """Le manda un mensaje a la persona por fuera del agente.

        Lo usa el panel cuando alguien marca "pedido listo": ese aviso no
        nace de una conversación con el modelo, así que no pasa por
        BufferDeMensajes ni por partir_respuesta — es un mensaje suelto.
        """
        if not texto.strip():
            return

        self._api(
            "POST",
            f"conversations/{conversacion_id}/messages",
            {"content": texto, "message_type": "outgoing"},
        )

    # -- La API ----------------------------------------------------------------

    def _api(self, metodo: str, camino: str, datos: dict | None = None) -> dict:
        url = f"{self.url}/api/v1/accounts/{self.cuenta_id}/{camino}"

        pedido = urllib.request.Request(
            url,
            data=json.dumps(datos).encode("utf-8") if datos is not None else None,
            method=metodo,
            headers={
                "Content-Type": "application/json",
                "api_access_token": self.token,
            },
        )

        try:
            with urllib.request.urlopen(pedido, timeout=ESPERA_DE_RED) as respuesta:
                cuerpo = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ErrorDeChatwoot(
                f"Chatwoot devolvió {e.code} en {metodo} {camino}: {detalle}"
            ) from None

        return json.loads(cuerpo) if cuerpo else {}
