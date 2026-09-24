"""Los ejemplos reales se incorporan sin reiniciar el servidor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agente.prompts import leer_prompt  # noqa: E402


def test_lee_ejemplos_cambiados_en_caliente(tmp_path):
    sistema = tmp_path / "sistema.md"
    ejemplos = tmp_path / "ejemplos.md"
    sistema.write_text("Sos Mundo Gráfico", encoding="utf-8")
    ejemplos.write_text("Cliente: ¿Cuánto sale?", encoding="utf-8")
    assert "¿Cuánto sale?" in leer_prompt(sistema)
    ejemplos.write_text("Cliente: ¿Cuándo está listo?", encoding="utf-8")
    assert "¿Cuándo está listo?" in leer_prompt(sistema)
    assert "¿Cuánto sale?" not in leer_prompt(sistema)


def test_sin_ejemplos_sigue_leyendo_sistema(tmp_path):
    sistema = tmp_path / "sistema.md"
    sistema.write_text("Sos Mundo Gráfico", encoding="utf-8")
    assert leer_prompt(sistema) == "Sos Mundo Gráfico"
