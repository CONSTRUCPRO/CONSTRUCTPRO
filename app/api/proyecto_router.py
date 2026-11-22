# app/api/proyecto_router.py
# CAPA API - HU-05 Gestión de Proyectos.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Los permisos se revisan contra la tabla permisos_rol de la HU-03 (módulo "Proyectos").
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.proyecto_repository import ProyectoRepository
from app.schemas.proyecto import (
    EstadoProyectoUpdate,
    ProyectoCreate,
    ProyectoResponse,
    ProyectoUpdate,
    ResponsableUpdate,
    UbicacionDatos,
)
from app.schemas.respuesta import Respuesta
from app.services.proyecto_service import ProyectoService

router = APIRouter(prefix="/api/v1/proyectos", tags=["Proyectos"])


def obtener_servicio(db: Session = Depends(get_db)) -> ProyectoService:
    return ProyectoService(ProyectoRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str] = None) -> dict:
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
    "Falta identificarse (encabezado X-Rol, temporal hasta la HU-02)",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    None, "Debe identificarse para usar este servicio.")
ERROR_403 = _ejemplo_error(
    "El rol no tiene el permiso en el módulo Proyectos", "AUT_SIN_PERMISO",
    "Su rol no le permite realizar esta operación.",
    "rol", "El rol Empleado no tiene permiso para 'crear' en el módulo Proyectos.")
ERROR_404 = _ejemplo_error(
    "El proyecto no existe", "REC_NO_ENCONTRADO", "El recurso solicitado no existe.",
    "proyecto_id", "No existe un proyecto con el identificador 999.")
ERROR_409_DUPLICADO = _ejemplo_error(
    "Nombre repetido para el mismo cliente (RN-018)", "REC_DUPLICADO",
    "Ya existe un registro con ese identificador.", "nombre",
    "El cliente Inversiones Andinas S.A.S. ya tiene un proyecto llamado 'Torre Cabecera Etapa 2'.",
    "RN-018")
ERROR_409_FINALIZADO = _ejemplo_error(
    "El proyecto está finalizado (RN-019)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "El proyecto 'Torre Cabecera Etapa 2' está finalizado y no admite modificaciones.", "RN-019")
ERROR_409_ESTADO = _ejemplo_error(
    "Transición de estado no permitida (RN-024 / RN-025)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "Un proyecto finalizado no puede cambiar de estado.", "RN-024")
ERROR_422_FECHAS = _ejemplo_error(
    "Fecha de fin anterior a la de inicio (RN-017)", "VAL_FORMATO_INVALIDO",
    "La información enviada contiene errores.", "fecha_fin_estimada",
    "La fecha de finalización no puede ser anterior a la fecha de inicio.", "RN-017")
ERROR_422_RESPONSABLE = _ejemplo_error(
    "Responsable inexistente, inactivo o sin rol Coordinador/Director (RN-016)",
    "NEG_REGLA_INCUMPLIDA", "La operación no cumple una regla de negocio.", "responsable_id",
    "El usuario Laura Gómez está inactivo y no puede ser responsable de un proyecto.", "RN-016")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[ProyectoResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar proyecto",
             description="Registra un proyecto en estado **activo** (FUN-016). El nombre es único "
                         "por cliente (RN-018), la fecha de fin no puede ser anterior a la de inicio "
                         "(RN-017) y el responsable debe ser un usuario activo con rol Coordinador o "
                         "Director (RN-016). La ubicación es opcional y se puede registrar después. "
                         "Requiere permiso *crear* en Proyectos.",
             responses={401: ERROR_401, 403: ERROR_403, 409: ERROR_409_DUPLICADO,
                        422: ERROR_422_FECHAS})
def crear_proyecto(datos: ProyectoCreate,
                   servicio: ProyectoService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "crear"))):
    return respuesta_exitosa(servicio.crear(datos), "Proyecto registrado correctamente.")


@router.get("", response_model=Respuesta[list[ProyectoResponse]],
            summary="Consultar proyectos",
            description="Consulta paginada de proyectos (FUN-017), con filtros opcionales por "
                        "estado, ciudad, cliente o responsable. La paginación va en `meta.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_proyectos(
        estado: Optional[str] = Query(None, description="activo | suspendido | finalizado"),
        ciudad: Optional[str] = Query(None, description="Ciudad de la obra, ej. Bucaramanga"),
        cliente: Optional[str] = Query(None, description="Texto contenido en el cliente"),
        responsable_id: Optional[int] = Query(None, description="Identificador del responsable"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: ProyectoService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "consultar"))):
    proyectos, paginacion = servicio.listar(estado, ciudad, cliente, responsable_id,
                                            pagina, por_pagina)
    return respuesta_exitosa(proyectos, "Consulta realizada correctamente.", paginacion)


@router.get("/{proyecto_id}", response_model=Respuesta[ProyectoResponse],
            summary="Detalle del proyecto",
            description="Devuelve los datos de un proyecto, con su ubicación y responsable.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_proyecto(proyecto_id: int,
                     servicio: ProyectoService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "consultar"))):
    return respuesta_exitosa(servicio.obtener(proyecto_id), "Consulta realizada correctamente.")


@router.put("/{proyecto_id}", response_model=Respuesta[ProyectoResponse],
            summary="Editar proyecto",
            description="Reemplaza los datos generales (FUN-018): nombre, cliente, descripción y "
                        "fechas. No se permite si el proyecto está finalizado (RN-019). Se siguen "
                        "validando RN-017 y RN-018.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                       409: ERROR_409_FINALIZADO, 422: ERROR_422_FECHAS})
def editar_proyecto(proyecto_id: int, datos: ProyectoUpdate,
                    servicio: ProyectoService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "editar"))):
    return respuesta_exitosa(servicio.editar(proyecto_id, datos),
                             "Proyecto actualizado correctamente.")


@router.put("/{proyecto_id}/ubicacion", response_model=Respuesta[ProyectoResponse],
            summary="Registrar ubicación",
            description="Guarda la dirección, la ciudad y las coordenadas de la obra (FUN-019). "
                        "Es obligatoria antes de generar solicitudes (RN-020, HU-12).",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                       409: ERROR_409_FINALIZADO})
def registrar_ubicacion(proyecto_id: int, datos: UbicacionDatos,
                        servicio: ProyectoService = Depends(obtener_servicio),
                        usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "editar"))):
    return respuesta_exitosa(servicio.registrar_ubicacion(proyecto_id, datos),
                             "Ubicación registrada correctamente.")


@router.patch("/{proyecto_id}/responsable", response_model=Respuesta[ProyectoResponse],
              summary="Asignar responsable",
              description="Cambia el responsable del proyecto (FUN-020). Debe ser un usuario activo "
                          "con rol Coordinador o Director (RN-016).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                         409: ERROR_409_FINALIZADO, 422: ERROR_422_RESPONSABLE})
def asignar_responsable(proyecto_id: int, datos: ResponsableUpdate,
                        servicio: ProyectoService = Depends(obtener_servicio),
                        usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "editar"))):
    return respuesta_exitosa(servicio.asignar_responsable(proyecto_id, datos),
                             "Responsable asignado correctamente.")


@router.patch("/{proyecto_id}/estado", response_model=Respuesta[ProyectoResponse],
              summary="Cambiar estado del proyecto",
              description="Pasa el proyecto entre activo, suspendido y finalizado (FUN-024). Un "
                          "proyecto finalizado no cambia de estado (RN-024) y no se puede finalizar "
                          "con órdenes de compra abiertas o pagos pendientes (RN-025).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ESTADO})
def cambiar_estado(proyecto_id: int, datos: EstadoProyectoUpdate,
                   servicio: ProyectoService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "editar"))):
    return respuesta_exitosa(servicio.cambiar_estado(proyecto_id, datos),
                             "Estado del proyecto actualizado correctamente.")
