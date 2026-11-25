# app/api/material_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.material_repository import MaterialRepository
from app.api.schemas.material import (
    EstadoUpdate,
    MaterialCreate,
    MaterialResponse,
    MaterialUpdate,
    PrecioUpdate,
)
from app.api.schemas.respuesta import Respuesta
from app.services.material_service import MaterialService

router = APIRouter(prefix="/api/v1/materiales", tags=["Materiales"])

# Permisos del módulo "Materiales" (tabla permisos_rol). Con los roles por defecto:
# Administrador y Coordinador crean, editan e inactivan; todos los roles consultan.
MODULO = "Materiales"


def obtener_servicio(db: Session = Depends(get_db)) -> MaterialService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return MaterialService(MaterialRepository(db))


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
ERROR_404 = _ejemplo_error("El material no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "material_id",
                           "No existe un material con el identificador 115.", None)
ERROR_409_DUPLICADO = _ejemplo_error(
    "Material repetido en la categoría (RN-031)", "REC_DUPLICADO",
    "Ya existe un registro con ese identificador.", "nombre",
    "Ya existe el material 'Cemento gris tipo I 50 kg' con unidad 'bulto' en la categoría Cementos.",
    "RN-031")
ERROR_409_ESTADO = _ejemplo_error(
    "El material ya está en ese estado (RN-035)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "estado",
    "El material ya se encuentra en estado 'inactivo'.", "RN-035")
ERROR_422_PRECIO = _ejemplo_error(
    "Regla de negocio incumplida (RN-032 unidad/categoría, RN-033 precio)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.", "precio_referencia",
    "El precio de referencia debe ser mayor que cero.", "RN-033")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[MaterialResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar material",
             description="Registra un material en el catálogo. Nace en estado **activo**. "
                         "Valida RN-031 (no repetido en la categoría), RN-032 (unidad y categoría "
                         "válidas) y RN-033 (precio mayor que cero).",
             responses={401: ERROR_401, 403: ERROR_403, 409: ERROR_409_DUPLICADO,
                        422: ERROR_422_PRECIO})
def crear_material(datos: MaterialCreate,
                   servicio: MaterialService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/materiales: registra un material (201)."""
    return respuesta_exitosa(servicio.crear(datos), "Material registrado correctamente.")


@router.get("", response_model=Respuesta[list[MaterialResponse]],
            summary="Consultar catálogo de materiales",
            description="Consulta paginada del catálogo. Filtros opcionales por categoría, "
                        "parte del nombre y estado. La paginación va en `meta.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403})
def listar_materiales(
        categoria_id: Optional[int] = Query(None, description="Id de la categoría"),
        nombre: Optional[str] = Query(None, description="Texto contenido en el nombre"),
        estado: Optional[str] = Query(None, description="activo | inactivo"),
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: MaterialService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/materiales: catálogo paginado con filtros."""
    items, paginacion = servicio.listar(categoria_id, nombre, estado, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{material_id}", response_model=Respuesta[MaterialResponse],
            summary="Detalle de un material",
            description="Devuelve los datos de un material por su identificador.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_material(material_id: int,
                     servicio: MaterialService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/materiales/{material_id}: un material."""
    return respuesta_exitosa(servicio.obtener(material_id), "Consulta realizada correctamente.")


@router.put("/{material_id}", response_model=Respuesta[MaterialResponse],
            summary="Editar material",
            description="Reemplaza nombre, unidad, categoría y precio de un material. "
                        "Valida RN-031, RN-032 y RN-033. El estado no cambia aquí.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                       409: ERROR_409_DUPLICADO, 422: ERROR_422_PRECIO})
def editar_material(material_id: int, datos: MaterialUpdate,
                    servicio: MaterialService = Depends(obtener_servicio),
                    usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """PUT /api/v1/materiales/{material_id}: reemplaza sus datos."""
    return respuesta_exitosa(servicio.editar(material_id, datos),
                             "Material actualizado correctamente.")


@router.patch("/{material_id}/precio", response_model=Respuesta[MaterialResponse],
              summary="Actualizar precio de referencia",
              description="Cambia solo el precio de referencia. Debe ser mayor que cero (RN-033).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_PRECIO})
def actualizar_precio(material_id: int, datos: PrecioUpdate,
                      servicio: MaterialService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """PATCH /api/v1/materiales/{material_id}/precio: cambia el precio de referencia."""
    return respuesta_exitosa(servicio.actualizar_precio(material_id, datos),
                             "Precio de referencia actualizado correctamente.")


@router.patch("/{material_id}/estado", response_model=Respuesta[MaterialResponse],
              summary="Inactivar o reactivar material",
              description="Un material no se elimina, solo se inactiva (RN-035). Un material "
                          "inactivo no se puede usar en solicitudes ni cotizaciones (RN-034).",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ESTADO})
def cambiar_estado(material_id: int, datos: EstadoUpdate,
                   servicio: MaterialService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "inactivar"))):
    """PATCH /api/v1/materiales/{material_id}/estado: inactiva o reactiva."""
    return respuesta_exitosa(servicio.cambiar_estado(material_id, datos),
                             "Estado del material actualizado correctamente.")
