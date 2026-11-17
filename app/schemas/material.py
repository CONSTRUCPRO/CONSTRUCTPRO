# app/schemas/material.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# Las reglas de negocio (RN-032 unidad, RN-033 precio) NO van aquí: van en el dominio,
# para que el error llegue con su número de regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.material import ESTADO_ACTIVO, ESTADO_INACTIVO, Material


# ── ENTRADA ───────────────────────────────────────────────

class MaterialCreate(BaseModel):
    """Datos para registrar un material (POST) o editarlo completo (PUT)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre": "Cemento gris tipo I 50 kg",
        "unidad": "bulto",
        "categoria_id": 1,
        "precio_referencia": 28500.00,
    }})

    nombre: str = Field(..., min_length=2, max_length=150, description="Nombre del material")
    unidad: str = Field(..., min_length=1, max_length=20,
                        description="Unidad de medida: bulto, kg, tonelada, m, m2, m3, unidad, galon, litro, rollo")
    categoria_id: int = Field(..., description="Identificador de la categoría")
    precio_referencia: float = Field(..., description="Precio de referencia en COP (mayor que cero, RN-033)")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        v = " ".join(v.split())  # quita espacios al inicio, al final y repetidos
        if len(v) < 2:
            raise ValueError("El nombre del material debe tener al menos 2 caracteres.")
        return v

    @field_validator("unidad")
    @classmethod
    def limpiar_unidad(cls, v: str) -> str:
        return v.strip().lower()


class MaterialUpdate(MaterialCreate):
    """PUT: se envían todos los campos del material."""
    pass


class PrecioUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"precio_referencia": 29900.00}})

    precio_referencia: float = Field(..., description="Nuevo precio de referencia en COP (mayor que cero, RN-033)")


class EstadoUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"estado": "inactivo"}})

    estado: str = Field(..., description="'inactivo' para inactivar o 'activo' para reactivar")

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in (ESTADO_ACTIVO, ESTADO_INACTIVO):
            raise ValueError("El estado debe ser 'activo' o 'inactivo'.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class MaterialResponse(BaseModel):
    material_id: str               # ids SIEMPRE como texto y con sufijo _id
    nombre: str
    categoria_id: str
    categoria: str                 # nombre de la categoría, como pide la HU
    unidad: str
    precio_referencia: float
    moneda: str = "COP"            # dinero SIEMPRE con su moneda
    estado: str
    fecha_registro: Optional[str]          # ISO 8601 UTC
    fecha_actualizacion: Optional[str]     # null si nunca se ha editado

    @classmethod
    def desde_modelo(cls, m: Material) -> "MaterialResponse":
        return cls(
            material_id=str(m.id),
            nombre=m.nombre,
            categoria_id=str(m.categoria_id),
            categoria=m.categoria.nombre,
            unidad=m.unidad,
            precio_referencia=float(m.precio_referencia),
            estado=m.estado,
            fecha_registro=fecha_iso(m.fecha_registro),
            fecha_actualizacion=fecha_iso(m.fecha_actualizacion),
        )
