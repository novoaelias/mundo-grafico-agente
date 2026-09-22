"""La hora de Laferrere, no la del servidor.

El VPS corre en UTC (es lo que trae Coolify por defecto). Si el corte por
horario de agenda.py comparara contra `datetime.now()` sin zona, un corte a
las 15:00 se evaluaría contra las 15:00 UTC — las 12:00 en Argentina — y el
bot dejaría de prometer entregas para "hoy" tres horas antes de lo que
tendría que ser. Todo lo que mire "qué hora es ahora" pasa por acá.

`tzdata` está en requirements.txt por las dudas: la imagen `python:slim` del
Dockerfile no siempre trae la base de husos horarios del sistema operativo,
y sin ella `ZoneInfo` no encuentra "America/Argentina/Buenos_Aires".
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

ZONA_LAFERRERE = ZoneInfo("America/Argentina/Buenos_Aires")

# `date.strftime("%A")` depende del locale del sistema operativo, y un
# contenedor Debian mínimo lo trae en inglés salvo que alguien instale y
# active el locale es_AR — un paso más para romperse en el servidor y no
# en la notebook de nadie. Más simple: los nombres a mano.
_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def ahora() -> datetime:
    return datetime.now(ZONA_LAFERRERE)


def hoy() -> date:
    return ahora().date()


def hora_actual() -> time:
    return ahora().time()


def formatear_fecha(fecha: date) -> str:
    """"lunes 21/09", en castellano siempre, sin depender del locale del SO."""
    return f"{_DIAS[fecha.weekday()]} {fecha.strftime('%d/%m')}"
