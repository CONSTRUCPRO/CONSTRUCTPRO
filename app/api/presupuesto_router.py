# app/api/presupuesto_router.py
# CAPA API - HU-06 Presupuesto del Proyecto.
# Recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_error, respuesta_exitosa
from app.core.seguridad import UsuarioActual, requiere_permiso, requiere_rol
from app.repositories.presupuesto_repository import PresupuestoRepository
from app.api.schemas.presupuesto import PresupuestoDatos, PresupuestoResponse
from app.api.schemas.respuesta import Respuesta
from app.services.presupuesto_service import PresupuestoService

router = APIRouter(prefix="/api/v1/proyectos", tags=["Presupuesto del proyecto"])

# RN-022: solo el rol director puede asignar o modificar el presupuesto.
solo_director = requiere_rol("Director", regla="RN-022")


def obtener_servicio(db: Session = Depends(get_db)) -> PresupuestoService:
    """
    Arma el servicio con su repositorio y la sesión de BD de esta petición (inyección de
    dependencias). Los endpoints lo reciben con Depends(obtener_servicio).
    """
    return PresupuestoService(PresupuestoRepository(db))


# ── Ejemplos de error para Swagger (documentación) ───────────

def _ejemplo_error(descripcion: str, codigo: str, mensaje_general: str,
                   campo: Optional[str], mensaje: str, regla: Optional[str] = None) -> dict:
    """
    Arma un ejemplo de respuesta de error para la documentación de Swagger (parámetro
    `responses=` de cada endpoint). Usa respuesta_error(), la misma función que arma los
    errores reales, así el ejemplo siempre coincide con lo que responde la API.
    """
    return {
        "description": descripcion,
        "content": {"application/json": {"example": respuesta_error(
            codigo, mensaje_general,
            [{"campo": campo, "codigo": codigo, "mensaje": mensaje, "regla": regla}])}},
    }


ERROR_401 = _ejemplo_error(
    "Sin token, token vencido o sesión cerrada (HU-02)",
    "AUT_CREDENCIALES_INVALIDAS", "El correo o la contraseña no son correctos.",
    None, "Debe iniciar sesión y enviar el token en el encabezado Authorization: Bearer <token>.")
ERROR_403 = _ejemplo_error(
    "Solo el director asigna o modifica el presupuesto (RN-022)", "AUT_SIN_PERMISO",
    "Su rol no le permite realizar esta operación.",
    "rol", "El rol Coordinador no puede realizar esta operación.", "RN-022")
ERROR_404 = _ejemplo_error(
    "El proyecto no existe o no tiene presupuesto", "REC_NO_ENCONTRADO",
    "El recurso solicitado no existe.", "proyecto_id",
    "No existe un proyecto con el identificador 999.")
ERROR_409 = _ejemplo_error(
    "El proyecto ya tiene presupuesto o está finalizado (RN-019)", "NEG_CONFLICTO_ESTADO",
    "El estado actual del recurso no permite esta operación.", "presupuesto_total",
    "El proyecto 'Torre Cabecera Etapa 2' ya tiene presupuesto asignado; use PUT para actualizarlo.")
ERROR_422_MONTO = _ejemplo_error(
    "Monto menor o igual a cero", "VAL_FORMATO_INVALIDO",
    "La información enviada contiene errores.", "presupuesto_total",
    "El presupuesto debe ser mayor que cero.")
ERROR_422_RN023 = _ejemplo_error(
    "El nuevo monto queda por debajo de lo comprometido y ejecutado (RN-023)",
    "NEG_PRESUPUESTO_INSUFICIENTE",
    "El presupuesto no puede ser menor que lo ya comprometido y ejecutado.",
    "presupuesto_total", "El proyecto tiene 44.815.500,00 COP comprometidos y ejecutados.", "RN-023")


# ── Endpoints ────────────────────────────────────────────────

@router.post("/{proyecto_id}/presupuesto", response_model=Respuesta[PresupuestoResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Asignar presupuesto",
             description="Asigna el presupuesto del proyecto en COP (FUN-021) y registra la fecha de "
                         "aprobación. **Solo el Director** (RN-022). El monto debe ser mayor que cero. "
                         "Si el proyecto ya tiene presupuesto, se actualiza con PUT.",
             responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409,
                        422: ERROR_422_MONTO})
def asignar_presupuesto(proyecto_id: int, datos: PresupuestoDatos,
                        servicio: PresupuestoService = Depends(obtener_servicio),
                        usuario: UsuarioActual = Depends(solo_director)):
    """
    POST /api/v1/proyectos/{proyecto_id}/presupuesto: asigna el presupuesto (solo Director, 201).
    """
    return respuesta_exitosa(servicio.asignar(proyecto_id, datos, usuario.usuario_id),
                             "Presupuesto asignado correctamente.")


@router.get("/{proyecto_id}/presupuesto", response_model=Respuesta[PresupuestoResponse],
            summary="Consultar presupuesto disponible",
            description="Devuelve el presupuesto total, lo comprometido, lo ejecutado y el saldo "
                        "disponible (FUN-022): `saldo_disponible = presupuesto_total - comprometido "
                        "- ejecutado`. Requiere permiso *consultar* en Proyectos.",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404})
def consultar_presupuesto(proyecto_id: int,
                          servicio: PresupuestoService = Depends(obtener_servicio),
                          usuario: UsuarioActual = Depends(requiere_permiso("Proyectos", "consultar"))):
    """GET /api/v1/proyectos/{proyecto_id}/presupuesto: total, comprometido, ejecutado y saldo."""
    return respuesta_exitosa(servicio.consultar(proyecto_id), "Consulta realizada correctamente.")


@router.put("/{proyecto_id}/presupuesto", response_model=Respuesta[PresupuestoResponse],
            summary="Actualizar presupuesto",
            description="Cambia el monto del presupuesto ante una adición o un recorte (FUN-023). "
                        "**Solo el Director** (RN-022). No puede quedar por debajo de lo comprometido "
                        "y ejecutado (RN-023).",
            responses={401: ERROR_401, 403: ERROR_403, 404: ERROR_404, 409: ERROR_409,
                       422: ERROR_422_RN023})
def actualizar_presupuesto(proyecto_id: int, datos: PresupuestoDatos,
                           servicio: PresupuestoService = Depends(obtener_servicio),
                           usuario: UsuarioActual = Depends(solo_director)):
    """PUT /api/v1/proyectos/{proyecto_id}/presupuesto: cambia el monto (solo Director, RN-023)."""
    return respuesta_exitosa(servicio.actualizar(proyecto_id, datos, usuario.usuario_id),
                             "Presupuesto actualizado correctamente.")
