# app/services/aprobacion_service.py
# CAPA SERVICIO - HU-20: consultar aprobaciones, decidir (aprobar o rechazar) y el histórico.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from datetime import date
from decimal import Decimal
from typing import Optional

from app.core.config import settings
from app.core.respuestas import construir_paginacion
from app.domain.aprobacion import ESTADO_EN_REVISION, Aprobacion
from app.domain.excepciones import NoAutenticadoError, RecursoNoEncontradoError
from app.repositories.aprobacion_repository import AprobacionRepository
from app.api.schemas.aprobacion import AprobacionResponse, DecisionDatos


class AprobacionService:
    """
    Casos de uso de la decisión de aprobación (HU-20). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: AprobacionRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    def _buscar(self, aprobacion_id: int) -> Aprobacion:
        """Trae la aprobación por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        aprobacion = self.repo.obtener_por_id(aprobacion_id)
        if not aprobacion:
            raise RecursoNoEncontradoError(
                f"No existe una aprobación con el identificador {aprobacion_id}.",
                campo="aprobacion_id")
        return aprobacion

    @staticmethod
    def _pagina(items: list[Aprobacion], total: int, pagina: int,
                por_pagina: int) -> tuple[list[AprobacionResponse], dict]:
        """Convierte una página de aprobaciones en respuestas con su meta.paginacion."""
        return ([AprobacionResponse.desde_modelo(a) for a in items],
                construir_paginacion(pagina, por_pagina, total))

    # ── Casos de uso ───────────────────────────────────────

    def listar(self, estado: Optional[str], proyecto_id: Optional[int],
               pagina: int, por_pagina: int) -> tuple[list[AprobacionResponse], dict]:
        """Compras por estado; si no se indica, las que esperan decisión (En revisión)."""
        items, total = self.repo.listar(estado or ESTADO_EN_REVISION, proyecto_id, pagina, por_pagina)
        return self._pagina(items, total, pagina, por_pagina)

    def obtener(self, aprobacion_id: int) -> AprobacionResponse:
        """Una aprobación con su decisión, si ya la tiene."""
        return AprobacionResponse.desde_modelo(self._buscar(aprobacion_id))

    def historico(self, proyecto_id: Optional[int], aprobador_id: Optional[int],
                  desde: Optional[date], hasta: Optional[date],
                  pagina: int, por_pagina: int) -> tuple[list[AprobacionResponse], dict]:
        """
        FUN-079: las ya decididas, la más reciente primero, con filtros por proyecto, aprobador y fechas.
        """
        items, total = self.repo.historico(proyecto_id, aprobador_id, desde, hasta, pagina, por_pagina)
        return self._pagina(items, total, pagina, por_pagina)

    def decidir(self, aprobacion_id: int, datos: DecisionDatos,
                usuario_id: Optional[str]) -> AprobacionResponse:
        """FUN-076 / FUN-077 / FUN-078: aprobar o rechazar una compra en revisión."""
        aprobacion = self._buscar(aprobacion_id)                                 # 404
        aprobador = self.repo.obtener_usuario(int(usuario_id)) if usuario_id else None
        if aprobador is None:
            raise NoAutenticadoError("No se pudo identificar al usuario de la sesión.",
                                     campo="Authorization")
        solicitantes = self.repo.solicitantes_de(aprobacion.cotizacion_id)
        aprobacion.decidir(datos.decision, aprobador, datos.motivo, solicitantes,
                           Decimal(str(settings.TOPE_APROBACION_COORDINADOR)))   # RN-066..079
        return AprobacionResponse.desde_modelo(self.repo.guardar(aprobacion))
