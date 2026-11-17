# app/domain/material.py
# CAPA DOMINIO: las entidades (tablas) Categoria y Material y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-09:
#   RN-031  No se repite un material con el mismo nombre y unidad dentro de una categoría.
#           (la consulta la hace el servicio; además queda la restricción UNIQUE en la BD)
#   RN-032  Todo material tiene unidad de medida y categoría válidas.
#   RN-033  El precio de referencia es mayor que cero.
#   RN-034  Un material inactivo no se puede usar en solicitudes ni cotizaciones.
#   RN-035  Un material no se elimina, solo se inactiva (por eso no hay endpoint DELETE).
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError

# RN-032: unidades de medida aceptadas en el catálogo (siempre en minúscula)
UNIDADES_VALIDAS = {"bulto", "kg", "tonelada", "m", "m2", "m3", "unidad", "galon", "litro", "rollo"}

ESTADO_ACTIVO = "activo"
ESTADO_INACTIVO = "inactivo"


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _a_dinero(valor: float) -> Decimal:
    """Convierte un float a Decimal con 2 decimales (columna Numeric(14, 2))."""
    return Decimal(str(round(valor, 2)))


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVO)

    materiales: Mapped[list["Material"]] = relationship(back_populates="categoria")

    def esta_activa(self) -> bool:
        return self.estado == ESTADO_ACTIVO


class Material(Base):
    __tablename__ = "materiales"
    __table_args__ = (
        # RN-031 también en la BD: misma categoría + nombre + unidad no se repite
        UniqueConstraint("categoria_id", "nombre", "unidad",
                         name="uq_materiales_categoria_nombre_unidad"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    unidad: Mapped[str] = mapped_column(String(20))
    categoria_id: Mapped[int] = mapped_column(ForeignKey("categorias.id"))
    precio_referencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVO)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    categoria: Mapped[Categoria] = relationship(back_populates="materiales")

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_unidad(unidad: str) -> None:
        """RN-032: la unidad debe estar en el catálogo de unidades."""
        if unidad not in UNIDADES_VALIDAS:
            raise ReglaNegocioError(
                "RN-032",
                f"La unidad de medida '{unidad}' no es válida. "
                f"Use una de: {', '.join(sorted(UNIDADES_VALIDAS))}.",
                campo="unidad",
            )

    @staticmethod
    def validar_categoria(categoria: Optional[Categoria], categoria_id: int) -> None:
        """RN-032: la categoría debe existir y estar activa."""
        if categoria is None or not categoria.esta_activa():
            raise ReglaNegocioError(
                "RN-032",
                f"La categoría {categoria_id} no existe o no está activa.",
                campo="categoria_id",
            )

    @staticmethod
    def validar_precio(precio: float) -> None:
        """RN-033: el precio de referencia debe ser mayor que cero."""
        if precio <= 0:
            raise ReglaNegocioError(
                "RN-033",
                "El precio de referencia debe ser mayor que cero.",
                campo="precio_referencia",
            )

    @classmethod
    def registrar(cls, nombre: str, unidad: str, categoria: Categoria,
                  precio_referencia: float) -> "Material":
        """Crea un material nuevo validando RN-032 y RN-033. Siempre nace activo."""
        cls.validar_unidad(unidad)
        cls.validar_precio(precio_referencia)
        return cls(
            nombre=nombre,
            unidad=unidad,
            categoria=categoria,
            precio_referencia=_a_dinero(precio_referencia),
            estado=ESTADO_ACTIVO,
        )

    def editar(self, nombre: str, unidad: str, categoria: Categoria,
               precio_referencia: float) -> None:
        """Edita todos los datos validando RN-032 y RN-033. El estado no cambia aquí."""
        self.validar_unidad(unidad)
        self.validar_precio(precio_referencia)
        self.nombre = nombre
        self.unidad = unidad
        self.categoria = categoria
        self.precio_referencia = _a_dinero(precio_referencia)

    def actualizar_precio(self, nuevo: float) -> None:
        """Cambia solo el precio de referencia (RN-033)."""
        self.validar_precio(nuevo)
        self.precio_referencia = _a_dinero(nuevo)

    def esta_activo(self) -> bool:
        return self.estado == ESTADO_ACTIVO

    def cambiar_estado(self, nuevo_estado: str) -> None:
        """
        RN-035: un material no se elimina; se inactiva (y se puede volver a activar).
        Si ya está en ese estado, es un conflicto (409).
        """
        if self.estado == nuevo_estado:
            raise ConflictoEstadoError(
                "RN-035",
                f"El material ya se encuentra en estado '{nuevo_estado}'.",
                campo="estado",
            )
        self.estado = nuevo_estado

    def verificar_disponible(self) -> None:
        """
        RN-034: un material inactivo no se puede usar en solicitudes ni cotizaciones.
        La llamarán la HU-12 (solicitudes) y la HU-17 (cotizaciones) antes de usar el material.
        """
        if not self.esta_activo():
            raise ConflictoEstadoError(
                "RN-034",
                f"El material '{self.nombre}' está inactivo y no puede usarse "
                f"en solicitudes ni cotizaciones.",
                campo="material_id",
            )
