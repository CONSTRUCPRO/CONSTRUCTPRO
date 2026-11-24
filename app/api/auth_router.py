# app/api/auth_router.py
# CAPA API - HU-02 Autenticación con Token.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, obtener_usuario_actual
from app.repositories.sesion_repository import SesionRepository
from app.schemas.auth import LoginDatos, RenovarDatos, SesionResponse
from app.schemas.respuesta import Respuesta
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Autenticación"])


def obtener_servicio(db: Session = Depends(get_db)) -> AuthService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return AuthService(SesionRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str] = None) -> dict:
    """
    Arma un ejemplo de respuesta de error con el sobre estándar, solo para la documentación de
    Swagger (parámetro `responses=` de cada endpoint). No se usa al responder de verdad.
    """
    return {
        "description": descripcion,
        "content": {"application/json": {"example": {
            "exito": False,
            "codigo": codigo,
            "mensaje": mensaje_general,
            "datos": None,
            "errores": [{"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}],
            "meta": {"timestamp": "2026-10-21T15:04:32Z", "version": "v1",
                     "peticion_id": "9f3c1a7e-52b1-4c0d-9a77-1b2e6d4f8a10", "paginacion": None},
        }}},
    }


ERROR_401_CREDENCIALES = _ejemplo_error(
    "Correo o contraseña incorrectos, cuenta inactiva (AUT_USUARIO_INACTIVO, RN-006) o "
    "bloqueada por 5 intentos fallidos (RN-007)",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    "contrasena", "Las credenciales enviadas no coinciden con ningún usuario activo.")
ERROR_401_RENOVACION = _ejemplo_error(
    "Token de renovación inválido, vencido o de una sesión cerrada",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    "token_renovacion", "El token de renovación no es válido.")
ERROR_401_TOKEN = _ejemplo_error(
    "Sin token, token vencido o sesión cerrada",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    "Authorization", "Debe iniciar sesión y enviar el token en el encabezado "
                     "Authorization: Bearer <token>.")


# ── Endpoints ────────────────────────────────────────────────

@router.post("/login", response_model=Respuesta[SesionResponse],
             summary="Iniciar sesión",
             description="Valida correo y contraseña y entrega un **token de acceso** (JWT, vence en "
                         "`expira_en`, RN-008) y un **token de renovación**. Un usuario inactivo no "
                         "puede entrar (RN-006) y la cuenta se bloquea temporalmente tras 5 intentos "
                         "fallidos seguidos (RN-007). Nunca devuelve la contraseña (RN-003).\n\n"
                         "En Swagger: copie `token_acceso`, pulse **Authorize** (candado) y péguelo.",
             responses={401: ERROR_401_CREDENCIALES})
def iniciar_sesion(datos: LoginDatos, servicio: AuthService = Depends(obtener_servicio)):
    """POST /api/v1/auth/login: valida credenciales y entrega los tokens (no pide token)."""
    return respuesta_exitosa(servicio.iniciar_sesion(datos), "Inicio de sesión exitoso.")


@router.post("/refresh", response_model=Respuesta[SesionResponse],
             summary="Renovar el token",
             description="Con el `token_renovacion` del login entrega un nuevo token de acceso con nueva "
                         "fecha de vencimiento y un nuevo token de renovación (el anterior deja de "
                         "servir). No exige el encabezado Authorization, para poder renovar aunque el "
                         "token de acceso ya haya vencido.",
             responses={401: ERROR_401_RENOVACION})
def renovar(datos: RenovarDatos, servicio: AuthService = Depends(obtener_servicio)):
    """POST /api/v1/auth/refresh: nuevos tokens a partir del token de renovación."""
    return respuesta_exitosa(servicio.renovar(datos), "Token renovado correctamente.")


@router.post("/logout", response_model=Respuesta[None],
             summary="Cerrar sesión",
             description="Cierra la sesión del token enviado: desde ese momento el token de acceso y el "
                         "de renovación dejan de funcionar (tabla `sesiones`).",
             responses={401: ERROR_401_TOKEN})
def cerrar_sesion(servicio: AuthService = Depends(obtener_servicio),
                  usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    """POST /api/v1/auth/logout: cierra la sesión del token con el que se llama."""
    servicio.cerrar_sesion(usuario.sesion_id)
    return respuesta_exitosa(None, "Sesión cerrada correctamente.")
