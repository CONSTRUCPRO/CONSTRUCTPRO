# app/repositories/usuario_repository.py
# CAPA REPOSITORIO - HU-01: solo guarda y consulta usuarios. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.rol import Rol
from app.domain.usuario import Usuario


class UsuarioRepository:
    """
    Acceso a datos de usuarios: solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, usuario_id: int) -> Optional[Usuario]:
        """El usuario con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Usuario, usuario_id)

    def obtener_rol(self, rol_id: int) -> Optional[Rol]:
        """Apoya la RN-002: el servicio verifica que el rol exista y esté activo."""
        return self.db.get(Rol, rol_id)

    def existe_correo(self, correo: str, excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-001: el correo no se repite."""
        consulta = select(Usuario.id).where(func.lower(Usuario.correo) == correo.lower())
        if excluir_id is not None:  # al editar, no se compara consigo mismo
            consulta = consulta.where(Usuario.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def existe_documento(self, numero_documento: str, excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-001: el número de documento no se repite."""
        consulta = select(Usuario.id).where(Usuario.numero_documento == numero_documento)
        if excluir_id is not None:
            consulta = consulta.where(Usuario.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def listar(self, estado: Optional[str], rol_id: Optional[int], nombre: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[Usuario], int]:
        """Devuelve (usuarios de la página, total de registros que cumplen el filtro)."""
        consulta = select(Usuario)
        if estado:
            consulta = consulta.where(Usuario.estado == estado.strip().lower())
        if rol_id:
            consulta = consulta.where(Usuario.rol_id == rol_id)
        if nombre:
            consulta = consulta.where(Usuario.nombre_completo.ilike(f"%{nombre.strip()}%"))

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        usuarios = self.db.scalars(
            consulta.options(selectinload(Usuario.rol))   # trae el rol en la misma consulta
            .order_by(Usuario.id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(usuarios), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, usuario: Usuario) -> Usuario:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(usuario)
        self.db.commit()
        self.db.refresh(usuario)
        return usuario
