"""El panel interno: `/panel/pedidos`, `/panel/catalogo`, `/panel/taller`.

`servidor_mundografico.py` monta `CARPETA_ESTATICOS` en el mismo FastAPI
que ya arma el kit para el webhook, y le agrega el router de acá — el
webhook de Chatwoot y el panel terminan siendo el mismo proceso y el mismo
puerto.
"""

from __future__ import annotations

from .rutas import CARPETA_ESTATICOS, crear_router

__all__ = ["CARPETA_ESTATICOS", "crear_router"]
