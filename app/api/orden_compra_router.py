# app/api/orden_compra_router.py
# CAPA API - HU-21 Generación de Orden de Compra.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Permisos del módulo "Ordenes de compra" (tabla permisos_rol).
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.orden_compra_repository import OrdenCompraRepository
from app.api.schemas.orden_compra import AnulacionDatos, OrdenCompraCreate, OrdenCompraResponse
from app.api.schemas.respuesta import Respuesta
from app.services.orden_compra_service import OrdenCompraService

router = APIRouter(prefix="/api/v1/ordenes-compra", tags=["Órdenes de compra"])
MODULO = "Ordenes de compra"


def obtener_servicio(db: Session = Depends(get_db)) -> OrdenCompraService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return OrdenCompraService(OrdenCompraRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str] = None) -> dict:
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


ERROR_401 = _ejemplo_error(
    "Sin token, token vencido o sesión cerrada (HU-02)", "AUT_CREDENCIALES_INVALIDAS",
    "El correo o la contraseña no son correctos.", "Authorization",
    "Debe iniciar sesión y enviar el token en el encabezado Authorization: Bearer <token>.")
ERROR_403 = _ejemplo_error(
    "El rol no tiene el permiso en el módulo Ordenes de compra", "AUT_SIN_PERMISO",
    "Su rol no le permite realizar esta operación.", "rol",
    "El rol Director no tiene permiso para 'crear' en el módulo Ordenes de compra.")
ERROR_404 = _ejemplo_error(
    "La orden o la aprobación no existe", "REC_NO_ENCONTRADO", "El recurso solicitado no existe.",
    "orden_compra_id", "No existe una orden de compra con el identificador 8891.")
ERROR_409_GENERAR = _ejemplo_error(
    "La compra no está aprobada (RN-081); también 409 REC_DUPLICADO si la cotización ya tiene "
    "orden (RN-083) o si el proveedor está inactivo (RN-039)", "NEG_COMPRA_NO_APROBADA",
    "No es posible generar la orden: la compra no está aprobada.", "aprobacion_id",
    "La aprobación 560 se encuentra en estado 'En revisión'.", "RN-081")
ERROR_409_ANULAR = _ejemplo_error(
    "La orden tiene pagos o envíos (RN-084), o ya está anulada o cerrada (RN-089)",
    "NEG_CONFLICTO_ESTADO", "El estado actual del recurso no permite esta operación.",
    "orden_compra_id", "La orden 8891 tiene 1 pago(s) y 0 envío(s) registrados y no puede anularse.",
    "RN-084")
ERROR_409_CONFIRMAR = _ejemplo_error(
    "Solo se confirman órdenes emitidas (RN-086 / RN-089)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "La orden 8891 ya está confirmada; solo se confirman órdenes emitidas.", "RN-086")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[OrdenCompraResponse], status_code=status.HTTP_201_CREATED,
             summary="Generar orden de compra",
             description="Genera la orden a partir de una aprobación **Aprobada** (RN-081). Copia "
                         "exactamente los ítems y valores aprobados (RN-082); el `valor_total` es el "
                         "monto autorizado. Cada cotización genera una sola orden (RN-083) y el "
                         "proveedor debe estar activo (RN-039). Queda en estado **emitida**.",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_GENERAR})
def generar_orden(datos: OrdenCompraCreate,
                  servicio: OrdenCompraService = Depends(obtener_servicio),
                  usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/ordenes-compra: genera la orden desde una aprobación (201)."""
    return respuesta_exitosa(servicio.generar(datos, usuario.usuario_id),
                             "Orden de compra generada correctamente.")


@router.get("", response_model=Respuesta[list[OrdenCompraResponse]],
            summary="Consultar órdenes de compra",
            description="Lista paginada (de la más reciente a la más antigua) con filtros opcionales "
                        "por proyecto, proveedor y estado.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_ordenes(
        proyecto_id: Optional[int] = Query(None, description="Identificador del proyecto"),
        proveedor_id: Optional[int] = Query(None, description="Identificador del proveedor"),
        estado: Optional[str] = Query(None, description="emitida | confirmada | cerrada | anulada"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: OrdenCompraService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/ordenes-compra: lista paginada con filtros."""
    items, paginacion = servicio.listar(proyecto_id, proveedor_id, estado, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{orden_compra_id}", response_model=Respuesta[OrdenCompraResponse],
            summary="Consultar orden con detalle",
            description="Devuelve la cabecera, el detalle y el estado de la orden (FUN-083).",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_orden(orden_compra_id: int,
                  servicio: OrdenCompraService = Depends(obtener_servicio),
                  usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/ordenes-compra/{orden_compra_id}: la orden con su detalle."""
    return respuesta_exitosa(servicio.obtener(orden_compra_id), "Consulta realizada correctamente.")


@router.patch("/{orden_compra_id}/confirmar", response_model=Respuesta[OrdenCompraResponse],
              summary="Registrar la confirmación del proveedor",
              description="Pasa la orden de **emitida** a **confirmada** (RN-086). En el sistema "
                          "completo lo hace el proveedor desde su portal (RN-088), que no está en este "
                          "sprint; aquí lo registra el coordinador. Es necesario para la HU-23: solo se "
                          "pagan órdenes confirmadas (RN-092).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_CONFIRMAR})
def confirmar_orden(orden_compra_id: int,
                    servicio: OrdenCompraService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """
    PATCH /api/v1/ordenes-compra/{orden_compra_id}/confirmar: registra la confirmación del proveedor.
    """
    return respuesta_exitosa(servicio.confirmar(orden_compra_id), "Orden de compra confirmada.")


@router.patch("/{orden_compra_id}/anular", response_model=Respuesta[OrdenCompraResponse],
              summary="Anular orden",
              description="Anula la orden si no tiene pagos ni envíos (RN-084) y no está anulada ni "
                          "cerrada (RN-089). Registra el motivo (opcional) y **libera el presupuesto** "
                          "comprometido del proyecto (FUN-084, RN-069).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ANULAR})
def anular_orden(orden_compra_id: int,
                 datos: Optional[AnulacionDatos] = Body(None),
                 servicio: OrdenCompraService = Depends(obtener_servicio),
                 usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "anular"))):
    """
    PATCH /api/v1/ordenes-compra/{orden_compra_id}/anular: anula y libera el presupuesto. El cuerpo es opcional.
    """
    return respuesta_exitosa(servicio.anular(orden_compra_id, datos or AnulacionDatos()),
                             "Orden de compra anulada.")
