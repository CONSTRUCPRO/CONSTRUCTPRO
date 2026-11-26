# app/api/pago_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Las rutas cuelgan de /pagos y de /ordenes-compra, por eso el router no lleva prefijo.
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.pago_repository import PagoRepository
from app.api.schemas.pago import AnulacionPago, PagoCreate, PagoResponse, PagosOrdenResponse
from app.api.schemas.respuesta import Respuesta
from app.services.pago_service import PagoService

router = APIRouter(tags=["Pagos"])

# Permisos del módulo "Pagos" (MODULO-08). Con los roles por defecto: el Administrador registra y
# anula; el Director consulta. Un rol "encargado de pagos" se crea con la HU-03 y estos permisos.
MODULO = "Pagos"


def obtener_servicio(db: Session = Depends(get_db)) -> PagoService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return PagoService(PagoRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str]) -> dict:
    """
    Arma un ejemplo de respuesta de error con el sobre estándar, solo para la documentación de
    Swagger (parámetro `responses=` de cada endpoint). No se usa al responder de verdad.
    """
    return {
        "description": descripcion,
        "content": {"application/json": {"example": {
            "exito": False,
            "codigo": codigo,
            "mensaje": mensaje_general,
            "datos": None,
            "errores": [{"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}],
            "meta": {"timestamp": "2026-10-21T15:04:32Z", "version": "v1",
                     "peticion_id": "9f3c1a7e-52b1-4c0d-9a77-1b2e6d4f8a10", "paginacion": None},
        }}},
    }


ERROR_401 = _ejemplo_error("Sin token, token vencido o sesión cerrada (HU-02)",
                           "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
                           None, "Debe iniciar sesión y enviar el token en el encabezado "
                           "Authorization: Bearer <token>.", None)
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Pagos", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Coordinador no tiene permiso para 'crear' en el módulo Pagos.",
                           None)
ERROR_404 = _ejemplo_error("La orden de compra o el pago no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "orden_compra_id",
                           "No existe una orden de compra con el identificador 8891.", None)
ERROR_409_ORDEN = _ejemplo_error(
    "La orden no está confirmada por el proveedor (RN-092)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "orden_compra_id",
    "La orden 8891 está emitida; solo se registran pagos sobre órdenes confirmadas por el "
    "proveedor.", "RN-092")
ERROR_409_ANULAR = _ejemplo_error(
    "El pago no se registró hoy (RN-094) o ya está anulado", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "pago_id",
    "El pago 4410 se registró el 2026-10-20; solo puede anularse el mismo día.", "RN-094")
ERROR_422_PAGO = _ejemplo_error(
    "El pago supera el saldo de la orden (RN-091). También 422: monto ≤ 0, moneda distinta de "
    "COP (RN-095) o sin método o fecha (RN-093)", "NEG_PAGO_EXCEDE_ORDEN",
    "El pago supera el valor pendiente de la orden de compra.", "monto",
    "El saldo pendiente de la orden 8891 es 7.815.500,00 COP.", "RN-091")


# ── Endpoints ────────────────────────────────────────────────

@router.post("/api/v1/pagos", response_model=Respuesta[PagoResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar pago",
             description="Registra un pago de una orden **confirmada** (RN-092) con monto, método, "
                         "fecha (RN-093) y referencia de la pasarela. La moneda es la de la orden "
                         "(RN-095) y la suma de pagos no supera su valor (RN-091). Genera el número "
                         "de transacción y pasa el valor de comprometido a ejecutado en el presupuesto "
                         "del proyecto. Devuelve el total pagado y el saldo pendiente.",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                        409: ERROR_409_ORDEN, 422: ERROR_422_PAGO})
def registrar_pago(datos: PagoCreate,
                   servicio: PagoService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/pagos: registra un pago de una orden (201)."""
    return respuesta_exitosa(servicio.registrar(datos, usuario.usuario_id),
                             "Pago registrado correctamente.")


@router.get("/api/v1/ordenes-compra/{orden_compra_id}/pagos",
            response_model=Respuesta[PagosOrdenResponse],
            summary="Consultar pagos de una orden",
            description="Devuelve los pagos de la orden (también los anulados, para la trazabilidad) "
                        "con el valor de la orden, el total pagado (solo pagos vigentes) y el saldo "
                        "pendiente. Si la orden no tiene pagos, `pagos` es una lista vacía.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def pagos_de_orden(orden_compra_id: int,
                   servicio: PagoService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/ordenes-compra/{orden_compra_id}/pagos: pagos de la orden y su saldo."""
    return respuesta_exitosa(servicio.pagos_de_orden(orden_compra_id),
                             "Consulta realizada correctamente.")


@router.patch("/api/v1/pagos/{pago_id}/anular", response_model=Respuesta[PagoResponse],
              summary="Anular pago",
              description="Anula un pago **solo el mismo día** en que se registró (RN-094). El valor "
                          "vuelve de ejecutado a comprometido en el presupuesto y deja de contar en "
                          "el total pagado de la orden.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ANULAR})
def anular_pago(pago_id: int, datos: Optional[AnulacionPago] = None,
                servicio: PagoService = Depends(obtener_servicio),
                usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "anular"))):
    """PATCH /api/v1/pagos/{pago_id}/anular: anula un pago del mismo día."""
    return respuesta_exitosa(servicio.anular(pago_id, datos or AnulacionPago()),
                             "Pago anulado correctamente.")
