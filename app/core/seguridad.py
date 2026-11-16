"""
Identificación del usuario que hace la petición.

TEMPORAL (hasta la HU-02 - Autenticación con Token):
    El usuario se "simula" con encabezados que se llenan en Swagger (/docs):
        X-Rol:        Administrador | Coordinador | Director | Empleado
        X-Usuario-Id: (opcional) id del usuario, ej. 12
    Cuando exista la HU-02, SOLO cambia el interior de `obtener_usuario_actual`
    (leerá el token JWT del encabezado Authorization). Los endpoints no se tocan.

Uso en un router:
    usuario: UsuarioActual = Depends(obtener_usuario_actual)        # cualquier usuario
    usuario: UsuarioActual = Depends(requiere_rol("Administrador",  # solo esos roles
                                                  regla="RN-014"))
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header

from app.domain.excepciones import NoAutenticadoError, PermisoDenegadoError


@dataclass
class UsuarioActual:
    usuario_id: Optional[str]
    rol: str


def obtener_usuario_actual(
    x_rol: Optional[str] = Header(
        default=None,
        description="TEMPORAL hasta la HU-02: rol del usuario (Administrador, Coordinador, Director, Empleado).",
    ),
    x_usuario_id: Optional[str] = Header(
        default=None,
        description="TEMPORAL hasta la HU-02: id del usuario que hace la petición.",
    ),
) -> UsuarioActual:
    if not x_rol or not x_rol.strip():
        raise NoAutenticadoError(
            "Debe identificarse para usar este servicio (encabezado X-Rol, temporal hasta la HU-02)."
        )
    return UsuarioActual(usuario_id=x_usuario_id, rol=x_rol.strip().capitalize())


def requiere_rol(*roles_permitidos: str, regla: Optional[str] = None):
    """Crea una dependencia que solo deja pasar a los roles indicados (si no, 403)."""
    permitidos = {r.capitalize() for r in roles_permitidos}

    def verificador(usuario: UsuarioActual = Depends(obtener_usuario_actual)) -> UsuarioActual:
        if usuario.rol not in permitidos:
            raise PermisoDenegadoError(
                f"El rol {usuario.rol} no puede realizar esta operación.", regla=regla
            )
        return usuario

    return verificador
