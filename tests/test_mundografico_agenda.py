"""Pruebas de la agenda: cuándo puede estar listo un trabajo. Sin Postgres.

    pytest
"""

from __future__ import annotations

import sys
from datetime import date, time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico.agenda import (  # noqa: E402
    motivo_por_el_que_no_entra_hoy,
    proxima_fecha,
)

# Lunes 21/09/2026, para que las cuentas de "día hábil" no dependan de qué
# día sea hoy de verdad al correr los tests.
LUNES = date(2026, 9, 21)
MARTES = date(2026, 9, 22)
MIERCOLES = date(2026, 9, 23)
SABADO = date(2026, 9, 26)
DOMINGO = date(2026, 9, 27)
LUNES_SIGUIENTE = date(2026, 9, 28)

TALLER = {
    "minutos_por_dia": 300,
    "dias_habiles": [1, 2, 3, 4, 5, 6],  # lunes a sábado
    "hora_corte_mismo_dia": time(15, 0),
    "feriados": [],
}


def taller(**cambios) -> dict:
    return {**TALLER, **cambios}


# -- El caso simple -------------------------------------------------------------


def test_un_trabajo_chico_entra_hoy_si_hay_lugar_y_no_paso_la_hora():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=60,
        desde=LUNES, ahora=time(10, 0),
    )

    assert resultado.fecha_promesa == LUNES
    assert resultado.entra_hoy is True
    assert resultado.minutos_por_dia == {LUNES: 60}


def test_sin_hora_no_hay_corte_por_horario():
    """Para tests o para el modo "cotizar sin comprometerse todavía"."""
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=60,
        desde=LUNES, ahora=None,
    )
    assert resultado.entra_hoy is True


# -- El corte por horario ---------------------------------------------------------


def test_pasada_la_hora_de_corte_no_promete_para_hoy():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=60,
        desde=LUNES, ahora=time(16, 0),
    )

    assert resultado.fecha_promesa == MARTES
    assert resultado.entra_hoy is False


def test_justo_en_la_hora_de_corte_ya_no_entra():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=60,
        desde=LUNES, ahora=time(15, 0),
    )
    assert resultado.fecha_promesa == MARTES


def test_el_corte_no_afecta_al_segundo_dia():
    """El corte de "hoy" no tiene que arrastrarse a mañana."""
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={LUNES: 300}, minutos_necesarios=100,
        desde=LUNES, ahora=time(16, 0),  # ya pasó el corte Y además hoy está lleno
    )
    assert resultado.fecha_promesa == MARTES
    assert resultado.minutos_por_dia == {MARTES: 100}


# -- Días no hábiles y feriados -----------------------------------------------------


def test_salta_el_fin_de_semana():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=60,
        desde=DOMINGO, ahora=None,
    )
    assert resultado.fecha_promesa == LUNES_SIGUIENTE


def test_respeta_dias_habiles_configurados():
    """Un taller que no abre los sábados."""
    solo_semana = taller(dias_habiles=[1, 2, 3, 4, 5])
    resultado = proxima_fecha(
        solo_semana, comprometido_por_dia={}, minutos_necesarios=60,
        desde=SABADO, ahora=None,
    )
    assert resultado.fecha_promesa == LUNES_SIGUIENTE


def test_salta_un_feriado():
    con_feriado = taller(feriados=[MARTES])
    resultado = proxima_fecha(
        con_feriado, comprometido_por_dia={}, minutos_necesarios=60,
        desde=LUNES, ahora=time(16, 0),  # hoy (lunes) ya no cuenta por el corte
    )
    assert resultado.fecha_promesa == MIERCOLES, "el martes es feriado, tiene que saltarlo"


# -- Carga ya comprometida ------------------------------------------------------------


def test_si_hoy_esta_lleno_pasa_al_dia_siguiente():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={LUNES: 300}, minutos_necesarios=60,
        desde=LUNES, ahora=time(10, 0),
    )
    assert resultado.fecha_promesa == MARTES


def test_usa_el_lugar_que_queda_libre_en_el_dia():
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={LUNES: 250}, minutos_necesarios=40,
        desde=LUNES, ahora=time(10, 0),
    )
    assert resultado.fecha_promesa == LUNES
    assert resultado.minutos_por_dia == {LUNES: 40}


def test_un_trabajo_grande_se_reparte_entre_varios_dias():
    # 300 libres hoy, necesita 700: hoy 300, mañana 300, pasado 100.
    resultado = proxima_fecha(
        TALLER, comprometido_por_dia={}, minutos_necesarios=700,
        desde=LUNES, ahora=time(10, 0),
    )

    assert resultado.fecha_promesa == MIERCOLES
    assert resultado.minutos_por_dia == {LUNES: 300, MARTES: 300, MIERCOLES: 100}
    assert resultado.se_reparte_en_varios_dias is True


def test_el_reparto_respeta_lo_ya_comprometido_de_cada_dia():
    resultado = proxima_fecha(
        TALLER,
        comprometido_por_dia={LUNES: 280, MARTES: 100},
        minutos_necesarios=250,
        desde=LUNES,
        ahora=time(10, 0),
    )
    # Lunes quedan 20, martes quedan 200: 20 + 200 = 220, faltan 30 más el miércoles.
    assert resultado.minutos_por_dia == {LUNES: 20, MARTES: 200, MIERCOLES: 30}
    assert resultado.fecha_promesa == MIERCOLES


def test_minutos_en_cero_o_negativos_es_un_error():
    with pytest.raises(ValueError):
        proxima_fecha(TALLER, {}, 0, LUNES)
    with pytest.raises(ValueError):
        proxima_fecha(TALLER, {}, -10, LUNES)


# -- El motivo para explicarle a la persona -----------------------------------------


def test_motivo_cuando_ya_paso_la_hora():
    motivo = motivo_por_el_que_no_entra_hoy(TALLER, {}, LUNES, ahora=time(16, 0))
    assert "horario" in motivo


def test_motivo_cuando_esta_lleno():
    motivo = motivo_por_el_que_no_entra_hoy(
        TALLER, {LUNES: 300}, LUNES, ahora=time(10, 0)
    )
    assert "lugar" in motivo


def test_motivo_cuando_no_es_dia_habil():
    motivo = motivo_por_el_que_no_entra_hoy(TALLER, {}, DOMINGO, ahora=time(10, 0))
    assert "día de atención" in motivo


def test_sin_motivo_cuando_hoy_entra():
    motivo = motivo_por_el_que_no_entra_hoy(TALLER, {}, LUNES, ahora=time(10, 0))
    assert motivo is None
