# app/domain/orden_compra.py
# CAPA DOMINIO - HU-21 Generación de Orden de Compra (MOD-07).
# Entidades OrdenCompra (tabla ordenes_compra) y OrdenDetalle (tabla orden_detalles) y sus reglas.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
#
# La orden nace de una aprobación "Aprobada" (HU-20) y copia los ítems de su cotización (HU-17).
#
# Reglas de la HU-21:
#   RN-081  No se genera orden si la compra no está aprobada (409 NEG_COMPRA_NO_APROBADA).
#   RN-082  La orden tiene exactamente los ítems y valores aprobados (se copian sin cambios).
#   RN-083  Cada cotización aprobada genera una única orden (también UNIQUE en la BD).
#   RN-084  Una orden con pagos o envíos registrados no puede anularse.
#   RN-039  El proveedor debe estar activo (Proveedor.verificar_puede_recibir_ordenes, HU-10).
#   RN-086  El estado solo avanza emitida -> confirmada -> cerrada.
#   RN-089  Una orden anulada o cerrada no admite más cambios de estado.
#   RN-069  Al anular, el valor comprometido se libera del presupuesto del proyecto (FUN-084).
#
# Para otras HU (no reimplementar):
#   verificar_pagable()  RN-092: solo se pagan órdenes confirmadas (HU-23, Alejandro).
#   ESTADOS_ABIERTOS     órdenes que cuentan para RN-040 (proveedor) y RN-025 (proyecto).
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.aprobacion import ESTADO_APROBADA as APROBACION_APROBADA
from app.domain.aprobacion import Aprobacion
from app.domain.excepciones import ConflictoEstadoError
from app.domain.material import Material
from app.domain.proveedor import Proveedor

ESTADO_EMITIDA = "emitida"
ESTADO_CONFIRMADA = "confirmada"    # el proveedor confirmó la orden (RN-086)
ESTADO_CERRADA = "cerrada"          # pago y recepción completos (RN-087, otras HU)
ESTADO_ANULADA = "anulada"
ESTADOS_ABIERTOS = (ESTADO_EMITIDA, ESTADO_CONFIRMADA)


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"

    id: Mapped[int] = mapped_column(primary_key=True)
    aprobacion_id: Mapped[int] = mapped_column(ForeignKey("aprobaciones.id"))
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), unique=True)  # RN-083
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"))
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_EMITIDA)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    impuestos: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    valor_total: Mapped[Decimal] = mapped_column(Numeric(16, 2))      # = monto autorizado (RN-082)
    emitida_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_emision: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_confirmacion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fecha_anulacion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    motivo_anulacion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    aprobacion: Mapped[Aprobacion] = relationship()
    proveedor: Mapped[Proveedor] = relationship()
    detalle: Mapped[list["OrdenDetalle"]] = relationship(
        back_populates="orden", cascade="all, delete-orphan", order_by="OrdenDetalle.id")

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def verificar_aprobada(aprobacion: Aprobacion) -> None:
        """RN-081: la compra debe estar aprobada (409 NEG_COMPRA_NO_APROBADA)."""
        if aprobacion.estado != APROBACION_APROBADA:
            raise ConflictoEstadoError(
                "RN-081", f"La aprobación {aprobacion.id} se encuentra en estado '{aprobacion.estado}'.",
                campo="aprobacion_id", codigo="NEG_COMPRA_NO_APROBADA")

    @classmethod
    def emitir(cls, aprobacion: Aprobacion, proveedor: Proveedor,
               emitida_por_id: Optional[int]) -> "OrdenCompra":
        """
        FUN-081 / FUN-082: emite la orden copiando exactamente lo aprobado (RN-082).
        Valida RN-081 y RN-039. La RN-083 (una sola orden) la revisa el servicio antes.
        """
        cls.verificar_aprobada(aprobacion)                                 # RN-081
        proveedor.verificar_puede_recibir_ordenes()                        # RN-039
        cotizacion = aprobacion.cotizacion
        orden = cls(aprobacion=aprobacion, cotizacion_id=cotizacion.id, proveedor=proveedor,
                    proyecto_id=cotizacion.proyecto_id, estado=ESTADO_EMITIDA,
                    subtotal=cotizacion.subtotal, impuestos=cotizacion.impuestos,
                    valor_total=aprobacion.monto_autorizado, emitida_por_id=emitida_por_id)
        orden.detalle = [OrdenDetalle(material_id=d.material_id, cantidad=d.cantidad,
                                      precio_unitario=d.precio_unitario, subtotal=d.subtotal)
                         for d in cotizacion.detalle]                       # RN-082
        return orden

    def esta_abierta(self) -> bool:
        return self.estado in ESTADOS_ABIERTOS

    def _verificar_modificable(self) -> None:
        """RN-089: una orden anulada o cerrada no admite más cambios de estado (409)."""
        if self.estado in (ESTADO_ANULADA, ESTADO_CERRADA):
            raise ConflictoEstadoError(
                "RN-089", f"La orden {self.id} está {self.estado} y no admite cambios de estado.",
                campo="estado")

    def confirmar(self) -> None:
        """RN-086: el proveedor confirma la orden (emitida -> confirmada)."""
        self._verificar_modificable()                                      # RN-089
        if self.estado != ESTADO_EMITIDA:
            raise ConflictoEstadoError(
                "RN-086", f"La orden {self.id} ya está {self.estado}; solo se confirman órdenes emitidas.",
                campo="estado")
        self.estado = ESTADO_CONFIRMADA
        self.fecha_confirmacion = _ahora_utc()

    def anular(self, motivo: Optional[str], pagos: int, envios: int) -> None:
        """
        FUN-084: anula la orden y registra el motivo.
        RN-089: no si está anulada o cerrada. RN-084: no si tiene pagos o envíos.
        El servicio libera después el presupuesto comprometido (RN-069).
        """
        self._verificar_modificable()                                      # RN-089
        if pagos > 0 or envios > 0:                                        # RN-084
            raise ConflictoEstadoError(
                "RN-084", f"La orden {self.id} tiene {pagos} pago(s) y {envios} envío(s) "
                          f"registrados y no puede anularse.", campo="orden_compra_id")
        self.estado = ESTADO_ANULADA
        self.fecha_anulacion = _ahora_utc()
        self.motivo_anulacion = (motivo or "").strip() or None

    def verificar_pagable(self) -> None:
        """Para la HU-23. RN-092: solo se registran pagos sobre órdenes confirmadas (409)."""
        if self.estado != ESTADO_CONFIRMADA:
            raise ConflictoEstadoError(
                "RN-092", f"La orden {self.id} está {self.estado}; solo se registran pagos sobre "
                          f"órdenes confirmadas por el proveedor.", campo="orden_compra_id")


class OrdenDetalle(Base):
    """Cada línea de la orden, copiada de la cotización aprobada (tabla orden_detalles)."""
    __tablename__ = "orden_detalles"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_compra_id: Mapped[int] = mapped_column(ForeignKey("ordenes_compra.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    orden: Mapped[OrdenCompra] = relationship(back_populates="detalle")
    material: Mapped[Material] = relationship()
