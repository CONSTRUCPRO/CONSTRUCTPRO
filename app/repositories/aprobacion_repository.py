# app/repositories/aprobacion_repository.py
# CAPA REPOSITORIO - HU-20: solo guarda y consulta aprobaciones. Sin reglas de negocio, sin HTTP.
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.aprobacion import ESTADO_APROBADA, ESTADO_RECHAZADA, Aprobacion
from app.domain.comparativo import Comparativo
from app.domain.cotizacion import Cotizacion, CotizacionDetalle
from app.domain.solicitud import Solicitud
from app.domain.usuario import Usuario


class AprobacionRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── Consultas ──────────────────────────────────────────

    def obtener_por_id(self, aprobacion_id: int) -> Optional[Aprobacion]:
        return self.db.get(Aprobacion, aprobacion_id)

    def obtener_usuario(self, usuario_id: int) -> Optional[Usuario]:
        return self.db.get(Usuario, usuario_id)

    def solicitantes_de(self, cotizacion_id: int) -> set[int]:
        """
        Apoya la RN-073: quiénes solicitaron los materiales de la cotización
        (cotizacion_detalles → comparativos → solicitudes.solicitante_id).
        """
        consulta = (
            select(Solicitud.solicitante_id)
            .join(Comparativo, Comparativo.solicitud_id == Solicitud.id)
            .join(CotizacionDetalle, CotizacionDetalle.comparativo_id == Comparativo.id)
            .where(CotizacionDetalle.cotizacion_id == cotizacion_id)
        )
        return set(self.db.scalars(consulta).all())

    def _paginar(self, consulta, orden, pagina: int, por_pagina: int) -> tuple[list[Aprobacion], int]:
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.options(selectinload(Aprobacion.cotizacion))
            .order_by(*orden).offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(items), total

    def listar(self, estado: Optional[str], proyecto_id: Optional[int],
               pagina: int, por_pagina: int) -> tuple[list[Aprobacion], int]:
        """Aprobaciones por estado (por defecto, las que están En revisión), las más antiguas primero."""
        consulta = select(Aprobacion).join(Aprobacion.cotizacion)
        if estado:
            consulta = consulta.where(func.lower(Aprobacion.estado) == estado.strip().lower())
        if proyecto_id:
            consulta = consulta.where(Cotizacion.proyecto_id == proyecto_id)
        return self._paginar(consulta, (Aprobacion.fecha_envio, Aprobacion.id), pagina, por_pagina)

    def historico(self, proyecto_id: Optional[int], aprobador_id: Optional[int],
                  desde: Optional[date], hasta: Optional[date],
                  pagina: int, por_pagina: int) -> tuple[list[Aprobacion], int]:
        """FUN-079: aprobaciones ya decididas, de la más reciente a la más antigua."""
        consulta = (select(Aprobacion).join(Aprobacion.cotizacion)
                    .where(Aprobacion.estado.in_((ESTADO_APROBADA, ESTADO_RECHAZADA))))
        if proyecto_id:
            consulta = consulta.where(Cotizacion.proyecto_id == proyecto_id)
        if aprobador_id:
            consulta = consulta.where(Aprobacion.aprobador_id == aprobador_id)
        if desde:
            consulta = consulta.where(Aprobacion.fecha_decision >= datetime.combine(desde, time.min))
        if hasta:
            consulta = consulta.where(Aprobacion.fecha_decision < datetime.combine(hasta + timedelta(days=1), time.min))
        return self._paginar(consulta, (Aprobacion.fecha_decision.desc(), Aprobacion.id.desc()),
                             pagina, por_pagina)

    # ── Escritura ──────────────────────────────────────────

    def guardar(self, aprobacion: Aprobacion) -> Aprobacion:
        """Guarda la aprobación; por la relación, también la cotización y el presupuesto modificados."""
        self.db.add(aprobacion)
        self.db.commit()
        self.db.refresh(aprobacion)
        return aprobacion
