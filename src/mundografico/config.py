"""Configuración de Mundo Gráfico. Todo lo que el AgentKit no sabe que existe.

Sigue la misma idea que `agente/config.py`: todo sale del `.env`, nada de
credenciales en el código, y esta es la única puerta de lectura. No tocamos
el `Config` del kit para no pelearnos con upstream — este es un config
paralelo, propio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
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
    horario_apertura: time = time(9, 0)
    horario_cierre: time = time(18, 0)
    # Política de pago para tomar un pedido nuevo. Se cambia acá y en el
    # panel de Taller sin tocar el prompt: el prompt solo dice "seguí la
    # política vigente" y la herramienta crear_pedido aplica la de verdad.
    politica_pago: str = "retiro"


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
                horario_apertura=_hora("MG_HORARIO_APERTURA", time(9, 0)),
                horario_cierre=_hora("MG_HORARIO_CIERRE", time(18, 0)),
                politica_pago=politica,
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


def _hora(nombre: str, por_defecto: time) -> time:
    valor = (os.getenv(nombre) or "").strip()
    if not valor:
        return por_defecto
    try:
        partes = [int(p) for p in valor.split(":")]
        while len(partes) < 2:
            partes.append(0)
        return time(partes[0], partes[1])
    except (ValueError, IndexError):
        raise ErrorDeConfiguracion(
            f"{nombre} tiene que ser HH:MM, no '{valor}'."
        ) from None
