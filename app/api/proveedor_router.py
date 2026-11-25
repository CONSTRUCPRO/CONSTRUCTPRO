# app/api/proveedor_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.proveedor_repository import ProveedorRepository
from app.api.schemas.proveedor import (
    EstadoProveedorUpdate,
    ProveedorCreate,
    ProveedorResponse,
    ProveedorUpdate,
)
from app.api.schemas.respuesta import Respuesta
from app.services.proveedor_service import ProveedorService

router = APIRouter(prefix="/api/v1/proveedores", tags=["Proveedores"])

# Los proveedores pertenecen al módulo "Materiales" (MODULO-03), así que usan sus permisos.
# Con los roles por defecto: Administrador y Coordinador crean, editan e inactivan;
# todos los roles consultan.
MODULO = "Materiales"


def obtener_servicio(db: Session = Depends(get_db)) -> ProveedorService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return ProveedorService(ProveedorRepository(db))


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
                           None, "Debe iniciar sesión y enviar el token en el encabezado Authorization: Bearer <token>.", None)
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Materiales", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Empleado no tiene permiso para 'crear' en el módulo Materiales.",
                           None)
ERROR_404 = _ejemplo_error("El proveedor no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "proveedor_id",
                           "No existe un proveedor con el identificador 8.", None)
ERROR_409_NIT = _ejemplo_error(
    "NIT repetido (RN-036)", "REC_DUPLICADO",
    "Ya existe un registro con ese identificador.", "nit",
    "Ya existe un proveedor con el NIT 900123456-7.", "RN-036")
ERROR_409_ORDENES = _ejemplo_error(
    "El proveedor tiene órdenes de compra abiertas (RN-040)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "El proveedor tiene 1 orden(es) de compra abierta(s) y no puede inactivarse.", "RN-040")
ERROR_422_FORMATO = _ejemplo_error(
    "Formato inválido (NIT, teléfono o correo)", "VAL_FORMATO_INVALIDO",
    "La información enviada contiene errores.", "correo",
    "El correo no tiene un formato válido. Ejemplo: ventas@elconstructor.co.", None)


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[ProveedorResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar proveedor",
             description="Registra un proveedor. Nace en estado **activo**. El NIT es único "
                         "(RN-036). Se valida el formato de NIT, teléfono y correo.",
             responses={401: ERROR_401, 403: ERROR_403, 409: ERROR_409_NIT,
                        422: ERROR_422_FORMATO})
def crear_proveedor(datos: ProveedorCreate,
                    servicio: ProveedorService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/proveedores: registra un proveedor (201)."""
    return respuesta_exitosa(servicio.crear(datos), "Proveedor registrado correctamente.")


@router.get("", response_model=Respuesta[list[ProveedorResponse]],
            summary="Consultar proveedores",
            description="Consulta paginada de proveedores. Filtros opcionales por estado y "
                        "parte de la razón social. La paginación va en `meta.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_proveedores(
        estado: Optional[str] = Query(None, description="activo | inactivo"),
        razon_social: Optional[str] = Query(None, description="Texto contenido en la razón social"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: ProveedorService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/proveedores: lista paginada con filtros."""
    items, paginacion = servicio.listar(estado, razon_social, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{proveedor_id}", response_model=Respuesta[ProveedorResponse],
            summary="Detalle de un proveedor",
            description="Devuelve los datos de un proveedor por su identificador.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_proveedor(proveedor_id: int,
                      servicio: ProveedorService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/proveedores/{proveedor_id}: un proveedor."""
    return respuesta_exitosa(servicio.obtener(proveedor_id), "Consulta realizada correctamente.")


@router.put("/{proveedor_id}", response_model=Respuesta[ProveedorResponse],
            summary="Editar proveedor",
            description="Reemplaza razón social, NIT, contacto, teléfono y correo. "
                        "El NIT sigue siendo único (RN-036). El estado no cambia aquí.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                       409: ERROR_409_NIT, 422: ERROR_422_FORMATO})
def editar_proveedor(proveedor_id: int, datos: ProveedorUpdate,
                     servicio: ProveedorService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """PUT /api/v1/proveedores/{proveedor_id}: reemplaza sus datos."""
    return respuesta_exitosa(servicio.editar(proveedor_id, datos),
                             "Proveedor actualizado correctamente.")


@router.patch("/{proveedor_id}/estado", status_code=status.HTTP_204_NO_CONTENT,
              summary="Inactivar o reactivar proveedor",
              description="Cambia el estado del proveedor. Responde **204 No Content** (sin cuerpo). "
                          "No se puede inactivar si tiene órdenes de compra abiertas (RN-040). "
                          "Un proveedor inactivo no puede recibir nuevas órdenes (RN-039).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ORDENES})
def cambiar_estado(proveedor_id: int, datos: EstadoProveedorUpdate,
                   servicio: ProveedorService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "inactivar"))):
    """PATCH /api/v1/proveedores/{proveedor_id}/estado: inactiva o reactiva (204)."""
    servicio.cambiar_estado(proveedor_id, datos)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
