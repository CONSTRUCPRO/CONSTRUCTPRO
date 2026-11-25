# app/services/presupuesto_service.py
# CAPA SERVICIO - HU-06: casos de uso del presupuesto del proyecto.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.domain.excepciones import ConflictoEstadoError, RecursoNoEncontradoError
from app.domain.presupuesto import Presupuesto
from app.domain.proyecto import Proyecto
from app.repositories.presupuesto_repository import PresupuestoRepository
from app.schemas.presupuesto import PresupuestoDatos, PresupuestoResponse


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    """El id del usuario llega como texto (encabezado); se guarda como número si se puede."""
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class PresupuestoService:
    """
    Casos de uso de el presupuesto del proyecto (HU-06). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: PresupuestoRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar_proyecto(self, proyecto_id: int) -> Proyecto:
        """Trae el proyecto por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO)."""
        proyecto = self.repo.obtener_proyecto(proyecto_id)
        if not proyecto:
            raise RecursoNoEncontradoError(
                f"No existe un proyecto con el identificador {proyecto_id}.", campo="proyecto_id")
        return proyecto

    def _presupuesto_de(self, proyecto: Proyecto) -> Presupuesto:
        """El presupuesto del proyecto o 404 si todavía no tiene uno asignado."""
        if proyecto.presupuesto is None:
            raise RecursoNoEncontradoError(
                f"El proyecto '{proyecto.nombre}' no tiene presupuesto asignado.",
                campo="presupuesto_total")
        return proyecto.presupuesto

    # ── Casos de uso ───────────────────────────────────────

    def asignar(self, proyecto_id: int, datos: PresupuestoDatos,
                usuario_id: Optional[str]) -> PresupuestoResponse:
        """FUN-021: asigna el presupuesto por primera vez."""
        proyecto = self._buscar_proyecto(proyecto_id)                        # 404
        proyecto.verificar_editable()                                        # RN-019
        if proyecto.presupuesto is not None:
            raise ConflictoEstadoError(
                None, f"El proyecto '{proyecto.nombre}' ya tiene presupuesto asignado; "
                      f"use PUT para actualizarlo.", campo="presupuesto_total")
        presupuesto = Presupuesto.asignar(datos.presupuesto_total, _a_entero(usuario_id))
        presupuesto.proyecto = proyecto
        return PresupuestoResponse.desde_modelo(self.repo.guardar(presupuesto))

    def consultar(self, proyecto_id: int) -> PresupuestoResponse:
        """FUN-022: presupuesto total, comprometido, ejecutado y saldo disponible."""
        proyecto = self._buscar_proyecto(proyecto_id)
        return PresupuestoResponse.desde_modelo(self._presupuesto_de(proyecto))

    def actualizar(self, proyecto_id: int, datos: PresupuestoDatos,
                   usuario_id: Optional[str]) -> PresupuestoResponse:
        """FUN-023: adición o recorte del presupuesto."""
        proyecto = self._buscar_proyecto(proyecto_id)
        proyecto.verificar_editable()                                        # RN-019
        presupuesto = self._presupuesto_de(proyecto)                         # 404
        presupuesto.actualizar(datos.presupuesto_total, _a_entero(usuario_id))  # RN-023
        return PresupuestoResponse.desde_modelo(self.repo.guardar(presupuesto))
