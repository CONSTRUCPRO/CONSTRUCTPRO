# app/services/proyecto_service.py
# CAPA SERVICIO - HU-05: casos de uso de proyectos.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.proyecto import Proyecto
from app.repositories.proyecto_repository import ProyectoRepository
from app.api.schemas.proyecto import (
    EstadoProyectoUpdate,
    ProyectoCreate,
    ProyectoResponse,
    ProyectoUpdate,
    ResponsableUpdate,
    UbicacionDatos,
)


class ProyectoService:
    """
    Casos de uso de proyectos (HU-05). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: ProyectoRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, proyecto_id: int) -> Proyecto:
        """Trae el proyecto por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        proyecto = self.repo.obtener_por_id(proyecto_id)
        if not proyecto:
            raise RecursoNoEncontradoError(
                f"No existe un proyecto con el identificador {proyecto_id}.",
                campo="proyecto_id",
            )
        return proyecto

    def _validar_nombre_unico(self, nombre: str, cliente: str,
                              excluir_id: Optional[int] = None) -> None:
        """RN-018: el nombre del proyecto es único por cliente."""
        if self.repo.existe_nombre_en_cliente(nombre, cliente, excluir_id):
            raise RecursoDuplicadoError(
                "RN-018", f"El cliente {cliente} ya tiene un proyecto llamado '{nombre}'.",
                campo="nombre")

    # ── Casos de uso ───────────────────────────────────────

    def crear(self, datos: ProyectoCreate) -> ProyectoResponse:
        """
        FUN-016: registra el proyecto activo. Valida RN-018 (nombre único por cliente), RN-016
        (responsable activo, Coordinador o Director) y RN-017 (fechas). La ubicación es opcional.
        """
        self._validar_nombre_unico(datos.nombre, datos.cliente)              # RN-018
        responsable = self.repo.obtener_usuario(datos.responsable_id)
        Proyecto.validar_responsable(responsable, datos.responsable_id)      # RN-016
        proyecto = Proyecto.registrar(datos.nombre, datos.cliente, datos.descripcion,
                                      datos.fecha_inicio, datos.fecha_fin_estimada,
                                      responsable)                           # RN-017
        if datos.ubicacion:
            u = datos.ubicacion
            proyecto.registrar_ubicacion(u.direccion, u.ciudad, u.latitud, u.longitud)
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def obtener(self, proyecto_id: int) -> ProyectoResponse:
        """Un proyecto con su ubicación y responsable."""
        return ProyectoResponse.desde_modelo(self._buscar(proyecto_id))

    def listar(self, estado: Optional[str], ciudad: Optional[str], cliente: Optional[str],
               responsable_id: Optional[int], pagina: int,
               por_pagina: int) -> tuple[list[ProyectoResponse], dict]:
        """FUN-017: lista paginada con filtros por estado, ciudad, cliente o responsable."""
        proyectos, total = self.repo.listar(estado, ciudad, cliente, responsable_id,
                                            pagina, por_pagina)
        return ([ProyectoResponse.desde_modelo(p) for p in proyectos],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, proyecto_id: int, datos: ProyectoUpdate) -> ProyectoResponse:
        """FUN-018: edita los datos generales. RN-019 (finalizado no se edita), RN-018 y RN-017."""
        proyecto = self._buscar(proyecto_id)                                 # 404
        proyecto.verificar_editable()                                        # RN-019 (409)
        self._validar_nombre_unico(datos.nombre, datos.cliente,
                                   excluir_id=proyecto_id)                   # RN-018
        proyecto.editar(datos.nombre, datos.cliente, datos.descripcion,
                        datos.fecha_inicio, datos.fecha_fin_estimada)        # RN-017
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def registrar_ubicacion(self, proyecto_id: int, datos: UbicacionDatos) -> ProyectoResponse:
        """FUN-019: registra o cambia la ubicación (RN-019: no en un proyecto finalizado)."""
        proyecto = self._buscar(proyecto_id)
        proyecto.registrar_ubicacion(datos.direccion, datos.ciudad,
                                     datos.latitud, datos.longitud)          # RN-019
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def asignar_responsable(self, proyecto_id: int, datos: ResponsableUpdate) -> ProyectoResponse:
        """FUN-020: cambia el responsable (RN-016 y RN-019)."""
        proyecto = self._buscar(proyecto_id)
        usuario = self.repo.obtener_usuario(datos.responsable_id)
        proyecto.asignar_responsable(usuario, datos.responsable_id)          # RN-019, RN-016
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def cambiar_estado(self, proyecto_id: int, datos: EstadoProyectoUpdate) -> ProyectoResponse:
        """
        FUN-024: activo <-> suspendido -> finalizado. RN-024: un finalizado no vuelve. RN-025: no se
        finaliza con órdenes de compra abiertas (el repositorio las cuenta).
        """
        proyecto = self._buscar(proyecto_id)
        compromisos = self.repo.contar_compromisos_abiertos(proyecto_id)
        proyecto.cambiar_estado(datos.estado, compromisos)                   # RN-024, RN-025
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))
