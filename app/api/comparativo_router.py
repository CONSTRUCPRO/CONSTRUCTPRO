# app/api/comparativo_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso
from app.repositories.comparativo_repository import ComparativoRepository
from app.api.schemas.comparativo import ComparativoCreate, ComparativoResponse, SeleccionDatos
from app.api.schemas.respuesta import Respuesta
from app.services.comparativo_service import ComparativoService

router = APIRouter(prefix="/api/v1/comparativos", tags=["Comparativo de precios"])

# El comparativo pertenece al módulo "Cotizaciones" (MODULO-05). Con los roles por defecto:
# Administrador y Coordinador generan y seleccionan; el Director solo consulta.
MODULO = "Cotizaciones"


def obtener_servicio(db: Session = Depends(get_db)) -> ComparativoService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return ComparativoService(ComparativoRepository(db))


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
ERROR_403 = _ejemplo_error("El rol no tiene el permiso en el módulo Cotizaciones", "AUT_SIN_PERMISO",
                           "Su rol no le permite realizar esta operación.", "rol",
                           "El rol Empleado no tiene permiso para 'crear' en el módulo Cotizaciones.",
                           None)
ERROR_404 = _ejemplo_error("La solicitud, el material o el comparativo no existe", "REC_NO_ENCONTRADO",
                           "El recurso solicitado no existe.", "comparativo_id",
                           "No existe un comparativo con el identificador 77.", None)
ERROR_409_GENERAR = _ejemplo_error(
    "Ya existe el comparativo de ese material, la solicitud no está pendiente o el material "
    "está inactivo (RN-034)", "REC_DUPLICADO", "Ya existe un registro con ese identificador.",
    "material_id", "Ya existe un comparativo del material 115 para la solicitud 305.", None)
ERROR_409_SELECCION = _ejemplo_error(
    "El comparativo ya tiene una oferta seleccionada o la solicitud ya no está pendiente",
    "NEG_CONFLICTO_ESTADO", "El estado actual del recurso no permite esta operación.",
    "proveedor_id", "El comparativo 77 ya tiene una oferta seleccionada.", None)
ERROR_422_INSUFICIENTE = _ejemplo_error(
    "Menos de dos proveedores con oferta (RN-056). También 422: material que no está en la "
    "solicitud (RN-057)", "NEG_COMPARATIVO_INSUFICIENTE",
    "Se requieren al menos dos proveedores para comparar.", "material_id",
    "El material 204 solo tiene un proveedor con oferta registrada.", "RN-056")
ERROR_422_SELECCION = _ejemplo_error(
    "Falta la justificación porque la oferta no es la más barata (RN-059). También 422: el "
    "proveedor no está en el comparativo (RN-058)", "NEG_REGLA_INCUMPLIDA",
    "La operación no cumple una regla de negocio.", "justificacion",
    "La oferta elegida no es la de menor precio; escriba la justificación.", "RN-059")


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=Respuesta[ComparativoResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Generar comparativo de precios",
             description="Genera el comparativo de un material de una solicitud **pendiente** con "
                         "las ofertas de los proveedores **activos** (tabla proveedor_material, HU-11), "
                         "ordenadas de menor a mayor precio. Guarda una copia de las ofertas: si un "
                         "proveedor cambia su precio después, el comparativo no cambia. "
                         "Valida RN-056 (mínimo dos proveedores), RN-057 (el material es de la "
                         "solicitud) y RN-034 (material activo).",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                        409: ERROR_409_GENERAR, 422: ERROR_422_INSUFICIENTE})
def generar_comparativo(datos: ComparativoCreate,
                        servicio: ComparativoService = Depends(obtener_servicio),
                        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "crear"))):
    """POST /api/v1/comparativos: genera el comparativo (201)."""
    return respuesta_exitosa(servicio.generar(datos), "Comparativo generado correctamente.")


@router.get("/{comparativo_id}", response_model=Respuesta[ComparativoResponse],
            summary="Consultar, ordenar y filtrar el comparativo",
            description="Devuelve el comparativo con sus ofertas. `orden` = `precio` (por defecto) o "
                        "`dias_entrega`; `disponible` y `dias_max` filtran la lista de ofertas. "
                        "Los filtros solo cambian lo que se muestra: `precio_minimo`, "
                        "`precio_maximo` y el ahorro son los del comparativo completo.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def obtener_comparativo(
        comparativo_id: int,
        orden: str = Query("precio", pattern="^(precio|dias_entrega)$",
                           description="precio | dias_entrega"),
        disponible: Optional[bool] = Query(None, description="true: solo ofertas disponibles"),
        dias_max: Optional[int] = Query(None, ge=0, description="Máximo de días de entrega"),
        servicio: ComparativoService = Depends(obtener_servicio),
        usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "consultar"))):
    """GET /api/v1/comparativos/{comparativo_id}: consulta, ordena y filtra las ofertas."""
    return respuesta_exitosa(servicio.obtener(comparativo_id, orden, disponible, dias_max),
                             "Consulta realizada correctamente.")


@router.patch("/{comparativo_id}/seleccion", response_model=Respuesta[ComparativoResponse],
              summary="Seleccionar la mejor alternativa",
              description="Elige la oferta de un proveedor del comparativo (RN-058). Si no es la de "
                          "menor precio, la `justificacion` es obligatoria (RN-059). Guarda el precio "
                          "elegido y el ahorro = precio_maximo − precio_seleccionado por unidad "
                          "(RN-060), y `ahorro_total` = ahorro × cantidad. Solo se selecciona una vez.",
              responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404,
                         409: ERROR_409_SELECCION, 422: ERROR_422_SELECCION})
def seleccionar_oferta(comparativo_id: int, datos: SeleccionDatos,
                       servicio: ComparativoService = Depends(obtener_servicio),
                       usuario: UsuarioActual = Depends(requiere_permiso(MODULO, "editar"))):
    """
    PATCH /api/v1/comparativos/{comparativo_id}/seleccion: elige la oferta y calcula el ahorro.
    """
    return respuesta_exitosa(servicio.seleccionar(comparativo_id, datos),
                             "Oferta seleccionada correctamente.")
