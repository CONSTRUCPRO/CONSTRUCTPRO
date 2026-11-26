# app/api/solicitud_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_error, respuesta_exitosa
from app.core.seguridad import UsuarioActual, obtener_usuario_actual, requiere_permiso
from app.repositories.solicitud_repository import SolicitudRepository
from app.api.schemas.respuesta import Pagina, Respuesta
from app.api.schemas.solicitud import SolicitudCreate, SolicitudResponse, SolicitudUpdate
from app.services.solicitud_service import SolicitudService

router = APIRouter(prefix="/api/v1/solicitudes", tags=["Solicitudes"])

# Crear y consultar usan los permisos del módulo "Solicitudes" (tabla permisos_rol).
# Editar y anular los decide la RN-044: solo el solicitante o el responsable del proyecto.
MODULO = "Solicitudes"


def obtener_servicio(db: Session = Depends(get_db)) -> SolicitudService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return SolicitudService(SolicitudRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str]) -> dict:
    """
    Arma un ejemplo de respuesta de error para la documentación de Swagger (parámetro
    `responses=` de cada endpoint). Usa respuesta_error(), la misma función que arma los
    errores reales, así el ejemplo siempre coincide con lo que responde la API.
    """
    return {
        "description": descripcion,
        "content": {"application/json": {"example": respuesta_error(
            codigo, mensaje_general,
            [{"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}])}},
    }


ERROR_401 = _ejemplo_error("Sin token, token vencido o sesión cerrada (HU-02)",
                           "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
                           None, "Debe iniciar sesión y enviar el token en el encabezado "
                           "Authorization: Bearer <token>.", None)
ERROR_403_PERMISO = _ejemplo_error("El rol no tiene el permiso en el módulo Solicitudes", "AUT_SIN_PERMISO",
                                   "Su rol no le permite realizar esta operación.", "rol",
                                   "El rol Director no tiene permiso para 'crear' en el módulo Solicitudes.",
                                   None)
ERROR_403_AUTOR = _ejemplo_error("No es el solicitante ni el responsable del proyecto (RN-044)",
                                 "AUT_SIN_PERMISO", "Su rol no le permite realizar esta operación.",
                                 "solicitud_id", "Solo el solicitante o el responsable del proyecto "
                                 "pueden modificar la solicitud 305.", "RN-044")
ERROR_404 = _ejemplo_error("La solicitud, el proyecto o un material no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "solicitud_id",
                           "No existe una solicitud con el identificador 305.", None)
ERROR_409_ESTADO = _ejemplo_error("La solicitud ya no está pendiente, o un material está inactivo "
                                  "(RN-034)", "NEG_CONFLICTO_ESTADO",
                                  "El estado actual del recurso no permite esta operación.", "estado",
                                  "La solicitud 305 está anulada y ya no se puede modificar.", None)
ERROR_422_PROYECTO = _ejemplo_error(
    "Proyecto no activo (RN-041), sin ubicación (RN-020) o sin presupuesto (RN-021). "
    "También 422: detalle vacío o cantidad ≤ 0 (RN-042) y material repetido (RN-043)",
    "NEG_PROYECTO_NO_ACTIVO", "El proyecto no está activo y no admite nuevas solicitudes.",
    "proyecto_id", "El proyecto 'Torre Cabecera Etapa 2' está suspendido y no admite nuevas "
    "solicitudes.", "RN-041")
ERROR_422_DETALLE = _ejemplo_error(
    "Detalle vacío o con cantidad ≤ 0 (RN-042), o material repetido (RN-043)",
    "NEG_REGLA_INCUMPLIDA", "La operación no cumple una regla de negocio.",
    "detalle.1.material_id", "El material 1 está repetido en la solicitud.", "RN-043")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[SolicitudResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Crear solicitud de materiales",
             description="Crea una solicitud **pendiente** con su detalle de materiales y cantidades. "
                         "El proyecto debe estar activo, con ubicación y presupuesto (RN-041, RN-020, "
                         "RN-021); cada material debe existir y estar activo (RN-034); al menos una "
                         "línea con cantidad mayor que cero (RN-042) y sin materiales repetidos "
                         "(RN-043). El solicitante es el usuario que inició sesión (el del token).",
             responses={401: ERROR_401, 403: ERROR_403_PERMISO, 404: ERROR_404,
                        409: ERROR_409_ESTADO, 422: ERROR_422_PROYECTO})
def crear_solicitud(datos: SolicitudCreate,
                    servicio: SolicitudService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/solicitudes: crea la solicitud (201)."""
    return respuesta_exitosa(servicio.crear(datos, usuario.usuario_id),
                             "Solicitud creada correctamente.")


@router.get("", response_model=Respuesta[Pagina[SolicitudResponse]],
            summary="Consultar solicitudes",
            description="Consulta paginada de solicitudes, de la más reciente a la más antigua. "
                        "Filtros opcionales por proyecto y estado. La paginación va en "
                        "`data.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403_PERMISO})
def listar_solicitudes(
        proyecto_id: Optional[int] = Query(None, description="Id del proyecto"),
        estado: Optional[str] = Query(None, description="pendiente | anulada"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: SolicitudService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/solicitudes: lista paginada con filtros."""
    items, paginacion = servicio.listar(proyecto_id, estado, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{solicitud_id}", response_model=Respuesta[SolicitudResponse],
            summary="Consultar solicitud",
            description="Devuelve la solicitud con su detalle de materiales.",
            responses={401: ERROR_401, 403: ERROR_403_PERMISO, 404: ERROR_404})
def obtener_solicitud(solicitud_id: int,
                      servicio: SolicitudService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/solicitudes/{solicitud_id}: una solicitud con su detalle."""
    return respuesta_exitosa(servicio.obtener(solicitud_id), "Consulta realizada correctamente.")


@router.put("/{solicitud_id}", response_model=Respuesta[SolicitudResponse],
            summary="Editar solicitud pendiente",
            description="Reemplaza el detalle de la solicitud. Solo el solicitante o el responsable "
                        "del proyecto pueden hacerlo (RN-044) y solo mientras esté **pendiente**. "
                        "Valida RN-034, RN-042 y RN-043.",
            responses={401: ERROR_401, 403: ERROR_403_AUTOR, 404: ERROR_404,
                       409: ERROR_409_ESTADO, 422: ERROR_422_DETALLE})
def editar_solicitud(solicitud_id: int, datos: SolicitudUpdate,
                     servicio: SolicitudService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    """
    PUT /api/v1/solicitudes/{solicitud_id}: reemplaza el detalle (quién puede lo decide la RN-044).
    """
    return respuesta_exitosa(servicio.editar(solicitud_id, datos, usuario.usuario_id),
                             "Solicitud actualizada correctamente.")


@router.patch("/{solicitud_id}/anular", response_model=Respuesta[SolicitudResponse],
              summary="Anular solicitud",
              description="Anula una solicitud **pendiente**. Solo el solicitante o el responsable "
                          "del proyecto pueden hacerlo (RN-044).",
              responses={401: ERROR_401, 403: ERROR_403_AUTOR, 404: ERROR_404, 409: ERROR_409_ESTADO})
def anular_solicitud(solicitud_id: int,
                     servicio: SolicitudService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    """PATCH /api/v1/solicitudes/{solicitud_id}/anular: anula la solicitud."""
    return respuesta_exitosa(servicio.anular(solicitud_id, usuario.usuario_id),
                             "Solicitud anulada correctamente.")
