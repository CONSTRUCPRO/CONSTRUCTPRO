# app/domain/proveedor_material.py
# CAPA DOMINIO: la entidad (tabla) ProveedorMaterial y SUS reglas de negocio.
# Es la oferta de un proveedor para un material: precio, disponibilidad y días de entrega.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-11:
#   RN-038  El precio ofrecido debe ser mayor que cero.
#   Solo se asocian materiales y proveedores activos.
#   Un material no se asocia dos veces al mismo proveedor: si ya existe, se actualiza la oferta.
#           (el servicio busca la oferta; además queda la restricción UNIQUE en la BD)
#   La consulta por material solo muestra proveedores activos (filtro del repositorio).
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.material import Material
from app.domain.proveedor import Proveedor


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _a_dinero(valor: float) -> Decimal:
    """Convierte un float a Decimal con 2 decimales (columna Numeric(14, 2))."""
    return Decimal(str(round(valor, 2)))


class ProveedorMaterial(Base):
    __tablename__ = "proveedor_material"
    __table_args__ = (
        # Un mismo material no se asocia dos veces al mismo proveedor
        UniqueConstraint("proveedor_id", "material_id", name="uq_proveedor_material"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)
    dias_entrega: Mapped[int] = mapped_column(Integer)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    proveedor: Mapped[Proveedor] = relationship()
    material: Mapped[Material] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_precio(precio: float) -> None:
        """RN-038: el precio ofrecido debe ser mayor que cero (422, como en el ejemplo del issue)."""
        if precio <= 0:
            raise ReglaNegocioError(
                "RN-038",
                "El precio ofrecido debe ser mayor que cero.",
                campo="precio",
                codigo="VAL_FORMATO_INVALIDO",
                mensaje_general="La información enviada contiene errores.",
            )

    @staticmethod
    def validar_participantes(proveedor: Proveedor, material: Material) -> None:
        """Solo se pueden asociar materiales y proveedores activos (409)."""
        if not proveedor.esta_activo():
            raise ConflictoEstadoError(
                None,
                f"El proveedor '{proveedor.razon_social}' está inactivo y no se le "
                f"pueden asociar materiales.",
                campo="proveedor_id",
            )
        if not material.esta_activo():
            raise ConflictoEstadoError(
                None,
                f"El material '{material.nombre}' está inactivo y no se puede asociar "
                f"a un proveedor.",
                campo="material_id",
            )

    @classmethod
    def registrar(cls, proveedor: Proveedor, material: Material, precio: float,
                  disponible: bool, dias_entrega: int) -> "ProveedorMaterial":
        """Crea la oferta validando que ambos estén activos y el precio (RN-038)."""
        cls.validar_participantes(proveedor, material)
        cls.validar_precio(precio)
        return cls(proveedor=proveedor, material=material, precio=_a_dinero(precio),
                   disponible=disponible, dias_entrega=dias_entrega)

    def actualizar(self, precio: float, disponible: bool, dias_entrega: int) -> None:
        """Si el material ya estaba asociado, se actualiza la oferta (no se duplica)."""
        self.validar_participantes(self.proveedor, self.material)
        self.validar_precio(precio)
        self.precio = _a_dinero(precio)
        self.disponible = disponible
        self.dias_entrega = dias_entrega
