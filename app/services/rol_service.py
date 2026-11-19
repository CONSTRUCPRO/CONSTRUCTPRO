# app/services/rol_service.py
# CAPA SERVICIO - HU-03: casos de uso de roles y permisos (FUN-011, 012, 013, 015).
# No importa FastAPI: lanza excepciones de dominio.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.rol import Rol
from app.repositories.rol_repository import RolRepository
from app.schemas.rol import (EstadoRolUpdate, PermisosRolResponse, PermisosUpdate,
                             RolCreate, RolResponse, RolUpdate)


class RolService:

    def __init__(self, repo: RolRepository):
        self.repo = repo

    def _buscar(self, rol_id: int) -> Rol:
        rol = self.repo.obtener_por_id(rol_id)
        if not rol:
            raise RecursoNoEncontradoError(f"No existe un rol con el identificador {rol_id}.",
                                           campo="rol_id")
        return rol

    def _validar_nombre_unico(self, nombre: str, excluir_id: Optional[int] = None) -> None:
        # RN-011: el nombre de un rol debe ser único
        if self.repo.existe_nombre(nombre, excluir_id):
            raise RecursoDuplicadoError("RN-011", f"Ya existe un rol con el nombre '{nombre}'.",
                                        campo="nombre")

    # FUN-011 Crear rol
    def crear(self, datos: RolCreate) -> RolResponse:
        self._validar_nombre_unico(datos.nombre)
        rol = Rol(nombre=datos.nombre, descripcion=datos.descripcion)
        rol.asignar_permisos(datos.permisos_dict())          # RN-013
        return RolResponse.desde_modelo(self.repo.guardar(rol))

    def listar(self, estado: Optional[str], pagina: int,
               por_pagina: int) -> tuple[list[RolResponse], dict]:
        roles, total = self.repo.listar(estado, pagina, por_pagina)
        return ([RolResponse.desde_modelo(r) for r in roles],
                construir_paginacion(pagina, por_pagina, total))

    def obtener(self, rol_id: int) -> RolResponse:
        return RolResponse.desde_modelo(self._buscar(rol_id))

    # FUN-012 Editar rol
    def editar(self, rol_id: int, datos: RolUpdate) -> RolResponse:
        rol = self._buscar(rol_id)
        self._validar_nombre_unico(datos.nombre, excluir_id=rol_id)
        rol.renombrar(datos.nombre, datos.descripcion)       # RN-015
        return RolResponse.desde_modelo(self.repo.guardar(rol))

    # FUN-013 Asignar permisos a un rol
    def asignar_permisos(self, rol_id: int, datos: PermisosUpdate) -> PermisosRolResponse:
        rol = self._buscar(rol_id)
        rol.asignar_permisos(datos.permisos_dict())          # RN-013
        return PermisosRolResponse.desde_modelo(self.repo.guardar(rol))

    # FUN-015 Consultar permisos de un rol
    def consultar_permisos(self, rol_id: int) -> PermisosRolResponse:
        return PermisosRolResponse.desde_modelo(self._buscar(rol_id))

    def cambiar_estado(self, rol_id: int, datos: EstadoRolUpdate) -> RolResponse:
        rol = self._buscar(rol_id)
        usuarios_activos = self.repo.contar_usuarios_activos(rol_id)
        rol.cambiar_estado(datos.estado, usuarios_activos)   # RN-015, RN-012
        return RolResponse.desde_modelo(self.repo.guardar(rol))

    # Usado por app/core/seguridad.py -> requiere_permiso(...) (FUN-009)
    def rol_tiene_permiso(self, nombre_rol: str, modulo: str, accion: str) -> bool:
        rol = self.repo.obtener_por_nombre(nombre_rol)
        return bool(rol and rol.tiene_permiso(modulo, accion))
