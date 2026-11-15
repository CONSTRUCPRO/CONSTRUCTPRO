# api/material_router.py
# CAPA API: rutas HTTP con FastAPI.
# Solo recibe peticiones y llama al servicio. Aquí NO hay lógica de negocio.

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from domain.excepciones import (
    ConstruProError,
    RecursoDuplicadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from domain.material import (
    EstadoUpdate,
    MaterialCreate,
    MaterialResponse,
    PrecioUpdate,
)
from repository.material_repository import material_repository
from service.material_service import MaterialService

router = APIRouter(
    prefix="/api/v1/materiales",
    tags=["Materiales"],
)

# Instanciar el servicio con inyección del repositorio
service = MaterialService(repo=material_repository)


def _a_http(error: ConstruProError) -> HTTPException:
    """Traduce un error del dominio al código HTTP correspondiente."""
    if isinstance(error, RecursoNoEncontradoError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=error.mensaje)
    if isinstance(error, RecursoDuplicadoError):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"codigo": "REC_DUPLICADO", "regla": error.regla,
                    "mensaje": error.mensaje},
        )
    if isinstance(error, ReglaNegocioError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"regla": error.regla, "mensaje": error.mensaje},
        )
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                         detail="Ocurrió un error inesperado. Intente nuevamente.")


# ── GET /api/v1/materiales ────────────────────────────────────
@router.get("", response_model=list[MaterialResponse])
def listar_materiales(
    categoria_id: Optional[int] = None,
    nombre: Optional[str] = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(10, ge=1, le=100),
):
    """Consulta el catálogo, filtrado por categoría o nombre y paginado."""
    return service.listar(categoria_id, nombre, pagina, por_pagina)


# ── GET /api/v1/materiales/{material_id} ──────────────────────
@router.get("/{material_id}", response_model=MaterialResponse)
def obtener_material(material_id: int):
    """Retorna el detalle de un material."""
    try:
        return service.obtener(material_id)
    except ConstruProError as e:
        raise _a_http(e)


# ── POST /api/v1/materiales ───────────────────────────────────
@router.post("", response_model=MaterialResponse,
             status_code=status.HTTP_201_CREATED)
def crear_material(datos: MaterialCreate):
    """Registra un material nuevo en el catálogo."""
    try:
        return service.crear(datos)
    except ConstruProError as e:
        raise _a_http(e)


# ── PUT /api/v1/materiales/{material_id} ──────────────────────
@router.put("/{material_id}", response_model=MaterialResponse)
def editar_material(material_id: int, datos: MaterialCreate):
    """Edita todos los datos de un material."""
    try:
        return service.actualizar(material_id, datos)
    except ConstruProError as e:
        raise _a_http(e)


# ── PATCH /api/v1/materiales/{material_id}/precio ─────────────
@router.patch("/{material_id}/precio", response_model=MaterialResponse)
def actualizar_precio(material_id: int, datos: PrecioUpdate):
    """Actualiza solo el precio de referencia."""
    try:
        return service.actualizar_precio(material_id, datos)
    except ConstruProError as e:
        raise _a_http(e)


# ── PATCH /api/v1/materiales/{material_id}/estado ─────────────
@router.patch("/{material_id}/estado", response_model=MaterialResponse)
def cambiar_estado(material_id: int, datos: EstadoUpdate):
    """Inactiva un material (no se elimina, RN-035)."""
    try:
        return service.cambiar_estado(material_id, datos)
    except ConstruProError as e:
        raise _a_http(e)