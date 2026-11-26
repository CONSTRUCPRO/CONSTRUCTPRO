# app/api/schemas/proveedor.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# El formato de NIT, teléfono y correo se valida aquí: si falla, la base común
# responde 422 VAL_FORMATO_INVALIDO con el mensaje en español del ValueError.
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.proveedor import ESTADO_ACTIVO, ESTADO_INACTIVO, Proveedor

# NIT colombiano: de 6 a 10 dígitos, guion y dígito de verificación. Ej.: 900123456-7
PATRON_NIT = re.compile(r"^\d{6,10}-\d$")
# Teléfono: de 7 a 15 dígitos, con + opcional al inicio. Ej.: 6076543210, +573001234567
PATRON_TELEFONO = re.compile(r"^\+?\d{7,15}$")
# Correo: algo@dominio.ext
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _limpiar_texto(v: str, campo: str) -> str:
    """
    Quita espacios de más y exige al menos 2 caracteres; el nombre del campo va en el mensaje de error.
    """
    v = " ".join(v.split())  # quita espacios al inicio, al final y repetidos
    if len(v) < 2:
        raise ValueError(f"El campo '{campo}' debe tener al menos 2 caracteres.")
    return v


# ── ENTRADA ───────────────────────────────────────────────

class ProveedorCreate(BaseModel):
    """Datos para registrar un proveedor (POST) o editarlo completo (PUT)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "razon_social": "Ferretería El Constructor S.A.S.",
        "nit": "900123456-7",
        "contacto": "Carlos Pérez",
        "telefono": "6076543210",
        "correo": "ventas@elconstructor.co",
    }})

    razon_social: str = Field(..., min_length=2, max_length=150, description="Razón social del proveedor")
    nit: str = Field(..., max_length=20, description="NIT con dígito de verificación, ej. 900123456-7 (único, RN-036)")
    contacto: str = Field(..., min_length=2, max_length=120, description="Nombre de la persona de contacto")
    telefono: str = Field(..., max_length=20, description="Teléfono de 7 a 15 dígitos, ej. 6076543210")
    correo: str = Field(..., max_length=120, description="Correo electrónico, ej. ventas@elconstructor.co")

    @field_validator("razon_social")
    @classmethod
    def limpiar_razon_social(cls, v: str) -> str:
        """Aplica _limpiar_texto a la razón social."""
        return _limpiar_texto(v, "razon_social")

    @field_validator("contacto")
    @classmethod
    def limpiar_contacto(cls, v: str) -> str:
        """Aplica _limpiar_texto al contacto."""
        return _limpiar_texto(v, "contacto")

    @field_validator("nit")
    @classmethod
    def validar_nit(cls, v: str) -> str:
        """
        Acepta '900.123.456-7' o '900123456-7' y exige 6 a 10 dígitos, guion y dígito de
        verificación. Solo se revisa la forma, no el cálculo de la DIAN (el NIT del ejemplo del
        issue no lo cumple y haría fallar el caso 1).
        """
        v = v.replace(" ", "").replace(".", "")  # acepta 900.123.456-7
        if not PATRON_NIT.match(v):
            raise ValueError("El NIT debe tener de 6 a 10 dígitos, un guion y el dígito "
                             "de verificación. Ejemplo: 900123456-7.")
        return v

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        """Quita espacios, guiones y paréntesis y exige de 7 a 15 dígitos."""
        v = re.sub(r"[\s\-()]", "", v)  # acepta (607) 654-3210
        if not PATRON_TELEFONO.match(v):
            raise ValueError("El teléfono debe tener de 7 a 15 dígitos (puede empezar con +). "
                             "Ejemplo: 6076543210.")
        return v

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        """Correo en minúscula con la forma algo@dominio.ext."""
        v = v.strip().lower()
        if not PATRON_CORREO.match(v):
            raise ValueError("El correo no tiene un formato válido. Ejemplo: ventas@elconstructor.co.")
        return v


class ProveedorUpdate(ProveedorCreate):
    """PUT: se envían todos los campos del proveedor."""
    pass


class EstadoProveedorUpdate(BaseModel):
    """Activar o inactivar un proveedor."""

    model_config = ConfigDict(json_schema_extra={"example": {"estado": "inactivo"}})

    estado: str = Field(..., description="'inactivo' para inactivar o 'activo' para reactivar")

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        """Solo 'activo' o 'inactivo'."""
        v = v.strip().lower()
        if v not in (ESTADO_ACTIVO, ESTADO_INACTIVO):
            raise ValueError("El estado debe ser 'activo' o 'inactivo'.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class ProveedorResponse(BaseModel):
    """Un proveedor en las respuestas."""

    proveedor_id: str              # ids SIEMPRE como texto y con sufijo _id
    razon_social: str
    nit: str
    contacto: str
    telefono: str
    correo: str
    estado: str
    fecha_registro: Optional[str]          # ISO 8601 UTC
    fecha_actualizacion: Optional[str]     # null si nunca se ha editado

    @classmethod
    def desde_modelo(cls, p: Proveedor) -> "ProveedorResponse":
        """
        Convierte el modelo de BD de un proveedor en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(
            proveedor_id=str(p.id),
            razon_social=p.razon_social,
            nit=p.nit,
            contacto=p.contacto,
            telefono=p.telefono,
            correo=p.correo,
            estado=p.estado,
            fecha_registro=fecha_iso(p.fecha_registro),
            fecha_actualizacion=fecha_iso(p.fecha_actualizacion),
        )
