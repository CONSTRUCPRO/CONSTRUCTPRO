# domain/material.py
# CAPA DOMINIO: define la entidad y sus reglas de negocio.
# No importa nada de FastAPI ni de base de datos.

from pydantic import BaseModel, ConfigDict, Field, field_validator
from domain.excepciones import ReglaNegocioError

# Ajusta esta lista a las unidades que use tu catálogo
UNIDADES_VALIDAS = {"kg", "bulto", "m", "m2", "m3", "unidad", "galon", "litro"}


# ── Schemas de ENTRADA (lo que recibe la API del cliente) ──
class MaterialCreate(BaseModel):
    nombre: str = Field(..., min_length=2, description="Nombre del material")
    unidad: str = Field(..., min_length=1, description="Unidad de medida")
    categoria_id: int = Field(..., description="Id de la categoría")
    precio_referencia: float = Field(..., description="Precio de referencia en COP")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v):
        return v.strip()

    @field_validator("unidad")
    @classmethod
    def limpiar_unidad(cls, v):
        return v.strip().lower()


class PrecioUpdate(BaseModel):
    precio_referencia: float


class EstadoUpdate(BaseModel):
    estado: str  # "activo" o "inactivo"


# ── Schema de SALIDA (lo que devuelve la API al cliente) ──
class MaterialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    unidad: str
    categoria_id: str
    precio_referencia: float
    moneda: str = "COP"
    estado: str


# ── Entidad interna del dominio (la "entidad real") ──
class Material:
    def __init__(self, id: int, nombre: str, unidad: str,
                 categoria_id: int, precio_referencia: float,
                 estado: str = "activo"):
        self._validar_unidad(unidad)             # RN-032
        self._validar_precio(precio_referencia)  # RN-033
        self.id = id
        self.nombre = nombre
        self.unidad = unidad
        self.categoria_id = categoria_id
        self.precio_referencia = round(precio_referencia, 2)
        self.estado = estado

    @staticmethod
    def _validar_unidad(unidad: str):
        if unidad not in UNIDADES_VALIDAS:
            raise ReglaNegocioError("RN-032", f"Unidad de medida no válida: '{unidad}'")

    @staticmethod
    def _validar_precio(precio: float):
        if precio <= 0:
            raise ReglaNegocioError("RN-033", "El precio de referencia debe ser mayor que cero")

    def actualizar_precio(self, nuevo: float):
        self._validar_precio(nuevo)
        self.precio_referencia = round(nuevo, 2)

    def esta_activo(self) -> bool:      # RN-034
        return self.estado == "activo"

    def inactivar(self):                # RN-035: se inactiva, nunca se elimina
        self.estado = "inactivo"

    def to_response(self) -> dict:
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "unidad": self.unidad,
            "categoria_id": str(self.categoria_id),
            "precio_referencia": self.precio_referencia,
            "moneda": "COP",
            "estado": self.estado,
        }