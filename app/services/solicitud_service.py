# app/services/solicitud_service.py
# CAPA SERVICIO: orquesta los casos de uso de las solicitudes de materiales.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import NoAutenticadoError, RecursoNoEncontradoError
from app.domain.material import Material
from app.domain.proyecto import Proyecto
from app.domain.solicitud import Solicitud
from app.domain.usuario import Usuario
from app.repositories.solicitud_repository import SolicitudRepository
from app.schemas.solicitud import LineaSolicitud, SolicitudCreate, SolicitudResponse, SolicitudUpdate


class SolicitudService:
    """
    Casos de uso de solicitudes de materiales (HU-12). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: SolicitudRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _usuario_actual(self, usuario_id: Optional[str]) -> Usuario:
        """
        El usuario autenticado (sale del token de la HU-02): es el solicitante
        o quien edita o anula la solicitud.
        """
        if not usuario_id or not str(usuario_id).isdigit():
            raise NoAutenticadoError(
                "No se pudo identificar al usuario de la sesión; inicie sesión nuevamente.",
                campo="Authorization")
        usuario = self.repo.obtener_usuario(int(usuario_id))
        if not usuario or not usuario.esta_activo():
            raise NoAutenticadoError(
                f"El usuario {usuario_id} no existe o está inactivo.", campo="Authorization")
        return usuario

    def _buscar(self, solicitud_id: int) -> Solicitud:
        """Trae la solicitud por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        solicitud = self.repo.obtener_por_id(solicitud_id)
        if not solicitud:
            raise RecursoNoEncontradoError(
                f"No existe una solicitud con el identificador {solicitud_id}.",
                campo="solicitud_id")
        return solicitud

    def _buscar_proyecto(self, proyecto_id: int) -> Proyecto:
        """Trae el proyecto por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        proyecto = self.repo.obtener_proyecto(proyecto_id)
        if not proyecto:
            raise RecursoNoEncontradoError(
                f"No existe un proyecto con el identificador {proyecto_id}.",
                campo="proyecto_id")
        return proyecto

    def _lineas(self, detalle: list[LineaSolicitud]) -> list[tuple[Material, int]]:
        """Valida RN-042 y RN-043 y cambia cada material_id por el Material (404 si no existe)."""
        Solicitud.validar_lineas([(l.material_id, l.cantidad) for l in detalle])  # RN-042, RN-043
        materiales = self.repo.obtener_materiales([l.material_id for l in detalle])
        for i, linea in enumerate(detalle):
            if linea.material_id not in materiales:
                raise RecursoNoEncontradoError(
                    f"No existe un material con el identificador {linea.material_id}.",
                    campo=f"detalle.{i}.material_id")
        return [(materiales[l.material_id], l.cantidad) for l in detalle]

    # ── Casos de uso ───────────────────────────────────────

    def crear(self, datos: SolicitudCreate, usuario_id: Optional[str]) -> SolicitudResponse:
        """
        Crea la solicitud pendiente. Valida el proyecto con verificar_admite_solicitudes()
        (RN-041 activo, RN-020 ubicación, RN-021 presupuesto), las líneas (RN-042, RN-043) y que
        cada material exista y esté activo (RN-034).
        """
        solicitante = self._usuario_actual(usuario_id)                  # 401
        proyecto = self._buscar_proyecto(datos.proyecto_id)             # 404
        proyecto.verificar_admite_solicitudes()                         # RN-041, RN-020, RN-021
        lineas = self._lineas(datos.detalle)                            # RN-042, RN-043, 404
        solicitud = Solicitud.registrar(proyecto, solicitante, lineas)  # RN-034
        return SolicitudResponse.desde_modelo(self.repo.guardar(solicitud))

    def obtener(self, solicitud_id: int) -> SolicitudResponse:
        """Una solicitud con sus líneas."""
        return SolicitudResponse.desde_modelo(self._buscar(solicitud_id))

    def listar(self, proyecto_id: Optional[int], estado: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[SolicitudResponse], dict]:
        """Lista paginada (la más reciente primero) con filtros por proyecto y estado."""
        items, total = self.repo.listar(proyecto_id, estado, pagina, por_pagina)
        return ([SolicitudResponse.desde_modelo(s) for s in items],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, solicitud_id: int, datos: SolicitudUpdate,
               usuario_id: Optional[str]) -> SolicitudResponse:
        """
        Reemplaza el detalle. Solo el solicitante o el responsable (RN-044), solo si está
        pendiente y si no tiene una cotización aprobada (RN-045).
        """
        usuario = self._usuario_actual(usuario_id)                      # 401
        solicitud = self._buscar(solicitud_id)                          # 404
        solicitud.verificar_autor(usuario.id)                           # RN-044 (403)
        solicitud.verificar_pendiente()                                 # 409
        solicitud.verificar_sin_compra_aprobada(
            self.repo.tiene_cotizacion_aprobada(solicitud.id))          # RN-045 (409)
        lineas = self._lineas(datos.detalle)                            # RN-042, RN-043, 404
        solicitud.editar(usuario.id, lineas)                            # RN-034
        return SolicitudResponse.desde_modelo(self.repo.guardar(solicitud))

    def anular(self, solicitud_id: int, usuario_id: Optional[str]) -> SolicitudResponse:
        """Anula la solicitud con las mismas condiciones que editar (RN-044, pendiente, RN-045)."""
        usuario = self._usuario_actual(usuario_id)                      # 401
        solicitud = self._buscar(solicitud_id)                          # 404
        solicitud.verificar_autor(usuario.id)                           # RN-044 (403)
        solicitud.verificar_sin_compra_aprobada(
            self.repo.tiene_cotizacion_aprobada(solicitud.id))          # RN-045 (409)
        solicitud.anular(usuario.id)                                    # RN-044, pendiente
        return SolicitudResponse.desde_modelo(self.repo.guardar(solicitud))
