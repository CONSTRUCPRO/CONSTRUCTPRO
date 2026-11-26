# app/repositories/pago_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.orden_compra import OrdenCompra
from app.domain.pago import ESTADO_REGISTRADO, Pago


class PagoRepository:
    """
    Acceso a datos de pagos: solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, pago_id: int) -> Optional[Pago]:
        """El pago con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Pago, pago_id)

    def obtener_orden(self, orden_compra_id: int) -> Optional[OrdenCompra]:
        """La orden con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(OrdenCompra, orden_compra_id)

    def total_pagado(self, orden_compra_id: int) -> Decimal:
        """Suma de los pagos vigentes (no anulados) de la orden: apoya la RN-091."""
        total = self.db.scalar(
            select(func.coalesce(func.sum(Pago.monto), 0))
            .where(Pago.orden_compra_id == orden_compra_id, Pago.estado == ESTADO_REGISTRADO)
        )
        return Decimal(str(total or 0))

    def pagos_de_orden(self, orden_compra_id: int) -> list[Pago]:
        """Todos los pagos de la orden, incluidos los anulados, del más antiguo al más reciente."""
        return list(self.db.scalars(
            select(Pago).where(Pago.orden_compra_id == orden_compra_id).order_by(Pago.id)
        ).all())

    # ── Escritura ──────────────────────────────────────────

    def registrar(self, pago: Pago) -> Pago:
        """Guarda un pago nuevo y le asigna su número de transacción (necesita el id)."""
        self.db.add(pago)
        self.db.flush()                      # asigna el id sin confirmar todavía
        pago.asignar_numero_transaccion()
        self.db.commit()                     # pago y presupuesto en una sola transacción
        self.db.refresh(pago)
        return pago

    def guardar(self, pago: Pago) -> Pago:
        """
        Guarda el pago (por ejemplo, al anularlo) (nuevo o modificado): add + commit, y refresh para recargar lo que puso
        la BD (id, fechas). Sirve igual para crear y para actualizar.
        """
        self.db.add(pago)
        self.db.commit()
        self.db.refresh(pago)
        return pago
