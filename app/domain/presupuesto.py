# app/domain/presupuesto.py
# CAPA DOMINIO - HU-06 Presupuesto del Proyecto (MOD-02).
# Entidad Presupuesto (tabla presupuestos): uno por proyecto.
# No importa FastAPI: las reglas lanzan excepciones de app.domain.excepciones.
#
#   saldo_disponible = presupuesto_total - comprometido - ejecutado
#
# Reglas de la HU-06:
#   RN-022  Solo el rol director asigna o modifica el presupuesto (se controla en el router).
#   RN-023  El presupuesto no puede reducirse por debajo de lo comprometido y ejecutado.
#   El monto debe ser mayor que cero (se valida en el schema).
#
# Métodos para otras HU (no reimplementar, llamarlos):
#   RN-066  verificar_saldo(monto): una compra no se aprueba si supera el saldo (HU-20).
#   RN-068  comprometer(monto): reserva el valor al enviar la compra a aprobación (HU-17/HU-20).
#   RN-069  liberar(monto): devuelve lo comprometido si la compra se rechaza o anula (HU-20).
#           ejecutar(monto): pasa de comprometido a ejecutado al registrar el pago (HU-23).
#
# Nota: este módulo NO importa proyecto.py (la relación usa el texto "Proyecto"); es
# proyecto.py el que importa este archivo. Así no hay importaciones circulares.
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ReglaNegocioError

MONEDA = "COP"


def _ahora_utc() -> datetime:
    """Hora actual en UTC: todas las fechas del sistema se guardan en UTC (Componente F)."""
    return datetime.now(timezone.utc)


def a_dinero(valor) -> Decimal:
    """Convierte a Decimal con 2 decimales (columnas Numeric(16, 2))."""
    return Decimal(str(round(float(valor), 2)))


def formato_cop(valor) -> str:
    """44815500 -> '44.815.500,00 COP' (formato colombiano, como en el ejemplo del issue)."""
    texto = f"{Decimal(valor):,.2f}"                       # 44,815,500.00
    texto = texto.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{texto} {MONEDA}"


class Presupuesto(Base):
    """
    El presupuesto de un proyecto (tabla presupuestos, uno por proyecto).

    Lleva tres montos: presupuesto_total (lo asignado), comprometido (compras aprobadas que
    aún no se pagan) y ejecutado (lo ya pagado). El saldo disponible sale de restar los dos
    últimos. Aprobaciones, órdenes y pagos mueven el dinero con los métodos de esta clase.
    """

    __tablename__ = "presupuestos"

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"), unique=True)  # uno por proyecto
    presupuesto_total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    comprometido: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    ejecutado: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    fecha_aprobacion: Mapped[date] = mapped_column(Date)
    aprobado_por_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # quien asignó/actualizó
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    proyecto: Mapped["Proyecto"] = relationship(back_populates="presupuesto")  # noqa: F821

    # ── Cálculos ──────────────────────────────────────────

    @property
    def comprometido_y_ejecutado(self) -> Decimal:
        """Lo que ya está usado del presupuesto: comprometido + ejecutado."""
        return (self.comprometido or Decimal("0")) + (self.ejecutado or Decimal("0"))

    @property
    def saldo_disponible(self) -> Decimal:
        """saldo_disponible = presupuesto_total - comprometido - ejecutado (FUN-022)."""
        return a_dinero(self.presupuesto_total) - self.comprometido_y_ejecutado

    # ── Reglas de negocio ─────────────────────────────────

    @classmethod
    def asignar(cls, monto: float, aprobado_por_id: Optional[int]) -> "Presupuesto":
        """FUN-021: crea el presupuesto con la fecha de aprobación de hoy."""
        return cls(presupuesto_total=a_dinero(monto), comprometido=Decimal("0"),
                   ejecutado=Decimal("0"), fecha_aprobacion=date.today(),
                   aprobado_por_id=aprobado_por_id)

    def actualizar(self, monto: float, aprobado_por_id: Optional[int]) -> None:
        """FUN-023 y RN-023: el nuevo monto no puede quedar por debajo de lo comprometido y ejecutado."""
        nuevo = a_dinero(monto)
        if nuevo < self.comprometido_y_ejecutado:
            raise ReglaNegocioError(
                "RN-023",
                f"El proyecto tiene {formato_cop(self.comprometido_y_ejecutado)} comprometidos y ejecutados.",
                campo="presupuesto_total",
                codigo="NEG_PRESUPUESTO_INSUFICIENTE",
                mensaje_general="El presupuesto no puede ser menor que lo ya comprometido y ejecutado.",
            )
        self.presupuesto_total = nuevo
        self.fecha_aprobacion = date.today()
        self.aprobado_por_id = aprobado_por_id

    def verificar_saldo(self, monto: float) -> None:
        """RN-066: el valor de una compra no puede superar el saldo disponible (422)."""
        if a_dinero(monto) > self.saldo_disponible:
            raise ReglaNegocioError(
                "RN-066",
                f"La compra por {formato_cop(a_dinero(monto))} supera el saldo disponible de "
                f"{formato_cop(self.saldo_disponible)}.",
                campo="monto",
                codigo="NEG_PRESUPUESTO_INSUFICIENTE",
            )

    def comprometer(self, monto: float) -> None:
        """RN-068: reserva el valor de la compra (verificando antes el saldo, RN-066)."""
        self.verificar_saldo(monto)
        self.comprometido = (self.comprometido or Decimal("0")) + a_dinero(monto)

    def liberar(self, monto: float) -> None:
        """RN-069: devuelve al saldo lo comprometido por una compra rechazada o anulada."""
        self.comprometido = max(Decimal("0"), (self.comprometido or Decimal("0")) - a_dinero(monto))

    def ejecutar(self, monto: float) -> None:
        """Al pagar, el valor pasa de comprometido a ejecutado (no cambia el saldo)."""
        valor = a_dinero(monto)
        self.comprometido = max(Decimal("0"), (self.comprometido or Decimal("0")) - valor)
        self.ejecutado = (self.ejecutado or Decimal("0")) + valor

    def revertir_ejecucion(self, monto: float) -> None:
        """HU-23: al anular un pago, el valor vuelve de ejecutado a comprometido (inverso de ejecutar)."""
        valor = a_dinero(monto)
        self.ejecutado = max(Decimal("0"), (self.ejecutado or Decimal("0")) - valor)
        self.comprometido = (self.comprometido or Decimal("0")) + valor
