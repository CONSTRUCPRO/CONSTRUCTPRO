# app/domain/cotizacion.py
# CAPA DOMINIO: las entidades (tablas) Cotizacion y CotizacionDetalle y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# La cotización se arma con los comparativos ya seleccionados (HU-16) de un mismo proyecto y
# un mismo proveedor: cada comparativo es una línea con su cantidad y el precio elegido.
#
# Reglas de la HU-17:
#   RN-061  Una cotización pertenece a un solo proyecto y un solo proveedor.
#   RN-062  total = suma de subtotales + impuestos (IVA 19 %).
#   RN-063  Los precios corresponden al comparativo vigente (seleccionado y con la solicitud
#           todavía pendiente).
#   RN-064  No se puede anular una cotización con presupuesto aprobado.
#   RN-065  Una cotización vencida no se puede enviar a aprobación.
#   Al enviarla se valida el saldo del proyecto con Presupuesto.verificar_saldo() (RN-066, HU-06).
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.comparativo import ESTADO_SELECCIONADO, Comparativo
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.material import Material
from app.domain.proveedor import Proveedor
from app.domain.proyecto import Proyecto

ESTADO_GENERADA = "Generada"
ESTADO_ENVIADA = "Enviada"        # en revisión de aprobación (HU-20)
ESTADO_APROBADA = "Aprobada"      # la pone la HU-20
ESTADO_RECHAZADA = "Rechazada"    # la pone la HU-20
ESTADO_ANULADA = "Anulada"

TASA_IVA = Decimal("0.19")        # RN-062
DIAS_VIGENCIA = 15                # la cotización vale 15 días desde que se genera
CENTAVOS = Decimal("0.01")


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoy_utc() -> date:
    return _ahora_utc().date()


def _redondear(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


class Cotizacion(Base):
    __tablename__ = "cotizaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))      # RN-061
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))  # RN-061
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_GENERADA)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    impuestos: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    vigente_hasta: Mapped[date] = mapped_column(Date)                         # RN-065
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    proyecto: Mapped[Proyecto] = relationship()
    proveedor: Mapped[Proveedor] = relationship()
    detalle: Mapped[list["CotizacionDetalle"]] = relationship(
        back_populates="cotizacion", cascade="all, delete-orphan",
        order_by="CotizacionDetalle.id",
    )

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_comparativos(comparativos: list[Comparativo]) -> None:
        """RN-063 (comparativo vigente) y RN-061 (un proyecto y un proveedor)."""
        for c in comparativos:
            if c.estado != ESTADO_SELECCIONADO or not c.solicitud.es_pendiente():
                raise ReglaNegocioError(
                    "RN-063", f"El comparativo {c.id} no está vigente: debe tener una oferta "
                              f"seleccionada y su solicitud debe estar pendiente.",
                    campo="comparativo_ids")
        proyectos = {c.solicitud.proyecto_id for c in comparativos}
        proveedores = {c.proveedor_seleccionado_id for c in comparativos}
        if len(proyectos) > 1 or len(proveedores) > 1:
            raise ReglaNegocioError(
                "RN-061", "Una cotización pertenece a un solo proyecto y un solo proveedor; los "
                          "comparativos enviados son de varios proyectos o proveedores.",
                campo="comparativo_ids")
        materiales = [c.material_id for c in comparativos]
        if len(materiales) != len(set(materiales)):
            raise ReglaNegocioError(
                None, "Un material aparece en más de un comparativo; genere una cotización "
                      "por cada uno.", campo="comparativo_ids")

    @classmethod
    def generar(cls, comparativos: list[Comparativo], hoy: date) -> "Cotizacion":
        """
        Crea la cotización en estado Generada con una línea por comparativo.
        RN-063: precio y cantidad salen del comparativo. RN-062: subtotal, IVA y total.
        """
        cls.validar_comparativos(comparativos)                        # RN-061, RN-063
        primero = comparativos[0]
        cotizacion = cls(proyecto_id=primero.solicitud.proyecto_id,
                         proveedor_id=primero.proveedor_seleccionado_id,
                         estado=ESTADO_GENERADA,
                         vigente_hasta=hoy + timedelta(days=DIAS_VIGENCIA))
        cotizacion.detalle = [
            CotizacionDetalle(comparativo_id=c.id, material_id=c.material_id,
                              cantidad=c.cantidad, precio_unitario=c.precio_seleccionado,
                              subtotal=_redondear(c.precio_seleccionado * c.cantidad))
            for c in comparativos
        ]
        cotizacion.calcular_totales()                                 # RN-062
        return cotizacion

    def calcular_totales(self) -> None:
        """RN-062: total = suma de subtotales + impuestos (IVA 19 %)."""
        self.subtotal = _redondear(sum((d.subtotal for d in self.detalle), Decimal("0")))
        self.impuestos = _redondear(self.subtotal * TASA_IVA)
        self.total = self.subtotal + self.impuestos

    def esta_vencida(self, hoy: date) -> bool:
        return hoy > self.vigente_hasta

    def enviar(self, hoy: date) -> None:
        """
        La envía a presupuesto y aprobación. Solo desde Generada.
        RN-065: no se envía si está vencida. RN-066 (HU-06): el total no supera el saldo.
        La aprobación "En revisión" la crea Aprobacion.abrir() (app/domain/aprobacion.py).
        """
        if self.estado != ESTADO_GENERADA:
            raise ConflictoEstadoError(
                None, f"La cotización {self.id} está {self.estado}; solo se envían cotizaciones "
                      f"en estado {ESTADO_GENERADA}.", campo="estado")
        if self.esta_vencida(hoy):                                    # RN-065
            raise ReglaNegocioError(
                "RN-065", f"La cotización {self.id} venció el {self.vigente_hasta.isoformat()} "
                          f"y no puede enviarse a aprobación.", campo="vigente_hasta")
        presupuesto = self.proyecto.presupuesto
        if presupuesto is None:                                       # RN-021 (HU-06)
            raise ReglaNegocioError(
                "RN-021", f"El proyecto '{self.proyecto.nombre}' no tiene presupuesto asignado.",
                campo="proyecto_id")
        presupuesto.verificar_saldo(float(self.total))                # RN-066
        self.estado = ESTADO_ENVIADA

    def anular(self) -> None:
        """RN-064: no se anula una cotización con presupuesto aprobado (409)."""
        if self.estado == ESTADO_APROBADA:
            raise ConflictoEstadoError(
                "RN-064", f"La cotización {self.id} tiene presupuesto aprobado.",
                campo="cotizacion_id", codigo="NEG_COTIZACION_APROBADA",
                mensaje_general="La cotización ya fue aprobada y no puede anularse.")
        if self.estado == ESTADO_ANULADA:
            raise ConflictoEstadoError(
                None, f"La cotización {self.id} ya está anulada.", campo="estado")
        self.estado = ESTADO_ANULADA


class CotizacionDetalle(Base):
    """Cada línea de la cotización: un comparativo seleccionado (tabla cotizacion_detalles)."""
    __tablename__ = "cotizacion_detalles"
    __table_args__ = (
        UniqueConstraint("cotizacion_id", "material_id", name="uq_cotizacion_detalle_material"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"))
    comparativo_id: Mapped[int] = mapped_column(ForeignKey("comparativos.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2))      # RN-063
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    cotizacion: Mapped[Cotizacion] = relationship(back_populates="detalle")
    material: Mapped[Material] = relationship()
