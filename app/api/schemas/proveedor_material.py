# app/api/schemas/proveedor_material.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# RN-038 (precio > 0) NO va aquí: va en el dominio, para que el error llegue con su regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.proveedor_material import ProveedorMaterial


# ── ENTRADA ───────────────────────────────────────────────

class OfertaCreate(BaseModel):
    """Oferta de un proveedor para un material del catálogo (POST)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "material_id": 1,
        "precio": 28500.00,
        "disponible": True,
        "dias_entrega": 3,
    }})

    material_id: int = Field(..., description="Identificador del material del catálogo")
    precio: float = Field(..., description="Precio ofrecido en COP (mayor que cero, RN-038)")
    disponible: bool = Field(True, description="Si el proveedor tiene el material disponible")
    dias_entrega: int = Field(..., ge=0, le=365, description="Días que tarda en entregar (0 a 365)")


# ── SALIDA ────────────────────────────────────────────────

class OfertaResponse(BaseModel):
    """Respuesta del POST: la oferta registrada o actualizada."""
    proveedor_id: str
    razon_social: str
    material_id: str
    material: str
    precio: float
    moneda: str = "COP"
    disponible: bool
    dias_entrega: int
    fecha_registro: Optional[str]
    fecha_actualizacion: Optional[str]

    @classmethod
    def desde_modelo(cls, o: ProveedorMaterial) -> "OfertaResponse":
        """
        Convierte el modelo de BD de una oferta en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            proveedor_id=str(o.proveedor_id),
            razon_social=o.proveedor.razon_social,
            material_id=str(o.material_id),
            material=o.material.nombre,
            precio=float(o.precio),
            disponible=o.disponible,
            dias_entrega=o.dias_entrega,
            fecha_registro=fecha_iso(o.fecha_registro),
            fecha_actualizacion=fecha_iso(o.fecha_actualizacion),
        )


class ProveedorDeMaterialResponse(BaseModel):
    """Cada elemento del GET /materiales/{material_id}/proveedores (contrato del issue)."""
    proveedor_id: str
    razon_social: str
    precio: float
    moneda: str = "COP"
    disponible: bool
    dias_entrega: int

    @classmethod
    def desde_modelo(cls, o: ProveedorMaterial) -> "ProveedorDeMaterialResponse":
        """
        Convierte el modelo de BD de una oferta vista desde el material en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).

        Tiene los campos exactos que pide el issue para la consulta por material.
        """
        return cls(
            proveedor_id=str(o.proveedor_id),
            razon_social=o.proveedor.razon_social,
            precio=float(o.precio),
            disponible=o.disponible,
            dias_entrega=o.dias_entrega,
        )
