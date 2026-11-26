# app/api/schemas/cotizacion.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "data" en el sobre estándar).
# Las reglas RN-061 a RN-065 NO van aquí: van en el dominio, para que el error llegue con su regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.aprobacion import Aprobacion
from app.domain.cotizacion import Cotizacion, CotizacionDetalle


# ── ENTRADA ───────────────────────────────────────────────

class CotizacionCreate(BaseModel):
    """Comparativos seleccionados (HU-16) con los que se arma la cotización (POST)."""
    model_config = ConfigDict(json_schema_extra={"example": {"comparativo_ids": [1, 2]}})

    comparativo_ids: list[int] = Field(
        ..., min_length=1,
        description="Comparativos con oferta seleccionada, del mismo proyecto y proveedor (RN-061)")


# ── SALIDA ────────────────────────────────────────────────

class LineaCotizacionResponse(BaseModel):
    """Una línea de la cotización: material, cantidad, precio unitario y subtotal."""

    comparativo_id: str
    material_id: str
    cantidad: int
    precio_unitario: float
    subtotal: float

    @classmethod
    def desde_modelo(cls, d: CotizacionDetalle) -> "LineaCotizacionResponse":
        """
        Convierte el modelo de BD de una línea de la cotización en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(comparativo_id=str(d.comparativo_id), material_id=str(d.material_id),
                   cantidad=d.cantidad, precio_unitario=float(d.precio_unitario),
                   subtotal=float(d.subtotal))


class AprobacionResumen(BaseModel):
    """Resumen de la aprobación de la cotización (null hasta que se envía)."""

    aprobacion_id: str
    estado: str                    # En revisión (la HU-20 la pasa a Aprobada / Rechazada)
    monto: float
    fecha_envio: Optional[str]

    @classmethod
    def desde_modelo(cls, a: Aprobacion) -> "AprobacionResumen":
        """
        Convierte el modelo de BD de la aprobación en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(aprobacion_id=str(a.id), estado=a.estado, monto=float(a.monto),
                   fecha_envio=fecha_iso(a.fecha_envio))


class CotizacionResponse(BaseModel):
    """La cotización con sus líneas, los totales y el resumen de su aprobación."""

    cotizacion_id: str
    proyecto_id: str
    proveedor_id: str
    estado: str                    # Generada | Enviada | Aprobada | Rechazada | Anulada
    moneda: str = "COP"
    subtotal: float
    impuestos: float               # IVA 19 % (RN-062)
    total: float
    detalle: list[LineaCotizacionResponse]
    vigente_hasta: Optional[str]   # fecha ISO (RN-065)
    fecha_registro: Optional[str]
    fecha_actualizacion: Optional[str]
    aprobacion: Optional[AprobacionResumen]   # null hasta que se envía

    @classmethod
    def desde_modelo(cls, c: Cotizacion,
                     aprobacion: Optional[Aprobacion] = None) -> "CotizacionResponse":
        """
        Convierte el modelo de BD de una cotización en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            cotizacion_id=str(c.id),
            proyecto_id=str(c.proyecto_id),
            proveedor_id=str(c.proveedor_id),
            estado=c.estado,
            subtotal=float(c.subtotal),
            impuestos=float(c.impuestos),
            total=float(c.total),
            detalle=[LineaCotizacionResponse.desde_modelo(d) for d in c.detalle],
            vigente_hasta=fecha_iso(c.vigente_hasta),
            fecha_registro=fecha_iso(c.fecha_registro),
            fecha_actualizacion=fecha_iso(c.fecha_actualizacion),
            aprobacion=None if aprobacion is None else AprobacionResumen.desde_modelo(aprobacion),
        )
