# app/api/__init__.py
# REGISTRO AUTOMÁTICO DE ROUTERS. Cada HU tiene su archivo <modulo>_router.py con una variable
# `router`. En vez de importarlos uno por uno en main.py (y chocar entre los dos cuando cada uno
# agregaba el suyo), esta función recorre la carpeta y registra todos los que encuentre.
import importlib
import pkgutil

from fastapi import FastAPI


def registrar_routers(aplicacion: FastAPI) -> None:
    """
    Busca todos los módulos dentro de app/api/ y registra automáticamente los que tengan
    una variable llamada `router`.

    pkgutil.iter_modules lista los archivos .py de esta carpeta, importlib los importa por
    nombre y include_router los conecta a la aplicación con sus rutas y su documentación.
    """
    for modulo in pkgutil.iter_modules(__path__):
        mod = importlib.import_module(f"{__name__}.{modulo.name}")
        router = getattr(mod, "router", None)
        if router is not None:
            aplicacion.include_router(router)