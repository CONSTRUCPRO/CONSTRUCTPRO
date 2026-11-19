# app/services/usuario_service.py
# CAPA SERVICIO - HU-01: casos de uso de usuarios.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.usuario import Usuario
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuario import (
    EstadoUsuarioUpdate,
    RolUsuarioUpdate,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)


class UsuarioService:

    def __init__(self, repo: UsuarioRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, usuario_id: int) -> Usuario:
        usuario = self.repo.obtener_por_id(usuario_id)
        if not usuario:
            raise RecursoNoEncontradoError(
                f"No existe un usuario con el identificador {usuario_id}.",
                campo="usuario_id",
            )
        return usuario

    def _validar_unicos(self, correo: str, numero_documento: str,
                        excluir_id: Optional[int] = None) -> None:
        """RN-001: correo y número de documento únicos."""
        if self.repo.existe_correo(correo, excluir_id):
            raise RecursoDuplicadoError("RN-001", f"El correo {correo} ya está registrado.",
                                        campo="correo")
        if self.repo.existe_documento(numero_documento, excluir_id):
            raise RecursoDuplicadoError(
                "RN-001", f"El número de documento {numero_documento} ya está registrado.",
                campo="numero_documento")

    # ── Casos de uso ───────────────────────────────────────

    def crear(self, datos: UsuarioCreate) -> UsuarioResponse:
        self._validar_unicos(datos.correo, datos.numero_documento)          # RN-001
        rol = self.repo.obtener_rol(datos.rol_id)
        Usuario.validar_rol_asignable(rol, datos.rol_id)                     # RN-002
        usuario = Usuario.registrar(datos.nombre_completo, datos.tipo_documento,
                                    datos.numero_documento, datos.correo, datos.telefono,
                                    datos.contrasena, rol)                   # RN-003
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))

    def obtener(self, usuario_id: int) -> UsuarioResponse:
        return UsuarioResponse.desde_modelo(self._buscar(usuario_id))

    def listar(self, estado: Optional[str], rol_id: Optional[int], nombre: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[UsuarioResponse], dict]:
        usuarios, total = self.repo.listar(estado, rol_id, nombre, pagina, por_pagina)
        return ([UsuarioResponse.desde_modelo(u) for u in usuarios],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, usuario_id: int, datos: UsuarioUpdate) -> UsuarioResponse:
        usuario = self._buscar(usuario_id)                                   # 404
        self._validar_unicos(datos.correo, datos.numero_documento,
                             excluir_id=usuario_id)                          # RN-001
        usuario.editar_perfil(datos.nombre_completo, datos.tipo_documento,
                              datos.numero_documento, datos.correo, datos.telefono)
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))

    def cambiar_estado(self, usuario_id: int, datos: EstadoUsuarioUpdate,
                       usuario_actual_id: Optional[str]) -> None:
        usuario = self._buscar(usuario_id)
        usuario.cambiar_estado(datos.estado, usuario_actual_id)              # RN-004, RN-009
        self.repo.guardar(usuario)

    def cambiar_rol(self, usuario_id: int, datos: RolUsuarioUpdate) -> UsuarioResponse:
        usuario = self._buscar(usuario_id)
        rol = self.repo.obtener_rol(datos.rol_id)
        usuario.asignar_rol(rol, datos.rol_id)                               # RN-002
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))
