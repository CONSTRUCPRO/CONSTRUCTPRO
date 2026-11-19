# app/services/proveedor_service.py
# CAPA SERVICIO: orquesta los casos de uso de proveedores.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.proveedor import Proveedor
from app.repositories.proveedor_repository import ProveedorRepository
from app.schemas.proveedor import (
    EstadoProveedorUpdate,
    ProveedorCreate,
    ProveedorResponse,
    ProveedorUpdate,
)


class ProveedorService:

    def __init__(self, repo: ProveedorRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar(self, proveedor_id: int) -> Proveedor:
        proveedor = self.repo.obtener_por_id(proveedor_id)
        if not proveedor:
            raise RecursoNoEncontradoError(
                f"No existe un proveedor con el identificador {proveedor_id}.",
                campo="proveedor_id",
            )
        return proveedor

    def _validar_nit_unico(self, nit: str, excluir_id: Optional[int] = None) -> None:
        if self.repo.existe_nit(nit, excluir_id):                     # RN-036
            raise RecursoDuplicadoError(
                "RN-036",
                f"Ya existe un proveedor con el NIT {nit}.",
                campo="nit",
            )

    # ── Casos de uso ───────────────────────────────────────

    def crear(self, datos: ProveedorCreate) -> ProveedorResponse:
        self._validar_nit_unico(datos.nit)                            # RN-036
        proveedor = Proveedor.registrar(datos.razon_social, datos.nit, datos.contacto,
                                        datos.telefono, datos.correo)
        return ProveedorResponse.desde_modelo(self.repo.guardar(proveedor))

    def obtener(self, proveedor_id: int) -> ProveedorResponse:
        return ProveedorResponse.desde_modelo(self._buscar(proveedor_id))

    def listar(self, estado: Optional[str], razon_social: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[ProveedorResponse], dict]:
        items, total = self.repo.listar(estado, razon_social, pagina, por_pagina)
        return ([ProveedorResponse.desde_modelo(p) for p in items],
                construir_paginacion(pagina, por_pagina, total))

    def editar(self, proveedor_id: int, datos: ProveedorUpdate) -> ProveedorResponse:
        proveedor = self._buscar(proveedor_id)                        # 404
        self._validar_nit_unico(datos.nit, excluir_id=proveedor_id)   # RN-036
        proveedor.editar(datos.razon_social, datos.nit, datos.contacto,
                         datos.telefono, datos.correo)
        return ProveedorResponse.desde_modelo(self.repo.guardar(proveedor))

    def cambiar_estado(self, proveedor_id: int, datos: EstadoProveedorUpdate) -> None:
        proveedor = self._buscar(proveedor_id)
        ordenes_abiertas = self.repo.contar_ordenes_abiertas(proveedor_id)
        proveedor.cambiar_estado(datos.estado, ordenes_abiertas)      # RN-040
        self.repo.guardar(proveedor)
