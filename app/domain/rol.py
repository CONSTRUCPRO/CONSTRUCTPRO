# app/domain/rol.py
# CAPA DOMINIO - HU-03 Gestión de Roles y Permisos (MOD-01, SUB-03).
# Entidades Rol y PermisoRol (tablas roles y permisos_rol) y sus reglas de negocio.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError

# Módulos del sistema (Tabla 4 del parcial) sobre los que se asignan permisos.
MODULOS = (
    "Usuarios", "Proyectos", "Materiales", "Solicitudes", "Cotizaciones",
    "Aprobaciones", "Ordenes de compra", "Pagos", "Logistica", "Inventario", "Reportes",
)

# Acciones que un rol puede tener sobre un módulo.
ACCIONES = ("crear", "consultar", "editar", "inactivar", "aprobar", "anular")

# RN-015: roles críticos del proceso que existen por defecto y no se pueden inactivar
# ni renombrar. Se incluye Administrador porque sin él nadie podría gestionar roles (RN-014).
ROLES_PROTEGIDOS = ("administrador", "coordinador", "director")


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    permisos: Mapped[list["PermisoRol"]] = relationship(
        back_populates="rol", cascade="all, delete-orphan", order_by="PermisoRol.id"
    )

    # ── Reglas de negocio ─────────────────────────────────

    def es_protegido(self) -> bool:
        return self.nombre.lower() in ROLES_PROTEGIDOS

    def renombrar(self, nuevo_nombre: str, descripcion: Optional[str]) -> None:
        """Editar rol. RN-015: los roles protegidos no cambian de nombre."""
        if self.es_protegido() and nuevo_nombre.lower() != self.nombre.lower():
            raise ConflictoEstadoError(
                "RN-015", f"El rol {self.nombre} es obligatorio del sistema y no puede renombrarse.",
                campo="nombre")
        self.nombre = nuevo_nombre
        self.descripcion = descripcion

    def asignar_permisos(self, permisos: dict[str, list[str]]) -> None:
        """
        Reemplaza los permisos del rol. `permisos` = {"Solicitudes": ["crear", "consultar"], ...}
        RN-013: todo rol debe quedar con al menos un permiso.
        """
        nuevos = {(modulo, accion) for modulo, acciones in permisos.items() for accion in acciones}
        if not nuevos:
            raise ReglaNegocioError("RN-013", "Todo rol debe tener al menos un permiso asociado.",
                                    campo="permisos")
        # Se quitan los que ya no están y se agregan solo los que faltan
        # (borrar y volver a insertar el mismo permiso choca con la restricción única).
        for permiso in list(self.permisos):
            if (permiso.modulo, permiso.accion) not in nuevos:
                self.permisos.remove(permiso)
        actuales = {(p.modulo, p.accion) for p in self.permisos}
        for modulo, accion in sorted(nuevos - actuales):
            self.permisos.append(PermisoRol(modulo=modulo, accion=accion))

    def cambiar_estado(self, nuevo_estado: str) -> None:
        """RN-015: los roles coordinador y director (y administrador) no se pueden inactivar."""
        if nuevo_estado == "inactivo" and self.es_protegido():
            raise ConflictoEstadoError(
                "RN-015", f"El rol {self.nombre} es obligatorio del sistema y no puede inactivarse.",
                campo="estado")
        self.estado = nuevo_estado

    def permisos_agrupados(self) -> dict[str, list[str]]:
        """{"Solicitudes": ["crear", "consultar"], ...} en el orden de MODULOS y de ACCIONES."""
        agrupados: dict[str, list[str]] = {}
        for p in self.permisos:
            agrupados.setdefault(p.modulo, []).append(p.accion)
        return {m: sorted(agrupados[m], key=ACCIONES.index) for m in MODULOS if m in agrupados}

    def tiene_permiso(self, modulo: str, accion: str) -> bool:
        if self.estado != "activo":
            return False
        return any(p.modulo == modulo and p.accion == accion for p in self.permisos)


class PermisoRol(Base):
    """Relación N:M entre roles y módulos/acciones (tabla permisos_rol)."""
    __tablename__ = "permisos_rol"
    __table_args__ = (UniqueConstraint("rol_id", "modulo", "accion", name="uq_permiso_rol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    modulo: Mapped[str] = mapped_column(String(40))
    accion: Mapped[str] = mapped_column(String(20))

    rol: Mapped[Rol] = relationship(back_populates="permisos")
