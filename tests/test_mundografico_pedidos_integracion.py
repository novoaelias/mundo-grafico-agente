"""Pruebas de integración de pedidos.py y base_datos.py contra Postgres real.

Estas SÍ tocan una base de verdad, a propósito: son las que prueban SQL,
transacciones y el candado de agenda, que no se pueden probar con listas de
Python. Por eso están separadas de los tests normales y apagadas por
defecto — nadie que corra `pytest` sin más se queda pegado esperando una
base que no tiene.

Para correrlas, apuntá a una base de desarrollo (nunca a la de producción:
el primer paso de cada test BORRA el schema `mundografico` entero) y
prendelas con la variable de entorno:

    MUNDOGRAFICO_TEST_DSN=postgresql://usuario:clave@localhost:5432/mundografico_dev pytest tests/test_mundografico_pedidos_integracion.py

Si abriste el túnel SSH al Postgres del VPS que arma el plan (Fase 0),
apuntá acá a `mundografico_dev`, no a `mundografico`.
"""

from __future__ import annotations

import os
import sys
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DSN = os.getenv("MUNDOGRAFICO_TEST_DSN", "")

pytestmark = pytest.mark.skipif(
    not DSN,
    reason=(
        "Necesita Postgres real. Corré con "
        "MUNDOGRAFICO_TEST_DSN=postgresql://... pytest"
    ),
)

if DSN:
    from mundografico import base_datos, pedidos


@pytest.fixture()
def conexion():
    """Un schema `mundografico` recién creado, con catálogo pero SIN los
    pedidos de demo (003_demo.sql no se corre acá): así cada test empieza
    con la agenda completamente vacía y las cuentas dan redondas."""
    base_datos.cerrar_pool()
    pool = base_datos.iniciar_pool(DSN)

    with pool.connection() as prep:
        prep.execute("DROP SCHEMA IF EXISTS mundografico CASCADE")
        prep.commit()

        for nombre in ("001_esquema.sql", "002_catalogo.sql"):
            archivo = base_datos.CARPETA_MIGRACIONES / nombre
            prep.execute(archivo.read_text(encoding="utf-8"))
            prep.commit()
        # Esta suite prueba el flujo de pedidos reales con un catálogo ya
        # validado. El seed sin validar se prueba por separado.
        prep.execute("UPDATE mundografico.productos SET precio_provisorio = FALSE")
        prep.commit()

    with pool.connection() as c:
        yield c
        c.rollback()

    base_datos.cerrar_pool()


def id_de_producto(conexion, nombre: str) -> int:
    return conexion.execute(
        "SELECT id FROM mundografico.productos WHERE nombre = %s", (nombre,)
    ).fetchone()["id"]


# -- crear_pedido --------------------------------------------------------------


def test_crea_un_pedido_completo(conexion):
    pedido = pedidos.crear_pedido(
        conexion,
        conversacion_id="conv-1",
        items=[{"producto": "lona", "cantidad": 2}],
        hoy=date(2026, 9, 21),
        ahora=time(10, 0),
        nombre_cliente="Marisa",
    )
    conexion.commit()

    assert pedido["numero"] == "MG-0001"
    assert pedido["estado"] == "pendiente"
    assert pedido["fecha_promesa"] == date(2026, 9, 21)
    assert pedido["cliente"]["nombre"] == "Marisa"
    assert float(pedido["total"]) == 2 * 4500

    guardado = pedidos.pedido_por_numero(conexion, "MG-0001")
    assert guardado is not None
    assert guardado["conversacion_id"] == "conv-1"
    assert pedidos.pedido_por_numero(conexion, "MG-0001", "otra-conversacion") is None


def test_los_numeros_de_pedido_son_correlativos(conexion):
    for _ in range(3):
        pedidos.crear_pedido(
            conexion, "conv-1", [{"producto": "sello", "cantidad": 1}],
            hoy=date(2026, 9, 21), ahora=time(10, 0),
        )
    conexion.commit()

    numeros = [p["numero"] for p in pedidos.pedidos_de_conversacion(conexion, "conv-1")]
    assert sorted(numeros) == ["MG-0001", "MG-0002", "MG-0003"]


def test_estado_pago_por_defecto_es_a_cobrar(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    assert pedido["estado_pago"] == "a_cobrar"


def test_estado_pago_se_puede_fijar_al_crear(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
        estado_pago="señado",
    )
    assert pedido["estado_pago"] == "señado"


def test_sin_productos_reconocidos_no_crea_nada(conexion):
    with pytest.raises(pedidos.PedidoInvalido):
        pedidos.crear_pedido(
            conexion, "conv-1", [{"producto": "un dron", "cantidad": 1}],
            hoy=date(2026, 9, 21),
        )


def test_no_crea_pedido_parcial(conexion):
    with pytest.raises(pedidos.PedidoInvalido):
        pedidos.crear_pedido(
            conexion, "conv-1", [
                {"producto": "sello", "cantidad": 1},
                {"producto": "un dron", "cantidad": 1},
            ], hoy=date(2026, 9, 21),
        )
    assert pedidos.pedidos_de_conversacion(conexion, "conv-1") == []


def test_precio_provisorio_solo_se_acepta_en_modo_demo(conexion):
    conexion.execute("UPDATE mundografico.productos SET precio_provisorio = TRUE WHERE nombre = 'Sello automático'")
    with pytest.raises(pedidos.PedidoInvalido, match="precios de ejemplo"):
        pedidos.crear_pedido(
            conexion, "conv-1", [{"producto": "sello", "cantidad": 1}],
            hoy=date(2026, 9, 21),
        )
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}],
        hoy=date(2026, 9, 21), permitir_precios_provisorios=True,
    )
    assert pedido["numero"].startswith("MG-")


def test_el_mismo_conversacion_id_reusa_el_cliente(conexion):
    p1 = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}],
        hoy=date(2026, 9, 21), nombre_cliente="Beto",
    )
    p2 = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}],
        hoy=date(2026, 9, 21),
    )
    conexion.commit()

    assert p1["cliente"]["id"] == p2["cliente"]["id"]
    assert p2["cliente"]["nombre"] == "Beto", "no se tiene que perder el nombre ya guardado"


# -- La agenda, con el candado adentro de una transacción real -----------------


def test_dos_pedidos_grandes_seguidos_caen_en_dias_distintos(conexion):
    # El taller por defecto tiene 300 min/día. "Lona banner" son 8 min/m2 + 20 fijos.
    # 35 m2 = 20 + 280 = 300: llena el día justo.
    p1 = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "lona", "cantidad": 35}],
        hoy=date(2026, 9, 21), ahora=time(10, 0),
    )
    p2 = pedidos.crear_pedido(
        conexion, "conv-2", [{"producto": "sello", "cantidad": 1}],
        hoy=date(2026, 9, 21), ahora=time(10, 0),
    )
    conexion.commit()

    assert p1["fecha_promesa"] == date(2026, 9, 21)
    assert p2["fecha_promesa"] == date(2026, 9, 22), "ya no quedaba lugar hoy"


def test_un_pedido_grande_reparte_minutos_en_asignacion_agenda(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "lona", "cantidad": 70}],  # 580 minutos
        hoy=date(2026, 9, 21), ahora=time(10, 0),
    )
    conexion.commit()

    filas = conexion.execute(
        "SELECT fecha, minutos FROM mundografico.asignacion_agenda "
        "WHERE pedido_id = %s ORDER BY fecha",
        (pedido["id"],),
    ).fetchall()

    assert [f["fecha"] for f in filas] == [date(2026, 9, 21), date(2026, 9, 22)]
    assert sum(f["minutos"] for f in filas) == pedido["minutos_estimados"]


def test_cancelar_un_pedido_libera_su_lugar_en_la_agenda(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "lona", "cantidad": 35}],  # llena el día
        hoy=date(2026, 9, 21), ahora=time(10, 0),
    )
    pedidos.cancelar_pedido(conexion, pedido["id"])
    conexion.commit()

    otro = pedidos.crear_pedido(
        conexion, "conv-2", [{"producto": "sello", "cantidad": 1}],
        hoy=date(2026, 9, 21), ahora=time(10, 0),
    )
    conexion.commit()

    assert otro["fecha_promesa"] == date(2026, 9, 21), "el cancelado ya no debería ocupar lugar"


# -- Cambios de estado -----------------------------------------------------------


def test_marcar_listo_y_despues_entregado(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    conexion.commit()

    listo = pedidos.marcar_listo(conexion, pedido["id"])
    assert listo["estado"] == "listo"
    assert listo["avisado_listo_en"] is None

    avisado = pedidos.registrar_aviso_enviado(conexion, pedido["id"])
    assert avisado["avisado_listo_en"] is not None

    entregado = pedidos.marcar_entregado(conexion, pedido["id"], monto_cobrado=6500)
    conexion.commit()

    assert entregado["estado"] == "entregado"
    assert entregado["estado_pago"] == "pagado"
    assert float(entregado["monto_cobrado"]) == 6500

    eventos = conexion.execute(
        "SELECT tipo FROM mundografico.eventos_pedido WHERE pedido_id = %s ORDER BY id",
        (pedido["id"],),
    ).fetchall()
    assert [e["tipo"] for e in eventos] == ["creado", "cambio_estado", "aviso_enviado", "cambio_estado"]


def test_marcar_listo_dos_veces_avisa(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    conexion.commit()

    pedidos.marcar_listo(conexion, pedido["id"])
    conexion.commit()

    with pytest.raises(ValueError):
        pedidos.marcar_listo(conexion, pedido["id"])


def test_aviso_solo_se_registra_una_vez_despues_del_envio(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    pedidos.marcar_listo(conexion, pedido["id"])
    assert pedidos.pedido_por_numero(conexion, pedido["numero"])["avisado_listo_en"] is None
    pedidos.registrar_aviso_enviado(conexion, pedido["id"])
    with pytest.raises(ValueError):
        pedidos.registrar_aviso_enviado(conexion, pedido["id"])


def test_entrega_parcial_no_se_marca_pagada(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    pedidos.marcar_listo(conexion, pedido["id"])
    entregado = pedidos.marcar_entregado(conexion, pedido["id"], monto_cobrado=1000)
    assert entregado["estado_pago"] == "señado"
    assert float(entregado["monto_cobrado"]) == 1000
    with pytest.raises(ValueError):
        pedidos.cancelar_pedido(conexion, pedido["id"])


def test_entrega_rechaza_monto_mayor_al_total(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    pedidos.marcar_listo(conexion, pedido["id"])
    with pytest.raises(ValueError, match="entre cero"):
        pedidos.marcar_entregado(conexion, pedido["id"], monto_cobrado=10000)


# -- Catálogo desde el panel ------------------------------------------------------


def test_producto_nuevo_guarda_escalas_como_array_json_no_como_objeto(conexion):
    """Sin Json() de por medio, psycopg adapta una lista de Python como
    ARRAY de Postgres, no como jsonb, y una lista vacía termina guardada
    como '{}' (objeto vacío) en vez de '[]' (array vacío) — no se nota
    hoy porque todo el código lee escalas con `or []`, pero un tramo de
    verdad ([{"desde": ...}]) con ese bug de vuelta directamente revienta
    al guardar."""
    producto = pedidos.crear_producto(conexion, {
        "nombre": "Imán de heladera", "precio_unitario": 500,
    })
    conexion.commit()

    tipo = conexion.execute(
        "SELECT jsonb_typeof(escalas) AS tipo FROM mundografico.productos WHERE id = %s",
        (producto["id"],),
    ).fetchone()["tipo"]

    assert tipo == "array"


def test_actualizar_producto_con_escalas_de_verdad_no_revienta(conexion):
    id_sello = id_de_producto(conexion, "Sello automático")

    actualizado = pedidos.actualizar_producto(conexion, id_sello, {
        "escalas": [{"desde": 10, "precio_unitario": 6000}],
    })
    conexion.commit()

    assert actualizado["escalas"] == [{"desde": 10, "precio_unitario": 6000}]


def test_actualizar_precio_sin_confirmar_mantiene_provisorio(conexion):
    id_sello = id_de_producto(conexion, "Sello automático")
    # La fixture confirma todo el catálogo para probar pedidos reales;
    # este caso necesita partir de un precio de ejemplo explícito.
    conexion.execute(
        "UPDATE mundografico.productos SET precio_provisorio = TRUE WHERE id = %s",
        (id_sello,),
    )

    actualizado = pedidos.actualizar_producto(conexion, id_sello, {"precio_unitario": 7000})
    conexion.commit()

    assert float(actualizado["precio_unitario"]) == 7000
    assert actualizado["precio_provisorio"] is True

    confirmado = pedidos.actualizar_producto(conexion, id_sello, {"precio_provisorio": False})
    assert confirmado["precio_provisorio"] is False


# -- Sheets: la cola de reintentos ------------------------------------------------


def test_pendientes_de_sheets_y_marcar_sincronizado(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    conexion.commit()

    pendientes = pedidos.pendientes_de_sheets(conexion)
    assert pedido["id"] in [p["id"] for p in pendientes]

    pedidos.marcar_sincronizado_con_sheets(conexion, pedido["id"])
    conexion.commit()

    pendientes = pedidos.pendientes_de_sheets(conexion)
    assert pedido["id"] not in [p["id"] for p in pendientes]


def test_sheets_no_borra_una_actualizacion_posterior(conexion):
    pedido = pedidos.crear_pedido(
        conexion, "conv-1", [{"producto": "sello", "cantidad": 1}], hoy=date(2026, 9, 21),
    )
    version_vieja = pedido["actualizado_en"]
    conexion.execute(
        "UPDATE mundografico.pedidos SET actualizado_en = actualizado_en + interval '1 second' "
        "WHERE id = %s",
        (pedido["id"],),
    )
    pedidos.marcar_sincronizado_con_sheets(conexion, pedido["id"], version_vieja)
    fila = pedidos.pedido_por_numero(conexion, pedido["numero"])
    assert fila["pendiente_sheets"] is True
