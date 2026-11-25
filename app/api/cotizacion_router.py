# app/api/cotizacion_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.cotizacion_repository import CotizacionRepository
from app.schemas.cotizacion import CotizacionCreate, CotizacionResponse
from app.schemas.respuesta import Respuesta
from app.services.cotizacion_service import CotizacionService

router = APIRouter(prefix="/api/v1/cotizaciones", tags=["Cotizaciones"])

# Permisos del módulo "Cotizaciones" (MODULO-05). Con los roles por defecto: Administrador y
# Coordinador generan, envían y anulan ("editar"); el Director solo consulta.
MODULO = "Cotizaciones"


def obtener_servicio(db: Session = Depends(get_db)) -> CotizacionService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return CotizacionService(CotizacionRepository(db))


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
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Cotizaciones", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Empleado no tiene permiso para 'crear' en el módulo Cotizaciones.",
                           None)
ERROR_404 = _ejemplo_error("La cotización o un comparativo no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "cotizacion_id",
                           "No existe una cotización con el identificador 1042.", None)
ERROR_409_GENERAR = _ejemplo_error(
    "Un comparativo ya está en otra cotización que no fue anulada", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "comparativo_ids",
    "El comparativo 77 ya está en otra cotización que no fue anulada.", None)
ERROR_409_ANULAR = _ejemplo_error(
    "La cotización ya fue aprobada (RN-064) o ya está anulada", "NEG_COTIZACION_APROBADA",
    "La cotización ya fue aprobada y no puede anularse.", "cotizacion_id",
    "La cotización 1042 tiene presupuesto aprobado.", "RN-064")
ERROR_409_ENVIAR = _ejemplo_error(
    "La cotización no está en estado Generada (ya fue enviada, aprobada o anulada)",
    "NEG_CONFLICTO_ESTADO", "El estado actual del recurso no permite esta operación.", "estado",
    "La cotización 1042 está Enviada; solo se envían cotizaciones en estado Generada.", None)
ERROR_422_GENERAR = _ejemplo_error(
    "Comparativos de varios proyectos o proveedores (RN-061). También 422: comparativo sin "
    "oferta seleccionada o con la solicitud ya no pendiente (RN-063)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.", "comparativo_ids",
    "Una cotización pertenece a un solo proyecto y un solo proveedor; los comparativos enviados "
    "son de varios proyectos o proveedores.", "RN-061")
ERROR_422_ENVIAR = _ejemplo_error(
    "El total supera el saldo disponible del proyecto (RN-066). También 422: cotización vencida "
    "(RN-065)", "NEG_PRESUPUESTO_INSUFICIENTE",
    "El valor de la compra supera el presupuesto disponible del proyecto.", "monto",
    "La compra por 14.815.500,00 COP supera el saldo disponible de 10.000.000,00 COP.", "RN-066")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[CotizacionResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Generar cotización",
             description="Genera la cotización en estado **Generada** a partir de comparativos con "
                         "oferta seleccionada (HU-16) de un mismo proyecto y proveedor (RN-061). "
                         "Toma la cantidad y el precio de cada comparativo (RN-063) y calcula "
                         "subtotal, IVA del 19 % y total (RN-062). Vale 15 días (`vigente_hasta`).",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                        409: ERROR_409_GENERAR, 422: ERROR_422_GENERAR})
def generar_cotizacion(datos: CotizacionCreate,
                       servicio: CotizacionService = Depends(obtener_servicio),
                       usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/cotizaciones: genera la cotización (201)."""
    return respuesta_exitosa(servicio.generar(datos), "Cotización generada correctamente.")


@router.get("", response_model=Respuesta[list[CotizacionResponse]],
            summary="Consultar cotizaciones",
            description="Consulta paginada, de la más reciente a la más antigua. Filtros opcionales "
                        "por proyecto y estado. La paginación va en `meta.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_cotizaciones(
        proyecto_id: Optional[int] = Query(None, description="Id del proyecto"),
        estado: Optional[str] = Query(None, description="Generada | Enviada | Aprobada | "
                                                        "Rechazada | Anulada"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: CotizacionService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/cotizaciones: lista paginada con filtros."""
    items, paginacion = servicio.listar(proyecto_id, estado, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{cotizacion_id}", response_model=Respuesta[CotizacionResponse],
            summary="Consultar cotización",
            description="Devuelve la cotización con su detalle y, si ya se envió, su aprobación.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_cotizacion(cotizacion_id: int,
                       servicio: CotizacionService = Depends(obtener_servicio),
                       usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/cotizaciones/{cotizacion_id}: una cotización."""
    return respuesta_exitosa(servicio.obtener(cotizacion_id), "Consulta realizada correctamente.")


@router.patch("/{cotizacion_id}/anular", response_model=Respuesta[CotizacionResponse],
              summary="Anular cotización",
              description="Anula la cotización. No se puede si ya tiene presupuesto aprobado "
                          "(RN-064, 409 `NEG_COTIZACION_APROBADA`). Si estaba en revisión, su "
                          "aprobación también queda Anulada.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ANULAR})
def anular_cotizacion(cotizacion_id: int,
                      servicio: CotizacionService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """PATCH /api/v1/cotizaciones/{cotizacion_id}/anular: anula la cotización."""
    return respuesta_exitosa(servicio.anular(cotizacion_id), "Cotización anulada correctamente.")


@router.post("/{cotizacion_id}/enviar", response_model=Respuesta[CotizacionResponse],
             summary="Enviar a presupuesto y aprobación",
             description="Envía una cotización **Generada** y vigente (RN-065). Valida que el total "
                         "no supere el saldo disponible del proyecto (RN-066, HU-06) y crea la "
                         "aprobación en estado **En revisión** (la decide la HU-20). La cotización "
                         "queda en estado Enviada.",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                        409: ERROR_409_ENVIAR, 422: ERROR_422_ENVIAR})
def enviar_cotizacion(cotizacion_id: int,
                      servicio: CotizacionService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """POST /api/v1/cotizaciones/{cotizacion_id}/enviar: la envía a presupuesto y aprobación."""
    return respuesta_exitosa(servicio.enviar(cotizacion_id, usuario.usuario_id),
                             "Cotización enviada a aprobación correctamente.")
