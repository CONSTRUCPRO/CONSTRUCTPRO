# app/repositories/proveedor_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.proveedor import Proveedor


class ProveedorRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, proveedor_id: int) -> Optional[Proveedor]:
        return self.db.get(Proveedor, proveedor_id)

    def existe_nit(self, nit: str, excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-036: el NIT no se repite en el sistema."""
        consulta = select(Proveedor.id).where(Proveedor.nit == nit)
        if excluir_id is not None:  # al editar, no se compara consigo mismo
            consulta = consulta.where(Proveedor.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def contar_ordenes_abiertas(self, proveedor_id: int) -> int:
        """
        Apoya la RN-040: cuántas órdenes de compra abiertas tiene el proveedor.
        PENDIENTE HU-21 (Jaime): la tabla de órdenes de compra todavía no existe,
        así que por ahora devuelve 0. Cuando exista, aquí se cuentan las órdenes
        de este proveedor en estado abierto (ej. "emitida"). El servicio y el
        dominio ya usan este valor, así que solo cambia este método.
        """
        return 0

    def listar(self, estado: Optional[str], razon_social: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[Proveedor], int]:
        """Devuelve (proveedores de la página, total de registros que cumplen el filtro)."""
        consulta = select(Proveedor)
        if estado:
            consulta = consulta.where(Proveedor.estado == estado.strip().lower())
        if razon_social:
            consulta = consulta.where(Proveedor.razon_social.ilike(f"%{razon_social.strip()}%"))

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.order_by(Proveedor.id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, proveedor: Proveedor) -> Proveedor:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(proveedor)
        self.db.commit()
        self.db.refresh(proveedor)
        return proveedor
