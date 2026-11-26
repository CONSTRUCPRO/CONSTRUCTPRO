# app/repositories/presupuesto_repository.py
# CAPA REPOSITORIO - HU-06: solo guarda y consulta. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy.orm import Session

from app.domain.presupuesto import Presupuesto
from app.domain.proyecto import Proyecto


class PresupuestoRepository:
    """
    Acceso a datos de presupuestos (se llega al presupuesto a través del proyecto): solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
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
