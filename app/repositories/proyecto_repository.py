# app/repositories/proyecto_repository.py
# CAPA REPOSITORIO - HU-05: solo guarda y consulta proyectos. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.orden_compra import ESTADOS_ABIERTOS, OrdenCompra
from app.domain.proyecto import Proyecto
from app.domain.usuario import Usuario


class ProyectoRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, proyecto_id: int) -> Optional[Proyecto]:
        return self.db.get(Proyecto, proyecto_id)

    def obtener_usuario(self, usuario_id: int) -> Optional[Usuario]:
        """Apoya la RN-016: el dominio verifica que el responsable esté activo y su rol."""
        return self.db.get(Usuario, usuario_id)

    def existe_nombre_en_cliente(self, nombre: str, cliente: str,
                                 excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-018: el nombre no se repite para el mismo cliente (sin importar mayúsculas)."""
        consulta = select(Proyecto.id).where(
            func.lower(Proyecto.nombre) == nombre.lower(),
            func.lower(Proyecto.cliente) == cliente.lower(),
        )
        if excluir_id is not None:  # al editar, no se compara consigo mismo
            consulta = consulta.where(Proyecto.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def contar_compromisos_abiertos(self, proyecto_id: int) -> int:
        """
        Apoya la RN-025: órdenes de compra abiertas (emitidas o confirmadas) del proyecto.
        Activada en la HU-21. Una orden con pagos pendientes sigue abierta hasta que se
        cierre, así que este conteo también cubre los pagos pendientes (HU-23).
        """
        return self.db.scalar(
            select(func.count(OrdenCompra.id))
            .where(OrdenCompra.proyecto_id == proyecto_id, OrdenCompra.estado.in_(ESTADOS_ABIERTOS))
        )

    def listar(self, estado: Optional[str], ciudad: Optional[str], cliente: Optional[str],
               responsable_id: Optional[int], pagina: int,
               por_pagina: int) -> tuple[list[Proyecto], int]:
        """Devuelve (proyectos de la página, total de registros que cumplen el filtro)."""
        consulta = select(Proyecto)
        if estado:
            consulta = consulta.where(Proyecto.estado == estado.strip().lower())
        if ciudad:
            consulta = consulta.where(func.lower(Proyecto.ciudad) == ciudad.strip().lower())
        if cliente:
            consulta = consulta.where(Proyecto.cliente.ilike(f"%{cliente.strip()}%"))
        if responsable_id:
            consulta = consulta.where(Proyecto.responsable_id == responsable_id)

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        proyectos = self.db.scalars(
            consulta.options(selectinload(Proyecto.responsable))  # trae el responsable de una vez
            .order_by(Proyecto.id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(proyectos), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, proyecto: Proyecto) -> Proyecto:
        """Sirve para crear y para actualizar: agrega, confirma y recarga desde la BD."""
        self.db.add(proyecto)
        self.db.commit()
        self.db.refresh(proyecto)
        return proyecto
