# app/repositories/solicitud_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.material import Material
from app.domain.proyecto import Proyecto
from app.domain.solicitud import Solicitud, SolicitudDetalle
from app.domain.usuario import Usuario


class SolicitudRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, solicitud_id: int) -> Optional[Solicitud]:
        return self.db.get(Solicitud, solicitud_id)

    def obtener_proyecto(self, proyecto_id: int) -> Optional[Proyecto]:
        return self.db.get(Proyecto, proyecto_id)

    def obtener_usuario(self, usuario_id: int) -> Optional[Usuario]:
        return self.db.get(Usuario, usuario_id)

    def obtener_materiales(self, ids: list[int]) -> dict[int, Material]:
        """Devuelve {id: Material} de los que existan (los que falten no aparecen)."""
        materiales = self.db.scalars(select(Material).where(Material.id.in_(ids))).all()
        return {m.id: m for m in materiales}

    def listar(self, proyecto_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[Solicitud], int]:
        """Devuelve (solicitudes de la página, total de registros que cumplen el filtro)."""
        consulta = select(Solicitud)
        if proyecto_id is not None:
            consulta = consulta.where(Solicitud.proyecto_id == proyecto_id)
        if estado:
            consulta = consulta.where(Solicitud.estado == estado.strip().lower())

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(Solicitud.detalle).selectinload(SolicitudDetalle.material))
            .order_by(Solicitud.id.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, solicitud: Solicitud) -> Solicitud:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(solicitud)
        self.db.commit()
        self.db.refresh(solicitud)
        return solicitud
