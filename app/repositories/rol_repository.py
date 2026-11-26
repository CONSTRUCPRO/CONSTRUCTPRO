# app/repositories/rol_repository.py
# CAPA REPOSITORIO - HU-03: solo guarda y consulta roles. Sin reglas de negocio.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.rol import Rol


class RolRepository:
    """
    Acceso a datos de roles: solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    def obtener_por_id(self, rol_id: int) -> Optional[Rol]:
        """El rol con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Rol, rol_id)

    def obtener_por_nombre(self, nombre: str) -> Optional[Rol]:
        """
        El rol con ese nombre sin importar mayúsculas (lo usa requiere_permiso con el rol del token).
        """
        return self.db.scalar(select(Rol).where(func.lower(Rol.nombre) == nombre.lower()))

    def existe_nombre(self, nombre: str, excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-011: ¿ya hay otro rol con ese nombre? Al editar se excluye el propio rol."""
        consulta = select(Rol.id).where(func.lower(Rol.nombre) == nombre.lower())
        if excluir_id is not None:
            consulta = consulta.where(Rol.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def listar(self, estado: Optional[str], pagina: int, por_pagina: int) -> tuple[list[Rol], int]:
        """
        Roles de la página pedida y el total, para data.paginacion. Se pagina en la BD (offset/limit).
        """
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
        """
        Guarda el rol y sus permisos (nuevo o modificado): add + commit, y refresh para recargar lo que puso
        la BD (id, fechas). Sirve igual para crear y para actualizar.
        """
        self.db.add(rol)
        self.db.commit()
        self.db.refresh(rol)
        return rol
