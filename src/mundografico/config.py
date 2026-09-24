"""Configuración de Mundo Gráfico. Todo lo que el AgentKit no sabe que existe.

Sigue la misma idea que `agente/config.py`: todo sale del `.env`, nada de
credenciales en el código, y esta es la única puerta de lectura. No tocamos
el `Config` del kit para no pelearnos con upstream — este es un config
paralelo, propio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]

load_dotenv(RAIZ / ".env")

POLITICAS_DE_PAGO_VALIDAS = ("retiro", "sena_50", "adelantado_100")

class ErrorDeConfiguracion(Exception):
    """Falta algo en el .env o está mal puesto."""


@dataclass
class ConfigNegocio:
    """Datos del local: los usa el prompt, la agenda y el panel."""

    nombre: str = "Mundo Gráfico"
    direccion: str = "Laferrere"
    # Solo "retiro" puede automatizarse sin un verificador de pagos. Si se
    # elige una política con seña, la herramienta deriva el cierre al equipo.
    # OJO: prompts/sistema.md es texto plano y debe actualizarse también.
    politica_pago: str = "retiro"
    modo_demo: bool = False


@dataclass
class ConfigPanel:
    """Acceso al panel interno (`/panel`)."""

    usuario: str = "mundografico"
    clave: str = ""


@dataclass
class ConfigSheets:
    """Registro de ventas en Google Sheets. Opcional: si falta algo, se
    apaga solo y el resto del sistema sigue andando (ver sheets.py)."""

    id_hoja: str = ""
    credenciales_json: str = ""
    nombre_pestaña: str = "Ventas"

    @property
    def activo(self) -> bool:
        return bool(self.id_hoja and self.credenciales_json)


@dataclass
class Config:
    postgres_dsn: str
    negocio: ConfigNegocio = field(default_factory=ConfigNegocio)
    panel: ConfigPanel = field(default_factory=ConfigPanel)
    sheets: ConfigSheets = field(default_factory=ConfigSheets)

    @classmethod
    def desde_entorno(cls) -> "Config":
        dsn = (os.getenv("POSTGRES_DSN") or "").strip()
        if not dsn:
            raise ErrorDeConfiguracion(
                "Falta POSTGRES_DSN en el .env: Mundo Gráfico necesita "
                "Postgres para guardar el catálogo y los pedidos."
            )

        politica = (os.getenv("POLITICA_PAGO") or "retiro").strip().lower()
        if politica not in POLITICAS_DE_PAGO_VALIDAS:
            raise ErrorDeConfiguracion(
                f"POLITICA_PAGO tiene que ser una de: "
                f"{', '.join(POLITICAS_DE_PAGO_VALIDAS)}. Tenés '{politica}'."
            )

        return cls(
            postgres_dsn=dsn,
            negocio=ConfigNegocio(
                nombre=(os.getenv("MG_NOMBRE") or "Mundo Gráfico").strip(),
                direccion=(os.getenv("MG_DIRECCION") or "Laferrere").strip(),
                politica_pago=politica,
                modo_demo=(os.getenv("MG_MODO_DEMO") or "false").strip().lower() in ("1", "true", "si", "sí"),
            ),
            panel=ConfigPanel(
                usuario=(os.getenv("PANEL_USUARIO") or "mundografico").strip(),
                clave=(os.getenv("PANEL_CLAVE") or "").strip(),
            ),
            sheets=ConfigSheets(
                id_hoja=(os.getenv("GOOGLE_SHEETS_ID") or "").strip(),
                credenciales_json=(os.getenv("GOOGLE_CREDENCIALES_JSON") or "").strip(),
                nombre_pestaña=(os.getenv("GOOGLE_SHEETS_PESTAÑA") or "Ventas").strip(),
            ),
        )
