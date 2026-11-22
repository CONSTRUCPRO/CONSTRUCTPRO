"""
Tokens de acceso (JWT) de ConstruPro - HU-02.

No importa FastAPI, así lo pueden usar tanto el servicio (al crear el token en el
login) como app/core/seguridad.py (al validarlo en cada petición).

El token lleva (RN-008):
    sub   -> usuario_id (texto)
    rol   -> nombre del rol al momento de iniciar sesión (solo informativo; en cada
             petición se usa el rol VIGENTE de la BD, RN-010)
    sid   -> id de la sesión (tabla sesiones), para poder invalidarlo con logout
    ver   -> version_sesion del usuario (RN-009)
    exp   -> fecha de vencimiento
    jti   -> identificador único del token (cada token renovado es distinto)
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.domain.excepciones import NoAutenticadoError

ALGORITMO = "HS256"


def crear_token_acceso(usuario_id: int, rol: str, sesion_id: int,
                       version_sesion: int) -> tuple[str, datetime]:
    """Devuelve (token, fecha de vencimiento en UTC)."""
    ahora = datetime.now(timezone.utc)
    expira = ahora + timedelta(minutes=settings.JWT_MINUTOS_ACCESO)
    carga = {"sub": str(usuario_id), "rol": rol, "sid": sesion_id, "ver": version_sesion,
             "iat": ahora, "exp": expira, "jti": uuid.uuid4().hex}
    return jwt.encode(carga, settings.JWT_SECRETO, algorithm=ALGORITMO), expira


def leer_token_acceso(token: str) -> dict:
    """Valida la firma y la vigencia del token. Si falla, 401."""
    try:
        return jwt.decode(token, settings.JWT_SECRETO, algorithms=[ALGORITMO],
                          options={"require": ["sub", "sid", "ver", "exp"]})
    except jwt.ExpiredSignatureError:
        raise NoAutenticadoError(
            "El token de acceso venció; renuévelo con POST /api/v1/auth/refresh.",
            campo="Authorization", regla="RN-008")
    except jwt.InvalidTokenError:
        raise NoAutenticadoError("El token de acceso no es válido.", campo="Authorization")
