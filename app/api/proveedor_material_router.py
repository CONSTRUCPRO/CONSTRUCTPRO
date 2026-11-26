# app/api/proveedor_material_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Las rutas cuelgan de /proveedores y de /materiales, por eso el router no lleva prefijo.
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_error, respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.proveedor_material_repository import ProveedorMaterialRepository
from app.api.schemas.proveedor_material import (
    OfertaCreate,
    OfertaResponse,
    ProveedorDeMaterialResponse,
)
from app.api.schemas.respuesta import Pagina, Respuesta
from app.services.proveedor_material_service import ProveedorMaterialService

router = APIRouter(tags=["Relación Material–Proveedor"])

# Las ofertas pertenecen al módulo "Materiales" (MODULO-03), así que usan sus permisos.
# Con los roles por defecto: Administrador y Coordinador asocian materiales; todos consultan.
MODULO = "Materiales"


def obtener_servicio(db: Session = Depends(get_db)) -> ProveedorMaterialService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return ProveedorMaterialService(ProveedorMaterialRepository(db))


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
                           None, "Debe iniciar sesión y enviar el token en el encabezado Authorization: Bearer <token>.", None)
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Materiales", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Empleado no tiene permiso para 'crear' en el módulo Materiales.",
                           None)
ERROR_404_PROVEEDOR = _ejemplo_error("El proveedor o el material no existe", "REC_NO_ENCONTRADO",
                                     "El recurso solicitado no existe.", "proveedor_id",
                                     "No existe un proveedor con el identificador 8.", None)
ERROR_404_MATERIAL = _ejemplo_error("El material no existe", "REC_NO_ENCONTRADO",
                                    "El recurso solicitado no existe.", "material_id",
                                    "No existe un material con el identificador 999.", None)
ERROR_409_INACTIVO = _ejemplo_error(
    "El proveedor o el material está inactivo", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "material_id",
    "El material 'Cemento gris tipo I 50 kg' está inactivo y no se puede asociar a un proveedor.",
    None)
ERROR_422_PRECIO = _ejemplo_error(
    "Precio ofrecido menor o igual a cero (RN-038)", "VAL_FORMATO_INVALIDO",
    "La información enviada contiene errores.", "precio",
    "El precio ofrecido debe ser mayor que cero.", "RN-038")


# ── Endpoints ────────────────────────────────────────────────

@router.post("/api/v1/proveedores/{proveedor_id}/materiales",
             response_model=Respuesta[OfertaResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Asociar material a un proveedor",
             description="Registra la oferta de un proveedor para un material del catálogo: "
                         "precio, disponibilidad y días de entrega. Responde **201** si la "
                         "oferta es nueva y **200** si el material ya estaba asociado y se "
                         "actualizó (no se duplica). El proveedor y el material deben estar "
                         "activos y el precio debe ser mayor que cero (RN-038).",
             responses={200: {"description": "La oferta ya existía y se actualizó"},
                        401: ERROR_401, 403: ERROR_403, 404: ERROR_404_PROVEEDOR,
                        409: ERROR_409_INACTIVO, 422: ERROR_422_PRECIO})
def asociar_material(proveedor_id: int, datos: OfertaCreate, response: Response,
                     servicio: ProveedorMaterialService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """
    POST /api/v1/proveedores/{proveedor_id}/materiales: registra la oferta (201) o, si ya
    existía, la actualiza (200). Por eso el código HTTP se cambia en `response`.
    """
    oferta, creada = servicio.asociar(proveedor_id, datos)
    if creada:
        return respuesta_exitosa(oferta, "Oferta registrada correctamente.")
    response.status_code = status.HTTP_200_OK
    return respuesta_exitosa(oferta, "Oferta actualizada correctamente.")


@router.get("/api/v1/materiales/{material_id}/proveedores",
            response_model=Respuesta[Pagina[ProveedorDeMaterialResponse]],
            summary="Consultar proveedores de un material",
            description="Devuelve los proveedores **activos** que ofrecen el material, con su "
                        "precio, disponibilidad y días de entrega. Es la base del comparativo "
                        "de precios (HU-16). La paginación va en `data.paginacion`.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404_MATERIAL})
def proveedores_de_material(
        material_id: int,
        pagina: int = Query(1, ge=1, description="Número de página"),
        por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
        servicio: ProveedorMaterialService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """
    GET /api/v1/materiales/{material_id}/proveedores: proveedores activos que ofrecen el material.
    """
    items, paginacion = servicio.proveedores_de_material(material_id, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)
