# app/services/usuario_service.py
# CAPA SERVICIO - HU-01: casos de uso de usuarios.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.usuario import Usuario
from app.repositories.usuario_repository import UsuarioRepository
from app.api.schemas.usuario import (
    EstadoUsuarioUpdate,
    RolUsuarioUpdate,
    UsuarioCreate,
    UsuarioResponse,
    UsuarioUpdate,
)


class UsuarioService:
    """
    Casos de uso de usuarios (HU-01). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: UsuarioRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, usuario_id: int) -> Usuario:
        """Trae el usuario por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
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
        """
        Registra un usuario: RN-001 (correo y documento únicos), RN-002 (rol válido) y RN-003 (contraseña cifrada).
        """
        self._validar_unicos(datos.correo, datos.numero_documento)          # RN-001
        rol = self.repo.obtener_rol(datos.rol_id)
        Usuario.validar_rol_asignable(rol, datos.rol_id)                     # RN-002
        usuario = Usuario.registrar(datos.nombre_completo, datos.tipo_documento,
                                    datos.numero_documento, datos.correo, datos.telefono,
                                    datos.contrasena, rol)                   # RN-003
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))

    def obtener(self, usuario_id: int) -> UsuarioResponse:
        """Un usuario por su id."""
        return UsuarioResponse.desde_modelo(self._buscar(usuario_id))

    def listar(self, estado: Optional[str], rol_id: Optional[int], nombre: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[UsuarioResponse], dict]:
        """Lista paginada con filtros opcionales por estado, rol y nombre."""
        usuarios, total = self.repo.listar(estado, rol_id, nombre, pagina, por_pagina)
        return ([UsuarioResponse.desde_modelo(u) for u in usuarios],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, usuario_id: int, datos: UsuarioUpdate) -> UsuarioResponse:
        """Edita el perfil (no el rol, la contraseña ni el estado) validando de nuevo la RN-001."""
        usuario = self._buscar(usuario_id)                                   # 404
        self._validar_unicos(datos.correo, datos.numero_documento,
                             excluir_id=usuario_id)                          # RN-001
        usuario.editar_perfil(datos.nombre_completo, datos.tipo_documento,
                              datos.numero_documento, datos.correo, datos.telefono)
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))

    def cambiar_estado(self, usuario_id: int, datos: EstadoUsuarioUpdate,
                       usuario_actual_id: Optional[str]) -> None:
        """Activa o inactiva: RN-004 (no a uno mismo) y RN-009 (inactivar cierra sus sesiones)."""
        usuario = self._buscar(usuario_id)
        usuario.cambiar_estado(datos.estado, usuario_actual_id)              # RN-004, RN-009
        self.repo.guardar(usuario)

    def cambiar_rol(self, usuario_id: int, datos: RolUsuarioUpdate) -> UsuarioResponse:
        """Asigna otro rol al usuario (RN-002: el rol debe existir y estar activo)."""
        usuario = self._buscar(usuario_id)
        rol = self.repo.obtener_rol(datos.rol_id)
        usuario.asignar_rol(rol, datos.rol_id)                               # RN-002
        return UsuarioResponse.desde_modelo(self.repo.guardar(usuario))
