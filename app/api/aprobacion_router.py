# app/api/aprobacion_router.py
# CAPA API - HU-20 Decisión de Aprobación.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Permisos del módulo "Aprobaciones" (tabla permisos_rol): consultar y aprobar.
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.aprobacion_repository import AprobacionRepository
from app.api.schemas.aprobacion import AprobacionResponse, DecisionDatos
from app.api.schemas.respuesta import Pagina, Respuesta
from app.services.aprobacion_service import AprobacionService

router = APIRouter(prefix="/api/v1/aprobaciones", tags=["Aprobaciones"])
MODULO = "Aprobaciones"


def obtener_servicio(db: Session = Depends(get_db)) -> AprobacionService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return AprobacionService(AprobacionRepository(db))


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
    "El Coordinador supera su tope (RN-076); también 403 NEG_SEGREGACION_FUNCIONES si el aprobador "
    "solicitó o envió la compra (RN-073), o si el rol no tiene permiso en Aprobaciones",
    "AUT_SIN_PERMISO", "Su rol no le permite realizar esta operación.", "aprobador_id",
    "El rol Coordinador no puede aprobar compras superiores a 10.000.000,00 COP.", "RN-076")
ERROR_404 = _ejemplo_error(
    "La aprobación no existe", "REC_NO_ENCONTRADO", "El recurso solicitado no existe.",
    "aprobacion_id", "No existe una aprobación con el identificador 560.")
ERROR_409 = _ejemplo_error(
    "La aprobación ya fue decidida (RN-078)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "La aprobación 560 ya está en estado 'Aprobada' y no puede modificarse.", "RN-078")
ERROR_422 = _ejemplo_error(
    "Rechazo sin motivo (RN-077); también 422 NEG_PRESUPUESTO_INSUFICIENTE si la compra supera "
    "el saldo del proyecto (RN-066)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.", "motivo",
    "Todo rechazo debe registrar el motivo.", "RN-077")


# ── Endpoints ────────────────────────────────────────────────

@router.get("", response_model=Respuesta[Pagina[AprobacionResponse]],
            summary="Consultar compras en revisión",
            description="Lista paginada de aprobaciones por estado. Si no se envía `estado`, devuelve "
                        "las que esperan decisión (**En revisión**), de la más antigua a la más reciente. "
                        "Requiere permiso *consultar* en Aprobaciones.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_aprobaciones(
        estado: Optional[str] = Query(None, description="En revisión | Aprobada | Rechazada | Anulada"),
        proyecto_id: Optional[int] = Query(None, description="Identificador del proyecto"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: AprobacionService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/aprobaciones: por defecto, las compras En revisión."""
    items, paginacion = servicio.listar(estado, proyecto_id, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/historico", response_model=Respuesta[Pagina[AprobacionResponse]],
            summary="Histórico de aprobaciones",
            description="Aprobaciones ya decididas (Aprobada o Rechazada) con aprobador, fecha, monto "
                        "autorizado y motivo (FUN-079), de la más reciente a la más antigua. Filtros "
                        "opcionales por proyecto, aprobador y rango de fechas de la decisión.",
            responses={401: ERROR_401, 403: ERROR_403})
def historico(
        proyecto_id: Optional[int] = Query(None, description="Identificador del proyecto"),
        aprobador_id: Optional[int] = Query(None, description="Identificador del aprobador"),
        desde: Optional[date] = Query(None, description="Fecha inicial AAAA-MM-DD (UTC)"),
        hasta: Optional[date] = Query(None, description="Fecha final AAAA-MM-DD (UTC)"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: AprobacionService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """
    GET /api/v1/aprobaciones/historico: decisiones tomadas. Va antes de /{id} para que 'historico' no se lea como un id.
    """
    items, paginacion = servicio.historico(proyecto_id, aprobador_id, desde, hasta, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{aprobacion_id}", response_model=Respuesta[AprobacionResponse],
            summary="Detalle de una aprobación",
            description="Devuelve una aprobación con su estado y, si ya se decidió, el aprobador, "
                        "la fecha, el monto autorizado y el motivo.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_aprobacion(aprobacion_id: int,
                       servicio: AprobacionService = Depends(obtener_servicio),
                       usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/aprobaciones/{aprobacion_id}: una aprobación."""
    return respuesta_exitosa(servicio.obtener(aprobacion_id), "Consulta realizada correctamente.")


@router.patch("/{aprobacion_id}", response_model=Respuesta[AprobacionResponse],
              summary="Aprobar o rechazar una compra",
              description="Registra la decisión sobre una compra **En revisión**: `aprobada` o "
                          "`rechazada` (con `motivo` obligatorio, RN-077). Valida el rol frente al monto "
                          "(RN-076: por encima del tope solo el Director), que el aprobador no haya "
                          "solicitado ni enviado la compra (RN-073) y, al aprobar, el saldo del proyecto "
                          "(RN-066), que queda comprometido (RN-068). Registra aprobador, fecha y monto "
                          "(RN-079) y la decisión es definitiva (RN-078). La cotización pasa a Aprobada "
                          "o Rechazada.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409,
                         422: ERROR_422})
def decidir(aprobacion_id: int, datos: DecisionDatos,
            servicio: AprobacionService = Depends(obtener_servicio),
            usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "aprobar"))):
    """
    PATCH /api/v1/aprobaciones/{aprobacion_id}: aprueba o rechaza; el mensaje depende de la decisión.
    """
    resultado = servicio.decidir(aprobacion_id, datos, usuario.usuario_id)
    mensaje = ("Compra aprobada correctamente." if resultado.estado == "Aprobada"
               else "Compra rechazada correctamente.")
    return respuesta_exitosa(resultado, mensaje)
