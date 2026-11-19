# app/domain/proveedor.py
# CAPA DOMINIO: la entidad (tabla) Proveedor y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Reglas de la HU-10:
#   RN-036  El NIT es único en el sistema.
#           (la consulta la hace el servicio; además queda la restricción UNIQUE en la BD)
#   RN-039  Un proveedor inactivo no puede recibir nuevas órdenes de compra.
#           (la usará la HU-21 de Jaime con verificar_puede_recibir_ordenes())
#   RN-040  Un proveedor con órdenes de compra abiertas no puede inactivarse.
#   El formato de correo y teléfono se valida en el schema (422 VAL_FORMATO_INVALIDO).
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError

ESTADO_ACTIVO = "activo"
ESTADO_INACTIVO = "inactivo"


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Proveedor(Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    razon_social: Mapped[str] = mapped_column(String(150))
    nit: Mapped[str] = mapped_column(String(20), unique=True)   # RN-036 también en la BD
    contacto: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str] = mapped_column(String(20))
    correo: Mapped[str] = mapped_column(String(120))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_ACTIVO)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )

    # ── Reglas de negocio ─────────────────────────────────

    @classmethod
    def registrar(cls, razon_social: str, nit: str, contacto: str,
                  telefono: str, correo: str) -> "Proveedor":
        """Crea un proveedor nuevo. Siempre nace activo."""
        return cls(razon_social=razon_social, nit=nit, contacto=contacto,
                   telefono=telefono, correo=correo, estado=ESTADO_ACTIVO)

    def editar(self, razon_social: str, nit: str, contacto: str,
               telefono: str, correo: str) -> None:
        """Edita los datos del proveedor. El estado no cambia aquí."""
        self.razon_social = razon_social
        self.nit = nit
        self.contacto = contacto
        self.telefono = telefono
        self.correo = correo

    def esta_activo(self) -> bool:
        return self.estado == ESTADO_ACTIVO

    def cambiar_estado(self, nuevo_estado: str, ordenes_abiertas: int) -> None:
        """
        Inactiva o reactiva el proveedor.
        RN-040: no se puede inactivar si tiene órdenes de compra abiertas.
        Si ya está en ese estado, es un conflicto (409).
        """
        if self.estado == nuevo_estado:
            raise ConflictoEstadoError(
                None,
                f"El proveedor ya se encuentra en estado '{nuevo_estado}'.",
                campo="estado",
            )
        if nuevo_estado == ESTADO_INACTIVO and ordenes_abiertas > 0:
            raise ConflictoEstadoError(
                "RN-040",
                f"El proveedor tiene {ordenes_abiertas} orden(es) de compra abierta(s) "
                f"y no puede inactivarse.",
                campo="estado",
            )
        self.estado = nuevo_estado

    def verificar_puede_recibir_ordenes(self) -> None:
        """
        RN-039: un proveedor inactivo no puede recibir nuevas órdenes de compra.
        La llamará la HU-21 (orden de compra) antes de crear la orden.
        """
        if not self.esta_activo():
            raise ConflictoEstadoError(
                "RN-039",
                f"El proveedor '{self.razon_social}' está inactivo y no puede "
                f"recibir nuevas órdenes de compra.",
                campo="proveedor_id",
            )
