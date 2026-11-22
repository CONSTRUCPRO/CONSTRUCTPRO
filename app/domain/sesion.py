# app/domain/sesion.py
# CAPA DOMINIO - HU-02 Autenticación con Token (MOD-01).
# Entidad Sesion (tabla sesiones): una por cada inicio de sesión.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
#
# Cómo funciona:
#   - Al iniciar sesión se crea una Sesion "activa" con un token de renovación.
#     En la BD se guarda solo el HASH (SHA-256) de ese token, nunca el token.
#   - El token de acceso (JWT) lleva el id de la sesión; en cada petición se revisa
#     que la sesión siga activa. Cerrar sesión (logout) la deja "cerrada" y así el
#     token queda invalidado aunque todavía no haya vencido.
#   - RN-008: el token de acceso vence (JWT_MINUTOS_ACCESO) y se renueva con el de renovación.
#   - RN-009: la sesión guarda la version_sesion del usuario; si el usuario se inactiva,
#     su versión sube y todas sus sesiones anteriores dejan de servir.
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import NoAutenticadoError
from app.domain.usuario import Usuario

ESTADO_ACTIVA = "activa"
ESTADO_CERRADA = "cerrada"


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    """SHA-256 del token de renovación: es lo único que se guarda en la BD."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def nuevo_token_renovacion() -> str:
    """Token aleatorio y difícil de adivinar."""
    return secrets.token_urlsafe(32)


class Sesion(Base):
    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    token_renovacion_hash: Mapped[str] = mapped_column(String(64), unique=True)
    version_sesion: Mapped[int] = mapped_column(Integer)                 # RN-009
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVA)
    expira_renovacion: Mapped[datetime] = mapped_column(DateTime)       # UTC sin zona
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_cierre: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    usuario: Mapped[Usuario] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    @classmethod
    def abrir(cls, usuario: Usuario, token_renovacion: str, ahora: datetime,
              dias_renovacion: int) -> "Sesion":
        """Crea la sesión al iniciar sesión."""
        return cls(usuario=usuario, token_renovacion_hash=hash_token(token_renovacion),
                   version_sesion=usuario.version_sesion or 0, estado=ESTADO_ACTIVA,
                   expira_renovacion=ahora + timedelta(days=dias_renovacion))

    def verificar_vigente(self) -> None:
        """La sesión debe estar activa y corresponder a la versión actual del usuario (RN-009)."""
        if self.estado != ESTADO_ACTIVA:
            raise NoAutenticadoError("La sesión fue cerrada; inicie sesión nuevamente.")
        if self.version_sesion != (self.usuario.version_sesion or 0):
            raise NoAutenticadoError(
                "La sesión fue invalidada porque la cuenta cambió de estado; inicie sesión nuevamente.",
                regla="RN-009")

    def renovar(self, nuevo_token: str, ahora: datetime, dias_renovacion: int) -> None:
        """RN-008: entrega un nuevo token de renovación (el anterior deja de servir)."""
        self.verificar_vigente()
        if ahora >= self.expira_renovacion:
            raise NoAutenticadoError(
                "El token de renovación venció; inicie sesión nuevamente.",
                campo="token_renovacion", regla="RN-008")
        self.usuario.verificar_activo()                                   # RN-006
        self.token_renovacion_hash = hash_token(nuevo_token)
        self.expira_renovacion = ahora + timedelta(days=dias_renovacion)

    def cerrar(self) -> None:
        """Logout: la sesión queda cerrada y sus tokens dejan de funcionar."""
        self.estado = ESTADO_CERRADA
        self.fecha_cierre = _ahora_utc()
