# app/repositories/comparativo_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.comparativo import Comparativo
from app.domain.material import Material
from app.domain.proveedor import ESTADO_ACTIVO, Proveedor
from app.domain.proveedor_material import ProveedorMaterial
from app.domain.solicitud import Solicitud


class ComparativoRepository:
    """
    Acceso a datos de comparativos: solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, comparativo_id: int) -> Optional[Comparativo]:
        """El comparativo con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Comparativo, comparativo_id)

    def obtener_solicitud(self, solicitud_id: int) -> Optional[Solicitud]:
        """La solicitud con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Solicitud, solicitud_id)

    def obtener_material(self, material_id: int) -> Optional[Material]:
        """El material con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Material, material_id)

    def existe(self, solicitud_id: int, material_id: int) -> bool:
        """¿Ya hay un comparativo para ese material de esa solicitud?"""
        return self.db.scalar(
            select(Comparativo.id).where(Comparativo.solicitud_id == solicitud_id,
                                         Comparativo.material_id == material_id)
        ) is not None

    def ofertas_de_material(self, material_id: int) -> list[ProveedorMaterial]:
        """Ofertas del material en proveedor_material (HU-11), SOLO de proveedores activos."""
        return list(self.db.scalars(
            select(ProveedorMaterial)
            .join(ProveedorMaterial.proveedor)
            .where(ProveedorMaterial.material_id == material_id,
                   Proveedor.estado == ESTADO_ACTIVO)
        ).all())

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, comparativo: Comparativo) -> Comparativo:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(comparativo)
        self.db.commit()
        self.db.refresh(comparativo)
        return comparativo
