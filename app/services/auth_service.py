# app/services/auth_service.py
# CAPA SERVICIO - HU-02: inicio de sesión, renovación del token y cierre de sesión.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from app.core.config import settings
from app.core.respuestas import fecha_iso
from app.core.tokens import crear_token_acceso
from app.domain.excepciones import NoAutenticadoError
from app.domain.sesion import Sesion, nuevo_token_renovacion
from app.domain.usuario import ahora_utc_sin_zona
from app.repositories.sesion_repository import SesionRepository
from app.schemas.auth import LoginDatos, RenovarDatos, SesionResponse

# Mismo mensaje para correo inexistente y contraseña errada: no se revela cuál falló.
MENSAJE_CREDENCIALES = "Las credenciales enviadas no coinciden con ningún usuario activo."


class AuthService:

    def __init__(self, repo: SesionRepository):
        self.repo = repo  # inyección de dependencia

    def _respuesta(self, sesion: Sesion, token_renovacion: str) -> SesionResponse:
        usuario = sesion.usuario
        token, expira = crear_token_acceso(usuario.id, usuario.rol.nombre, sesion.id,
                                           sesion.version_sesion)
        return SesionResponse(usuario_id=str(usuario.id), nombre_completo=usuario.nombre_completo,
                              rol=usuario.rol.nombre, token_acceso=token,
                              token_renovacion=token_renovacion, expira_en=fecha_iso(expira))

    # ── Casos de uso ───────────────────────────────────────

    def iniciar_sesion(self, datos: LoginDatos) -> SesionResponse:
        """FUN: login con correo y contraseña (RN-003, RN-006, RN-007, RN-008)."""
        ahora = ahora_utc_sin_zona()
        usuario = self.repo.obtener_usuario_por_correo(datos.correo)
        if usuario is None:
            raise NoAutenticadoError(MENSAJE_CREDENCIALES, campo="contrasena")
        usuario.verificar_no_bloqueado(ahora)                                # RN-007
        if not usuario.verificar_contrasena(datos.contrasena):               # RN-003
            usuario.registrar_intento_fallido(ahora, settings.MAX_INTENTOS_FALLIDOS,
                                              settings.MINUTOS_BLOQUEO)      # RN-007
            self.repo.guardar(usuario)
            raise NoAutenticadoError(MENSAJE_CREDENCIALES, campo="contrasena")
        usuario.verificar_activo()                                           # RN-006
        usuario.registrar_ingreso_exitoso()
        token_renovacion = nuevo_token_renovacion()
        sesion = Sesion.abrir(usuario, token_renovacion, ahora, settings.DIAS_TOKEN_RENOVACION)
        self.repo.guardar(usuario, sesion)
        return self._respuesta(sesion, token_renovacion)

    def renovar(self, datos: RenovarDatos) -> SesionResponse:
        """Entrega un nuevo token de acceso y un nuevo token de renovación (RN-008)."""
        sesion = self.repo.obtener_por_token_renovacion(datos.token_renovacion)
        if sesion is None:
            raise NoAutenticadoError("El token de renovación no es válido.",
                                     campo="token_renovacion")
        nuevo = nuevo_token_renovacion()
        sesion.renovar(nuevo, ahora_utc_sin_zona(), settings.DIAS_TOKEN_RENOVACION)
        self.repo.guardar(sesion)
        return self._respuesta(sesion, nuevo)

    def cerrar_sesion(self, sesion_id: int) -> None:
        """Logout: cierra la sesión del token con el que se hizo la petición."""
        sesion = self.repo.obtener_sesion(sesion_id)
        if sesion is not None:
            sesion.cerrar()
            self.repo.guardar(sesion)
