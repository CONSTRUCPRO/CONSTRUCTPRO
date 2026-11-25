# app/api/schemas/orden_compra.py
# Esquemas Pydantic de la HU-21: entrada (generar y anular) y salida (la orden con su detalle).
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.orden_compra import OrdenCompra, OrdenDetalle


# ── ENTRADA ───────────────────────────────────────────────

class OrdenCompraCreate(BaseModel):
    """
    Para generar la orden basta con la aprobación: de ahí salen proveedor, proyecto, líneas y valor.
    """

    model_config = ConfigDict(json_schema_extra={"example": {"aprobacion_id": 1}})

    aprobacion_id: int = Field(..., description="Aprobación en estado Aprobada (RN-081)")


class AnulacionDatos(BaseModel):
    """Motivo de la anulación; es opcional (FUN-084)."""

    model_config = ConfigDict(json_schema_extra={"example": {"motivo": "El proyecto canceló la compra."}})

    motivo: Optional[str] = Field(None, max_length=500, description="Motivo de la anulación (FUN-084)")


# ── SALIDA ────────────────────────────────────────────────

class LineaOrdenResponse(BaseModel):
    """Una línea de la orden con el nombre del material."""

    material_id: str
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float

    @classmethod
    def desde_modelo(cls, d: OrdenDetalle) -> "LineaOrdenResponse":
        """
        Convierte el modelo de BD de una línea de la orden en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(material_id=str(d.material_id), nombre=d.material.nombre, cantidad=d.cantidad,
                   precio_unitario=float(d.precio_unitario), subtotal=float(d.subtotal))


class OrdenCompraResponse(BaseModel):
    """Campos del ejemplo del issue, más subtotal, IVA y las fechas de confirmación, anulación y cierre."""
    orden_compra_id: str
    aprobacion_id: str
    cotizacion_id: str
    proveedor_id: str
    proveedor: str
    proyecto_id: str
    estado: str                          # emitida | confirmada | cerrada | anulada
    moneda: str = "COP"
    subtotal: float
    impuestos: float
    valor_total: float                   # = monto autorizado en la aprobación (RN-082)
    fecha_emision: Optional[str]
    fecha_confirmacion: Optional[str]
    fecha_anulacion: Optional[str]
    motivo_anulacion: Optional[str]
    fecha_cierre: Optional[str]          # RN-087: pagada por completo y recibida
    detalle: list[LineaOrdenResponse]

    @classmethod
    def desde_modelo(cls, o: OrdenCompra) -> "OrdenCompraResponse":
        """
        Convierte el modelo de BD de una orden de compra en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            orden_compra_id=str(o.id),
            aprobacion_id=str(o.aprobacion_id),
            cotizacion_id=str(o.cotizacion_id),
            proveedor_id=str(o.proveedor_id),
            proveedor=o.proveedor.razon_social,
            proyecto_id=str(o.proyecto_id),
            estado=o.estado,
            subtotal=float(o.subtotal),
            impuestos=float(o.impuestos),
            valor_total=float(o.valor_total),
            fecha_emision=fecha_iso(o.fecha_emision),
            fecha_confirmacion=fecha_iso(o.fecha_confirmacion),
            fecha_anulacion=fecha_iso(o.fecha_anulacion),
            motivo_anulacion=o.motivo_anulacion,
            fecha_cierre=fecha_iso(o.fecha_cierre),
            detalle=[LineaOrdenResponse.desde_modelo(d) for d in o.detalle],
        )
