# app/repositories/rol_repository.py
# CAPA REPOSITORIO - HU-03: solo guarda y consulta roles. Sin reglas de negocio.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.rol import Rol


class RolRepository:

    def __init__(self, db: Session):
        self.db = db

    def obtener_por_id(self, rol_id: int) -> Optional[Rol]:
        return self.db.get(Rol, rol_id)

    def obtener_por_nombre(self, nombre: str) -> Optional[Rol]:
        return self.db.scalar(select(Rol).where(func.lower(Rol.nombre) == nombre.lower()))

    def existe_nombre(self, nombre: str, excluir_id: Optional[int] = None) -> bool:
        consulta = select(Rol.id).where(func.lower(Rol.nombre) == nombre.lower())
        if excluir_id is not None:
            consulta = consulta.where(Rol.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def listar(self, estado: Optional[str], pagina: int, por_pagina: int) -> tuple[list[Rol], int]:
        consulta = select(Rol)
        if estado:
            consulta = consulta.where(Rol.estado == estado)
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        roles = self.db.scalars(
            consulta.order_by(Rol.id).offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(roles), total

    def contar_usuarios_activos(self, rol_id: int) -> int:
        """Apoya la RN-012: cuántos usuarios activos tienen asignado este rol."""
        # Import local: usuario.py ya importa rol.py, así se evita un import circular.
        from app.domain.usuario import Usuario
        return self.db.scalar(
            select(func.count(Usuario.id))
            .where(Usuario.rol_id == rol_id, Usuario.estado == "activo")
        )

    def guardar(self, rol: Rol) -> Rol:
        self.db.add(rol)
        self.db.commit()
        self.db.refresh(rol)
        return rol
