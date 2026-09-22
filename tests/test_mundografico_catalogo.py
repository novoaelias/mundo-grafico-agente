"""Pruebas del catálogo: búsqueda y cotización. Sin Postgres ni red.

    pytest
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico.catalogo import buscar_producto, cotizar, normalizar  # noqa: E402

LONA = {
    "id": 1,
    "nombre": "Lona banner",
    "alias": ["lona", "banner", "cartel", "gigantografia"],
    "unidad": "m2",
    "precio_unitario": 4500,
    "cantidad_minima": 1,
    "escalas": [
        {"desde": 5, "precio_unitario": 4000},
        {"desde": 15, "precio_unitario": 3600},
    ],
    "minutos_preparacion": 20,
    "minutos_por_unidad": 8,
    "activo": True,
}

TARJETAS = {
    "id": 2,
    "nombre": "Tarjetas personales",
    "alias": ["tarjetas"],
    "unidad": "ciento",
    "precio_unitario": 3500,
    "cantidad_minima": 1,
    "escalas": [],
    "minutos_preparacion": 30,
    "minutos_por_unidad": 2,
    "activo": True,
}

SELLO_DE_BAJA = {
    "id": 3,
    "nombre": "Sello viejo",
    "alias": ["sello"],
    "unidad": "unidad",
    "precio_unitario": 1000,
    "cantidad_minima": 1,
    "escalas": [],
    "minutos_preparacion": 5,
    "minutos_por_unidad": 1,
    "activo": False,
}

CATALOGO = [LONA, TARJETAS, SELLO_DE_BAJA]


# -- normalizar ---------------------------------------------------------------


def test_normalizar_saca_acentos_y_pasa_a_minuscula():
    assert normalizar("Señalización") == "senalizacion"
    assert normalizar("  Lona  ") == "lona"


# -- buscar_producto ------------------------------------------------------------


def test_encuentra_por_nombre_exacto():
    encontrados = buscar_producto(CATALOGO, "Lona banner")
    assert encontrados[0]["id"] == 1


def test_encuentra_por_alias():
    encontrados = buscar_producto(CATALOGO, "banner")
    assert encontrados[0]["id"] == 1


def test_encuentra_por_alias_sin_acento():
    encontrados = buscar_producto(CATALOGO, "gigantografía")
    assert encontrados[0]["id"] == 1


def test_no_devuelve_productos_dados_de_baja():
    encontrados = buscar_producto(CATALOGO, "sello")
    assert encontrados == []


def test_algo_sin_relacion_no_encuentra_nada():
    encontrados = buscar_producto(CATALOGO, "servicio de catering")
    assert encontrados == []


def test_consulta_vacia_no_encuentra_nada():
    assert buscar_producto(CATALOGO, "") == []
    assert buscar_producto(CATALOGO, "   ") == []


def test_respeta_el_maximo_de_resultados():
    catalogo_repetido = [dict(LONA, id=i, nombre=f"Lona {i}") for i in range(5)]
    encontrados = buscar_producto(catalogo_repetido, "lona", maximo=2)
    assert len(encontrados) == 2


# -- cotizar --------------------------------------------------------------------


def test_cotiza_un_item_simple():
    resultado = cotizar(CATALOGO, [{"producto": "tarjetas", "cantidad": 3}])

    assert len(resultado.items) == 1
    item = resultado.items[0]
    assert item.producto_id == 2
    assert item.cantidad == 3
    assert item.precio_unitario == 3500
    assert item.subtotal == 10500
    assert resultado.total == 10500


def test_aplica_la_escala_que_corresponde():
    # 10 m2 de lona: entra en la escala "desde 5", no en la de "desde 15".
    resultado = cotizar(CATALOGO, [{"producto": "lona", "cantidad": 10}])

    item = resultado.items[0]
    assert item.precio_unitario == 4000
    assert item.subtotal == 40000


def test_aplica_la_escala_mas_alta_que_alcanza():
    resultado = cotizar(CATALOGO, [{"producto": "lona", "cantidad": 20}])

    assert resultado.items[0].precio_unitario == 3600


def test_sin_escala_alcanzada_usa_precio_de_lista():
    resultado = cotizar(CATALOGO, [{"producto": "lona", "cantidad": 2}])

    assert resultado.items[0].precio_unitario == 4500


def test_cantidad_menor_a_la_minima_se_cobra_la_minima_y_avisa():
    catalogo = [dict(TARJETAS, cantidad_minima=50)]
    resultado = cotizar(catalogo, [{"producto": "tarjetas", "cantidad": 10}])

    item = resultado.items[0]
    assert item.cantidad == 50
    assert "mínima" in item.aviso
    assert item.subtotal == 50 * 3500


def test_varios_items_se_suman():
    resultado = cotizar(
        CATALOGO,
        [
            {"producto": "lona", "cantidad": 2},
            {"producto": "tarjetas", "cantidad": 1},
        ],
    )

    assert len(resultado.items) == 2
    assert resultado.total == (2 * 4500) + (1 * 3500)


def test_calcula_los_minutos_totales():
    resultado = cotizar(CATALOGO, [{"producto": "lona", "cantidad": 2}])
    # 20 de preparación + 8 por m2 * 2 = 36
    assert resultado.items[0].minutos == 36
    assert resultado.minutos_totales == 36


def test_producto_no_encontrado_no_rompe_ni_inventa_precio():
    resultado = cotizar(CATALOGO, [{"producto": "helicóptero a medida", "cantidad": 1}])

    assert resultado.items == []
    assert resultado.no_encontrados == ["helicóptero a medida"]
    assert resultado.total == 0


def test_mezcla_encontrados_y_no_encontrados():
    resultado = cotizar(
        CATALOGO,
        [
            {"producto": "lona", "cantidad": 1},
            {"producto": "algo raro", "cantidad": 1},
        ],
    )

    assert len(resultado.items) == 1
    assert resultado.no_encontrados == ["algo raro"]


def test_item_sin_cantidad_o_sin_nombre_se_ignora():
    resultado = cotizar(
        CATALOGO,
        [
            {"producto": "", "cantidad": 5},
            {"producto": "lona", "cantidad": 0},
            {"producto": "lona", "cantidad": -3},
        ],
    )

    assert resultado.items == []
    assert resultado.no_encontrados == []


def test_el_texto_incluye_el_total_y_los_no_encontrados():
    resultado = cotizar(
        CATALOGO,
        [
            {"producto": "tarjetas", "cantidad": 1},
            {"producto": "algo raro", "cantidad": 1},
        ],
    )

    texto = resultado.texto()
    assert "Tarjetas personales" in texto
    assert "Total: $3.500" in texto
    assert "No encontré 'algo raro'" in texto


def test_cotizacion_vacia_lo_dice():
    from mundografico.catalogo import Cotizacion

    assert Cotizacion().texto() == "No hay nada para cotizar."
