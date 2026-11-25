# app/domain/solicitud.py
# CAPA DOMINIO: las entidades (tablas) Solicitud y SolicitudDetalle y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-12:
#   RN-041  No se crean solicitudes para proyectos suspendidos o finalizados.
#   RN-020  El proyecto debe tener ubicación registrada.
#   RN-021  El proyecto debe tener presupuesto asignado.
#           (las tres las aplica Proyecto.verificar_admite_solicitudes() de la HU-05/HU-06)
#   RN-034  Cada material debe existir y estar activo (Material.verificar_disponible(), HU-09).
#   RN-042  Toda solicitud tiene al menos una línea con cantidad mayor que cero.
#   RN-043  Un material no se repite en la misma solicitud.
#           (además queda la restricción UNIQUE en la BD)
#   RN-044  Solo el solicitante o el responsable del proyecto pueden editarla (o anularla).
#   RN-045  Una solicitud con cotización aprobada no puede editarse ni anularse
#           (ya hay una compra autorizada sobre ella: cambiarla dejaría datos inconsistentes).
#   Solo se editan o anulan solicitudes en estado pendiente.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, PermisoDenegadoError, ReglaNegocioError
from app.domain.material import Material
from app.domain.proyecto import Proyecto
from app.domain.usuario import Usuario

ESTADO_PENDIENTE = "pendiente"
ESTADO_ANULADA = "anulada"


def _ahora_utc() -> datetime:
    """Hora actual en UTC: todas las fechas del sistema se guardan en UTC (Componente F)."""
    return datetime.now(timezone.utc)


class Solicitud(Base):
    """
    Un pedido formal de materiales para un proyecto (tabla solicitudes), con sus líneas en
    solicitud_detalles. Es el primer paso de la cadena de compra:
    solicitud -> comparativo -> cotización -> aprobación -> orden -> pago e inventario.
    El solicitante es el usuario del token (no viene en el cuerpo de la petición).
    """

    __tablename__ = "solicitudes"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_PENDIENTE)
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    proyecto: Mapped[Proyecto] = relationship()
    solicitante: Mapped[Usuario] = relationship()
    detalle: Mapped[list["SolicitudDetalle"]] = relationship(
        back_populates="solicitud", cascade="all, delete-orphan",
        order_by="SolicitudDetalle.id",
    )

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_lineas(lineas: list[tuple[int, int]]) -> None:
        """
        Valida el detalle recibido como [(material_id, cantidad), ...].
        RN-042: al menos una línea y todas con cantidad mayor que cero.
        RN-043: un material no se repite en la misma solicitud.
        """
        if not lineas:
            raise ReglaNegocioError(
                "RN-042", "La solicitud debe tener al menos un material.", campo="detalle")
        vistos: set[int] = set()
        for i, (material_id, cantidad) in enumerate(lineas):
            if cantidad <= 0:
                raise ReglaNegocioError(
                    "RN-042", f"La cantidad del material {material_id} debe ser mayor que cero.",
                    campo=f"detalle.{i}.cantidad")
            if material_id in vistos:
                raise ReglaNegocioError(
                    "RN-043", f"El material {material_id} está repetido en la solicitud.",
                    campo=f"detalle.{i}.material_id")
            vistos.add(material_id)

    @staticmethod
    def validar_materiales(materiales: list[Material]) -> None:
        """RN-034: todos los materiales deben estar activos en el catálogo."""
        for material in materiales:
            material.verificar_disponible()

    @classmethod
    def registrar(cls, proyecto: Proyecto, solicitante: Usuario,
                  lineas: list[tuple[Material, int]]) -> "Solicitud":
        """Crea la solicitud en estado pendiente con sus líneas (RN-041, RN-020, RN-021, RN-034)."""
        proyecto.verificar_admite_solicitudes()                    # RN-041, RN-020, RN-021
        cls.validar_materiales([m for m, _ in lineas])             # RN-034
        solicitud = cls(proyecto=proyecto, solicitante=solicitante, estado=ESTADO_PENDIENTE)
        solicitud.detalle = [SolicitudDetalle(material=m, cantidad=c) for m, c in lineas]
        return solicitud

    def es_pendiente(self) -> bool:
        """True mientras la solicitud no se haya anulado."""
        return self.estado == ESTADO_PENDIENTE

    def verificar_autor(self, usuario_id: int) -> None:
        """RN-044: solo el solicitante o el responsable del proyecto pueden editarla (403)."""
        if usuario_id not in (self.solicitante_id, self.proyecto.responsable_id):
            raise PermisoDenegadoError(
                f"Solo el solicitante o el responsable del proyecto pueden modificar "
                f"la solicitud {self.id}.",
                regla="RN-044", campo="solicitud_id")

    def verificar_sin_compra_aprobada(self, tiene_cotizacion_aprobada: bool) -> None:
        """
        RN-045: una solicitud con cotización aprobada no puede editarse ni anularse (409).
        El repositorio responde si alguna cotización de sus comparativos ya está Aprobada.
        """
        if tiene_cotizacion_aprobada:
            raise ConflictoEstadoError(
                "RN-045", f"La solicitud {self.id} tiene una cotización aprobada y ya no puede "
                          f"editarse ni anularse.", campo="solicitud_id")

    def verificar_pendiente(self) -> None:
        """Solo se editan o anulan solicitudes en estado pendiente (409)."""
        if not self.es_pendiente():
            raise ConflictoEstadoError(
                None, f"La solicitud {self.id} está {self.estado} y ya no se puede modificar.",
                campo="estado")

    def editar(self, usuario_id: int, lineas: list[tuple[Material, int]]) -> None:
        """
        Reemplaza el detalle de la solicitud (RN-044, pendiente, RN-034).
        Las líneas de materiales que siguen se actualizan; las que no vienen se quitan.
        """
        self.verificar_autor(usuario_id)                            # RN-044
        self.verificar_pendiente()
        self.validar_materiales([m for m, _ in lineas])             # RN-034
        nuevas = {m.id: (m, c) for m, c in lineas}
        for linea in list(self.detalle):
            if linea.material_id in nuevas:
                linea.cantidad = nuevas.pop(linea.material_id)[1]
            else:
                self.detalle.remove(linea)
        for material, cantidad in nuevas.values():
            self.detalle.append(SolicitudDetalle(material=material, cantidad=cantidad))
        # Solo cambiaron las líneas (otra tabla), así que la fecha se marca a mano
        self.fecha_actualizacion = _ahora_utc()

    def anular(self, usuario_id: int) -> None:
        """Anula la solicitud (RN-044 y solo si está pendiente)."""
        self.verificar_autor(usuario_id)                            # RN-044
        self.verificar_pendiente()
        self.estado = ESTADO_ANULADA


class SolicitudDetalle(Base):
    """Cada línea de la solicitud: un material y su cantidad (tabla solicitud_detalles)."""
    __tablename__ = "solicitud_detalles"
    __table_args__ = (
        # RN-043 también en la BD: un material no se repite en la misma solicitud
        UniqueConstraint("solicitud_id", "material_id", name="uq_solicitud_detalle_material"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    cantidad: Mapped[int] = mapped_column(Integer)

    solicitud: Mapped[Solicitud] = relationship(back_populates="detalle")
    material: Mapped[Material] = relationship()
