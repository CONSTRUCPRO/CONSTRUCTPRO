# app/api/inventario_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
# Las rutas cuelgan de /inventario y de /ordenes-compra (recepción), por eso el router no lleva
# prefijo y la recepción no choca con orden_compra_router.py.
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.inventario_repository import InventarioRepository
from app.api.schemas.inventario import (
    EntradaCreate,
    EntradaResponse,
    ExistenciaResponse,
    MovimientoResponse,
    RecepcionResponse,
    SalidaCreate,
)
from app.api.schemas.respuesta import Respuesta
from app.services.inventario_service import InventarioService

router = APIRouter(tags=["Inventario"])

# Permisos del módulo "Inventario" (MODULO-10). Con los roles por defecto: el Empleado (almacenista
# o residente de obra) y el Administrador registran; Coordinador y Director solo consultan.
MODULO = "Inventario"


def obtener_servicio(db: Session = Depends(get_db)) -> InventarioService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return InventarioService(InventarioRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str]) -> dict:
    """
    Arma un ejemplo de respuesta de error con el sobre estándar, solo para la documentación de
    Swagger (parámetro `responses=` de cada endpoint). No se usa al responder de verdad.
    """
    return {
        "description": descripcion,
        "content": {"application/json": {"example": {
            "exito": False,
            "codigo": codigo,
            "mensaje": mensaje_general,
            "datos": None,
            "errores": [{"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}],
            "meta": {"timestamp": "2026-10-21T15:04:32Z", "version": "v1",
                     "peticion_id": "9f3c1a7e-52b1-4c0d-9a77-1b2e6d4f8a10", "paginacion": None},
        }}},
    }


ERROR_401 = _ejemplo_error("Sin token, token vencido o sesión cerrada (HU-02)",
                           "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
                           None, "Debe iniciar sesión y enviar el token en el encabezado "
                           "Authorization: Bearer <token>.", None)
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Inventario", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Coordinador no tiene permiso para 'crear' en el módulo Inventario.",
                           None)
ERROR_404 = _ejemplo_error("La orden, el proyecto o el material no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "orden_compra_id",
                           "No existe una orden de compra con el identificador 8891.", None)
ERROR_409_ENTRADA = _ejemplo_error(
    "La orden no tiene la recepción confirmada (RN-121). También 409: la entrada de la orden ya "
    "se registró", "NEG_RECEPCION_NO_CONFIRMADA",
    "El inventario solo puede actualizarse tras confirmar la recepción.", "orden_compra_id",
    "La orden 8891 no tiene la recepción confirmada; registre primero la recepción del material.",
    "RN-121")
ERROR_409_RECEPCION = _ejemplo_error(
    "La orden no está confirmada, ya se recibió, o está anulada o cerrada (RN-089)",
    "NEG_CONFLICTO_ESTADO", "El estado actual del recurso no permite esta operación.", "estado",
    "La orden 8891 está emitida; solo se registra la recepción de órdenes confirmadas por el "
    "proveedor.", None)
ERROR_422_SALIDA = _ejemplo_error(
    "Salida mayor que la existencia (RN-122). También 422: cantidad menor o igual a cero",
    "NEG_STOCK_INSUFICIENTE", "No hay existencias suficientes para registrar la salida.",
    "cantidad", "Se solicitaron 400 bultos y solo hay 260 disponibles.", "RN-122")


# ── Endpoints ────────────────────────────────────────────────

@router.patch("/api/v1/ordenes-compra/{orden_compra_id}/recepcion",
              response_model=Respuesta[RecepcionResponse],
              summary="Registrar la recepción de una orden",
              description="El almacenista confirma que el material de una orden **confirmada** llegó "
                          "a la obra. Guarda la fecha y quién recibe (RN-112). Se registra una sola "
                          "vez; una orden anulada o cerrada no se recibe (RN-089). Una orden recibida "
                          "ya no se puede anular (RN-084). Desde aquí ya puede entrar al inventario.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_RECEPCION})
def registrar_recepcion(orden_compra_id: int,
                        servicio: InventarioService = Depends(obtener_servicio),
                        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """PATCH /api/v1/ordenes-compra/{orden_compra_id}/recepcion: el material llegó a la obra."""
    return respuesta_exitosa(servicio.registrar_recepcion(orden_compra_id, usuario.usuario_id),
                             "Recepción de la orden registrada correctamente.")


@router.post("/api/v1/inventario/entradas", response_model=Respuesta[EntradaResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar entrada por recepción",
             description="Suma al inventario del proyecto los materiales de una orden con la "
                         "**recepción confirmada** (RN-121). Crea un movimiento de entrada por cada "
                         "material, con la orden como documento de origen. Cada orden entra una "
                         "sola vez.",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409_ENTRADA})
def registrar_entrada(datos: EntradaCreate,
                      servicio: InventarioService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/inventario/entradas: entrada por la recepción de una orden (201)."""
    return respuesta_exitosa(servicio.registrar_entrada(datos, usuario.usuario_id),
                             "Entrada registrada correctamente.")


@router.post("/api/v1/inventario/salidas", response_model=Respuesta[MovimientoResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar salida hacia la obra",
             description="Descuenta del inventario del proyecto el material que se usa en la obra. "
                         "No se puede sacar más de la existencia disponible (RN-122). Guarda el motivo "
                         "y el responsable (el usuario del token).",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 422: ERROR_422_SALIDA})
def registrar_salida(datos: SalidaCreate,
                     servicio: InventarioService = Depends(obtener_servicio),
                     usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/inventario/salidas: salida de material hacia la obra (201)."""
    return respuesta_exitosa(servicio.registrar_salida(datos, usuario.usuario_id),
                             "Salida registrada correctamente.")


@router.get("/api/v1/inventario", response_model=Respuesta[list[ExistenciaResponse]],
            summary="Consultar existencias del proyecto",
            description="Existencia actual de cada material en el proyecto, paginada. Si el proyecto "
                        "todavía no tiene inventario, devuelve una lista vacía.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def existencias(proyecto_id: int = Query(..., description="Id del proyecto"),
                pagina: int = Query(1, ge=1, description="Número de página"),
                por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
                servicio: InventarioService = Depends(obtener_servicio),
                usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/inventario?proyecto_id=: existencias del proyecto."""
    items, paginacion = servicio.existencias(proyecto_id, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/api/v1/inventario/movimientos", response_model=Respuesta[list[MovimientoResponse]],
            summary="Consultar movimientos (trazabilidad)",
            description="Entradas y salidas del proyecto, de la más reciente a la más antigua. "
                        "Filtros opcionales por material y tipo.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def movimientos(proyecto_id: int = Query(..., description="Id del proyecto"),
                material_id: Optional[int] = Query(None, description="Id del material"),
                tipo: Optional[str] = Query(None, description="entrada | salida"),
                pagina: int = Query(1, ge=1, description="Número de página"),
                por_pagina: int = Query(20, ge=1, le=100, description="Registros por página"),
                servicio: InventarioService = Depends(obtener_servicio),
                usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/inventario/movimientos?proyecto_id=: historial de entradas y salidas."""
    items, paginacion = servicio.movimientos(proyecto_id, material_id, tipo, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)
