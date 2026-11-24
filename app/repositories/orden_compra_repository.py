# app/repositories/orden_compra_repository.py
# CAPA REPOSITORIO - HU-21: solo guarda y consulta órdenes de compra. Sin reglas, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.aprobacion import Aprobacion
from app.domain.orden_compra import OrdenCompra
from app.domain.pago import ESTADO_REGISTRADO, Pago
from app.domain.proveedor import Proveedor


class OrdenCompraRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, orden_id: int) -> Optional[OrdenCompra]:
        return self.db.get(OrdenCompra, orden_id)

    def obtener_aprobacion(self, aprobacion_id: int) -> Optional[Aprobacion]:
        return self.db.get(Aprobacion, aprobacion_id)

    def obtener_proveedor(self, proveedor_id: int) -> Optional[Proveedor]:
        return self.db.get(Proveedor, proveedor_id)

    def orden_de_cotizacion(self, cotizacion_id: int) -> Optional[OrdenCompra]:
        """Apoya la RN-083: la orden que ya tenga esa cotización (sin importar su estado)."""
        return self.db.scalar(select(OrdenCompra).where(OrdenCompra.cotizacion_id == cotizacion_id))

    def contar_pagos(self, orden_id: int) -> int:
        """Apoya la RN-084: pagos vigentes (no anulados) de la orden (HU-23)."""
        return self.db.scalar(
            select(func.count()).select_from(Pago)
            .where(Pago.orden_compra_id == orden_id, Pago.estado == ESTADO_REGISTRADO)
        ) or 0

    def contar_envios(self, orden_id: int) -> int:
        """
        Apoya la RN-084. Los envíos son del módulo de Logística, que no está en este sprint;
        mientras tanto cuenta la recepción de la HU-29: una orden recibida no se anula.
        """
        orden = self.db.get(OrdenCompra, orden_id)
        return 1 if orden is not None and orden.fecha_recepcion is not None else 0

    def listar(self, proyecto_id: Optional[int], proveedor_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[OrdenCompra], int]:
        consulta = select(OrdenCompra)
        if proyecto_id:
            consulta = consulta.where(OrdenCompra.proyecto_id == proyecto_id)
        if proveedor_id:
            consulta = consulta.where(OrdenCompra.proveedor_id == proveedor_id)
        if estado:
            consulta = consulta.where(OrdenCompra.estado == estado.strip().lower())
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(OrdenCompra.detalle), selectinload(OrdenCompra.proveedor))
            .order_by(OrdenCompra.id.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, orden: OrdenCompra) -> OrdenCompra:
        """Guarda la orden (y el presupuesto liberado, si se anuló) en la misma transacción."""
        self.db.add(orden)
        self.db.commit()
        self.db.refresh(orden)
        return orden
