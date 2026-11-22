# app/repositories/presupuesto_repository.py
# CAPA REPOSITORIO - HU-06: solo guarda y consulta. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.presupuesto import Presupuesto
from app.domain.proyecto import Proyecto


class PresupuestoRepository:

    def __init__(self, db: Session):
        self.db = db

    def obtener_proyecto(self, proyecto_id: int) -> Optional[Proyecto]:
        """El proyecto con su presupuesto (proyecto.presupuesto es None si no tiene)."""
        return self.db.get(Proyecto, proyecto_id)

    def guardar(self, presupuesto: Presupuesto) -> Presupuesto:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(presupuesto)
        self.db.commit()
        self.db.refresh(presupuesto)
        return presupuesto
