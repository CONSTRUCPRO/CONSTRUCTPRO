import importlib
import pkgutil

from fastapi import FastAPI


def registrar_routers(aplicacion: FastAPI) -> None:
    """
    Busca todos los módulos dentro de app/api/ y registra
    automáticamente los que tengan una variable llamada `router`.
    """
    for modulo in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{modulo.name}")
        router = getattr(mod, "router", None)
        if router is not None:
            aplicacion.include_router(router)