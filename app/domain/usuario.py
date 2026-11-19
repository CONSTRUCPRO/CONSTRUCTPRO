# app/domain/usuario.py
# CAPA DOMINIO - HU-01 Gestión de Usuarios (MOD-01).
# Entidad Usuario (tabla usuarios) y sus reglas de negocio.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-01:
#   RN-001  Correo y número de documento únicos (la consulta la hace el servicio;
#           además hay restricción UNIQUE en la BD).
#   RN-002  Todo usuario tiene un rol asignado, y ese rol debe existir y estar activo.
#   RN-003  La contraseña se guarda cifrada (bcrypt) y nunca se devuelve.
#   RN-004  Un usuario no puede inactivar su propia cuenta.
#   RN-005  Un usuario no se elimina, solo se inactiva (no existe DELETE).
#   RN-009  Al inactivar un usuario se invalidan sus sesiones: se incrementa
#           version_sesion. La HU-02 guardará ese número dentro del token y
#           rechazará los tokens que tengan una versión anterior.
from datetime import datetime, timezone
from typing import Optional

import bcrypt
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.rol import Rol

ESTADO_ACTIVO = "activo"
ESTADO_INACTIVO = "inactivo"

# Tipos de documento aceptados en Colombia
TIPOS_DOCUMENTO = ("CC", "CE", "TI", "PA", "NIT")


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre_completo: Mapped[str] = mapped_column(String(120))
    tipo_documento: Mapped[str] = mapped_column(String(5))
    numero_documento: Mapped[str] = mapped_column(String(20), unique=True)   # RN-001
    correo: Mapped[str] = mapped_column(String(120), unique=True)            # RN-001
    telefono: Mapped[str] = mapped_column(String(20))
    contrasena_hash: Mapped[str] = mapped_column(String(100))                # RN-003
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))              # RN-002
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVO)
    version_sesion: Mapped[int] = mapped_column(Integer, default=0)          # RN-009
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    rol: Mapped[Rol] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_rol_asignable(rol: Optional[Rol], rol_id: int) -> None:
        """RN-002: el rol debe existir y estar activo."""
        if rol is None:
            raise ReglaNegocioError("RN-002", f"No existe un rol con el identificador {rol_id}.",
                                    campo="rol_id")
        if rol.estado != "activo":
            raise ReglaNegocioError("RN-002", f"El rol {rol.nombre} está inactivo y no puede "
                                    f"asignarse a un usuario.", campo="rol_id")

    @classmethod
    def registrar(cls, nombre_completo: str, tipo_documento: str, numero_documento: str,
                  correo: str, telefono: str, contrasena: str, rol: Rol) -> "Usuario":
        """Crea un usuario nuevo. Siempre nace activo y con la contraseña cifrada."""
        usuario = cls(nombre_completo=nombre_completo, tipo_documento=tipo_documento,
                      numero_documento=numero_documento, correo=correo, telefono=telefono,
                      rol=rol, estado=ESTADO_ACTIVO, version_sesion=0)
        usuario.establecer_contrasena(contrasena)
        return usuario

    def establecer_contrasena(self, contrasena: str) -> None:
        """RN-003: nunca se guarda la contraseña en texto plano, solo su hash bcrypt."""
        self.contrasena_hash = bcrypt.hashpw(contrasena.encode("utf-8"),
                                             bcrypt.gensalt()).decode("utf-8")

    def verificar_contrasena(self, contrasena: str) -> bool:
        """La usará la HU-02 (login) para comparar la contraseña enviada con el hash."""
        return bcrypt.checkpw(contrasena.encode("utf-8"), self.contrasena_hash.encode("utf-8"))

    def editar_perfil(self, nombre_completo: str, tipo_documento: str, numero_documento: str,
                      correo: str, telefono: str) -> None:
        """Edita los datos del perfil. El rol, la contraseña y el estado no cambian aquí."""
        self.nombre_completo = nombre_completo
        self.tipo_documento = tipo_documento
        self.numero_documento = numero_documento
        self.correo = correo
        self.telefono = telefono

    def asignar_rol(self, rol: Optional[Rol], rol_id: int) -> None:
        """Cambia el rol del usuario (RN-002)."""
        self.validar_rol_asignable(rol, rol_id)
        self.rol = rol

    def esta_activo(self) -> bool:
        return self.estado == ESTADO_ACTIVO

    def cambiar_estado(self, nuevo_estado: str, usuario_actual_id: Optional[str]) -> None:
        """
        Activa o inactiva el usuario.
        RN-004: nadie puede inactivar su propia cuenta.
        RN-009: al inactivar, se invalidan todas sus sesiones (version_sesion + 1).
        """
        if self.estado == nuevo_estado:
            raise ConflictoEstadoError(
                None, f"El usuario ya se encuentra en estado '{nuevo_estado}'.", campo="estado")
        if nuevo_estado == ESTADO_INACTIVO and usuario_actual_id is not None \
                and str(usuario_actual_id) == str(self.id):
            raise ReglaNegocioError("RN-004", "No puede inactivar su propia cuenta.",
                                    campo="usuario_id")
        self.estado = nuevo_estado
        if nuevo_estado == ESTADO_INACTIVO:
            self.version_sesion = (self.version_sesion or 0) + 1      # RN-009
