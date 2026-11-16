"""
Modelos Pydantic del sobre estándar, para que Swagger (/docs) muestre
la forma real de las respuestas.

Uso en un router:
    @router.post("", response_model=Respuesta[RolResponse], status_code=201)
    @router.get("", response_model=Respuesta[list[RolResponse]])
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Paginacion(BaseModel):
    pagina: int
    por_pagina: int
    total_registros: int
    total_paginas: int


class Meta(BaseModel):
    timestamp: str
    version: str
    peticion_id: str
    paginacion: Optional[Paginacion] = None


class ErrorDetalle(BaseModel):
    campo: Optional[str] = None
    codigo: str
    mensaje: str
    regla: Optional[str] = None


class Respuesta(BaseModel, Generic[T]):
    exito: bool
    codigo: str
    mensaje: str
    datos: Optional[T] = None
    errores: list[ErrorDetalle] = []
    meta: Meta
