# service/material_service.py
# CAPA SERVICIO: orquesta dominio + repositorio.
# No importa nada de FastAPI aquí.

from typing import Optional

from domain.excepciones import (
    RecursoDuplicadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from domain.material import (
    EstadoUpdate,
    Material,
    MaterialCreate,
    MaterialResponse,
    PrecioUpdate,
)
from repository.material_repository import MaterialRepository


class MaterialService:

    def __init__(self, repo: MaterialRepository):
        # Inyección de dependencia: recibe el repositorio desde afuera
        self.repo = repo

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, id: int) -> Material:
        material = self.repo.obtener_por_id(id)
        if not material:
            raise RecursoNoEncontradoError(f"Material con id {id} no encontrado")
        return material

    def _validar_categoria(self, categoria_id: int):
        # RN-032: la categoría debe existir
        if not self.repo.categoria_existe(categoria_id):
            raise ReglaNegocioError("RN-032", f"La categoría {categoria_id} no existe")

    def _validar_duplicado(self, datos: MaterialCreate,
                           excluir_id: Optional[int] = None):
        # RN-031: mismo nombre + unidad dentro de una categoría
        if self.repo.existe_duplicado(datos.nombre, datos.unidad,
                                      datos.categoria_id, excluir_id):
            raise RecursoDuplicadoError(
                "RN-031",
                "Ya existe un material con el mismo nombre y unidad en esa categoría",
            )

    # ── Casos de uso ───────────────────────────────────────

    def listar(self, categoria_id: Optional[int] = None,
               nombre: Optional[str] = None,
               pagina: int = 1, por_pagina: int = 10) -> list[MaterialResponse]:
        materiales = self.repo.listar(categoria_id, nombre)
        inicio = (pagina - 1) * por_pagina
        pagina_actual = materiales[inicio:inicio + por_pagina]
        return [MaterialResponse(**m.to_response()) for m in pagina_actual]

    def obtener(self, id: int) -> MaterialResponse:
        return MaterialResponse(**self._buscar(id).to_response())

    def crear(self, datos: MaterialCreate) -> MaterialResponse:
        self._validar_categoria(datos.categoria_id)   # RN-032
        self._validar_duplicado(datos)                # RN-031
        # El dominio valida la unidad (RN-032) y el precio (RN-033)
        material = self.repo.crear(
            nombre=datos.nombre,
            unidad=datos.unidad,
            categoria_id=datos.categoria_id,
            precio_referencia=datos.precio_referencia,
        )
        return MaterialResponse(**material.to_response())

    def actualizar(self, id: int, datos: MaterialCreate) -> MaterialResponse:
        self._buscar(id)                              # 404 si no existe
        self._validar_categoria(datos.categoria_id)   # RN-032
        self._validar_duplicado(datos, excluir_id=id) # RN-031
        material = self.repo.actualizar(
            id=id,
            nombre=datos.nombre,
            unidad=datos.unidad,
            categoria_id=datos.categoria_id,
            precio_referencia=datos.precio_referencia,
        )
        return MaterialResponse(**material.to_response())

    def actualizar_precio(self, id: int, datos: PrecioUpdate) -> MaterialResponse:
        material = self._buscar(id)
        material.actualizar_precio(datos.precio_referencia)  # RN-033
        return MaterialResponse(**material.to_response())

    def cambiar_estado(self, id: int, datos: EstadoUpdate) -> MaterialResponse:
        material = self._buscar(id)
        # RN-035: un material no se elimina, solo se inactiva
        if datos.estado != "inactivo":
            raise ReglaNegocioError(
                "RN-035",
                "Un material no se elimina; solo se puede cambiar su estado a 'inactivo'",
            )
        material.inactivar()
        return MaterialResponse(**material.to_response())