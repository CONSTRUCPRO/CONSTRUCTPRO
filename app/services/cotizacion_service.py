# app/services/cotizacion_service.py
# CAPA SERVICIO: orquesta los casos de uso de la cotización.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.aprobacion import Aprobacion
from app.domain.cotizacion import Cotizacion, hoy_utc
from app.domain.excepciones import ConflictoEstadoError, RecursoNoEncontradoError
from app.repositories.cotizacion_repository import CotizacionRepository
from app.schemas.cotizacion import CotizacionCreate, CotizacionResponse


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class CotizacionService:

    def __init__(self, repo: CotizacionRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, cotizacion_id: int) -> Cotizacion:
        cotizacion = self.repo.obtener_por_id(cotizacion_id)
        if not cotizacion:
            raise RecursoNoEncontradoError(
                f"No existe una cotización con el identificador {cotizacion_id}.",
                campo="cotizacion_id")
        return cotizacion

    def _respuesta(self, cotizacion: Cotizacion) -> CotizacionResponse:
        return CotizacionResponse.desde_modelo(
            cotizacion, self.repo.ultima_aprobacion(cotizacion.id))

    # ── Casos de uso ───────────────────────────────────────

    def generar(self, datos: CotizacionCreate) -> CotizacionResponse:
        ids = list(dict.fromkeys(datos.comparativo_ids))              # sin repetidos, en orden
        comparativos = self.repo.obtener_comparativos(ids)
        faltantes = [i for i in ids if i not in comparativos]
        if faltantes:
            raise RecursoNoEncontradoError(
                f"No existe el comparativo {faltantes[0]}.", campo="comparativo_ids")
        ya_cotizados = self.repo.comparativos_ya_cotizados(ids)
        if ya_cotizados:
            raise ConflictoEstadoError(
                None, f"El comparativo {ya_cotizados[0]} ya está en otra cotización que no fue "
                      f"anulada.", campo="comparativo_ids")
        cotizacion = Cotizacion.generar([comparativos[i] for i in ids], hoy_utc())  # RN-061..063
        return self._respuesta(self.repo.guardar(cotizacion))

    def obtener(self, cotizacion_id: int) -> CotizacionResponse:
        return self._respuesta(self._buscar(cotizacion_id))

    def listar(self, proyecto_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[CotizacionResponse], dict]:
        items, total = self.repo.listar(proyecto_id, estado, pagina, por_pagina)
        return ([self._respuesta(c) for c in items],
                construir_paginacion(pagina, por_pagina, total))

    def anular(self, cotizacion_id: int) -> CotizacionResponse:
        cotizacion = self._buscar(cotizacion_id)
        cotizacion.anular()                                            # RN-064
        aprobacion = self.repo.ultima_aprobacion(cotizacion.id)
        if aprobacion is not None:
            aprobacion.cancelar()                                      # si estaba en revisión
        return self._respuesta(self.repo.guardar(cotizacion, aprobacion))

    def enviar(self, cotizacion_id: int, usuario_id: Optional[str]) -> CotizacionResponse:
        cotizacion = self._buscar(cotizacion_id)
        cotizacion.enviar(hoy_utc())                                   # RN-065, RN-066
        aprobacion = Aprobacion.abrir(cotizacion, _a_entero(usuario_id))
        return self._respuesta(self.repo.guardar(cotizacion, aprobacion))