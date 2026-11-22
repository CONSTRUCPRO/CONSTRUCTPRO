# app/repositories/proveedor_material_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.material import Material
from app.domain.proveedor import ESTADO_ACTIVO, Proveedor
from app.domain.proveedor_material import ProveedorMaterial


class ProveedorMaterialRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_proveedor(self, proveedor_id: int) -> Optional[Proveedor]:
        return self.db.get(Proveedor, proveedor_id)

    def obtener_material(self, material_id: int) -> Optional[Material]:
        return self.db.get(Material, material_id)

    def obtener_oferta(self, proveedor_id: int, material_id: int) -> Optional[ProveedorMaterial]:
        """La oferta de ese proveedor para ese material, si ya existe."""
        return self.db.scalar(
            select(ProveedorMaterial).where(
                ProveedorMaterial.proveedor_id == proveedor_id,
                ProveedorMaterial.material_id == material_id,
            )
        )

    def listar_por_material(self, material_id: int, pagina: int,
                            por_pagina: int) -> tuple[list[ProveedorMaterial], int]:
        """Ofertas de un material, SOLO de proveedores activos. Devuelve (página, total)."""
        consulta = (
            select(ProveedorMaterial)
            .join(ProveedorMaterial.proveedor)
            .where(ProveedorMaterial.material_id == material_id,
                   Proveedor.estado == ESTADO_ACTIVO)
        )
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(ProveedorMaterial.proveedor))
            .order_by(ProveedorMaterial.proveedor_id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, oferta: ProveedorMaterial) -> ProveedorMaterial:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(oferta)
        self.db.commit()
        self.db.refresh(oferta)
        return oferta
