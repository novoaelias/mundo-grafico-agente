"""Pruebas del cliente de Chatwoot. No sale a internet: se pisa `_api()`.

    pytest
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico.chatwoot_api import ClienteChatwoot  # noqa: E402


class ClienteFalso(ClienteChatwoot):
    def __init__(self, respuestas: dict | None = None):
        super().__init__(url="https://chatwoot.ejemplo.com", token="x", cuenta_id=1)
        self.llamadas: list[dict] = []
        self._respuestas = respuestas or {}

    def _api(self, metodo, camino, datos=None):
        self.llamadas.append({"metodo": metodo, "camino": camino, "datos": datos})
        clave = f"{metodo} {camino}"
        if clave in self._respuestas:
            return self._respuestas[clave]
        if camino.endswith("/labels") and metodo == "GET":
            return {"payload": []}
        return {}


def test_sin_datos_avisa_que_faltan():
    with pytest.raises(ValueError, match="CHATWOOT_URL"):
        ClienteChatwoot(url="", token="", cuenta_id=1)


# -- datos_contacto -----------------------------------------------------------


def test_lee_nombre_y_telefono_del_contacto():
    cliente = ClienteFalso({
        "GET conversations/55": {
            "meta": {"sender": {"id": 9, "name": "Marisa", "phone_number": "+549..."}}
        }
    })

    datos = cliente.datos_contacto("55")

    assert datos == {"nombre": "Marisa", "telefono": "+549...", "contacto_id": "9"}


def test_contacto_sin_telefono_queda_vacio():
    """El caso de Telegram: hay nombre pero no hay teléfono."""
    cliente = ClienteFalso({
        "GET conversations/55": {"meta": {"sender": {"id": 9, "name": "Marisa"}}}
    })

    datos = cliente.datos_contacto("55")

    assert datos["telefono"] == ""


def test_si_chatwoot_no_contesta_devuelve_todo_vacio():
    class ClienteQueExplota(ClienteChatwoot):
        def __init__(self):
            super().__init__(url="https://x.com", token="x", cuenta_id=1)

        def _api(self, metodo, camino, datos=None):
            raise ConnectionError("caído")

    datos = ClienteQueExplota().datos_contacto("55")

    assert datos == {"nombre": "", "telefono": "", "contacto_id": ""}


# -- etiquetas ------------------------------------------------------------------


def test_agregar_etiqueta_suma_a_las_que_ya_habia():
    cliente = ClienteFalso({
        "GET conversations/12/labels": {"payload": ["ventas"]}
    })

    cliente.agregar_etiqueta("12", "humano")

    envio = [l for l in cliente.llamadas if l["camino"] == "conversations/12/labels" and l["metodo"] == "POST"]
    assert envio[0]["datos"] == {"labels": ["ventas", "humano"]}


def test_agregar_etiqueta_que_ya_estaba_no_hace_nada():
    cliente = ClienteFalso({
        "GET conversations/12/labels": {"payload": ["humano"]}
    })

    cliente.agregar_etiqueta("12", "humano")

    posts = [l for l in cliente.llamadas if l["metodo"] == "POST"]
    assert posts == []


def test_si_falla_leer_etiquetas_no_reemplaza_la_lista():
    class ClienteQueExplota(ClienteFalso):
        def _api(self, metodo, camino, datos=None):
            if metodo == "GET":
                raise ConnectionError("caído")
            return super()._api(metodo, camino, datos)

    cliente = ClienteQueExplota()
    with pytest.raises(ConnectionError):
        cliente.agregar_etiqueta("12", "humano")
    assert not any(llamada["metodo"] == "POST" for llamada in cliente.llamadas)


def test_quitar_etiqueta_humano_conserva_las_demas():
    cliente = ClienteFalso({
        "GET conversations/12/labels": {"payload": ["ventas", "humano", "urgente"]}
    })
    cliente.quitar_etiqueta("12", "humano")
    posts = [l for l in cliente.llamadas if l["metodo"] == "POST"]
    assert posts[0]["datos"] == {"labels": ["ventas", "urgente"]}


# -- mensajes -----------------------------------------------------------------


def test_nota_privada_va_marcada_como_privada():
    cliente = ClienteFalso()

    cliente.nota_privada("12", "ojo con este cliente")

    envio = cliente.llamadas[0]
    assert envio["camino"] == "conversations/12/messages"
    assert envio["datos"] == {
        "content": "ojo con este cliente",
        "message_type": "outgoing",
        "private": True,
    }


def test_enviar_mensaje_no_es_privado():
    cliente = ClienteFalso()

    cliente.enviar_mensaje("12", "tu pedido está listo")

    datos = cliente.llamadas[0]["datos"]
    assert "private" not in datos
    assert datos["message_type"] == "outgoing"


def test_enviar_mensaje_vacio_no_llama_a_la_api():
    cliente = ClienteFalso()

    cliente.enviar_mensaje("12", "   ")

    assert cliente.llamadas == []
