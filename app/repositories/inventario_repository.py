# app/repositories/inventario_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.inventario import Inventario, MovimientoInventario
from app.domain.material import Material
from app.domain.orden_compra import OrdenCompra
from app.domain.proyecto import Proyecto


class InventarioRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_orden(self, orden_compra_id: int) -> Optional[OrdenCompra]:
        return self.db.get(OrdenCompra, orden_compra_id)

    def obtener_proyecto(self, proyecto_id: int) -> Optional[Proyecto]:
        return self.db.get(Proyecto, proyecto_id)

    def obtener_material(self, material_id: int) -> Optional[Material]:
        return self.db.get(Material, material_id)

    def existencia(self, proyecto_id: int, material_id: int) -> Optional[Inventario]:
        """El registro de inventario de ese material en ese proyecto, si existe."""
        return self.db.scalar(select(Inventario).where(Inventario.proyecto_id == proyecto_id,
                                                       Inventario.material_id == material_id))

    def entrada_registrada(self, orden_compra_id: int) -> bool:
        """¿La orden ya dio entrada al inventario? (cada recepción entra una sola vez)."""
        return self.db.scalar(
            select(MovimientoInventario.id).where(
                MovimientoInventario.orden_compra_id == orden_compra_id).limit(1)
        ) is not None

    def listar_existencias(self, proyecto_id: int, pagina: int,
                           por_pagina: int) -> tuple[list[Inventario], int]:
        """Existencias del proyecto, ordenadas por material. Devuelve (página, total)."""
        consulta = select(Inventario).where(Inventario.proyecto_id == proyecto_id)
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(Inventario.material))
            .order_by(Inventario.material_id)
            .offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(items), total

    def listar_movimientos(self, proyecto_id: int, material_id: Optional[int], tipo: Optional[str],
                           pagina: int, por_pagina: int) -> tuple[list[MovimientoInventario], int]:
        """Movimientos del proyecto, del más reciente al más antiguo. Devuelve (página, total)."""
        consulta = select(MovimientoInventario).where(MovimientoInventario.proyecto_id == proyecto_id)
        if material_id is not None:
            consulta = consulta.where(MovimientoInventario.material_id == material_id)
        if tipo:
            consulta = consulta.where(MovimientoInventario.tipo == tipo.strip().lower())
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(MovimientoInventario.material))
            .order_by(MovimientoInventario.id.desc())
            .offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, *objetos) -> None:
        """Guarda todo en una sola transacción (inventario, movimientos u orden)."""
        self.db.add_all(objetos)
        self.db.commit()
        for objeto in objetos:
            self.db.refresh(objeto)
