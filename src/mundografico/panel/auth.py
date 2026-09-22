"""Login del panel interno: HTTP Basic, un solo usuario compartido.

No es para exponer esto a cualquiera de internet sin más — pero alcanza:
el panel vive detrás del HTTPS que pone Coolify, y adentro de eso, un
usuario y una clave compartidos por el equipo es lo que corresponde a un
local con dos o tres personas atendiendo. El día que haga falta un login
por persona, esto es lo primero que se reemplaza.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from ..config import ConfigPanel

_seguridad = HTTPBasic()


def requerir_acceso(config: ConfigPanel):
    """Arma la dependencia de FastAPI que protege una ruta.

    Se arma una por config (no una global) para que los tests puedan
    probar con una clave de mentira sin tocar el .env.
    """

    def verificar(credenciales: HTTPBasicCredentials = Depends(_seguridad)) -> str:
        if not config.clave:
            # Fallar cerrado: mejor un panel que no entra nadie que uno
            # que, por un .env a medio completar, acepta cualquier clave
            # vacía como si fuera correcta.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="El panel no tiene PANEL_CLAVE configurada en el .env.",
            )

        usuario_ok = secrets.compare_digest(credenciales.username, config.usuario)
        clave_ok = secrets.compare_digest(credenciales.password, config.clave)

        if not (usuario_ok and clave_ok):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario o clave incorrectos.",
                headers={"WWW-Authenticate": "Basic"},
            )

        return credenciales.username

    return verificar
