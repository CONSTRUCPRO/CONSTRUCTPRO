# app/api/rol_router.py
# CAPA API - HU-03 Gestión de Roles y Permisos.
# Solo recibe la petición, llama al servicio y devuelve el sobre estándar.
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, obtener_usuario_actual, requiere_rol
from app.repositories.rol_repository import RolRepository
from app.schemas.respuesta import Respuesta
from app.schemas.rol import (EstadoRolUpdate, PermisosRolResponse, PermisosUpdate,
                             RolCreate, RolResponse, RolUpdate)
from app.services.rol_service import RolService

router = APIRouter(prefix="/api/v1/roles", tags=["Roles y permisos"])

# RN-014: solo el rol administrador puede crear roles o modificar permisos.
solo_administrador = requiere_rol("Administrador", regla="RN-014")


def obtener_servicio(db: Session = Depends(get_db)) -> RolService:
    return RolService(RolRepository(db))


@router.post("", response_model=Respuesta[RolResponse], status_code=status.HTTP_201_CREATED,
             summary="Crear rol (FUN-011)")
def crear_rol(datos: RolCreate,
              servicio: RolService = Depends(obtener_servicio),
              usuario: UsuarioActual = Depends(solo_administrador)):
    """Crea un rol con nombre, descripción y al menos un permiso. Solo Administrador."""
    return respuesta_exitosa(servicio.crear(datos), "Rol creado correctamente.")


@router.get("", response_model=Respuesta[list[RolResponse]], summary="Consultar roles")
def listar_roles(estado: Optional[Literal["activo", "inactivo"]] = None,
                 pagina: int = Query(1, ge=1),
                 por_pagina: int = Query(10, ge=1, le=100),
                 servicio: RolService = Depends(obtener_servicio),
                 usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    """Lista los roles con sus permisos, paginados."""
    roles, paginacion = servicio.listar(estado, pagina, por_pagina)
    return respuesta_exitosa(roles, "Consulta realizada correctamente.", paginacion)


@router.get("/{rol_id}", response_model=Respuesta[RolResponse], summary="Detalle de un rol")
def obtener_rol(rol_id: int,
                servicio: RolService = Depends(obtener_servicio),
                usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    return respuesta_exitosa(servicio.obtener(rol_id), "Consulta realizada correctamente.")


@router.put("/{rol_id}", response_model=Respuesta[RolResponse], summary="Editar rol (FUN-012)")
def editar_rol(rol_id: int, datos: RolUpdate,
               servicio: RolService = Depends(obtener_servicio),
               usuario: UsuarioActual = Depends(solo_administrador)):
    """Modifica el nombre o la descripción. Los roles del sistema no se renombran (RN-015)."""
    return respuesta_exitosa(servicio.editar(rol_id, datos), "Rol actualizado correctamente.")


@router.put("/{rol_id}/permisos", response_model=Respuesta[PermisosRolResponse],
            summary="Asignar permisos a un rol (FUN-013)")
def asignar_permisos(rol_id: int, datos: PermisosUpdate,
                     servicio: RolService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(solo_administrador)):
    """Reemplaza los permisos del rol. Debe quedar al menos uno (RN-013)."""
    return respuesta_exitosa(servicio.asignar_permisos(rol_id, datos),
                             "Permisos asignados correctamente.")


@router.get("/{rol_id}/permisos", response_model=Respuesta[PermisosRolResponse],
            summary="Consultar permisos de un rol (FUN-015)")
def consultar_permisos(rol_id: int,
                       servicio: RolService = Depends(obtener_servicio),
                       usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    return respuesta_exitosa(servicio.consultar_permisos(rol_id),
                             "Consulta realizada correctamente.")


@router.patch("/{rol_id}/estado", response_model=Respuesta[RolResponse],
              summary="Activar o inactivar un rol")
def cambiar_estado(rol_id: int, datos: EstadoRolUpdate,
                   servicio: RolService = Depends(obtener_servicio),
                   usuario: UsuarioActual = Depends(solo_administrador)):
    """Coordinador, Director y Administrador no se pueden inactivar (RN-015).
    Tampoco un rol que tenga usuarios activos asignados (RN-012)."""
    return respuesta_exitosa(servicio.cambiar_estado(rol_id, datos),
                             "Estado del rol actualizado correctamente.")
