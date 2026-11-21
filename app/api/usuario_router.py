# app/api/usuario_router.py
# CAPA API - HU-01 Gestión de Usuarios.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Los permisos se revisan contra la tabla permisos_rol de la HU-03 (requiere_permiso).
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.respuesta import Respuesta
from app.schemas.usuario import (
    EstadoUsuarioUpdate,
    RolUsuarioUpdate,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)
from app.services.usuario_service import UsuarioService

router = APIRouter(prefix="/api/v1/usuarios", tags=["Usuarios"])


def obtener_servicio(db: Session = Depends(get_db)) -> UsuarioService:
    return UsuarioService(UsuarioRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   errores: list[dict]) -> dict:
    return {
        "description": descripcion,
        "content": {"application/json": {"example": {
            "exito": False,
            "codigo": codigo,
            "mensaje": mensaje_general,
            "datos": None,
            "errores": errores,
            "meta": {"timestamp": "2026-10-21T15:04:32Z", "version": "v1",
                     "peticion_id": "9f3c1a7e-52b1-4c0d-9a77-1b2e6d4f8a10", "paginacion": None},
        }}},
    }


def _error(campo: Optional[str], codigo: str, mensaje: str, regla: Optional[str] = None) -> dict:
    return {"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}


ERROR_401 = _ejemplo_error(
    "Falta identificarse (encabezado X-Rol, temporal hasta la HU-02)",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    [_error(None, "AUT_CREDENCIALES_INVALIDAS", "Debe identificarse para usar este servicio.")])
ERROR_403 = _ejemplo_error(
    "El rol no tiene el permiso en el módulo Usuarios", "AUT_SIN_PERMISO",
    "Su rol no le permite realizar esta operación.",
    [_error("rol", "AUT_SIN_PERMISO",
            "El rol Empleado no tiene permiso para 'crear' en el módulo Usuarios.")])
ERROR_404 = _ejemplo_error(
    "El usuario no existe", "REC_NO_ENCONTRADO", "El recurso solicitado no existe.",
    [_error("usuario_id", "REC_NO_ENCONTRADO", "No existe un usuario con el identificador 12.")])
ERROR_409_DUPLICADO = _ejemplo_error(
    "Correo o documento repetido (RN-001)", "REC_DUPLICADO",
    "Ya existe un registro con ese identificador.",
    [_error("correo", "REC_DUPLICADO", "El correo laura@construpro.co ya está registrado.",
            "RN-001")])
ERROR_409_ESTADO = _ejemplo_error(
    "El usuario ya está en ese estado", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.",
    [_error("estado", "NEG_CONFLICTO_ESTADO", "El usuario ya se encuentra en estado 'inactivo'.")])
ERROR_422_DATOS = _ejemplo_error(
    "Datos inválidos: un error por cada campo con problema", "VAL_CAMPO_REQUERIDO",
    "El campo indicado es obligatorio.",
    [_error("numero_documento", "VAL_CAMPO_REQUERIDO",
            "El campo 'numero_documento' es obligatorio."),
     _error("correo", "VAL_FORMATO_INVALIDO",
            "El correo no tiene un formato válido. Ejemplo: laura@construpro.co.")])
ERROR_422_ROL = _ejemplo_error(
    "El rol no existe o está inactivo (RN-002)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.",
    [_error("rol_id", "NEG_REGLA_INCUMPLIDA", "No existe un rol con el identificador 9.",
            "RN-002")])
ERROR_422_PROPIA = _ejemplo_error(
    "Intenta inactivar su propia cuenta (RN-004)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.",
    [_error("usuario_id", "NEG_REGLA_INCUMPLIDA", "No puede inactivar su propia cuenta.",
            "RN-004")])


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[UsuarioResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar usuario",
             description="Registra un usuario en estado **activo**. Correo y documento únicos "
                         "(RN-001), rol obligatorio y activo (RN-002) y contraseña cifrada que "
                         "nunca se devuelve (RN-003). Requiere permiso *crear* en Usuarios.",
             responses={401: ERROR_401, 403: ERROR_403, 409: ERROR_409_DUPLICADO,
                        422: ERROR_422_DATOS})
def crear_usuario(datos: UsuarioCreate,
                  servicio: UsuarioService = Depends(obtener_servicio),
                  usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "crear"))):
    return respuesta_exitosa(servicio.crear(datos), "Usuario registrado correctamente.")


@router.get("", response_model=Respuesta[list[UsuarioResponse]],
            summary="Consultar usuarios",
            description="Consulta paginada de usuarios, con filtros opcionales. Nunca incluye "
                        "la contraseña (RN-003). La paginación va en `meta.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_usuarios(
        estado: Optional[str] = Query(None, description="activo | inactivo"),
        rol_id: Optional[int] = Query(None, description="Identificador del rol"),
        nombre: Optional[str] = Query(None, description="Texto contenido en el nombre completo"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: UsuarioService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "consultar"))):
    usuarios, paginacion = servicio.listar(estado, rol_id, nombre, pagina, por_pagina)
    return respuesta_exitosa(usuarios, "Consulta realizada correctamente.", paginacion)


@router.get("/{usuario_id}", response_model=Respuesta[UsuarioResponse],
            summary="Consultar un usuario",
            description="Devuelve los datos de un usuario por su identificador.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_usuario(usuario_id: int,
                    servicio: UsuarioService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "consultar"))):
    return respuesta_exitosa(servicio.obtener(usuario_id), "Consulta realizada correctamente.")


@router.put("/{usuario_id}", response_model=Respuesta[UsuarioResponse],
            summary="Editar datos del perfil",
            description="Reemplaza nombre, tipo y número de documento, correo y teléfono. "
                        "Correo y documento siguen siendo únicos (RN-001). El rol y el estado "
                        "no cambian aquí.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                       409: ERROR_409_DUPLICADO, 422: ERROR_422_DATOS})
def editar_usuario(usuario_id: int, datos: UsuarioUpdate,
                   servicio: UsuarioService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "editar"))):
    return respuesta_exitosa(servicio.editar(usuario_id, datos),
                             "Usuario actualizado correctamente.")


@router.patch("/{usuario_id}/estado", status_code=status.HTTP_204_NO_CONTENT,
              summary="Activar o inactivar usuario",
              description="Cambia el estado del usuario. Responde **204 No Content** (sin cuerpo). "
                          "Nadie puede inactivar su propia cuenta (RN-004). Al inactivar se "
                          "invalidan todas sus sesiones (RN-009). Los usuarios no se eliminan, "
                          "solo se inactivan (RN-005).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                         409: ERROR_409_ESTADO, 422: ERROR_422_PROPIA})
def cambiar_estado(usuario_id: int, datos: EstadoUsuarioUpdate,
                   servicio: UsuarioService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "inactivar"))):
    servicio.cambiar_estado(usuario_id, datos, usuario.usuario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{usuario_id}/rol", response_model=Respuesta[UsuarioResponse],
              summary="Asignar rol a un usuario",
              description="Cambia el rol del usuario. El rol debe existir y estar activo (RN-002). "
                          "Requiere permiso *editar* en Usuarios.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_ROL})
def cambiar_rol(usuario_id: int, datos: RolUsuarioUpdate,
                servicio: UsuarioService = Depends(obtener_servicio),
                usuario: UsuarioActual = Depends(requiere_permiso("Usuarios", "editar"))):
    return respuesta_exitosa(servicio.cambiar_rol(usuario_id, datos),
                             "Rol del usuario actualizado correctamente.")
