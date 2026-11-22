# app/domain/aprobacion.py
# CAPA DOMINIO: la entidad (tabla) Aprobacion.
#
# VERSIÓN MÍNIMA creada en la HU-17 (Alejandro): al enviar una cotización se abre su aprobación
# en estado "En revisión" (caso 2 de la HU-17).
# La HU-20 (Jaime, Decisión de Aprobación) la amplía con su propia migración: aprobador,
# fecha y observación de la decisión, estados Aprobada / Rechazada, topes por rol y
# segregación de funciones. Al aprobar o rechazar, la HU-20 también cambia el estado de la
# cotización (Cotizacion.estado = "Aprobada" / "Rechazada").
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.cotizacion import Cotizacion

ESTADO_EN_REVISION = "En revisión"
ESTADO_ANULADA = "Anulada"        # la cotización se anuló mientras estaba en revisión


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Aprobacion(Base):
    __tablename__ = "aprobaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_EN_REVISION)
    monto: Mapped[Decimal] = mapped_column(Numeric(16, 2))        # total de la cotización
    enviado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_envio: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    cotizacion: Mapped[Cotizacion] = relationship()

    @classmethod
    def abrir(cls, cotizacion: Cotizacion, enviado_por_id: Optional[int]) -> "Aprobacion":
        """Crea la aprobación En revisión por el total de la cotización enviada."""
        return cls(cotizacion=cotizacion, estado=ESTADO_EN_REVISION, monto=cotizacion.total,
                   enviado_por_id=enviado_por_id)

    def esta_en_revision(self) -> bool:
        return self.estado == ESTADO_EN_REVISION

    def cancelar(self) -> None:
        """Si la cotización se anula mientras está en revisión, la aprobación queda Anulada."""
        if self.esta_en_revision():
            self.estado = ESTADO_ANULADA
