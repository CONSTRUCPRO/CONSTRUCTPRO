# main.py
# PUNTO DE ENTRADA de ConstruPro. Aquí se crea la aplicación FastAPI y se arma en tres pasos:
#   1. registrar_manejadores(app): todo error (de negocio, de validación o inesperado) sale
#      con el sobre JSON estándar (app/core/errores.py).
#   2. Dos rutas públicas de diagnóstico: "/" y "/health".
#   3. registrar_routers(app): agrega solos todos los routers de app/api/ (cada HU tiene el suyo),
#      así que para sumar un módulo nuevo no hay que tocar este archivo.
# Se ejecuta con:  uvicorn main:app --reload     (documentación interactiva en /docs)
from fastapi import FastAPI

from app.api import registrar_routers
from app.core.config import settings
from app.core.errores import registrar_manejadores
from app.core.respuestas import respuesta_exitosa


app = FastAPI(title=settings.APP_NAME)

# Convierte todos los errores al sobre JSON estándar de ConstruPro
registrar_manejadores(app)



# Las dos rutas públicas también responden con el sobre estándar (Componente F):
# toda respuesta del sistema tiene la misma forma, incluso las de diagnóstico.
@app.get("/", tags=["Estado del servicio"], summary="Bienvenida")
def raiz():
    """Ruta de bienvenida: confirma que la API está arriba e indica dónde está la documentación."""
    return respuesta_exitosa({"nombre": settings.APP_NAME, "documentacion": "/docs"},
                             "ConstruPro está funcionando.")


@app.get("/health", tags=["Estado del servicio"], summary="Verificar que el servicio responde")
def salud():
    """
    Chequeo de salud ("health check"): lo usan quien despliega o monitorea el servicio para
    saber si responde. Es pública (no pide token) y no consulta la base de datos.
    """
    return respuesta_exitosa({"estado": "ok", "version": "1.0.0", "ambiente": settings.APP_ENV},
                             "El servicio está disponible.")


# Registra automáticamente todos los routers de app/api/
registrar_routers(app)
