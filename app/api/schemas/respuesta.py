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
    """Datos de paginación que van en meta.paginacion cuando la respuesta es una lista."""

    pagina: int
    por_pagina: int
    total_registros: int
    total_paginas: int


class Meta(BaseModel):
    """Metadatos de toda respuesta: hora, versión, id de la petición y paginación."""

    timestamp: str
    version: str
    peticion_id: str
    paginacion: Optional[Paginacion] = None


class ErrorDetalle(BaseModel):
    """Un problema concreto: en qué campo, con qué código, qué pasó y qué regla se incumplió."""

    campo: Optional[str] = None
    codigo: str
    mensaje: str
    regla: Optional[str] = None


class Respuesta(BaseModel, Generic[T]):
    """
    El sobre estándar del Componente F, genérico en T (el tipo de `datos`).

    Respuesta[UsuarioResponse] le dice a Swagger cómo luce una respuesta con un usuario, y
    Respuesta[list[UsuarioResponse]] una con una lista. Solo documenta: el JSON real lo arma
    respuesta_exitosa() o los manejadores de errores.
    """

    exito: bool
    codigo: str
    mensaje: str
    datos: Optional[T] = None
    errores: list[ErrorDetalle] = []
    meta: Meta
