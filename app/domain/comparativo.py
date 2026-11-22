# app/domain/comparativo.py
# CAPA DOMINIO: las entidades (tablas) Comparativo y ComparativoOferta y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# El comparativo guarda una "foto" de las ofertas de proveedor_material (HU-11) en el momento
# en que se genera: si después un proveedor cambia su precio, el comparativo y el ahorro
# calculado no cambian.
#
# Reglas de la HU-16:
#   RN-056  El comparativo requiere mínimo dos proveedores con oferta.
#   RN-057  Solo se comparan ofertas del mismo material y unidad de la solicitud.
#   RN-058  La oferta seleccionada debe pertenecer al comparativo.
#   RN-059  Si no se elige la de menor precio, la justificación es obligatoria.
#   RN-060  ahorro = precio_maximo − precio_seleccionado (por unidad).
#   Además: solo se compara para solicitudes pendientes y el material debe estar activo (RN-034).
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.material import Material
from app.domain.proveedor_material import ProveedorMaterial
from app.domain.solicitud import Solicitud

ESTADO_ABIERTO = "abierto"              # generado, sin oferta elegida
ESTADO_SELECCIONADO = "seleccionado"    # ya tiene la oferta elegida y el ahorro calculado
MINIMO_PROVEEDORES = 2                  # RN-056
ORDENES = ("precio", "dias_entrega")


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Comparativo(Base):
    __tablename__ = "comparativos"
    __table_args__ = (
        # Un solo comparativo por material de cada solicitud (el ahorro no se cuenta dos veces)
        UniqueConstraint("solicitud_id", "material_id", name="uq_comparativo_solicitud_material"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    unidad: Mapped[str] = mapped_column(String(20))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_minimo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    precio_maximo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ABIERTO)
    proveedor_seleccionado_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("proveedores.id"), nullable=True)
    precio_seleccionado: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    ahorro: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)   # RN-060
    justificacion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)   # RN-059
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_seleccion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    solicitud: Mapped[Solicitud] = relationship()
    material: Mapped[Material] = relationship()
    ofertas: Mapped[list["ComparativoOferta"]] = relationship(
        back_populates="comparativo", cascade="all, delete-orphan",
        order_by="ComparativoOferta.id",   # se guardan ya ordenadas por precio
    )

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def _verificar_solicitud_pendiente(solicitud: Solicitud) -> None:
        """Solo se compara (y se selecciona) para solicitudes pendientes (409)."""
        if not solicitud.es_pendiente():
            raise ConflictoEstadoError(
                None, f"La solicitud {solicitud.id} está {solicitud.estado}; solo se comparan "
                      f"precios de solicitudes pendientes.", campo="solicitud_id")

    @staticmethod
    def cantidad_en_solicitud(solicitud: Solicitud, material: Material) -> int:
        """RN-057: el material debe ser uno de los pedidos en la solicitud (422)."""
        for linea in solicitud.detalle:
            if linea.material_id == material.id:
                return linea.cantidad
        raise ReglaNegocioError(
            "RN-057", f"El material {material.id} no hace parte de la solicitud {solicitud.id}; "
                      f"solo se comparan ofertas del material y la unidad solicitados.",
            campo="material_id")

    @staticmethod
    def validar_suficientes(material: Material, ofertas: list[ProveedorMaterial]) -> None:
        """RN-056: se requieren al menos dos proveedores con oferta (422)."""
        if len(ofertas) < MINIMO_PROVEEDORES:
            detalle = ("no tiene proveedores" if not ofertas
                       else "solo tiene un proveedor")
            raise ReglaNegocioError(
                "RN-056", f"El material {material.id} {detalle} con oferta registrada.",
                campo="material_id", codigo="NEG_COMPARATIVO_INSUFICIENTE")

    @classmethod
    def generar(cls, solicitud: Solicitud, material: Material,
                ofertas: list[ProveedorMaterial]) -> "Comparativo":
        """
        Crea el comparativo con la foto de las ofertas, ordenadas de menor a mayor precio.
        Valida: solicitud pendiente, RN-034, RN-057 y RN-056.
        """
        cls._verificar_solicitud_pendiente(solicitud)
        material.verificar_disponible()                                    # RN-034
        cantidad = cls.cantidad_en_solicitud(solicitud, material)          # RN-057
        # RN-057: solo ofertas de ese material (todas en su única unidad del catálogo)
        ofertas = [o for o in ofertas if o.material_id == material.id]
        cls.validar_suficientes(material, ofertas)                         # RN-056
        precios = [o.precio for o in ofertas]
        comparativo = cls(solicitud=solicitud, material=material, unidad=material.unidad,
                          cantidad=cantidad, precio_minimo=min(precios),
                          precio_maximo=max(precios), estado=ESTADO_ABIERTO)
        comparativo.ofertas = [
            ComparativoOferta(proveedor_id=o.proveedor_id, precio=o.precio,
                              disponible=o.disponible, dias_entrega=o.dias_entrega)
            for o in sorted(ofertas, key=lambda o: (o.precio, o.dias_entrega, o.proveedor_id))
        ]
        return comparativo

    def ofertas_filtradas(self, orden: str = "precio", disponible: Optional[bool] = None,
                          dias_max: Optional[int] = None) -> list["ComparativoOferta"]:
        """Ordena y filtra las ofertas para la consulta (no cambia lo guardado)."""
        ofertas = [o for o in self.ofertas
                   if (disponible is None or o.disponible == disponible)
                   and (dias_max is None or o.dias_entrega <= dias_max)]
        if orden == "dias_entrega":
            return sorted(ofertas, key=lambda o: (o.dias_entrega, o.precio, o.proveedor_id))
        return sorted(ofertas, key=lambda o: (o.precio, o.dias_entrega, o.proveedor_id))

    def seleccionar(self, proveedor_id: int, justificacion: Optional[str]) -> None:
        """
        Elige la oferta de un proveedor y calcula el ahorro.
        RN-058: la oferta debe ser del comparativo. RN-059: justificación si no es la más barata.
        RN-060: ahorro = precio_maximo − precio_seleccionado.
        """
        if self.estado == ESTADO_SELECCIONADO:
            raise ConflictoEstadoError(
                None, f"El comparativo {self.id} ya tiene una oferta seleccionada.",
                campo="proveedor_id")
        self._verificar_solicitud_pendiente(self.solicitud)
        oferta = next((o for o in self.ofertas if o.proveedor_id == proveedor_id), None)
        if oferta is None:                                                 # RN-058
            raise ReglaNegocioError(
                "RN-058", f"El proveedor {proveedor_id} no tiene una oferta en el "
                          f"comparativo {self.id}.", campo="proveedor_id")
        justificacion = (justificacion or "").strip() or None
        if oferta.precio > self.precio_minimo and not justificacion:       # RN-059
            raise ReglaNegocioError(
                "RN-059", "La oferta elegida no es la de menor precio; escriba la justificación.",
                campo="justificacion")
        self.proveedor_seleccionado_id = proveedor_id
        self.precio_seleccionado = oferta.precio
        self.ahorro = self.precio_maximo - oferta.precio                   # RN-060
        self.justificacion = justificacion
        self.estado = ESTADO_SELECCIONADO
        self.fecha_seleccion = _ahora_utc()

    @property
    def ahorro_total(self) -> Optional[Decimal]:
        """Ahorro de toda la cantidad pedida (ahorro por unidad × cantidad)."""
        return None if self.ahorro is None else self.ahorro * self.cantidad


class ComparativoOferta(Base):
    """Foto de una oferta en el momento de generar el comparativo (tabla comparativo_ofertas)."""
    __tablename__ = "comparativo_ofertas"
    __table_args__ = (
        UniqueConstraint("comparativo_id", "proveedor_id", name="uq_comparativo_oferta_proveedor"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    comparativo_id: Mapped[int] = mapped_column(ForeignKey("comparativos.id"))
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    disponible: Mapped[bool] = mapped_column(Boolean)
    dias_entrega: Mapped[int] = mapped_column(Integer)

    comparativo: Mapped[Comparativo] = relationship(back_populates="ofertas")
    