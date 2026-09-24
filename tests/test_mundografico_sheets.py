"""Pruebas de la sincronización con Google Sheets. Sin salir a internet:
se monkeypatchea `sheets._abrir_hoja` para devolver una hoja de mentira.

    pytest
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico import pedidos as datos  # noqa: E402
from mundografico import sheets  # noqa: E402
from mundografico.config import ConfigSheets  # noqa: E402

CONFIG_ACTIVA = ConfigSheets(id_hoja="hoja-123", credenciales_json='{"x": 1}')
CONFIG_APAGADA = ConfigSheets()  # sin id_hoja ni credenciales: activo == False

PEDIDO = {
    "id": 1, "numero": "MG-0001",
    "detalle": [{"nombre": "Lona banner", "cantidad": 2, "unidad": "m2"}],
    "total": 9000, "estado": "pendiente", "estado_pago": "a_cobrar",
    "monto_cobrado": None, "cliente_nombre": "Marisa", "cliente_telefono": "",
    "creado_en": datetime(2026, 9, 22, 10, 30), "fecha_promesa": date(2026, 9, 22),
}


class CeldaFalsa:
    def __init__(self, fila):
        self.row = fila


class HojaFalsa:
    def __init__(self, celda_existente=None):
        self._celda_existente = celda_existente
        self.actualizaciones: list[tuple[list, str]] = []
        self.agregados: list[list] = []
        self.consultas = []

    def find(self, query, in_column=1):
        self.consultas.append(query)
        return self._celda_existente

    def update(self, values, range_name):
        self.actualizaciones.append((values, range_name))

    def append_row(self, fila):
        self.agregados.append(fila)


def test_config_apagada_no_hace_nada(monkeypatch):
    llamado = []
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: llamado.append(1))

    assert sheets.sincronizar_pedido(CONFIG_APAGADA, PEDIDO) is False
    assert llamado == []


def test_pedido_nuevo_se_agrega(monkeypatch):
    hoja = HojaFalsa(celda_existente=None)
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: hoja)

    assert sheets.sincronizar_pedido(CONFIG_ACTIVA, PEDIDO) is True
    assert len(hoja.agregados) == 1
    fila = hoja.agregados[0]
    assert fila[0] == "MG-0001"
    assert fila[2] == "Marisa"
    assert fila[5] == 9000.0
    assert "Lona banner" in fila[4]
    assert hoja.consultas[0].search("MG-00010") is None
    assert hoja.consultas[0].search("MG-0001") is not None


def test_pedido_existente_se_actualiza_en_su_fila(monkeypatch):
    hoja = HojaFalsa(celda_existente=CeldaFalsa(fila=7))
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: hoja)

    assert sheets.sincronizar_pedido(CONFIG_ACTIVA, PEDIDO) is True
    assert hoja.agregados == []
    assert len(hoja.actualizaciones) == 1
    _valores, rango = hoja.actualizaciones[0]
    assert rango.startswith("A7:")
    assert rango.endswith("7")


def test_monto_cobrado_vacio_se_manda_como_string_vacio(monkeypatch):
    hoja = HojaFalsa()
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: hoja)

    sheets.sincronizar_pedido(CONFIG_ACTIVA, PEDIDO)

    assert hoja.agregados[0][8] == ""


def test_monto_cobrado_presente_se_castea_a_float(monkeypatch):
    hoja = HojaFalsa()
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: hoja)

    sheets.sincronizar_pedido(CONFIG_ACTIVA, {**PEDIDO, "monto_cobrado": 8500})

    assert hoja.agregados[0][8] == 8500.0


def test_un_error_de_la_api_no_revienta_y_devuelve_false(monkeypatch):
    def explota(config):
        raise ConnectionError("Google no contesta")

    monkeypatch.setattr(sheets, "_abrir_hoja", explota)

    assert sheets.sincronizar_pedido(CONFIG_ACTIVA, PEDIDO) is False


def test_columna_entregado_solo_si_esta_entregado(monkeypatch):
    hoja = HojaFalsa()
    monkeypatch.setattr(sheets, "_abrir_hoja", lambda config: hoja)

    sheets.sincronizar_pedido(CONFIG_ACTIVA, {**PEDIDO, "estado": "entregado"})

    assert hoja.agregados[0][-1] == "sí"


# -- sincronizar_pendientes ----------------------------------------------------


def test_sincronizar_pendientes_marca_los_que_salieron_bien(monkeypatch):
    pendientes = [{**PEDIDO, "id": 1, "numero": "MG-0001"}, {**PEDIDO, "id": 2, "numero": "MG-0002"}]
    marcados = []
    conexiones_activas = [0]

    class PoolFalso:
        @contextmanager
        def connection(self):
            conexiones_activas[0] += 1
            try:
                yield object()
            finally:
                conexiones_activas[0] -= 1

    monkeypatch.setattr(datos, "pendientes_de_sheets", lambda conexion: pendientes)
    monkeypatch.setattr(datos, "marcar_sincronizado_con_sheets", lambda conexion, pedido_id, actualizado_en=None: marcados.append(pedido_id))
    def sincronizar_sin_transaccion(config, pedido):
        assert conexiones_activas[0] == 0
        return pedido["numero"] == "MG-0001"

    monkeypatch.setattr(sheets, "sincronizar_pedido", sincronizar_sin_transaccion)

    cantidad = sheets.sincronizar_pendientes(CONFIG_ACTIVA, PoolFalso())

    assert cantidad == 1
    assert marcados == [1]


def test_sincronizar_pendientes_con_config_apagada_no_consulta_la_base(monkeypatch):
    consultado = []
    monkeypatch.setattr(datos, "pendientes_de_sheets", lambda conexion: consultado.append(1))

    cantidad = sheets.sincronizar_pendientes(CONFIG_APAGADA, pool=None)

    assert cantidad == 0
    assert consultado == []
