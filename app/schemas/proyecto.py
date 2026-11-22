# app/schemas/proyecto.py
# Esquemas Pydantic de la HU-05: validan la FORMA de la entrada y definen la SALIDA.
# Si un validador lanza ValueError("mensaje"), la base común responde 422
# VAL_FORMATO_INVALIDO con ese mensaje. Si falta un campo, 422 VAL_CAMPO_REQUERIDO.
# La regla de fechas (RN-017) NO se valida aquí sino en el dominio, para que el error
# lleve "regla": "RN-017" como pide el caso 3 del issue.
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.proyecto import ESTADOS, Proyecto


def _limpiar(v: Optional[str], campo: str, minimo: int = 2) -> Optional[str]:
    """Quita espacios al inicio, al final y repetidos, y exige un largo mínimo."""
    if v is None:
        return None
    v = " ".join(v.split())
    if len(v) < minimo:
        raise ValueError(f"El campo '{campo}' debe tener al menos {minimo} caracteres.")
    return v


# ── ENTRADA ───────────────────────────────────────────────

class UbicacionDatos(BaseModel):
    """Ubicación de la obra (FUN-019). Las coordenadas son opcionales."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "direccion": "Cra 35 # 48-20",
        "ciudad": "Bucaramanga",
        "latitud": 7.1193,
        "longitud": -73.1227,
    }})

    direccion: str = Field(..., max_length=200, description="Dirección de la obra")
    ciudad: str = Field(..., max_length=100, description="Ciudad de la obra")
    latitud: Optional[float] = Field(None, ge=-90, le=90, description="Entre -90 y 90")
    longitud: Optional[float] = Field(None, ge=-180, le=180, description="Entre -180 y 180")

    @field_validator("direccion")
    @classmethod
    def validar_direccion(cls, v: str) -> str:
        return _limpiar(v, "direccion", minimo=5)

    @field_validator("ciudad")
    @classmethod
    def validar_ciudad(cls, v: str) -> str:
        return _limpiar(v, "ciudad")


class ProyectoDatosGenerales(BaseModel):
    """Datos generales: los comparten el registro (POST) y la edición (PUT)."""
    nombre: str = Field(..., max_length=150, description="Único por cliente (RN-018)")
    cliente: str = Field(..., max_length=150, description="Cliente de la obra")
    descripcion: Optional[str] = Field(None, max_length=500)
    fecha_inicio: date = Field(..., description="Formato AAAA-MM-DD")
    fecha_fin_estimada: date = Field(
        ..., description="Formato AAAA-MM-DD. No puede ser anterior a fecha_inicio (RN-017)")

    @field_validator("nombre")
    @classmethod
    def validar_nombre(cls, v: str) -> str:
        return _limpiar(v, "nombre", minimo=3)

    @field_validator("cliente")
    @classmethod
    def validar_cliente(cls, v: str) -> str:
        return _limpiar(v, "cliente")

    @field_validator("descripcion")
    @classmethod
    def validar_descripcion(cls, v: Optional[str]) -> Optional[str]:
        return _limpiar(v, "descripcion") if v and v.strip() else None


class ProyectoCreate(ProyectoDatosGenerales):
    """POST: datos generales + responsable. La ubicación es opcional (se puede registrar después)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre": "Torre Cabecera Etapa 2",
        "cliente": "Inversiones Andinas S.A.S.",
        "descripcion": "Edificio residencial de 12 pisos",
        "fecha_inicio": "2026-11-01",
        "fecha_fin_estimada": "2027-12-15",
        "responsable_id": 1,
        "ubicacion": {"direccion": "Cra 35 # 48-20", "ciudad": "Bucaramanga",
                      "latitud": 7.1193, "longitud": -73.1227},
    }})

    responsable_id: int = Field(..., description="Usuario activo con rol Coordinador o Director (RN-016)")
    ubicacion: Optional[UbicacionDatos] = Field(None, description="Opcional al registrar")


class ProyectoUpdate(ProyectoDatosGenerales):
    """PUT: solo datos generales. No se permite si el proyecto está finalizado (RN-019)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre": "Torre Cabecera Etapa 2",
        "cliente": "Inversiones Andinas S.A.S.",
        "descripcion": "Edificio residencial de 14 pisos",
        "fecha_inicio": "2026-11-01",
        "fecha_fin_estimada": "2028-03-30",
    }})


class ResponsableUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"responsable_id": 1}})

    responsable_id: int = Field(..., description="Usuario activo con rol Coordinador o Director (RN-016)")


class EstadoProyectoUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"estado": "finalizado"}})

    estado: str = Field(..., description="activo | suspendido | finalizado")

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ESTADOS:
            raise ValueError(f"El estado debe ser uno de: {', '.join(ESTADOS)}.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class UbicacionResponse(BaseModel):
    direccion: str
    ciudad: str
    latitud: Optional[float]
    longitud: Optional[float]


class ProyectoResponse(BaseModel):
    proyecto_id: str               # ids SIEMPRE como texto y con sufijo _id
    nombre: str
    cliente: str
    descripcion: Optional[str]
    fecha_inicio: str              # AAAA-MM-DD
    fecha_fin_estimada: str        # AAAA-MM-DD
    responsable_id: str
    responsable: str               # nombre del responsable
    estado: str
    ubicacion: Optional[UbicacionResponse]   # null mientras no se registre
    fecha_registro: Optional[str]            # ISO 8601 UTC
    fecha_actualizacion: Optional[str]       # null si nunca se ha editado

    @classmethod
    def desde_modelo(cls, p: Proyecto) -> "ProyectoResponse":
        ubicacion = None
        if p.tiene_ubicacion():
            ubicacion = UbicacionResponse(direccion=p.direccion, ciudad=p.ciudad,
                                          latitud=p.latitud, longitud=p.longitud)
        return cls(
            proyecto_id=str(p.id),
            nombre=p.nombre,
            cliente=p.cliente,
            descripcion=p.descripcion,
            fecha_inicio=fecha_iso(p.fecha_inicio),
            fecha_fin_estimada=fecha_iso(p.fecha_fin_estimada),
            responsable_id=str(p.responsable_id),
            responsable=p.responsable.nombre_completo,
            estado=p.estado,
            ubicacion=ubicacion,
            fecha_registro=fecha_iso(p.fecha_registro),
            fecha_actualizacion=fecha_iso(p.fecha_actualizacion),
        )
