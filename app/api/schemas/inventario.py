# app/api/schemas/inventario.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "data" en el sobre estándar).
# RN-121, RN-122 y cantidad > 0 NO van aquí: van en el dominio, para que el error llegue con su regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.inventario import Inventario, MovimientoInventario
from app.domain.orden_compra import OrdenCompra


# ── ENTRADA ───────────────────────────────────────────────

class EntradaCreate(BaseModel):
    """Entrada al inventario por la recepción de una orden de compra (POST .../entradas)."""
    model_config = ConfigDict(json_schema_extra={"example": {"orden_compra_id": 1}})

    orden_compra_id: int = Field(..., description="Orden con la recepción confirmada (RN-121)")


class SalidaCreate(BaseModel):
    """Salida de material hacia la obra (POST .../salidas)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "proyecto_id": 1, "material_id": 1, "cantidad": 40, "motivo": "Fundición placa piso 3",
    }})

    proyecto_id: int = Field(..., description="Proyecto de donde sale el material")
    material_id: int = Field(..., description="Material que se usa en la obra")
    cantidad: int = Field(..., description="Cantidad que sale (mayor que cero; no más que la existencia, RN-122)")
    motivo: str = Field(..., min_length=3, max_length=200, description="Para qué se usa el material")

    @field_validator("motivo")
    @classmethod
    def limpiar_motivo(cls, v: str) -> str:
        """
        El motivo de la salida es obligatorio: sin espacios de más y con al menos 3 caracteres.
        """
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("El motivo debe tener al menos 3 caracteres.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class MovimientoResponse(BaseModel):
    """Un movimiento del inventario con la existencia antes y después (trazabilidad)."""

    movimiento_id: str
    tipo: str                          # entrada | salida
    proyecto_id: str
    material_id: str
    cantidad: int
    unidad: str
    motivo: str
    responsable_id: Optional[str]
    existencia_anterior: int
    existencia_actual: int
    orden_compra_id: Optional[str]     # documento de origen (solo en las entradas)
    fecha: Optional[str]

    @classmethod
    def desde_modelo(cls, m: MovimientoInventario) -> "MovimientoResponse":
        """
        Convierte el modelo de BD de un movimiento de inventario en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            movimiento_id=str(m.id), tipo=m.tipo, proyecto_id=str(m.proyecto_id),
            material_id=str(m.material_id), cantidad=m.cantidad, unidad=m.material.unidad,
            motivo=m.motivo,
            responsable_id=None if m.responsable_id is None else str(m.responsable_id),
            existencia_anterior=m.existencia_anterior, existencia_actual=m.existencia_actual,
            orden_compra_id=None if m.orden_compra_id is None else str(m.orden_compra_id),
            fecha=fecha_iso(m.fecha),
        )


class EntradaResponse(BaseModel):
    """Respuesta de la entrada: un movimiento por cada material de la orden."""
    orden_compra_id: str
    proyecto_id: str
    movimientos: list[MovimientoResponse]


class ExistenciaResponse(BaseModel):
    """La existencia actual de un material en el proyecto."""

    proyecto_id: str
    material_id: str
    material: str
    unidad: str
    existencia: int
    fecha_actualizacion: Optional[str]

    @classmethod
    def desde_modelo(cls, i: Inventario) -> "ExistenciaResponse":
        """
        Convierte el modelo de BD de una existencia en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(proyecto_id=str(i.proyecto_id), material_id=str(i.material_id),
                   material=i.material.nombre, unidad=i.material.unidad, existencia=i.existencia,
                   fecha_actualizacion=fecha_iso(i.fecha_actualizacion))


class RecepcionResponse(BaseModel):
    """Respuesta del PATCH /ordenes-compra/{id}/recepcion."""
    orden_compra_id: str
    proyecto_id: str
    proveedor_id: str
    estado: str
    fecha_recepcion: Optional[str]
    recibida_por_id: Optional[str]

    @classmethod
    def desde_modelo(cls, o: OrdenCompra) -> "RecepcionResponse":
        """
        Convierte el modelo de BD de la recepción de una orden en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(orden_compra_id=str(o.id), proyecto_id=str(o.proyecto_id),
                   proveedor_id=str(o.proveedor_id), estado=o.estado,
                   fecha_recepcion=fecha_iso(o.fecha_recepcion),
                   recibida_por_id=None if o.recibida_por_id is None else str(o.recibida_por_id))
