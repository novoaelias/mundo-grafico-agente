"""Pruebas de las herramientas del agente. Sin Postgres ni Chatwoot real.

Estrategia: en vez de simular cursores de psycopg, se monkeypatchea
`mundografico.pedidos` (el módulo `datos` que usan las herramientas) a
nivel de función — `productos_activos`, `obtener_taller`, etc. devuelven
listas de Python de mentira. Así lo que se prueba de verdad es la
herramienta (qué le pide a `datos`, cómo arma el texto para el modelo,
qué hace con un error), reusando `catalogo.cotizar` y `agenda.proxima_fecha`
de verdad —esos ya tienen sus propios tests— en vez de duplicarlos acá.

    pytest
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico import base_datos  # noqa: E402
from mundografico import pedidos as datos  # noqa: E402
from mundografico.config import ConfigNegocio, ConfigSheets  # noqa: E402
from mundografico.herramientas import _contexto  # noqa: E402
from mundografico.herramientas.humano import pasar_a_humano  # noqa: E402
from mundografico.herramientas.pedidos import (  # noqa: E402
    calcular_entrega,
    crear_pedido,
    estado_pedido,
)
from mundografico.herramientas.productos import buscar_producto, cotizar  # noqa: E402

CONFIG = {"configurable": {"thread_id": "conv-77"}}

TALLER = {
    "minutos_por_dia": 300,
    "dias_habiles": [1, 2, 3, 4, 5, 6],
    "hora_corte_mismo_dia": time(15, 0),
    "feriados": [],
}

PRODUCTOS = [
    {
        "id": 1, "nombre": "Lona banner", "alias": ["lona", "banner"],
        "unidad": "m2", "precio_unitario": 4500, "cantidad_minima": 1,
        "escalas": [{"desde": 5, "precio_unitario": 4000}],
        "minutos_preparacion": 20, "minutos_por_unidad": 8, "activo": True,
    },
    {
        "id": 2, "nombre": "Sello automático", "alias": ["sello"],
        "unidad": "unidad", "precio_unitario": 6500, "cantidad_minima": 1,
        "escalas": [], "minutos_preparacion": 15, "minutos_por_unidad": 20,
        "activo": True,
    },
]


class PoolFalso:
    """Ninguna función de `datos` monkeypatcheada llega a usar la conexión
    de verdad, así que alcanza con devolver cualquier cosa."""

    @contextmanager
    def connection(self):
        yield object()


class ChatwootFalso:
    def __init__(self):
        self.notas: list[tuple[str, str]] = []
        self.etiquetas: list[tuple[str, str]] = []
        self._contacto = {"nombre": "Marisa", "telefono": "+54911...", "contacto_id": "9"}

    def datos_contacto(self, conversacion_id):
        return self._contacto

    def nota_privada(self, conversacion_id, texto):
        self.notas.append((conversacion_id, texto))

    def agregar_etiqueta(self, conversacion_id, etiqueta):
        self.etiquetas.append((conversacion_id, etiqueta))


@pytest.fixture(autouse=True)
def contexto_de_prueba(monkeypatch):
    monkeypatch.setattr(base_datos, "obtener_pool", lambda: PoolFalso())
    chatwoot = ChatwootFalso()
    _contexto._reemplazar_para_tests(
        _contexto.Contexto(
            chatwoot=chatwoot, negocio=ConfigNegocio(), sheets=ConfigSheets(),
            etiqueta_humano="humano",
        )
    )
    return chatwoot


# -- buscar_producto y cotizar --------------------------------------------------


def test_buscar_producto_devuelve_texto_legible(monkeypatch):
    monkeypatch.setattr(datos, "productos_activos", lambda conexion: PRODUCTOS)

    texto = buscar_producto.invoke({"consulta": "banner"})

    assert "Lona banner" in texto
    assert "$4.500" in texto


def test_buscar_producto_sin_resultados(monkeypatch):
    monkeypatch.setattr(datos, "productos_activos", lambda conexion: PRODUCTOS)

    texto = buscar_producto.invoke({"consulta": "helicóptero"})

    assert "No encontré" in texto


def test_cotizar_devuelve_el_texto_de_la_cotizacion(monkeypatch):
    monkeypatch.setattr(datos, "productos_activos", lambda conexion: PRODUCTOS)

    texto = cotizar.invoke({"items": [{"producto": "lona", "cantidad": 2}]})

    assert "Total: $9.000" in texto


# -- calcular_entrega -----------------------------------------------------------


def preparar_agenda(monkeypatch, comprometido=None):
    monkeypatch.setattr(datos, "productos_activos", lambda conexion: PRODUCTOS)
    monkeypatch.setattr(datos, "obtener_taller", lambda conexion: TALLER)
    monkeypatch.setattr(
        datos, "comprometido_por_dia", lambda conexion, hoy: comprometido or {}
    )


def test_calcular_entrega_hoy_mismo(monkeypatch):
    preparar_agenda(monkeypatch)

    texto = calcular_entrega.invoke({"items": [{"producto": "sello", "cantidad": 1}]})

    assert "hoy mismo" in texto


def test_calcular_entrega_da_el_motivo_cuando_no_llega_hoy(monkeypatch):
    hoy_ocupado = {date.today(): 300}
    preparar_agenda(monkeypatch, comprometido=hoy_ocupado)

    texto = calcular_entrega.invoke({"items": [{"producto": "sello", "cantidad": 1}]})

    assert "No llega para hoy" in texto
    assert "lugar" in texto


def test_calcular_entrega_producto_no_encontrado(monkeypatch):
    preparar_agenda(monkeypatch)

    texto = calcular_entrega.invoke({"items": [{"producto": "algo raro", "cantidad": 1}]})

    assert "No pude calcular" in texto


# -- crear_pedido -----------------------------------------------------------------


def test_crear_pedido_usa_el_contacto_de_chatwoot_y_arma_el_texto(monkeypatch, contexto_de_prueba):
    capturado = {}

    def crear_falso(conexion, **kwargs):
        capturado.update(kwargs)
        from mundografico.agenda import ResultadoAgenda
        return {
            "id": 1,
            "numero": "MG-0001",
            "total": 9000,
            "cliente": {"nombre": "Marisa", "telefono": "+54911..."},
            "agenda": ResultadoAgenda(fecha_promesa=date(2026, 9, 22), minutos_por_dia={}, desde=date(2026, 9, 22)),
        }

    monkeypatch.setattr(datos, "crear_pedido", crear_falso)

    texto = crear_pedido.invoke(
        {"items": [{"producto": "lona", "cantidad": 2}], "como_paga": "paga al retirar"},
        config=CONFIG,
    )

    assert capturado["conversacion_id"] == "conv-77"
    assert capturado["nombre_cliente"] == "Marisa"
    assert capturado["notas"] == "paga al retirar"
    assert "MG-0001" in texto
    assert "$9.000" in texto


def test_crear_pedido_invalido_devuelve_el_motivo_sin_reventar(monkeypatch):
    def crear_falso(conexion, **kwargs):
        raise datos.PedidoInvalido("no encontré 'un dron'")

    monkeypatch.setattr(datos, "crear_pedido", crear_falso)

    texto = crear_pedido.invoke(
        {"items": [{"producto": "un dron", "cantidad": 1}], "como_paga": "paga al retirar"},
        config=CONFIG,
    )

    assert "no encontré 'un dron'" in texto


# -- estado_pedido -----------------------------------------------------------------


def test_estado_pedido_por_numero(monkeypatch):
    monkeypatch.setattr(
        datos, "pedido_por_numero",
        lambda conexion, numero: {
            "numero": "MG-0002", "estado": "listo", "total": 6500,
            "fecha_promesa": date(2026, 9, 22),
        },
    )

    texto = estado_pedido.invoke({"numero": "mg-0002"}, config=CONFIG)

    assert "listo para retirar" in texto


def test_estado_pedido_sin_numero_busca_por_conversacion(monkeypatch):
    monkeypatch.setattr(
        datos, "pedidos_de_conversacion",
        lambda conexion, conversacion: [
            {"numero": "MG-0003", "estado": "pendiente", "total": 1000,
             "fecha_promesa": date(2026, 9, 22)},
        ],
    )

    texto = estado_pedido.invoke({"numero": ""}, config=CONFIG)

    assert "MG-0003" in texto
    assert "en cola" in texto


def test_estado_pedido_no_encontrado(monkeypatch):
    monkeypatch.setattr(datos, "pedido_por_numero", lambda conexion, numero: None)

    texto = estado_pedido.invoke({"numero": "MG-9999"}, config=CONFIG)

    assert "No encontré" in texto


# -- pasar_a_humano -----------------------------------------------------------------


def test_pasar_a_humano_deja_nota_y_pone_etiqueta(contexto_de_prueba):
    texto = pasar_a_humano.invoke({"motivo": "quiere un diseño a medida"}, config=CONFIG)

    assert contexto_de_prueba.notas == [("conv-77", "🤖 Derivado por el bot: quiere un diseño a medida")]
    assert contexto_de_prueba.etiquetas == [("conv-77", "humano")]
    assert "una persona" in texto


# -- El thread_id llega de verdad por RunnableConfig, no por un dict a mano ----


def test_el_thread_id_llega_por_el_grafo_de_verdad(monkeypatch):
    """Lo mismo que la verificación de la Fase 1, pero con una herramienta
    real del proyecto en vez de una de juguete."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode, tools_condition

    monkeypatch.setattr(
        datos, "pedidos_de_conversacion",
        lambda conexion, conversacion: [
            {"numero": "MG-0005", "estado": "pendiente", "total": 500,
             "fecha_promesa": date(2026, 9, 22)},
        ] if conversacion == "conv-del-grafo" else [],
    )

    class ModeloFalso(GenericFakeChatModel):
        def bind_tools(self, herramientas, **kwargs):
            return self

    respuestas = iter([
        AIMessage("", tool_calls=[{"name": "estado_pedido", "args": {"numero": ""}, "id": "1"}]),
        AIMessage("listo"),
    ])
    modelo = ModeloFalso(messages=respuestas).bind_tools([estado_pedido])

    def nodo_modelo(estado):
        return {"messages": [modelo.invoke(estado["messages"])]}

    grafo = StateGraph(MessagesState)
    grafo.add_node("modelo", nodo_modelo)
    grafo.add_node("herramientas", ToolNode([estado_pedido]))
    grafo.add_edge(START, "modelo")
    grafo.add_conditional_edges("modelo", tools_condition, {"tools": "herramientas", END: END})
    grafo.add_edge("herramientas", "modelo")
    compilado = grafo.compile(checkpointer=InMemorySaver())

    salida = compilado.invoke(
        {"messages": [HumanMessage("¿cómo va mi pedido?")]},
        config={"configurable": {"thread_id": "conv-del-grafo"}},
    )

    mensaje_herramienta = salida["messages"][-2]
    assert "MG-0005" in mensaje_herramienta.content
