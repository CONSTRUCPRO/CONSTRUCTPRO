"""
Identificación del usuario que hace la petición (HU-02 - Autenticación con Token).

Toda petición a un endpoint protegido debe enviar el encabezado
    Authorization: Bearer <token_acceso>
que se obtiene con POST /api/v1/auth/login. En Swagger (/docs) se usa el botón
"Authorize" (candado) y se pega solo el token, sin la palabra Bearer.

En cada petición se valida (si algo falla, 401):
    - que el token exista, tenga firma válida y no haya vencido (RN-008),
    - que su sesión siga activa (logout la cierra),
    - que el usuario siga activo (RN-006) y no se haya invalidado su sesión (RN-009),
    - y se toma el rol VIGENTE del usuario en la BD, no el del token (RN-010).

Uso en un router (no cambió respecto al encabezado temporal X-Rol):
    usuario: UsuarioActual = Depends(obtener_usuario_actual)        # cualquier usuario
    usuario: UsuarioActual = Depends(requiere_rol("Administrador",  # solo esos roles
                                                  regla="RN-014"))
    usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "crear"))
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tokens import leer_token_acceso
from app.domain.excepciones import NoAutenticadoError, PermisoDenegadoError

# auto_error=False: si falta el token, respondemos nosotros con el sobre estándar (401).
esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token de acceso de POST /api/v1/auth/login (pegue solo el token).",
)


@dataclass
class UsuarioActual:
    """
    Quién está haciendo la petición, según su token: id, rol vigente y sesión.

    Los routers lo reciben con Depends(...) y se lo pasan al servicio cuando la regla lo
    necesita (por ejemplo, RN-004: nadie se inactiva a sí mismo; RN-073: segregación).
    """

    usuario_id: Optional[str]
    rol: str
    sesion_id: Optional[int] = None


def obtener_usuario_actual(
    credenciales: Optional[HTTPAuthorizationCredentials] = Depends(esquema_bearer),
    db: Session = Depends(get_db),
) -> UsuarioActual:
    """
    Dependencia que protege los endpoints: valida el token y devuelve el UsuarioActual.

    Pasos (si alguno falla, 401):
      1. Que venga el encabezado Authorization: Bearer <token>.
      2. Que el token tenga firma válida y no haya vencido (RN-008).
      3. Que su sesión exista y pertenezca a ese usuario.
      4. Que el usuario siga activo (RN-006) y la sesión siga abierta y vigente (logout, RN-009).
    El rol se toma de la BD en este momento, no del token (RN-010).
    """
    # Import local: evita importar los modelos al cargar este módulo.
    from app.domain.sesion import Sesion

    if credenciales is None or not credenciales.credentials:
        raise NoAutenticadoError(
            "Debe iniciar sesión y enviar el token en el encabezado Authorization: Bearer <token>.",
            campo="Authorization")
    carga = leer_token_acceso(credenciales.credentials)                     # firma y RN-008

    sesion = db.get(Sesion, carga["sid"])
    if sesion is None or str(sesion.usuario_id) != str(carga["sub"]):
        raise NoAutenticadoError("El token de acceso no es válido.", campo="Authorization")
    usuario = sesion.usuario
    usuario.verificar_activo()                                              # RN-006
    sesion.verificar_vigente()                                              # logout y RN-009
    if carga["ver"] != (usuario.version_sesion or 0):                       # RN-009
        raise NoAutenticadoError("La sesión fue invalidada; inicie sesión nuevamente.",
                                 regla="RN-009")
    # RN-010: se usa el rol vigente del usuario, no el que tenía al iniciar sesión.
    return UsuarioActual(usuario_id=str(usuario.id), rol=usuario.rol.nombre, sesion_id=sesion.id)


def requiere_rol(*roles_permitidos: str, regla: Optional[str] = None):
    """Crea una dependencia que solo deja pasar a los roles indicados (si no, 403)."""
    permitidos = {r.capitalize() for r in roles_permitidos}

    def verificador(usuario: UsuarioActual = Depends(obtener_usuario_actual)) -> UsuarioActual:
        """Deja pasar solo si el rol del usuario está entre los permitidos; si no, 403."""
        if usuario.rol.capitalize() not in permitidos:
            raise PermisoDenegadoError(
                f"El rol {usuario.rol} no puede realizar esta operación.", regla=regla
            )
        return usuario

    return verificador


def requiere_permiso(modulo: str, accion: str):
    """
    HU-03 / FUN-009: deja pasar solo si el rol del usuario tiene el permiso
    (modulo, accion) registrado en la tabla permisos_rol. Si no, 403 AUT_SIN_PERMISO.

    Uso en un router:
        usuario: UsuarioActual = Depends(requiere_permiso("Solicitudes", "crear"))
    """
    # Importes locales para no crear dependencias circulares al arrancar la app.
    from app.repositories.rol_repository import RolRepository
    from app.services.rol_service import RolService

    def verificador(usuario: UsuarioActual = Depends(obtener_usuario_actual),
                    db: Session = Depends(get_db)) -> UsuarioActual:
        """
        Deja pasar solo si el rol del usuario tiene el permiso (módulo, acción) en la tabla
        permisos_rol de la HU-03; si no, 403 AUT_SIN_PERMISO.
        """
        if not RolService(RolRepository(db)).rol_tiene_permiso(usuario.rol, modulo, accion):
            raise PermisoDenegadoError(
                f"El rol {usuario.rol} no tiene permiso para '{accion}' en el módulo {modulo}."
            )
        return usuario

    return verificador
