# app/domain/pago.py
# CAPA DOMINIO: la entidad (tabla) Pago y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-23:
#   RN-091  La suma de pagos vigentes no supera el valor total de la orden.
#   RN-092  Solo se paga sobre órdenes confirmadas (OrdenCompra.verificar_pagable(), HU-21).
#   RN-093  Todo pago registra método y fecha.
#   RN-094  Un pago solo se anula el mismo día en que se registró.
#   RN-095  La moneda del pago es la de la orden (COP).
#   Además: el monto es mayor que cero. Al pagar, el valor pasa de comprometido a ejecutado en
#   el presupuesto del proyecto (Presupuesto.ejecutar, HU-06); al anular, se revierte.
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError
from app.domain.orden_compra import ESTADO_CERRADA as ESTADO_ORDEN_CERRADA
from app.domain.orden_compra import OrdenCompra
from app.domain.presupuesto import MONEDA, a_dinero, formato_cop

# Los pagos se registran y anulan en Colombia: "el mismo día" (RN-094) y "fecha no futura" (RN-093)
# se miden en hora de Colombia (UTC-5, sin horario de verano), aunque las fechas se guarden en UTC.
ZONA_COLOMBIA = timezone(timedelta(hours=-5), "COT")
ESTADO_REGISTRADO = "registrado"
ESTADO_ANULADO = "anulado"
METODOS_PAGO = ("transferencia", "pse", "consignacion", "cheque", "tarjeta", "efectivo")


def _ahora_utc() -> datetime:
    """Hora actual en UTC: todas las fechas del sistema se guardan en UTC (Componente F)."""
    return datetime.now(timezone.utc)


def hoy_colombia() -> date:
    """
    La fecha de hoy en Colombia: con ella se decide 'el mismo día' (RN-094) y 'fecha no futura' (RN-093).
    """
    return datetime.now(ZONA_COLOMBIA).date()


def dia_colombia(momento: datetime) -> date:
    """Día en Colombia de una fecha guardada en UTC (SQLite la devuelve sin zona horaria)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA_COLOMBIA).date()


class Pago(Base):
    """
    Un pago a una orden de compra (tabla pagos): monto en COP, método, fecha, número de
    transacción interno y estado (registrado o anulado). Al registrarse mueve el dinero de
    comprometido a ejecutado en el presupuesto; si se anula, lo devuelve.
    """

    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(primary_key=True)
    orden_compra_id: Mapped[int] = mapped_column(ForeignKey("ordenes_compra.id"))
    monto: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    moneda: Mapped[str] = mapped_column(String(3), default=MONEDA)                    # RN-095
    metodo_pago: Mapped[str] = mapped_column(String(20))                              # RN-093
    fecha_pago: Mapped[date] = mapped_column(Date)                                    # RN-093
    numero_transaccion: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    referencia_pasarela: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_REGISTRADO)
    registrado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_anulacion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    motivo_anulacion: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    orden: Mapped[OrdenCompra] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    @staticmethod
    def validar_datos(monto: float, moneda: Optional[str], metodo_pago: Optional[str],
                      fecha_pago: Optional[date], hoy: date) -> None:
        """Monto > 0, RN-095 (moneda de la orden) y RN-093 (método y fecha)."""
        if monto <= 0:
            raise ReglaNegocioError(
                None, "El monto del pago debe ser mayor que cero.", campo="monto")
        if (moneda or MONEDA).upper() != MONEDA:                                      # RN-095
            raise ReglaNegocioError(
                "RN-095", f"La moneda del pago debe ser la de la orden ({MONEDA}).",
                campo="moneda")
        if not metodo_pago or metodo_pago not in METODOS_PAGO:                         # RN-093
            raise ReglaNegocioError(
                "RN-093", f"El método de pago es obligatorio y debe ser uno de: "
                          f"{', '.join(METODOS_PAGO)}.", campo="metodo_pago")
        if fecha_pago is None or fecha_pago > hoy:                                     # RN-093
            raise ReglaNegocioError(
                "RN-093", "La fecha del pago es obligatoria y no puede ser futura.",
                campo="fecha_pago")

    @staticmethod
    def validar_saldo(orden: OrdenCompra, total_pagado: Decimal, monto: float) -> None:
        """RN-091: la suma de pagos vigentes no supera el valor de la orden (422)."""
        saldo = orden.valor_total - total_pagado
        if a_dinero(monto) > saldo:
            raise ReglaNegocioError(
                "RN-091", f"El saldo pendiente de la orden {orden.id} es {formato_cop(saldo)}.",
                campo="monto", codigo="NEG_PAGO_EXCEDE_ORDEN")

    @classmethod
    def registrar(cls, orden: OrdenCompra, total_pagado: Decimal, monto: float,
                  moneda: Optional[str], metodo_pago: Optional[str], fecha_pago: Optional[date],
                  referencia_pasarela: Optional[str], registrado_por_id: Optional[int],
                  hoy: date) -> "Pago":
        """Valida RN-092, RN-095, RN-093 y RN-091, y ejecuta el valor en el presupuesto."""
        orden.verificar_pagable()                                          # RN-092 (HU-21)
        cls.validar_datos(monto, moneda, metodo_pago, fecha_pago, hoy)     # RN-095, RN-093
        cls.validar_saldo(orden, total_pagado, monto)                      # RN-091
        orden.aprobacion.cotizacion.proyecto.presupuesto.ejecutar(monto)   # HU-06
        return cls(orden=orden, monto=a_dinero(monto), moneda=MONEDA, metodo_pago=metodo_pago,
                   fecha_pago=fecha_pago, referencia_pasarela=referencia_pasarela,
                   estado=ESTADO_REGISTRADO, registrado_por_id=registrado_por_id)

    def asignar_numero_transaccion(self) -> None:
        """Número de transacción interno: TX-AAAAMMDD-00000 (necesita el id ya asignado)."""
        self.numero_transaccion = f"TX-{dia_colombia(self.fecha_registro):%Y%m%d}-{self.id:05d}"

    def anular(self, motivo: Optional[str], hoy: date) -> None:
        """RN-094: solo el mismo día de su registro (409). Revierte la ejecución del presupuesto."""
        if self.estado == ESTADO_ANULADO:
            raise ConflictoEstadoError(
                None, f"El pago {self.id} ya está anulado.", campo="estado")
        if self.orden.estado == ESTADO_ORDEN_CERRADA:                       # RN-089
            raise ConflictoEstadoError(
                "RN-089", f"La orden {self.orden_compra_id} ya está cerrada (pagada y recibida); "
                          f"sus pagos no pueden anularse.", campo="pago_id")
        registrado = dia_colombia(self.fecha_registro)
        if registrado != hoy:                                              # RN-094
            raise ConflictoEstadoError(
                "RN-094", f"El pago {self.id} se registró el {registrado.isoformat()}; "
                          f"solo puede anularse el mismo día.",
                campo="pago_id")
        self.estado = ESTADO_ANULADO
        self.fecha_anulacion = _ahora_utc()
        self.motivo_anulacion = (motivo or "").strip() or None
        self.orden.aprobacion.cotizacion.proyecto.presupuesto.revertir_ejecucion(float(self.monto))
