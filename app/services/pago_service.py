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
    """El usuario_id del token llega como texto; se guarda como número (None si no viene)."""
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class PagoService:
    """
    Casos de uso de pagos (HU-23). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: PagoRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar_orden(self, orden_compra_id: int) -> OrdenCompra:
        """Trae la orden por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        orden = self.repo.obtener_orden(orden_compra_id)
        if not orden:
            raise RecursoNoEncontradoError(
                f"No existe una orden de compra con el identificador {orden_compra_id}.",
                campo="orden_compra_id")
        return orden

    def _buscar(self, pago_id: int) -> Pago:
        """Trae el pago por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        pago = self.repo.obtener_por_id(pago_id)
        if not pago:
            raise RecursoNoEncontradoError(
                f"No existe un pago con el identificador {pago_id}.", campo="pago_id")
        return pago

    def _con_saldo(self, pago: Pago) -> PagoResponse:
        """Arma la respuesta del pago con el saldo actualizado de su orden."""
        return PagoResponse.con_saldo(pago, self.repo.total_pagado(pago.orden_compra_id))

    # ── Casos de uso ───────────────────────────────────────

    def registrar(self, datos: PagoCreate, usuario_id: Optional[str]) -> PagoResponse:
        """
        Registra un pago: RN-092 (orden confirmada), RN-095 (COP), RN-093 (método y fecha) y RN-091
        (no superar el saldo). Si con este pago la orden queda pagada y ya fue recibida, se cierra (RN-087).
        """
        orden = self._buscar_orden(datos.orden_compra_id)                  # 404
        pago = Pago.registrar(                                             # RN-091 a RN-095
            orden, self.repo.total_pagado(orden.id), datos.monto, datos.moneda,
            datos.metodo_pago, datos.fecha_pago, datos.referencia_pasarela,
            _a_entero(usuario_id), hoy_colombia())
        # RN-087: si con este pago se completa el valor y la orden ya fue recibida, se cierra.
        # Se hace antes de guardar para que pago y cierre queden en la misma transacción.
        orden.cerrar_si_completa(self.repo.total_pagado(orden.id) + pago.monto)
        return self._con_saldo(self.repo.registrar(pago))

    def pagos_de_orden(self, orden_compra_id: int) -> PagosOrdenResponse:
        """Todos los pagos de la orden, incluidos los anulados, con su saldo pendiente."""
        orden = self._buscar_orden(orden_compra_id)                        # 404
        return PagosOrdenResponse.desde_modelo(
            orden, self.repo.pagos_de_orden(orden.id), self.repo.total_pagado(orden.id))

    def anular(self, pago_id: int, datos: AnulacionPago) -> PagoResponse:
        """
        Anula un pago del mismo día (RN-094) y devuelve el valor a comprometido. No si la orden está cerrada (RN-089).
        """
        pago = self._buscar(pago_id)                                       # 404
        pago.anular(datos.motivo, hoy_colombia())                          # RN-094
        return self._con_saldo(self.repo.guardar(pago))
