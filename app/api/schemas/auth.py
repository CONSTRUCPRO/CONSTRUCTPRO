# app/api/schemas/auth.py
# Esquemas Pydantic de la HU-02: entrada del login y la renovación, y salida de la sesión.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── ENTRADA ───────────────────────────────────────────────

class LoginDatos(BaseModel):
    """Datos del login: correo y contraseña."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "correo": "admin@construpro.co",
        "contrasena": "Admin2026",
    }})

    correo: str = Field(..., max_length=120)
    contrasena: str = Field(..., max_length=64)

    @field_validator("correo")
    @classmethod
    def normalizar_correo(cls, v: str) -> str:
        """El correo se compara en minúscula y sin espacios, como se guardó."""
        return v.strip().lower()


class RenovarDatos(BaseModel):
    """El token de renovación que entregó el login, para pedir tokens nuevos."""

    model_config = ConfigDict(json_schema_extra={"example": {
        "token_renovacion": "pegue aquí el token_renovacion que entregó el login",
    }})

    token_renovacion: str = Field(..., min_length=10, max_length=200)


# ── SALIDA ────────────────────────────────────────────────

class SesionResponse(BaseModel):
    """Forma exacta del ejemplo del issue. Nunca incluye la contraseña (RN-003)."""
    usuario_id: str
    nombre_completo: str
    rol: str
    token_acceso: str
    token_renovacion: str
    expira_en: Optional[str]       # ISO 8601 UTC: cuándo vence el token de acceso
