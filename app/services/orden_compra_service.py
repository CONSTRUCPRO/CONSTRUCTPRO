# app/services/orden_compra_service.py
# CAPA SERVICIO - HU-21: generar, consultar, confirmar y anular órdenes de compra.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.orden_compra import OrdenCompra
from app.repositories.orden_compra_repository import OrdenCompraRepository
from app.schemas.orden_compra import AnulacionDatos, OrdenCompraCreate, OrdenCompraResponse


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    """El usuario_id del token llega como texto; se guarda como número (None si no viene)."""
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class OrdenCompraService:
    """
    Casos de uso de órdenes de compra (HU-21). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: OrdenCompraRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    def _buscar(self, orden_id: int) -> OrdenCompra:
        """Trae la orden por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        orden = self.repo.obtener_por_id(orden_id)
        if not orden:
            raise RecursoNoEncontradoError(
                f"No existe una orden de compra con el identificador {orden_id}.",
                campo="orden_compra_id")
        return orden

    # ── Casos de uso ───────────────────────────────────────

    def generar(self, datos: OrdenCompraCreate, usuario_id: Optional[str]) -> OrdenCompraResponse:
        """FUN-081 / FUN-082."""
        aprobacion = self.repo.obtener_aprobacion(datos.aprobacion_id)
        if not aprobacion:
            raise RecursoNoEncontradoError(
                f"No existe una aprobación con el identificador {datos.aprobacion_id}.",
                campo="aprobacion_id")
        OrdenCompra.verificar_aprobada(aprobacion)                              # RN-081 (409)
        existente = self.repo.orden_de_cotizacion(aprobacion.cotizacion_id)
        if existente:                                                           # RN-083 (409)
            raise RecursoDuplicadoError(
                "RN-083", f"La cotización {aprobacion.cotizacion_id} ya generó la orden de compra "
                          f"{existente.id} ({existente.estado}).", campo="aprobacion_id")
        proveedor = self.repo.obtener_proveedor(aprobacion.cotizacion.proveedor_id)
        orden = OrdenCompra.emitir(aprobacion, proveedor, _a_entero(usuario_id))  # RN-039, RN-082
        return OrdenCompraResponse.desde_modelo(self.repo.guardar(orden))

    def obtener(self, orden_id: int) -> OrdenCompraResponse:
        """Una orden con su detalle (FUN-083)."""
        return OrdenCompraResponse.desde_modelo(self._buscar(orden_id))

    def listar(self, proyecto_id: Optional[int], proveedor_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[OrdenCompraResponse], dict]:
        """Lista paginada con filtros por proyecto, proveedor y estado."""
        items, total = self.repo.listar(proyecto_id, proveedor_id, estado, pagina, por_pagina)
        return ([OrdenCompraResponse.desde_modelo(o) for o in items],
                construir_paginacion(pagina, por_pagina, total))

    def confirmar(self, orden_id: int) -> OrdenCompraResponse:
        """RN-086: registra la confirmación del proveedor (emitida -> confirmada)."""
        orden = self._buscar(orden_id)
        orden.confirmar()
        return OrdenCompraResponse.desde_modelo(self.repo.guardar(orden))

    def anular(self, orden_id: int, datos: AnulacionDatos) -> OrdenCompraResponse:
        """FUN-084: anula si no hay pagos ni envíos (RN-084) y libera el presupuesto (RN-069)."""
        orden = self._buscar(orden_id)
        orden.anular(datos.motivo, self.repo.contar_pagos(orden.id),
                     self.repo.contar_envios(orden.id))                        # RN-089, RN-084
        presupuesto = orden.aprobacion.cotizacion.proyecto.presupuesto
        if presupuesto is not None:
            presupuesto.liberar(float(orden.valor_total))                       # RN-069
        return OrdenCompraResponse.desde_modelo(self.repo.guardar(orden))
