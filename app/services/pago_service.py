# app/services/pago_service.py
# CAPA SERVICIO: orquesta los casos de uso de los pagos.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.domain.excepciones import RecursoNoEncontradoError
from app.domain.orden_compra import OrdenCompra
from app.domain.pago import Pago, hoy_colombia
from app.repositories.pago_repository import PagoRepository
from app.schemas.pago import AnulacionPago, PagoCreate, PagoResponse, PagosOrdenResponse


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class PagoService:

    def __init__(self, repo: PagoRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar_orden(self, orden_compra_id: int) -> OrdenCompra:
        orden = self.repo.obtener_orden(orden_compra_id)
        if not orden:
            raise RecursoNoEncontradoError(
                f"No existe una orden de compra con el identificador {orden_compra_id}.",
                campo="orden_compra_id")
        return orden

    def _buscar(self, pago_id: int) -> Pago:
        pago = self.repo.obtener_por_id(pago_id)
        if not pago:
            raise RecursoNoEncontradoError(
                f"No existe un pago con el identificador {pago_id}.", campo="pago_id")
        return pago

    def _con_saldo(self, pago: Pago) -> PagoResponse:
        return PagoResponse.con_saldo(pago, self.repo.total_pagado(pago.orden_compra_id))

    # ── Casos de uso ───────────────────────────────────────

    def registrar(self, datos: PagoCreate, usuario_id: Optional[str]) -> PagoResponse:
        orden = self._buscar_orden(datos.orden_compra_id)                  # 404
        pago = Pago.registrar(                                             # RN-091 a RN-095
            orden, self.repo.total_pagado(orden.id), datos.monto, datos.moneda,
            datos.metodo_pago, datos.fecha_pago, datos.referencia_pasarela,
            _a_entero(usuario_id), hoy_colombia())
        return self._con_saldo(self.repo.registrar(pago))

    def pagos_de_orden(self, orden_compra_id: int) -> PagosOrdenResponse:
        orden = self._buscar_orden(orden_compra_id)                        # 404
        return PagosOrdenResponse.desde_modelo(
            orden, self.repo.pagos_de_orden(orden.id), self.repo.total_pagado(orden.id))

    def anular(self, pago_id: int, datos: AnulacionPago) -> PagoResponse:
        pago = self._buscar(pago_id)                                       # 404
        pago.anular(datos.motivo, hoy_colombia())                          # RN-094
        return self._con_saldo(self.repo.guardar(pago))
