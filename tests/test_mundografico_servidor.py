"""Prueba de integración de `servidor_mundografico.construir_app`: que el
webhook del kit y el panel realmente convivan en el mismo FastAPI, sin
levantar un servidor de verdad ni tocar Postgres, Chatwoot o Anthropic.

Es la prueba que detecta el error más tonto y más caro de este archivo:
que un import cruzado entre el kit y mundografico esté mal armado y todo
reviente recién al arrancar el proceso de verdad, en el servidor.

    pytest
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para importar servidor_mundografico

from agente.config import Config as ConfigAgente  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mundografico import base_datos  # noqa: E402
from mundografico.config import Config as ConfigMG  # noqa: E402
from mundografico.config import ConfigPanel  # noqa: E402


@pytest.fixture()
def app(monkeypatch, tmp_path):
    # Nada de red: ni a Postgres (aplicar_migraciones), ni a Anthropic
    # (listar_modelos, que crear_modelo llama para saber el tope de tokens).
    monkeypatch.setattr(base_datos, "aplicar_migraciones", lambda dsn: ["001_esquema.sql"])
    import agente.modelos as modelos_del_kit
    monkeypatch.setattr(modelos_del_kit, "listar_modelos", lambda proveedor, api_key: [])

    import servidor_mundografico

    config_agente = ConfigAgente(
        proveedor="claude",
        modelo="modelo-de-prueba",
        api_key="clave-de-prueba",
        max_tokens=1024,
        memoria_mensajes=20,
        prompt_sistema=Path(__file__).resolve().parents[1] / "prompts" / "sistema.md",
        modo="test",
        sqlite_ruta=str(tmp_path / "conversaciones.db"),
        chatwoot_url="https://chatwoot.ejemplo.com",
        chatwoot_token="token-de-prueba",
        chatwoot_cuenta_id="1",
        chatwoot_webhook_token="secreto",
    )
    config_mg = ConfigMG(
        postgres_dsn="postgresql://usuario:clave@localhost/mundografico_test",
        panel=ConfigPanel(usuario="mundografico", clave="clave-panel"),
    )

    return servidor_mundografico.construir_app(config_agente, config_mg)


def test_el_webhook_del_kit_sigue_andando(app):
    with TestClient(app) as cliente:
        respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "ok"


def test_el_panel_quedo_montado_y_pide_login(app):
    with TestClient(app) as cliente:
        respuesta = cliente.get("/panel/pedidos")
    assert respuesta.status_code == 401


def test_los_estaticos_del_panel_se_sirven(app):
    with TestClient(app) as cliente:
        respuesta = cliente.get("/panel/estaticos/estilos.css")
    assert respuesta.status_code == 200
    assert "topbar" in respuesta.text


def test_las_migraciones_se_aplicaron_al_construir(app):
    assert app.state.migraciones_aplicadas == ["001_esquema.sql"]
