# app/services/inventario_service.py
# CAPA SERVICIO: orquesta la recepción de órdenes y las entradas y salidas del inventario.
# No importa FastAPI ni lanza HTTPException: lanza excepciones de dominio
# y la capa API (app/core/errores.py) las traduce al sobre estándar.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import ConflictoEstadoError, RecursoNoEncontradoError
from app.domain.inventario import TIPO_ENTRADA, TIPO_SALIDA, Inventario, MovimientoInventario
from app.domain.orden_compra import OrdenCompra
from app.domain.proyecto import Proyecto
from app.repositories.inventario_repository import InventarioRepository
from app.schemas.inventario import (
    EntradaCreate,
    EntradaResponse,
    ExistenciaResponse,
    MovimientoResponse,
    RecepcionResponse,
    SalidaCreate,
)


def _a_entero(usuario_id: Optional[str]) -> Optional[int]:
    return int(usuario_id) if usuario_id and str(usuario_id).isdigit() else None


class InventarioService:

    def __init__(self, repo: InventarioRepository):
        self.repo = repo  # inyección de dependencia

    # ── Apoyos internos ────────────────────────────────────

    def _buscar_orden(self, orden_compra_id: int) -> OrdenCompra:
        orden = self.repo.obtener_orden(orden_compra_id)
        if not orden:
            raise RecursoNoEncontradoError(
                f"No existe una orden de compra con el identificador {orden_compra_id}.",
                campo="orden_compra_id")
        return orden

    def _buscar_proyecto(self, proyecto_id: int) -> Proyecto:
        proyecto = self.repo.obtener_proyecto(proyecto_id)
        if not proyecto:
            raise RecursoNoEncontradoError(
                f"No existe un proyecto con el identificador {proyecto_id}.", campo="proyecto_id")
        return proyecto

    def _inventario(self, proyecto_id: int, material_id: int) -> Inventario:
        """El inventario del material en el proyecto; si no existe, uno nuevo en 0."""
        inventario = self.repo.existencia(proyecto_id, material_id)
        if inventario is None:
            material = self.repo.obtener_material(material_id)
            if not material:
                raise RecursoNoEncontradoError(
                    f"No existe un material con el identificador {material_id}.",
                    campo="material_id")
            inventario = Inventario(proyecto_id=proyecto_id, material=material, existencia=0)
        return inventario

    # ── Casos de uso ───────────────────────────────────────

    def registrar_recepcion(self, orden_compra_id: int,
                            usuario_id: Optional[str]) -> RecepcionResponse:
        orden = self._buscar_orden(orden_compra_id)                        # 404
        orden.registrar_recepcion(_a_entero(usuario_id))                   # RN-089, RN-112
        self.repo.guardar(orden)
        return RecepcionResponse.desde_modelo(orden)

    def registrar_entrada(self, datos: EntradaCreate,
                          usuario_id: Optional[str]) -> EntradaResponse:
        orden = self._buscar_orden(datos.orden_compra_id)                  # 404
        orden.verificar_recibida()                                         # RN-121
        if self.repo.entrada_registrada(orden.id):
            raise ConflictoEstadoError(
                None, f"La entrada de la orden {orden.id} ya fue registrada en el inventario.",
                campo="orden_compra_id")
        objetos, movimientos = [], []
        for linea in orden.detalle:
            inventario = self._inventario(orden.proyecto_id, linea.material_id)
            movimiento = MovimientoInventario.registrar(
                TIPO_ENTRADA, inventario, linea.cantidad,
                f"Recepción de la orden de compra {orden.id}", _a_entero(usuario_id), orden.id)
            objetos += [inventario, movimiento]
            movimientos.append(movimiento)
        self.repo.guardar(*objetos)
        return EntradaResponse(orden_compra_id=str(orden.id), proyecto_id=str(orden.proyecto_id),
                               movimientos=[MovimientoResponse.desde_modelo(m) for m in movimientos])

    def registrar_salida(self, datos: SalidaCreate, usuario_id: Optional[str]) -> MovimientoResponse:
        self._buscar_proyecto(datos.proyecto_id)                           # 404
        inventario = self._inventario(datos.proyecto_id, datos.material_id)
        movimiento = MovimientoInventario.registrar(                       # RN-122, cantidad > 0
            TIPO_SALIDA, inventario, datos.cantidad, datos.motivo, _a_entero(usuario_id))
        self.repo.guardar(inventario, movimiento)
        return MovimientoResponse.desde_modelo(movimiento)

    def existencias(self, proyecto_id: int, pagina: int,
                    por_pagina: int) -> tuple[list[ExistenciaResponse], dict]:
        self._buscar_proyecto(proyecto_id)                                 # 404
        items, total = self.repo.listar_existencias(proyecto_id, pagina, por_pagina)
        return ([ExistenciaResponse.desde_modelo(i) for i in items],
                construir_paginacion(pagina, por_pagina, total))

    def movimientos(self, proyecto_id: int, material_id: Optional[int], tipo: Optional[str],
                    pagina: int, por_pagina: int) -> tuple[list[MovimientoResponse], dict]:
        self._buscar_proyecto(proyecto_id)                                 # 404
        items, total = self.repo.listar_movimientos(proyecto_id, material_id, tipo, pagina, por_pagina)
        return ([MovimientoResponse.desde_modelo(m) for m in items],
                construir_paginacion(pagina, por_pagina, total))
