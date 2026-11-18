# app/schemas/rol.py
# Esquemas Pydantic de la HU-03: validan la entrada y definen la salida.
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.rol import ACCIONES, MODULOS, Rol


class PermisoModulo(BaseModel):
    """Un módulo con sus acciones permitidas, ej. {"modulo": "Solicitudes", "acciones": ["crear"]}."""
    modulo: str
    acciones: list[str]

    @field_validator("modulo")
    @classmethod
    def modulo_existe(cls, v: str) -> str:
        # FUN-013 paso 2: validar que los módulos existan
        for m in MODULOS:
            if m.lower() == v.strip().lower():
                return m
        raise ValueError(f"El módulo '{v}' no existe. Módulos válidos: {', '.join(MODULOS)}.")

    @field_validator("acciones")
    @classmethod
    def acciones_validas(cls, v: list[str]) -> list[str]:
        limpias = [a.strip().lower() for a in v]
        invalidas = [a for a in limpias if a not in ACCIONES]
        if invalidas:
            raise ValueError(f"Acciones no válidas: {', '.join(invalidas)}. "
                             f"Acciones válidas: {', '.join(ACCIONES)}.")
        return limpias


def _a_diccionario(permisos: list[PermisoModulo]) -> dict[str, list[str]]:
    """Une módulos repetidos: [{Solicitudes:[crear]}, {Solicitudes:[editar]}] -> {Solicitudes:[crear, editar]}."""
    resultado: dict[str, list[str]] = {}
    for p in permisos:
        resultado.setdefault(p.modulo, []).extend(p.acciones)
    return resultado


class RolCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=255)
    permisos: list[PermisoModulo] = Field(
        default_factory=list, description="Al menos un permiso (RN-013).")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return " ".join(v.split()).capitalize()

    def permisos_dict(self) -> dict[str, list[str]]:
        return _a_diccionario(self.permisos)


class RolUpdate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=60)
    descripcion: Optional[str] = Field(None, max_length=255)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return " ".join(v.split()).capitalize()


class PermisosUpdate(BaseModel):
    permisos: list[PermisoModulo] = Field(..., description="Al menos un permiso (RN-013).")

    def permisos_dict(self) -> dict[str, list[str]]:
        return _a_diccionario(self.permisos)


class EstadoRolUpdate(BaseModel):
    estado: Literal["activo", "inactivo"]


class RolResponse(BaseModel):
    rol_id: str
    nombre: str
    descripcion: Optional[str]
    estado: str
    fecha_registro: Optional[str]
    permisos: list[PermisoModulo]

    @classmethod
    def desde_modelo(cls, rol: Rol) -> "RolResponse":
        return cls(
            rol_id=str(rol.id),
            nombre=rol.nombre,
            descripcion=rol.descripcion,
            estado=rol.estado,
            fecha_registro=fecha_iso(rol.fecha_registro),
            permisos=[PermisoModulo(modulo=m, acciones=a)
                      for m, a in rol.permisos_agrupados().items()],
        )


class PermisosRolResponse(BaseModel):
    """Forma exacta del ejemplo de la HU-03: {rol_id, nombre, permisos}."""
    rol_id: str
    nombre: str
    permisos: list[PermisoModulo]

    @classmethod
    def desde_modelo(cls, rol: Rol) -> "PermisosRolResponse":
        return cls(
            rol_id=str(rol.id),
            nombre=rol.nombre,
            permisos=[PermisoModulo(modulo=m, acciones=a)
                      for m, a in rol.permisos_agrupados().items()],
        )
