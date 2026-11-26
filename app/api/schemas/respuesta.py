"""
Modelos Pydantic del sobre estándar (success, message, data), para que Swagger (/docs)
muestre la forma real de las respuestas.

Uso en un router:
    @router.post("", response_model=Respuesta[RolResponse], status_code=201)
    @router.get("", response_model=Respuesta[Pagina[RolResponse]])     # consulta paginada
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Paginacion(BaseModel):
    """Datos de paginación que van en data.paginacion cuando la respuesta es una lista."""

    pagina: int
    por_pagina: int
    total_registros: int
    total_paginas: int


class Pagina(BaseModel, Generic[T]):
    """
    Lo que va en `data` en una consulta paginada: los registros de la página pedida y los datos
    para pedir las demás páginas.
    """

    registros: list[T]
    paginacion: Paginacion


class Respuesta(BaseModel, Generic[T]):
    """
    El sobre estándar, genérico en T (el tipo de `data`).

    Respuesta[UsuarioResponse] le dice a Swagger cómo luce una respuesta con un usuario, y
    Respuesta[Pagina[UsuarioResponse]] una con una página de usuarios. Solo documenta: el JSON
    real lo arma respuesta_exitosa() o los manejadores de errores (app/core/respuestas.py).

    El orden de los campos es el del ejemplo del docente: message, data, success.
    """

    message: str
    data: Optional[T] = None
    success: bool
