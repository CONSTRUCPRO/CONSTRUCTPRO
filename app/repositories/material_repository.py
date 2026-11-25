# app/repositories/material_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.material import Categoria, Material


class MaterialRepository:
    """
    Acceso a datos de materiales y categorías: solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, material_id: int) -> Optional[Material]:
        """El material con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Material, material_id)

    def obtener_categoria(self, categoria_id: int) -> Optional[Categoria]:
        """La categoría con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Categoria, categoria_id)

    def existe_duplicado(self, nombre: str, unidad: str, categoria_id: int,
                         excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-031: mismo nombre (sin importar mayúsculas) + unidad + categoría."""
        consulta = select(Material.id).where(
            func.lower(Material.nombre) == nombre.lower(),
            Material.unidad == unidad,
            Material.categoria_id == categoria_id,
        )
        if excluir_id is not None:  # al editar, no se compara consigo mismo
            consulta = consulta.where(Material.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def listar(self, categoria_id: Optional[int], nombre: Optional[str],
               estado: Optional[str], pagina: int,
               por_pagina: int) -> tuple[list[Material], int]:
        """Devuelve (materiales de la página, total de registros que cumplen el filtro)."""
        consulta = select(Material)
        if categoria_id is not None:
            consulta = consulta.where(Material.categoria_id == categoria_id)
        if nombre:
            consulta = consulta.where(Material.nombre.ilike(f"%{nombre.strip()}%"))
        if estado:
            consulta = consulta.where(Material.estado == estado.strip().lower())

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(Material.categoria))  # trae las categorías en 1 consulta
            .order_by(Material.id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, material: Material) -> Material:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)
        return material
