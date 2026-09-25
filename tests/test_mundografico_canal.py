"""Los adjuntos de Chatwoot llegan al agente sin atribuirles contenido."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico.canal import ChatwootMundoGrafico  # noqa: E402


def _canal():
    return ChatwootMundoGrafico("https://chatwoot.example", "token", 1)


def _evento(texto, tipo="incoming"):
    return {
        "event": "message_created", "id": 42,
        "conversation": {"id": 7, "labels": []},
        "content": texto, "message_type": tipo, "private": False,
        "attachments": [{"file_type": "audio"}],
    }


def test_audio_sin_texto_pide_descripcion():
    mensaje = _canal().traducir(_evento(None))
    assert mensaje.conversacion == "7"
    assert mensaje.identificador == "42"
    assert "describa por escrito" in mensaje.texto


def test_imagen_con_texto_tampoco_se_interpreta_como_vista():
    mensaje = _canal().traducir(_evento("Quiero esto"))
    assert "Quiero esto" in mensaje.texto
    assert "No podés verlo" in mensaje.texto


def test_adjunto_saliente_se_filtra_igual_que_en_el_kit():
    canal = _canal()
    mensaje = canal.traducir(_evento(None, tipo="outgoing"))
    assert canal.deberia_responder(mensaje) is False


def test_si_faltan_etiquetas_y_chatwoot_no_contesta_el_bot_se_calla():
    canal = _canal()
    evento = _evento("Hola")
    evento["conversation"].pop("labels")
    canal._api = lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("caído"))
    mensaje = canal.traducir(evento)
    assert canal.deberia_responder(mensaje) is False


def test_demo_aclara_precio_aunque_el_modelo_lo_omita():
    canal = ChatwootMundoGrafico("https://chatwoot.example", "token", 1, modo_demo=True)
    enviados = []
    canal._api = lambda metodo, camino, datos=None: enviados.append(datos["content"])

    canal.enviar("7", ["500 volantes salen $7.500.", "¿Te va bien?"])

    assert "demo" in enviados[0].lower()
    assert enviados[1:] == ["500 volantes salen $7.500.", "¿Te va bien?"]


def test_demo_no_repite_aclaracion_ni_interviene_sin_precio():
    canal = ChatwootMundoGrafico("https://chatwoot.example", "token", 1, modo_demo=True)
    enviados = []
    canal._api = lambda metodo, camino, datos=None: enviados.append(datos["content"])

    canal.enviar("7", ["Precio de demostración: $7.500."])
    canal.enviar("7", ["¿Necesitás algo más?"])

    assert enviados == ["Precio de demostración: $7.500.", "¿Necesitás algo más?"]
