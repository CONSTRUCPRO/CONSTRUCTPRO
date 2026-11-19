"""
Manejo global de errores de ConstruPro.

Convierte CUALQUIER error en el sobre JSON estándar:
- Excepciones de negocio (ConstruProError y sus hijas) -> su código HTTP y del catálogo.
- Errores de validación de Pydantic                   -> 422 VAL_CAMPO_REQUERIDO / VAL_FORMATO_INVALIDO
                                                          (400 si el JSON está mal formado).
- Errores HTTP de FastAPI (ruta inexistente, etc.)    -> sobre con el código equivalente.
- Cualquier otro error inesperado                      -> 500 ERR_INTERNO; el detalle va al log,
                                                          nunca al cliente.

Gracias a esto, los routers NO necesitan try/except.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.respuestas import peticion_id_actual, respuesta_error
from app.domain.excepciones import CATALOGO_MENSAJES, ConstruProError

logger = logging.getLogger("construpro")

# Código HTTP -> código del catálogo, para los errores que lanza el propio FastAPI.
_CODIGOS_HTTP = {
    400: "VAL_FORMATO_INVALIDO",
    401: "AUT_CREDENCIALES_INVALIDAS",
    403: "AUT_SIN_PERMISO",
    404: "REC_NO_ENCONTRADO",
}


def _campo_de(loc: tuple) -> str:
    """('body', 'correo') -> 'correo';  ('query', 'pagina') -> 'pagina'."""
    partes = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return ".".join(partes) if partes else "cuerpo"


def registrar_manejadores(app: FastAPI) -> None:
    """Se llama una sola vez desde main.py."""

    @app.middleware("http")
    async def asignar_peticion_id(request: Request, call_next):
        peticion_id = str(uuid.uuid4())
        peticion_id_actual.set(peticion_id)
        respuesta = await call_next(request)
        respuesta.headers["X-Peticion-Id"] = peticion_id
        return respuesta

    @app.exception_handler(ConstruProError)
    async def manejar_error_negocio(request: Request, exc: ConstruProError):
        error = {"campo": exc.campo, "codigo": exc.codigo,
                 "mensaje": exc.mensaje, "regla": exc.regla}
        return JSONResponse(
            status_code=exc.http_status,
            content=respuesta_error(exc.codigo, exc.mensaje_general, [error]),
        )

    @app.exception_handler(RequestValidationError)
    async def manejar_error_validacion(request: Request, exc: RequestValidationError):
        errores = []
        json_mal_formado = False
        for err in exc.errors():
            campo = _campo_de(err.get("loc", ()))
            tipo = err.get("type", "")
            if tipo == "json_invalid":
                json_mal_formado = True
                errores.append({"campo": "cuerpo", "codigo": "VAL_FORMATO_INVALIDO",
                                "mensaje": "El cuerpo de la petición no es un JSON válido.",
                                "regla": None})
            elif tipo == "missing":
                errores.append({"campo": campo, "codigo": "VAL_CAMPO_REQUERIDO",
                                "mensaje": f"El campo '{campo}' es obligatorio.",
                                "regla": None})
            else:
                # Si un validador del schema lanzó ValueError("mensaje en español"),
                # se usa ese mensaje; si no, uno genérico.
                ctx_error = (err.get("ctx") or {}).get("error")
                mensaje = (str(ctx_error) if tipo == "value_error" and ctx_error
                           else f"El campo '{campo}' no tiene un formato válido.")
                errores.append({"campo": campo, "codigo": "VAL_FORMATO_INVALIDO",
                                "mensaje": mensaje, "regla": None})

        return JSONResponse(
            status_code=400 if json_mal_formado else 422,
            content=respuesta_error(errores[0]["codigo"],
                                    "La información enviada contiene errores.", errores),
        )

    @app.exception_handler(StarletteHTTPException)
    async def manejar_error_http(request: Request, exc: StarletteHTTPException):
        codigo = _CODIGOS_HTTP.get(exc.status_code, "VAL_FORMATO_INVALIDO")
        return JSONResponse(
            status_code=exc.status_code,
            content=respuesta_error(codigo, CATALOGO_MENSAJES[codigo]),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def manejar_error_inesperado(request: Request, exc: Exception):
        peticion_id = peticion_id_actual.get()
        logger.exception("Error no controlado. peticion_id=%s ruta=%s %s",
                         peticion_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=respuesta_error("ERR_INTERNO", CATALOGO_MENSAJES["ERR_INTERNO"]),
            headers={"X-Peticion-Id": peticion_id or ""},
        )
