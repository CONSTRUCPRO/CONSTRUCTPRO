"""
Sobre de respuesta estándar de ConstruPro (Componente F del parcial).

Toda respuesta de la API tiene esta forma:
    {exito, codigo, mensaje, datos, errores, meta{timestamp, version, peticion_id, paginacion}}

Uso en un router:
    return respuesta_exitosa(datos=rol, mensaje="Rol creado correctamente.")
"""
import math
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

VERSION_API = "v1"

# Identificador de la petición en curso. Lo asigna el middleware de app/core/errores.py
# y sirve para buscar en el log el detalle de un error.
peticion_id_actual: ContextVar[Optional[str]] = ContextVar("peticion_id_actual", default=None)


def obtener_peticion_id() -> str:
    """Devuelve el id de la petición en curso (o crea uno si no existe)."""
    peticion_id = peticion_id_actual.get()
    if not peticion_id:
        peticion_id = str(uuid.uuid4())
        peticion_id_actual.set(peticion_id)
    return peticion_id


def construir_meta(paginacion: Optional[dict] = None) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version": VERSION_API,
        "peticion_id": obtener_peticion_id(),
        "paginacion": paginacion,
    }


def respuesta_exitosa(datos: Any = None,
                      mensaje: str = "Operación realizada correctamente.",
                      paginacion: Optional[dict] = None) -> dict:
    """Sobre para respuestas exitosas (200 / 201)."""
    return {
        "exito": True,
        "codigo": "OK",
        "mensaje": mensaje,
        "datos": datos,
        "errores": [],
        "meta": construir_meta(paginacion),
    }


def respuesta_error(codigo: str, mensaje: str,
                    errores: Optional[list[dict]] = None) -> dict:
    """Sobre para respuestas con error. Lo usan los manejadores de app/core/errores.py."""
    return {
        "exito": False,
        "codigo": codigo,
        "mensaje": mensaje,
        "datos": None,
        "errores": errores or [],
        "meta": construir_meta(),
    }


def construir_paginacion(pagina: int, por_pagina: int, total_registros: int) -> dict:
    """Objeto meta.paginacion para las consultas que devuelven listas."""
    return {
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_registros": total_registros,
        "total_paginas": math.ceil(total_registros / por_pagina) if total_registros else 0,
    }



def fecha_iso(valor) -> Optional[str]:
    """
    Formatea fechas según el estándar (ISO 8601, UTC):
      datetime -> "2026-09-14T15:04:32Z"     date -> "2026-09-14"     None -> None
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        if valor.tzinfo is not None:
            valor = valor.astimezone(timezone.utc)
        return valor.strftime("%Y-%m-%dT%H:%M:%SZ")
    return valor.isoformat()
