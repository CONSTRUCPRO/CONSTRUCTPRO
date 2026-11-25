# app/api/schemas/usuario.py
# Esquemas Pydantic de la HU-01: validan la FORMA de la entrada y definen la SALIDA.
# Si un validador lanza ValueError("mensaje"), la base común responde 422
# VAL_FORMATO_INVALIDO con ese mensaje. Si falta un campo, 422 VAL_CAMPO_REQUERIDO.
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.usuario import ESTADO_ACTIVO, ESTADO_INACTIVO, TIPOS_DOCUMENTO, Usuario

# Documento: de 5 a 15 letras o dígitos (el pasaporte puede tener letras). Ej.: 1098765432
PATRON_DOCUMENTO = re.compile(r"^[A-Za-z0-9]{5,15}$")
# Teléfono: de 7 a 15 dígitos, con + opcional al inicio. Ej.: 3001234567
PATRON_TELEFONO = re.compile(r"^\+?\d{7,15}$")
# Correo: algo@dominio.ext
PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


# ── Validaciones reutilizables ────────────────────────────

def _limpiar_nombre(v: str) -> str:
    """Quita espacios de más y exige al menos 3 caracteres."""
    v = " ".join(v.split())  # quita espacios al inicio, al final y repetidos
    if len(v) < 3:
        raise ValueError("El nombre completo debe tener al menos 3 caracteres.")
    return v


def _validar_tipo_documento(v: str) -> str:
    """El tipo de documento en mayúscula y dentro de TIPOS_DOCUMENTO (CC, CE, TI, PA, NIT)."""
    v = v.strip().upper()
    if v not in TIPOS_DOCUMENTO:
        raise ValueError(f"El tipo de documento debe ser uno de: {', '.join(TIPOS_DOCUMENTO)}.")
    return v


def _validar_documento(v: str) -> str:
    """Quita puntos y espacios (acepta '1.098.765.432') y exige de 5 a 15 letras o dígitos."""
    v = v.replace(" ", "").replace(".", "").upper()  # acepta 1.098.765.432
    if not PATRON_DOCUMENTO.match(v):
        raise ValueError("El número de documento debe tener de 5 a 15 letras o dígitos, "
                         "sin espacios ni símbolos. Ejemplo: 1098765432.")
    return v


def _validar_correo(v: str) -> str:
    """Correo en minúscula con la forma algo@dominio.ext."""
    v = v.strip().lower()
    if not PATRON_CORREO.match(v):
        raise ValueError("El correo no tiene un formato válido. Ejemplo: laura@construpro.co.")
    return v


def _validar_telefono(v: str) -> str:
    """Quita espacios, guiones y paréntesis y exige de 7 a 15 dígitos (con + opcional)."""
    v = re.sub(r"[\s\-()]", "", v)  # acepta (300) 123-4567
    if not PATRON_TELEFONO.match(v):
        raise ValueError("El teléfono debe tener de 7 a 15 dígitos (puede empezar con +). "
                         "Ejemplo: 3001234567.")
    return v


# ── ENTRADA ───────────────────────────────────────────────

class UsuarioPerfil(BaseModel):
    """Datos del perfil: los comparten el registro (POST) y la edición (PUT)."""
    nombre_completo: str = Field(..., max_length=120, description="Nombre y apellidos")
    tipo_documento: str = Field(..., description=f"Uno de: {', '.join(TIPOS_DOCUMENTO)}")
    numero_documento: str = Field(..., max_length=20, description="Único en el sistema (RN-001)")
    correo: str = Field(..., max_length=120, description="Único en el sistema (RN-001)")
    telefono: str = Field(..., max_length=20, description="De 7 a 15 dígitos")

    @field_validator("nombre_completo")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        """Aplica _limpiar_nombre al nombre completo."""
        return _limpiar_nombre(v)

    @field_validator("tipo_documento")
    @classmethod
    def validar_tipo_documento(cls, v: str) -> str:
        """Aplica _validar_tipo_documento."""
        return _validar_tipo_documento(v)

    @field_validator("numero_documento")
    @classmethod
    def validar_documento(cls, v: str) -> str:
        """Aplica _validar_documento."""
        return _validar_documento(v)

    @field_validator("correo")
    @classmethod
    def validar_correo(cls, v: str) -> str:
        """Aplica _validar_correo."""
        return _validar_correo(v)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        """Aplica _validar_telefono."""
        return _validar_telefono(v)


class UsuarioCreate(UsuarioPerfil):
    """POST: perfil + contraseña + rol."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre_completo": "Laura Gómez",
        "tipo_documento": "CC",
        "numero_documento": "1098765432",
        "correo": "laura@construpro.co",
        "telefono": "3001234567",
        "contrasena": "Construpro2026",
        "rol_id": 2,
    }})

    contrasena: str = Field(..., max_length=64,
                            description="Mínimo 8 caracteres, con al menos una letra y un número. "
                                        "Se guarda cifrada (RN-003).")
    rol_id: int = Field(..., description="Rol del usuario, obligatorio (RN-002)")

    @field_validator("contrasena")
    @classmethod
    def validar_contrasena(cls, v: str) -> str:
        """Contraseña de mínimo 8 caracteres con al menos una letra y un número."""
        if len(v) < 8 or not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("La contraseña debe tener mínimo 8 caracteres, "
                             "con al menos una letra y un número.")
        return v


class UsuarioUpdate(UsuarioPerfil):
    """PUT: solo datos del perfil. El rol cambia con PATCH /rol y el estado con PATCH /estado."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre_completo": "Laura Gómez Ruiz",
        "tipo_documento": "CC",
        "numero_documento": "1098765432",
        "correo": "laura.gomez@construpro.co",
        "telefono": "3001234567",
    }})


class EstadoUsuarioUpdate(BaseModel):
    """Activar o inactivar un usuario."""

    model_config = ConfigDict(json_schema_extra={"example": {"estado": "inactivo"}})

    estado: str = Field(..., description="'inactivo' para inactivar o 'activo' para reactivar")

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        """Solo 'activo' o 'inactivo' (en minúscula)."""
        v = v.strip().lower()
        if v not in (ESTADO_ACTIVO, ESTADO_INACTIVO):
            raise ValueError("El estado debe ser 'activo' o 'inactivo'.")
        return v


class RolUsuarioUpdate(BaseModel):
    """Cambiar el rol de un usuario (PATCH /usuarios/{id}/rol)."""

    model_config = ConfigDict(json_schema_extra={"example": {"rol_id": 3}})

    rol_id: int = Field(..., description="Nuevo rol del usuario (debe existir y estar activo)")


# ── SALIDA ────────────────────────────────────────────────

class UsuarioResponse(BaseModel):
    """Nunca incluye la contraseña ni su hash (RN-003)."""
    usuario_id: str              # ids SIEMPRE como texto y con sufijo _id
    nombre_completo: str
    tipo_documento: str
    numero_documento: str
    correo: str
    telefono: str
    rol_id: str
    rol: str
    estado: str
    fecha_registro: Optional[str]          # ISO 8601 UTC
    fecha_actualizacion: Optional[str]     # null si nunca se ha editado

    @classmethod
    def desde_modelo(cls, u: Usuario) -> "UsuarioResponse":
        """
        Convierte el modelo de BD de un usuario en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).

        Nunca incluye la contraseña ni su hash (RN-003).
        """
        return cls(
            usuario_id=str(u.id),
            nombre_completo=u.nombre_completo,
            tipo_documento=u.tipo_documento,
            numero_documento=u.numero_documento,
            correo=u.correo,
            telefono=u.telefono,
            rol_id=str(u.rol_id),
            rol=u.rol.nombre,
            estado=u.estado,
            fecha_registro=fecha_iso(u.fecha_registro),
            fecha_actualizacion=fecha_iso(u.fecha_actualizacion),
        )
