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
from app.api.schemas.cotizacion import CotizacionCreate, CotizacionResponse


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    """El usuario_id del token llega como texto; se guarda como número (None si no viene)."""
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class CotizacionService:
    """
    Casos de uso de cotizaciones (HU-17). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: CotizacionRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, cotizacion_id: int) -> Cotizacion:
        """Trae la cotización por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        cotizacion = self.repo.obtener_por_id(cotizacion_id)
        if not cotizacion:
            raise RecursoNoEncontradoError(
                f"No existe una cotización con el identificador {cotizacion_id}.",
                campo="cotizacion_id")
        return cotizacion

    def _respuesta(self, cotizacion: Cotizacion) -> CotizacionResponse:
        """Arma la respuesta incluyendo el resumen de su última aprobación."""
        return CotizacionResponse.desde_modelo(
            cotizacion, self.repo.ultima_aprobacion(cotizacion.id))

    # ── Casos de uso ───────────────────────────────────────

    def generar(self, datos: CotizacionCreate) -> CotizacionResponse:
        """
        Genera la cotización con los comparativos pedidos (sin repetidos). Valida que existan, que
        no estén en otra cotización vigente y las reglas RN-061, RN-062 y RN-063 del dominio.
        """
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
        """Una cotización con su detalle y su aprobación."""
        return self._respuesta(self._buscar(cotizacion_id))

    def listar(self, proyecto_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[CotizacionResponse], dict]:
        """Lista paginada con filtros por proyecto y estado (útil para ver las Enviadas)."""
        items, total = self.repo.listar(proyecto_id, estado, pagina, por_pagina)
        return ([self._respuesta(c) for c in items],
                construir_paginacion(pagina, por_pagina, total))

    def anular(self, cotizacion_id: int) -> CotizacionResponse:
        """
        Anula la cotización (RN-064: no si está Aprobada) y cancela su aprobación si estaba en revisión.
        """
        cotizacion = self._buscar(cotizacion_id)
        cotizacion.anular()                                            # RN-064
        aprobacion = self.repo.ultima_aprobacion(cotizacion.id)
        if aprobacion is not None:
            aprobacion.cancelar()                                      # si estaba en revisión
        return self._respuesta(self.repo.guardar(cotizacion, aprobacion))

    def enviar(self, cotizacion_id: int, usuario_id: Optional[str]) -> CotizacionResponse:
        """
        La envía a aprobación: RN-065 (no vencida) y RN-066 (el total cabe en el saldo). Crea la
        aprobación En revisión que luego decide la HU-20.
        """
        cotizacion = self._buscar(cotizacion_id)
        cotizacion.enviar(hoy_utc())                                   # RN-065, RN-066
        aprobacion = Aprobacion.abrir(cotizacion, _a_entero(usuario_id))
        return self._respuesta(self.repo.guardar(cotizacion, aprobacion))
