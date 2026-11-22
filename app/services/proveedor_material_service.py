# app/services/proveedor_material_service.py
# CAPA SERVICIO: orquesta los casos de uso de la relación material–proveedor.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoNoEncontradoError
from app.domain.material import Material
from app.domain.proveedor import Proveedor
from app.domain.proveedor_material import ProveedorMaterial
from app.repositories.proveedor_material_repository import ProveedorMaterialRepository
from app.schemas.proveedor_material import (
    OfertaCreate,
    OfertaResponse,
    ProveedorDeMaterialResponse,
)


class ProveedorMaterialService:

    def __init__(self, repo: ProveedorMaterialRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar_proveedor(self, proveedor_id: int) -> Proveedor:
        proveedor = self.repo.obtener_proveedor(proveedor_id)
        if not proveedor:
            raise RecursoNoEncontradoError(
                f"No existe un proveedor con el identificador {proveedor_id}.",
                campo="proveedor_id",
            )
        return proveedor

    def _buscar_material(self, material_id: int) -> Material:
        material = self.repo.obtener_material(material_id)
        if not material:
            raise RecursoNoEncontradoError(
                f"No existe un material con el identificador {material_id}.",
                campo="material_id",
            )
        return material

    # ── Casos de uso ───────────────────────────────────────

    def asociar(self, proveedor_id: int, datos: OfertaCreate) -> tuple[OfertaResponse, bool]:
        """
        Asocia un material a un proveedor con su oferta.
        Si el material ya estaba asociado a ese proveedor, actualiza la oferta.
        Devuelve (oferta, creada): creada=True si es nueva, False si se actualizó.
        """
        proveedor = self._buscar_proveedor(proveedor_id)               # 404
        material = self._buscar_material(datos.material_id)            # 404
        oferta = self.repo.obtener_oferta(proveedor.id, material.id)
        if oferta is None:
            oferta = ProveedorMaterial.registrar(                      # activos + RN-038
                proveedor, material, datos.precio, datos.disponible, datos.dias_entrega)
            creada = True
        else:
            oferta.actualizar(datos.precio, datos.disponible, datos.dias_entrega)
            creada = False
        return OfertaResponse.desde_modelo(self.repo.guardar(oferta)), creada

    def proveedores_de_material(self, material_id: int, pagina: int,
                                por_pagina: int) -> tuple[list[ProveedorDeMaterialResponse], dict]:
        """Proveedores ACTIVOS que ofrecen el material (404 si el material no existe)."""
        self._buscar_material(material_id)                             # 404
        items, total = self.repo.listar_por_material(material_id, pagina, por_pagina)
        return ([ProveedorDeMaterialResponse.desde_modelo(o) for o in items],
                construir_paginacion(pagina, por_pagina, total))
