"""Carga del prompt del sistema desde un archivo de texto.

El prompt vive en prompts/sistema.md, no adentro del código. Dos motivos:
lo podés editar sin tocar Python, y se relee en cada mensaje — o sea que
cambiás la personalidad del agente con el agente andando.
"""

from __future__ import annotations

from pathlib import Path

PROMPT_DE_EMERGENCIA = (
    "Sos un asistente útil. Respondé en español, de forma clara y directa."
)


def leer_prompt(ruta: Path) -> str:
    """Lee el sistema y, si existe, suma ejemplos de diálogo editables."""
    try:
        texto = ruta.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return PROMPT_DE_EMERGENCIA

    texto = texto or PROMPT_DE_EMERGENCIA
    ejemplos = ruta.with_name("ejemplos.md")
    if ejemplos.is_file():
        contenido = ejemplos.read_text(encoding="utf-8").strip()
        if contenido:
            texto += "\n\n" + contenido
    return texto


def guardar_prompt(ruta: Path, texto: str) -> None:
    """Guarda el prompt del sistema (lo usa el editor de la plataforma web)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto.strip() + "\n", encoding="utf-8")
