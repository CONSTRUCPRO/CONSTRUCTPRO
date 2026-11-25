# app/services/comparativo_service.py
# CAPA SERVICIO: orquesta los casos de uso del comparativo de precios.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.domain.comparativo import Comparativo
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.repositories.comparativo_repository import ComparativoRepository
from app.api.schemas.comparativo import ComparativoCreate, ComparativoResponse, SeleccionDatos


class ComparativoService:
    """
    Casos de uso de el comparativo de precios (HU-16). Orquesta: busca con el repositorio, aplica las reglas del
    dominio y devuelve el schema de salida. Solo lanza excepciones de dominio; la capa API
    las convierte en el sobre de error.
    """

    def __init__(self, repo: ComparativoRepository):
        """
        Recibe el repositorio por parámetro (inyección de dependencias): en las pruebas se le pasa uno con una BD en memoria.
        """
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, comparativo_id: int) -> Comparativo:
        """
        Trae el comparativo por su id o lanza RecursoNoEncontradoError (404 REC_NO_ENCONTRADO).
        """
        comparativo = self.repo.obtener_por_id(comparativo_id)
        if not comparativo:
            raise RecursoNoEncontradoError(
                f"No existe un comparativo con el identificador {comparativo_id}.",
                campo="comparativo_id")
        return comparativo

    # ── Casos de uso ───────────────────────────────────────

    def generar(self, datos: ComparativoCreate) -> ComparativoResponse:
        """
        Arma el comparativo de un material de la solicitud con las ofertas de proveedores activos.
        Valida RN-057 (el material está en la solicitud), RN-056 (al menos dos proveedores) y que no
        exista ya un comparativo para ese material de esa solicitud (409).
        """
        solicitud = self.repo.obtener_solicitud(datos.solicitud_id)
        if not solicitud:
            raise RecursoNoEncontradoError(
                f"No existe una solicitud con el identificador {datos.solicitud_id}.",
                campo="solicitud_id")
        material = self.repo.obtener_material(datos.material_id)
        if not material:
            raise RecursoNoEncontradoError(
                f"No existe un material con el identificador {datos.material_id}.",
                campo="material_id")
        if self.repo.existe(solicitud.id, material.id):
            raise RecursoDuplicadoError(
                None, f"Ya existe un comparativo del material {material.id} para la "
                      f"solicitud {solicitud.id}.", campo="material_id")
        ofertas = self.repo.ofertas_de_material(material.id)
        comparativo = Comparativo.generar(solicitud, material, ofertas)   # RN-034, 056, 057
        return ComparativoResponse.desde_modelo(self.repo.guardar(comparativo))

    def obtener(self, comparativo_id: int, orden: str = "precio",
                disponible: Optional[bool] = None,
                dias_max: Optional[int] = None) -> ComparativoResponse:
        """
        El comparativo con las ofertas ordenadas y filtradas como se pida (no cambia lo guardado).
        """
        comparativo = self._buscar(comparativo_id)
        return ComparativoResponse.desde_modelo(
            comparativo, comparativo.ofertas_filtradas(orden, disponible, dias_max))

    def seleccionar(self, comparativo_id: int, datos: SeleccionDatos) -> ComparativoResponse:
        """
        Elige la oferta: RN-058 (debe estar en el comparativo), RN-059 (justificación) y RN-060 (ahorro).
        """
        comparativo = self._buscar(comparativo_id)
        comparativo.seleccionar(datos.proveedor_id, datos.justificacion)  # RN-058, 059, 060
        return ComparativoResponse.desde_modelo(self.repo.guardar(comparativo))
