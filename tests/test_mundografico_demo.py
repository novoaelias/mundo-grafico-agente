"""El calendario ficticio debe seguir siendo útil después del primer deploy."""

from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mundografico.demo import dias_de_demo  # noqa: E402


def test_demo_salta_domingo_y_feriado():
    taller = {"dias_habiles": [1, 2, 3, 4, 5, 6], "feriados": [date(2026, 9, 28)]}
    assert dias_de_demo(taller, date(2026, 9, 27)) == [
        date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1),
    ]


def test_demo_empieza_hoy_si_abre():
    taller = {"dias_habiles": [1, 2, 3, 4, 5], "feriados": []}
    assert dias_de_demo(taller, date(2026, 9, 24))[0] == date(2026, 9, 24)
