"""
Manejo global de errores de ConstruPro.

Convierte CUALQUIER error en el sobre JSON estándar {message, data, success}, con success = false
y en data el código del catálogo (data.codigo) y el detalle (data.errores):
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
        """
        Middleware: a cada petición le da un identificador único (peticion_id).

        Ese id viaja en el encabezado X-Peticion-Id de la respuesta; si algo falla, el mismo id
        aparece en el log junto al detalle técnico, así se encuentra el error.
        """
        peticion_id = str(uuid.uuid4())
        peticion_id_actual.set(peticion_id)
        respuesta = await call_next(request)
        respuesta.headers["X-Peticion-Id"] = peticion_id
        return respuesta

    @app.exception_handler(ConstruProError)
    async def manejar_error_negocio(request: Request, exc: ConstruProError):
        """
        Errores de negocio (ConstruProError y sus hijas, lanzadas por el dominio y los servicios).

        Cada excepción ya trae su código HTTP, el código del catálogo, el mensaje, el campo y la
        regla; aquí solo se empacan en el sobre estándar con un elemento en `data.errores`.
        """
        error = {"campo": exc.campo, "codigo": exc.codigo,
                 "mensaje": exc.mensaje, "regla": exc.regla}
        return JSONResponse(
            status_code=exc.http_status,
            content=respuesta_error(exc.codigo, exc.mensaje_general, [error]),
        )

    @app.exception_handler(RequestValidationError)
    async def manejar_error_validacion(request: Request, exc: RequestValidationError):
        """
        Errores de validación de Pydantic (datos de entrada que no cumplen el schema).

        Arma un elemento en `data.errores` por cada campo con problema: VAL_CAMPO_REQUERIDO si falta,
        VAL_FORMATO_INVALIDO si viene mal. Si el JSON ni siquiera se puede leer, responde 400.
        """
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
        """
        Errores HTTP que lanza el propio FastAPI/Starlette, no nuestro código: ruta inexistente
        (404), método no permitido (405), etc. También salen con el sobre estándar.
        """
        codigo = _CODIGOS_HTTP.get(exc.status_code, "VAL_FORMATO_INVALIDO")
        mensaje = CATALOGO_MENSAJES[codigo]
        errores = None
        ruta = f"{request.method} {request.url.path}"
        if exc.status_code == 404:
            # La ruta no existe (los 404 de negocio llegan como ConstruProError, no por aquí)
            errores = [{"campo": "ruta", "codigo": codigo, "regla": None,
                        "mensaje": f"La ruta {ruta} no existe. Consulte /docs."}]
        elif exc.status_code == 405:
            # Método no permitido: por ejemplo DELETE, que no existe porque los registros no
            # se eliminan, se inactivan o anulan (RN-005, RN-035). El catálogo (Tabla 57) no
            # tiene un código propio para esto, así que se usa el de formato con un mensaje claro.
            mensaje = "El método usado no está permitido en esta ruta."
            errores = [{"campo": "metodo", "codigo": codigo, "regla": None,
                        "mensaje": f"{ruta} no está permitido. Consulte /docs para ver los "
                                   f"métodos disponibles en esta ruta."}]
        return JSONResponse(
            status_code=exc.status_code,
            content=respuesta_error(codigo, mensaje, errores),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def manejar_error_inesperado(request: Request, exc: Exception):
        """
        Cualquier error que nadie esperaba (por ejemplo, la BD no responde): 500 ERR_INTERNO.

        Al cliente solo le llega el mensaje amigable del catálogo; el detalle técnico (traceback)
        se escribe en el log con el peticion_id, nunca en la respuesta (Definición de Hecho).
        """
        peticion_id = peticion_id_actual.get()
        logger.exception("Error no controlado. peticion_id=%s ruta=%s %s",
                         peticion_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=respuesta_error("ERR_INTERNO", CATALOGO_MENSAJES["ERR_INTERNO"]),
            headers={"X-Peticion-Id": peticion_id or ""},
        )
