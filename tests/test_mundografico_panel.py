"""Pruebas del panel interno. Sin Postgres ni Chatwoot real: se
monkeypatchea `mundografico.pedidos` igual que en test_mundografico_herramientas.py.

    pytest
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from mundografico import base_datos  # noqa: E402
from mundografico import pedidos as datos  # noqa: E402
from mundografico.config import Config, ConfigNegocio, ConfigPanel  # noqa: E402
from mundografico.panel import CARPETA_ESTATICOS, crear_router  # noqa: E402
from mundografico.panel.rutas import _avisar_listo  # noqa: E402

CREDENCIALES = ("mundografico", "clave-de-prueba")

TALLER = {
    "minutos_por_dia": 300,
    "dias_habiles": [1, 2, 3, 4, 5, 6],
    "hora_corte_mismo_dia": time(15, 0),
    "feriados": [date(2026, 12, 25)],
}

PEDIDO = {
    "id": 1, "numero": "MG-0001", "conversacion_id": "conv-1",
    "detalle": [{"nombre": "Lona banner", "cantidad": 2, "unidad": "m2"}],
    "total": 9000, "estado": "pendiente", "estado_pago": "a_cobrar",
    "fecha_promesa": date(2026, 9, 22), "notas": "",
    "cliente_nombre": "Marisa", "cliente_telefono": "",
}


class ChatwootFalso:
    def __init__(self):
        self.mensajes: list[tuple[str, str]] = []
        self.labels = ["humano", "urgente"]

    def enviar_mensaje(self, conversacion_id, texto):
        self.mensajes.append((conversacion_id, texto))

    def etiquetas(self, conversacion_id):
        return self.labels

    def quitar_etiqueta(self, conversacion_id, etiqueta):
        self.labels = [label for label in self.labels if label != etiqueta]


class PoolFalso:
    @contextmanager
    def connection(self):
        yield object()


@pytest.fixture()
def chatwoot(monkeypatch):
    monkeypatch.setattr(base_datos, "obtener_pool", lambda: PoolFalso())
    return ChatwootFalso()


@pytest.fixture()
def cliente(chatwoot):
    config = Config(
        postgres_dsn="postgresql://x",
        negocio=ConfigNegocio(nombre="Mundo Gráfico", direccion="Laferrere"),
        panel=ConfigPanel(usuario=CREDENCIALES[0], clave=CREDENCIALES[1]),
    )
    app = FastAPI()
    app.mount("/panel/estaticos", StaticFiles(directory=str(CARPETA_ESTATICOS)))
    app.include_router(crear_router(config, chatwoot))
    return TestClient(app)


# -- Autenticación --------------------------------------------------------------


def test_sin_credenciales_da_401(cliente):
    respuesta = cliente.get("/panel/pedidos")
    assert respuesta.status_code == 401


def test_con_credenciales_equivocadas_da_401(cliente, monkeypatch):
    monkeypatch.setattr(datos, "listar_pedidos", lambda conexion, estado=None: [])
    monkeypatch.setattr(datos, "carga_de_hoy", lambda conexion, hoy: {"usado": 0, "total": 300, "porcentaje": 0})

    respuesta = cliente.get("/panel/pedidos", auth=("mundografico", "mal"))
    assert respuesta.status_code == 401


def test_con_credenciales_correctas_entra(cliente, monkeypatch):
    monkeypatch.setattr(datos, "listar_pedidos", lambda conexion, estado=None: [])
    monkeypatch.setattr(datos, "carga_de_hoy", lambda conexion, hoy: {"usado": 0, "total": 300, "porcentaje": 0})

    respuesta = cliente.get("/panel/pedidos", auth=CREDENCIALES)
    assert respuesta.status_code == 200


def test_sin_panel_clave_configurada_falla_cerrado(monkeypatch, chatwoot):
    monkeypatch.setattr(datos, "listar_pedidos", lambda conexion, estado=None: [])
    config = Config(
        postgres_dsn="x",
        panel=ConfigPanel(usuario="admin", clave=""),  # sin clave en el .env
    )
    app = FastAPI()
    app.include_router(crear_router(config, chatwoot))
    cliente_local = TestClient(app)

    respuesta = cliente_local.get("/panel/pedidos", auth=("admin", ""))
    assert respuesta.status_code == 500


# -- Pedidos ----------------------------------------------------------------------


def test_aviso_de_listo_indica_que_es_demo(chatwoot):
    config = Config(postgres_dsn="x", negocio=ConfigNegocio(modo_demo=True))

    assert _avisar_listo(chatwoot, config, PEDIDO) is True
    assert chatwoot.mensajes[0][1].startswith("[DEMO]")


def test_lista_de_pedidos_muestra_la_carga_de_hoy(cliente, monkeypatch):
    monkeypatch.setattr(datos, "listar_pedidos", lambda conexion, estado=None: [PEDIDO])
    monkeypatch.setattr(
        datos, "carga_de_hoy", lambda conexion, hoy: {"usado": 300, "total": 300, "porcentaje": 100}
    )

    respuesta = cliente.get("/panel/pedidos", auth=CREDENCIALES)

    assert respuesta.status_code == 200
    assert "MG-0001" in respuesta.text
    assert "TALLER LLENO" in respuesta.text


def test_panel_muestra_bot_pausado_y_lo_reanuda(cliente, monkeypatch, chatwoot):
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: PEDIDO)
    estado = cliente.get("/panel/pedidos/1/bot", auth=CREDENCIALES)
    assert estado.status_code == 200
    assert "Bot en pausa" in estado.text

    reanudado = cliente.post("/panel/pedidos/1/reanudar-bot", auth=CREDENCIALES)
    assert reanudado.status_code == 200
    assert "Bot activo" in reanudado.text
    assert chatwoot.labels == ["urgente"]


def test_panel_no_finge_estado_bot_si_chatwoot_falla(cliente, monkeypatch, chatwoot):
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: PEDIDO)

    def falla(conversacion_id):
        raise ConnectionError("Chatwoot caído")

    chatwoot.etiquetas = falla
    estado = cliente.get("/panel/pedidos/1/bot", auth=CREDENCIALES)
    assert estado.status_code == 200
    assert "Estado no disponible" in estado.text
    assert "Bot activo" not in estado.text


def test_marcar_listo_avisa_por_chatwoot_y_devuelve_la_fila(cliente, monkeypatch, chatwoot):
    pedido_listo = {**PEDIDO, "estado": "listo", "avisado_listo_en": None}
    monkeypatch.setattr(datos, "marcar_listo", lambda conexion, pedido_id: pedido_listo)
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: pedido_listo)
    monkeypatch.setattr(datos, "registrar_aviso_enviado", lambda conexion, pedido_id: pedido_listo.update(avisado_listo_en="ahora"))

    respuesta = cliente.post("/panel/pedidos/1/listo", auth=CREDENCIALES)

    assert respuesta.status_code == 200
    assert len(chatwoot.mensajes) == 1
    conversacion, texto = chatwoot.mensajes[0]
    assert conversacion == "conv-1"
    assert "MG-0001" in texto
    assert "listo" in texto.lower()
    assert "Aviso pendiente" not in respuesta.text
    assert "Guardar" not in respuesta.text  # es la fila del pedido, no la de catálogo


def test_marcar_listo_no_revienta_si_chatwoot_falla(cliente, monkeypatch, chatwoot):
    def explota(conversacion_id, texto):
        raise ConnectionError("caído")

    chatwoot.enviar_mensaje = explota
    pedido_listo = {**PEDIDO, "estado": "listo", "avisado_listo_en": None}
    monkeypatch.setattr(datos, "marcar_listo", lambda conexion, pedido_id: pedido_listo)
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: pedido_listo)

    respuesta = cliente.post("/panel/pedidos/1/listo", auth=CREDENCIALES)

    assert respuesta.status_code == 200, "marcar listo no puede fallar porque el aviso falló"
    assert "Aviso pendiente" in respuesta.text
    assert "Reintentar aviso" in respuesta.text


def test_reintentar_aviso_pendiente(cliente, monkeypatch, chatwoot):
    pedido_listo = {**PEDIDO, "estado": "listo", "avisado_listo_en": None}
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: pedido_listo)
    monkeypatch.setattr(datos, "registrar_aviso_enviado", lambda conexion, pedido_id: pedido_listo.update(avisado_listo_en="ahora"))

    respuesta = cliente.post("/panel/pedidos/1/aviso", auth=CREDENCIALES)

    assert respuesta.status_code == 200
    assert len(chatwoot.mensajes) == 1
    assert "Aviso pendiente" not in respuesta.text


def test_marcar_entregado_manda_el_monto(cliente, monkeypatch):
    capturado = {}

    def marcar_falso(conexion, pedido_id, monto_cobrado):
        capturado["monto"] = monto_cobrado
        return {**PEDIDO, "estado": "entregado", "estado_pago": "pagado"}

    monkeypatch.setattr(datos, "marcar_entregado", marcar_falso)
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: PEDIDO)

    respuesta = cliente.post(
        "/panel/pedidos/1/entregado", auth=CREDENCIALES, data={"monto_cobrado": "8500"}
    )

    assert respuesta.status_code == 200
    assert capturado["monto"] == 8500.0


def test_cancelar_pedido(cliente, monkeypatch):
    monkeypatch.setattr(datos, "cancelar_pedido", lambda conexion, pedido_id, motivo="": {**PEDIDO, "estado": "cancelado"})
    monkeypatch.setattr(datos, "pedido_con_cliente", lambda conexion, pedido_id: PEDIDO)

    respuesta = cliente.post("/panel/pedidos/1/cancelar", auth=CREDENCIALES, data={"motivo": "se arrepintió"})

    assert respuesta.status_code == 200


# -- Catálogo -----------------------------------------------------------------------

PRODUCTO = {
    "id": 5, "nombre": "Sello automático", "categoria": "sellos", "unidad": "unidad",
    "precio_unitario": 6500, "cantidad_minima": 1, "escalas": [],
    "minutos_preparacion": 15, "minutos_por_unidad": 20,
    "precio_provisorio": True, "activo": True,
}


def test_ver_catalogo(cliente, monkeypatch):
    monkeypatch.setattr(datos, "todos_los_productos", lambda conexion: [PRODUCTO])

    respuesta = cliente.get("/panel/catalogo", auth=CREDENCIALES)

    assert respuesta.status_code == 200
    assert "Sello autom" in respuesta.text


def test_actualizar_producto_apaga_activo_cuando_no_llega_el_checkbox(cliente, monkeypatch):
    capturado = {}

    def actualizar_falso(conexion, producto_id, cambios):
        capturado.update(cambios)
        return {**PRODUCTO, **cambios}

    monkeypatch.setattr(datos, "actualizar_producto", actualizar_falso)

    respuesta = cliente.post(
        "/panel/catalogo/5", auth=CREDENCIALES,
        data={
            "nombre": "Sello automático", "categoria": "sellos", "unidad": "unidad",
            "precio_unitario": "7000", "cantidad_minima": "1",
            "minutos_preparacion": "15", "minutos_por_unidad": "20",
            # sin "activo": así llega un checkbox sin marcar de verdad
        },
    )

    assert respuesta.status_code == 200
    assert capturado["activo"] is False
    assert capturado["precio_unitario"] == 7000.0
    assert "precio_provisorio" not in capturado


def test_precio_provisorio_requiere_confirmacion_explicita(cliente, monkeypatch):
    capturado = {}

    def actualizar_falso(conexion, producto_id, cambios):
        capturado.update(cambios)
        return {**PRODUCTO, **cambios}

    monkeypatch.setattr(datos, "actualizar_producto", actualizar_falso)
    respuesta = cliente.post(
        "/panel/catalogo/5", auth=CREDENCIALES,
        data={"nombre": "Sello automático", "precio_unitario": "7000", "confirmar_precio": "true"},
    )
    assert respuesta.status_code == 200
    assert capturado["precio_provisorio"] is False


def test_crear_producto_nuevo(cliente, monkeypatch):
    capturado = {}

    def crear_falso(conexion, valores):
        capturado.update(valores)
        return {**PRODUCTO, **valores, "id": 99}

    monkeypatch.setattr(datos, "crear_producto", crear_falso)
    monkeypatch.setattr(datos, "todos_los_productos", lambda conexion: [PRODUCTO])

    respuesta = cliente.post(
        "/panel/catalogo/nuevo", auth=CREDENCIALES,
        data={
            "nombre": "Imán de heladera", "categoria": "souvenirs", "unidad": "unidad",
            "precio_unitario": "500", "cantidad_minima": "1",
            "minutos_preparacion": "5", "minutos_por_unidad": "1",
        },
    )

    assert respuesta.status_code == 200
    assert capturado["nombre"] == "Imán de heladera"
    assert capturado["precio_provisorio"] is False, "lo carga el dueño a mano: no es un precio de ejemplo"


# -- Taller ---------------------------------------------------------------------------


def test_ver_taller(cliente, monkeypatch):
    monkeypatch.setattr(datos, "obtener_taller", lambda conexion: TALLER)

    respuesta = cliente.get("/panel/taller", auth=CREDENCIALES)

    assert respuesta.status_code == 200
    assert "25/12/2026" in respuesta.text


def test_actualizar_taller_parsea_dias_y_feriados(cliente, monkeypatch):
    capturado = {}

    def actualizar_falso(conexion, cambios):
        capturado.update(cambios)
        return TALLER

    monkeypatch.setattr(datos, "actualizar_taller", actualizar_falso)

    respuesta = cliente.post(
        "/panel/taller", auth=CREDENCIALES,
        data={
            "minutos_por_dia": "360",
            "hora_corte_mismo_dia": "14:30",
            "dias_habiles": ["1", "2", "3", "4", "5"],
            "feriados": "25/12/2026, 01/01/2027\n09/07/2027",
        },
    )

    assert respuesta.status_code == 200
    assert capturado["minutos_por_dia"] == 360
    assert capturado["hora_corte_mismo_dia"] == time(14, 30)
    assert capturado["dias_habiles"] == [1, 2, 3, 4, 5]
    assert capturado["feriados"] == [date(2026, 12, 25), date(2027, 1, 1), date(2027, 7, 9)]


def test_actualizar_taller_sin_dias_marcados_rechaza(cliente):
    respuesta = cliente.post(
        "/panel/taller", auth=CREDENCIALES,
        data={"minutos_por_dia": "300", "hora_corte_mismo_dia": "15:00", "feriados": ""},
    )
    assert respuesta.status_code == 422
