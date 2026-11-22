# app/services/proyecto_service.py
# CAPA SERVICIO - HU-05: casos de uso de proyectos.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.proyecto import Proyecto
from app.repositories.proyecto_repository import ProyectoRepository
from app.schemas.proyecto import (
    EstadoProyectoUpdate,
    ProyectoCreate,
    ProyectoResponse,
    ProyectoUpdate,
    ResponsableUpdate,
    UbicacionDatos,
)


class ProyectoService:

    def __init__(self, repo: ProyectoRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, proyecto_id: int) -> Proyecto:
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
        return ProyectoResponse.desde_modelo(self._buscar(proyecto_id))

    def listar(self, estado: Optional[str], ciudad: Optional[str], cliente: Optional[str],
               responsable_id: Optional[int], pagina: int,
               por_pagina: int) -> tuple[list[ProyectoResponse], dict]:
        proyectos, total = self.repo.listar(estado, ciudad, cliente, responsable_id,
                                            pagina, por_pagina)
        return ([ProyectoResponse.desde_modelo(p) for p in proyectos],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, proyecto_id: int, datos: ProyectoUpdate) -> ProyectoResponse:
        proyecto = self._buscar(proyecto_id)                                 # 404
        proyecto.verificar_editable()                                        # RN-019 (409)
        self._validar_nombre_unico(datos.nombre, datos.cliente,
                                   excluir_id=proyecto_id)                   # RN-018
        proyecto.editar(datos.nombre, datos.cliente, datos.descripcion,
                        datos.fecha_inicio, datos.fecha_fin_estimada)        # RN-017
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def registrar_ubicacion(self, proyecto_id: int, datos: UbicacionDatos) -> ProyectoResponse:
        proyecto = self._buscar(proyecto_id)
        proyecto.registrar_ubicacion(datos.direccion, datos.ciudad,
                                     datos.latitud, datos.longitud)          # RN-019
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def asignar_responsable(self, proyecto_id: int, datos: ResponsableUpdate) -> ProyectoResponse:
        proyecto = self._buscar(proyecto_id)
        usuario = self.repo.obtener_usuario(datos.responsable_id)
        proyecto.asignar_responsable(usuario, datos.responsable_id)          # RN-019, RN-016
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))

    def cambiar_estado(self, proyecto_id: int, datos: EstadoProyectoUpdate) -> ProyectoResponse:
        proyecto = self._buscar(proyecto_id)
        compromisos = self.repo.contar_compromisos_abiertos(proyecto_id)
        proyecto.cambiar_estado(datos.estado, compromisos)                   # RN-024, RN-025
        return ProyectoResponse.desde_modelo(self.repo.guardar(proyecto))
