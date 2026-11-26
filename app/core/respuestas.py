"""
Sobre de respuesta estándar de ConstruPro (formato indicado por el docente, issue #54).

Toda respuesta de la API tiene exactamente tres claves, en este orden:
    {"message": ..., "data": ..., "success": true | false}

- Éxito:              data = el registro (o la lista, si no se pagina).
- Consulta paginada:  data = {"registros": [...], "paginacion": {...}}
- Error:              data = {"codigo": "REC_DUPLICADO", "errores": [{campo, codigo, mensaje, regla}]}

Los campos que van DENTRO de data siguen en español y en snake_case (material_id, fecha_registro...).

Uso en un router:
    return respuesta_exitosa(datos=rol, mensaje="Rol creado correctamente.")
"""
import math
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# Identificador de la petición en curso. Lo asigna el middleware de app/core/errores.py, viaja en
# el encabezado X-Peticion-Id y sirve para buscar en el log el detalle de un error.
peticion_id_actual: ContextVar[Optional[str]] = ContextVar("peticion_id_actual", default=None)


def obtener_peticion_id() -> str:
    """Devuelve el id de la petición en curso (o crea uno si no existe)."""
    peticion_id = peticion_id_actual.get()
    if not peticion_id:
        peticion_id = str(uuid.uuid4())
        peticion_id_actual.set(peticion_id)
    return peticion_id


def respuesta_exitosa(datos: Any = None,
                      mensaje: str = "Operación realizada correctamente.",
                      paginacion: Optional[dict] = None) -> dict:
    """
    Sobre para respuestas exitosas (200 / 201).

    Si llega `paginacion` (consultas que devuelven una página de resultados), la lista y la
    paginación se empacan juntas dentro de data: {"registros": [...], "paginacion": {...}}.
    """
    if paginacion is not None:
        datos = {"registros": datos, "paginacion": paginacion}
    return {
        "message": mensaje,
        "data": datos,
        "success": True,
    }


def respuesta_error(codigo: str, mensaje: str,
                    errores: Optional[list[dict]] = None) -> dict:
    """
    Sobre para respuestas con error. Lo usan los manejadores de app/core/errores.py y los
    ejemplos de error de Swagger de cada router.

    `mensaje` es el mensaje general del catálogo (Tabla 57); el detalle de cada problema va en
    data.errores (siempre es un arreglo, aunque esté vacío).
    """
    return {
        "message": mensaje,
        "data": {
            "codigo": codigo,
            "errores": errores or [],
        },
        "success": False,
    }


def construir_paginacion(pagina: int, por_pagina: int, total_registros: int) -> dict:
    """Objeto data.paginacion para las consultas que devuelven listas."""
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
