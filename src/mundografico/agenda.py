"""Cuándo puede estar listo un trabajo, según la carga real del taller.

Esta es la pieza que distingue a un bot que solo cotiza de uno que además
sabe organizar el taller: nunca promete algo para hoy si ya no hay minutos
libres hoy, y reparte los trabajos grandes entre los días que hagan falta.

Como `catalogo.py`, es lógica pura: recibe la configuración del taller y
cuánto hay ya comprometido por día (`pedidos.py` los lee de Postgres) y
devuelve una fecha, sin tocar la base. Así se prueba con fechas y números
de mentira, sin depender de qué día es hoy de verdad ni de tener Postgres
levantado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time, timedelta

# Tope de días hacia adelante que se recorren buscando lugar. Sin esto, una
# configuración rota (por ejemplo `dias_habiles` vacío) dejaría el cálculo
# buscando para siempre en vez de avisar que algo está mal puesto.
MAXIMO_DIAS_DE_BUSQUEDA = 180


@dataclass
class ResultadoAgenda:
    fecha_promesa: date
    # Cuántos minutos de ESTE trabajo caen en cada día. Sirve para explicar
    # un reparto ("hoy arrancamos, mañana lo terminamos") y es lo que
    # pedidos.py guarda en asignacion_agenda para que el próximo cálculo
    # sepa qué días ya están ocupados.
    minutos_por_dia: dict[date, int] = field(default_factory=dict)
    # El "desde" que se le pasó a proxima_fecha. Hace falta guardarlo para
    # poder contestar entra_hoy: con un solo día asignado, ese día es
    # siempre a la vez el mínimo y la fecha_promesa, así que comparar contra
    # fecha_promesa no alcanza para saber si ese día era hoy o ya era mañana.
    desde: date = None  # type: ignore[assignment]

    @property
    def entra_hoy(self) -> bool:
        return self.desde in self.minutos_por_dia

    @property
    def se_reparte_en_varios_dias(self) -> bool:
        return len(self.minutos_por_dia) > 1


def proxima_fecha(
    taller: dict,
    comprometido_por_dia: dict[date, int],
    minutos_necesarios: int,
    desde: date,
    ahora: time | None = None,
) -> ResultadoAgenda:
    """La fecha más temprana en la que este trabajo puede estar listo.

    `taller` trae `minutos_por_dia`, `dias_habiles` (1=lunes..7=domingo),
    `hora_corte_mismo_dia` y `feriados`.

    `comprometido_por_dia` es lo que ya está reservado en cada fecha por
    otros pedidos activos (suma de `asignacion_agenda`).

    `ahora`, si se pasa, es la hora actual: si ya se cruzó
    `hora_corte_mismo_dia`, el día de `desde` queda sin capacidad aunque
    tenga minutos libres — no porque no entre en el papel, sino porque ya
    no queda tiempo real de producirlo y tenerlo listo hoy.
    """
    if minutos_necesarios <= 0:
        raise ValueError("minutos_necesarios tiene que ser mayor a 0.")

    asignado: dict[date, int] = {}
    restante = minutos_necesarios
    dia = desde

    for indice in range(MAXIMO_DIAS_DE_BUSQUEDA):
        if _es_habil(dia, taller):
            capacidad = _capacidad_de(dia, taller, comprometido_por_dia)

            # El corte por hora solo puede afectar al primer día del
            # recorrido (hoy). A partir del segundo día siempre es mañana
            # como mínimo, así que la hora actual ya no importa.
            es_hoy = indice == 0
            if es_hoy and ahora is not None and ahora >= taller["hora_corte_mismo_dia"]:
                capacidad = 0

            usar = min(capacidad, restante)
            if usar > 0:
                asignado[dia] = usar
                restante -= usar

        if restante <= 0:
            break

        dia += timedelta(days=1)
    else:
        raise ValueError(
            f"No se pudo encontrar lugar para {minutos_necesarios} minutos "
            f"dentro de {MAXIMO_DIAS_DE_BUSQUEDA} días. Revisá la "
            f"configuración del taller (minutos por día, días hábiles)."
        )

    return ResultadoAgenda(fecha_promesa=max(asignado), minutos_por_dia=asignado, desde=desde)


def motivo_por_el_que_no_entra_hoy(
    taller: dict,
    comprometido_por_dia: dict[date, int],
    hoy: date,
    ahora: time | None = None,
) -> str | None:
    """Por qué un trabajo (de cualquier tamaño) no puede prometerse para
    hoy. Devuelve None si hoy todavía tiene lugar.

    Se usa para que el bot explique el motivo en vez de solo dar la fecha:
    no es lo mismo "hoy no abrimos" que "hoy ya está lleno de pedidos".
    """
    if not _es_habil(hoy, taller):
        return "hoy no es día de atención"

    if ahora is not None and ahora >= taller["hora_corte_mismo_dia"]:
        return (
            f"ya pasó el horario límite para comprometer entregas de hoy "
            f"({taller['hora_corte_mismo_dia'].strftime('%H:%M')})"
        )

    if _capacidad_de(hoy, taller, comprometido_por_dia) <= 0:
        return "hoy ya no queda lugar en el taller"

    return None


def _es_habil(dia: date, taller: dict) -> bool:
    if dia.isoweekday() not in taller["dias_habiles"]:
        return False
    if dia in (taller.get("feriados") or []):
        return False
    return True


def _capacidad_de(dia: date, taller: dict, comprometido_por_dia: dict[date, int]) -> int:
    usado = comprometido_por_dia.get(dia, 0)
    return max(0, taller["minutos_por_dia"] - usado)
