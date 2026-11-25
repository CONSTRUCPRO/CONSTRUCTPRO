# app/api/schemas/solicitud.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# RN-042 (cantidad > 0 y al menos una línea) y RN-043 (material repetido) NO van aquí:
# van en el dominio, para que el error llegue con su número de regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.solicitud import Solicitud, SolicitudDetalle


# ── ENTRADA ───────────────────────────────────────────────

class LineaSolicitud(BaseModel):
    """Una línea del pedido: qué material y cuántas unidades (entero mayor que cero, RN-042)."""

    material_id: int = Field(..., description="Identificador del material del catálogo")
    cantidad: int = Field(..., description="Cantidad solicitada (mayor que cero, RN-042)")


class SolicitudCreate(BaseModel):
    """Datos para crear una solicitud (POST)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "proyecto_id": 1,
        "detalle": [
            {"material_id": 1, "cantidad": 300},
            {"material_id": 2, "cantidad": 150},
        ],
    }})

    proyecto_id: int = Field(..., description="Proyecto que pide los materiales")
    detalle: list[LineaSolicitud] = Field(..., description="Materiales y cantidades (RN-042, RN-043)")


class SolicitudUpdate(BaseModel):
    """PUT: se envía el detalle completo; reemplaza al anterior. El proyecto no cambia."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "detalle": [
            {"material_id": 1, "cantidad": 320},
            {"material_id": 2, "cantidad": 150},
        ],
    }})

    detalle: list[LineaSolicitud] = Field(..., description="Materiales y cantidades (RN-042, RN-043)")


# ── SALIDA ────────────────────────────────────────────────

class LineaSolicitudResponse(BaseModel):
    """Una línea en la respuesta, con el nombre y la unidad del material."""

    material_id: str
    nombre: str
    cantidad: int
    unidad: str

    @classmethod
    def desde_modelo(cls, d: SolicitudDetalle) -> "LineaSolicitudResponse":
        """
        Convierte el modelo de BD de una línea de la solicitud en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(material_id=str(d.material_id), nombre=d.material.nombre,
                   cantidad=d.cantidad, unidad=d.material.unidad)


class SolicitudResponse(BaseModel):
    """Una solicitud con su detalle."""

    solicitud_id: str
    proyecto_id: str
    solicitante_id: str
    estado: str
    fecha_solicitud: Optional[str]         # ISO 8601 UTC
    fecha_actualizacion: Optional[str]     # null si nunca se ha editado
    detalle: list[LineaSolicitudResponse]

    @classmethod
    def desde_modelo(cls, s: Solicitud) -> "SolicitudResponse":
        """
        Convierte el modelo de BD de una solicitud en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            solicitud_id=str(s.id),
            proyecto_id=str(s.proyecto_id),
            solicitante_id=str(s.solicitante_id),
            estado=s.estado,
            fecha_solicitud=fecha_iso(s.fecha_solicitud),
            fecha_actualizacion=fecha_iso(s.fecha_actualizacion),
            detalle=[LineaSolicitudResponse.desde_modelo(d) for d in s.detalle],
        )
