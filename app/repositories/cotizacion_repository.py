# app/repositories/cotizacion_repository.py
# CAPA REPOSITORIO: solo guarda y consulta en la BD. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.aprobacion import Aprobacion
from app.domain.comparativo import Comparativo
from app.domain.cotizacion import ESTADO_ANULADA, Cotizacion, CotizacionDetalle


class CotizacionRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, cotizacion_id: int) -> Optional[Cotizacion]:
        return self.db.get(Cotizacion, cotizacion_id)

    def obtener_comparativos(self, ids: list[int]) -> dict[int, Comparativo]:
        """Devuelve {id: Comparativo} de los que existan (los que falten no aparecen)."""
        comparativos = self.db.scalars(select(Comparativo).where(Comparativo.id.in_(ids))).all()
        return {c.id: c for c in comparativos}

    def comparativos_ya_cotizados(self, ids: list[int]) -> list[int]:
        """Comparativos que ya están en una cotización que no fue anulada."""
        return list(self.db.scalars(
            select(CotizacionDetalle.comparativo_id)
            .join(CotizacionDetalle.cotizacion)
            .where(CotizacionDetalle.comparativo_id.in_(ids),
                   Cotizacion.estado != ESTADO_ANULADA)
        ).all())

    def ultima_aprobacion(self, cotizacion_id: int) -> Optional[Aprobacion]:
        return self.db.scalar(
            select(Aprobacion).where(Aprobacion.cotizacion_id == cotizacion_id)
            .order_by(Aprobacion.id.desc()).limit(1)
        )

    def listar(self, proyecto_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[Cotizacion], int]:
        """Devuelve (cotizaciones de la página, total de registros que cumplen el filtro)."""
        consulta = select(Cotizacion)
        if proyecto_id is not None:
            consulta = consulta.where(Cotizacion.proyecto_id == proyecto_id)
        if estado:
            consulta = consulta.where(func.lower(Cotizacion.estado) == estado.strip().lower())

        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(Cotizacion.detalle))
            .order_by(Cotizacion.id.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
        ).all()
        return list(items), total

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, cotizacion: Cotizacion,
                aprobacion: Optional[Aprobacion] = None) -> Cotizacion:
        """Guarda la cotización (y, si viene, su aprobación) en una sola transacción."""
        self.db.add(cotizacion)
        if aprobacion is not None:
            self.db.add(aprobacion)
        self.db.commit()
        self.db.refresh(cotizacion)
        return cotizacion