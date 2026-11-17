# app/services/material_service.py
# CAPA SERVICIO: orquesta los casos de uso del catálogo de materiales.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.material import Categoria, Material
from app.repositories.material_repository import MaterialRepository
from app.schemas.material import (
    EstadoUpdate,
    MaterialCreate,
    MaterialResponse,
    MaterialUpdate,
    PrecioUpdate,
)


class MaterialService:

    def __init__(self, repo: MaterialRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, material_id: int) -> Material:
        material = self.repo.obtener_por_id(material_id)
        if not material:
            raise RecursoNoEncontradoError(
                f"No existe un material con el identificador {material_id}.",
                campo="material_id",
            )
        return material

    def _categoria_valida(self, categoria_id: int) -> Categoria:
        categoria = self.repo.obtener_categoria(categoria_id)
        Material.validar_categoria(categoria, categoria_id)          # RN-032
        return categoria

    def _validar_duplicado(self, nombre: str, unidad: str, categoria: Categoria,
                           excluir_id: Optional[int] = None) -> None:
        if self.repo.existe_duplicado(nombre, unidad, categoria.id, excluir_id):  # RN-031
            raise RecursoDuplicadoError(
                "RN-031",
                f"Ya existe el material '{nombre}' con unidad '{unidad}' "
                f"en la categoría {categoria.nombre}.",
                campo="nombre",
            )

    # ── Casos de uso ───────────────────────────────────────

    def crear(self, datos: MaterialCreate) -> MaterialResponse:
        categoria = self._categoria_valida(datos.categoria_id)        # RN-032
        self._validar_duplicado(datos.nombre, datos.unidad, categoria)  # RN-031
        material = Material.registrar(                                # RN-032 unidad, RN-033 precio
            datos.nombre, datos.unidad, categoria, datos.precio_referencia
        )
        return MaterialResponse.desde_modelo(self.repo.guardar(material))

    def obtener(self, material_id: int) -> MaterialResponse:
        return MaterialResponse.desde_modelo(self._buscar(material_id))

    def listar(self, categoria_id: Optional[int], nombre: Optional[str],
               estado: Optional[str], pagina: int,
               por_pagina: int) -> tuple[list[MaterialResponse], dict]:
        items, total = self.repo.listar(categoria_id, nombre, estado, pagina, por_pagina)
        return ([MaterialResponse.desde_modelo(m) for m in items],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, material_id: int, datos: MaterialUpdate) -> MaterialResponse:
        material = self._buscar(material_id)                          # 404
        categoria = self._categoria_valida(datos.categoria_id)        # RN-032
        self._validar_duplicado(datos.nombre, datos.unidad, categoria,
                                excluir_id=material_id)               # RN-031
        material.editar(datos.nombre, datos.unidad, categoria,
                        datos.precio_referencia)                      # RN-032, RN-033
        return MaterialResponse.desde_modelo(self.repo.guardar(material))

    def actualizar_precio(self, material_id: int, datos: PrecioUpdate) -> MaterialResponse:
        material = self._buscar(material_id)
        material.actualizar_precio(datos.precio_referencia)           # RN-033
        return MaterialResponse.desde_modelo(self.repo.guardar(material))

    def cambiar_estado(self, material_id: int, datos: EstadoUpdate) -> MaterialResponse:
        material = self._buscar(material_id)
        material.cambiar_estado(datos.estado)                         # RN-035
        return MaterialResponse.desde_modelo(self.repo.guardar(material))
