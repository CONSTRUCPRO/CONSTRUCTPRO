# app/schemas/orden_compra.py
# Esquemas Pydantic de la HU-21: entrada (generar y anular) y salida (la orden con su detalle).
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.orden_compra import OrdenCompra, OrdenDetalle


# ── ENTRADA ───────────────────────────────────────────────

class OrdenCompraCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"aprobacion_id": 1}})

    aprobacion_id: int = Field(..., description="Aprobación en estado Aprobada (RN-081)")


class AnulacionDatos(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"motivo": "El proyecto canceló la compra."}})

    motivo: Optional[str] = Field(None, max_length=500, description="Motivo de la anulación (FUN-084)")


# ── SALIDA ────────────────────────────────────────────────

class LineaOrdenResponse(BaseModel):
    material_id: str
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float

    @classmethod
    def desde_modelo(cls, d: OrdenDetalle) -> "LineaOrdenResponse":
        return cls(material_id=str(d.material_id), nombre=d.material.nombre, cantidad=d.cantidad,
                   precio_unitario=float(d.precio_unitario), subtotal=float(d.subtotal))


class OrdenCompraResponse(BaseModel):
    """Campos del ejemplo del issue, más subtotal, IVA y las fechas de confirmación y anulación."""
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
    detalle: list[LineaOrdenResponse]

    @classmethod
    def desde_modelo(cls, o: OrdenCompra) -> "OrdenCompraResponse":
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
            detalle=[LineaOrdenResponse.desde_modelo(d) for d in o.detalle],
        )
