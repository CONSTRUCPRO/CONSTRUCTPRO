# main.py
# PUNTO DE ENTRADA de ConstruPro. Aquí se crea la aplicación FastAPI y se arma en tres pasos:
#   1. registrar_manejadores(app): todo error (de negocio, de validación o inesperado) sale
#      con el sobre JSON estándar (app/core/errores.py).
#   2. Dos rutas públicas de diagnóstico: "/" y "/health".
#   3. registrar_routers(app): agrega solos todos los routers de app/api/ (cada HU tiene el suyo),
#      así que para sumar un módulo nuevo no hay que tocar este archivo.
# Se ejecuta con:  uvicorn main:app --reload     (o: python main.py)
# Documentación interactiva: /docs (Swagger UI) y /redoc (ReDoc).
from fastapi import FastAPI

from app.api import registrar_routers
from app.core.config import settings
from app.core.errores import registrar_manejadores
from app.core.respuestas import respuesta_exitosa

VERSION = "1.0.0"

# title, description y version aparecen en la documentación de /docs y /redoc
app = FastAPI(
    title=settings.APP_NAME,
    description="API REST de ConstruPro para gestionar el abastecimiento de materiales de obras "
                "de construcción, con arquitectura de capas (api, services, domain, repositories). "
                "Para usar los endpoints protegidos: POST /api/v1/auth/login y luego el botón Authorize.",
    version=VERSION,
)

# Convierte todos los errores al sobre JSON estándar de ConstruPro
registrar_manejadores(app)


# La ruta raíz responde con el sobre estándar (Componente F).
@app.get("/", tags=["Estado del servicio"], summary="Bienvenida")
def raiz():
    """Ruta de bienvenida: confirma que la API está arriba e indica dónde está la documentación."""
    return respuesta_exitosa({"nombre": settings.APP_NAME, "version": VERSION,
                              "documentacion": "/docs"},
                             "ConstruPro está funcionando.")


# /health responde EXACTAMENTE como lo muestra la guía de setup del profesor (paso 8):
#   {"status": "ok", "version": "1.0.0", "environment": "development"}
# Es un chequeo técnico de infraestructura, no una API de negocio, por eso no lleva el sobre.
@app.get("/health", tags=["Estado del servicio"], summary="Verificar que el servicio responde")
def salud():
    """
    Chequeo de salud ("health check"): lo usan quien despliega o monitorea el servicio para
    saber si responde. Es pública (no pide token) y no consulta la base de datos.
    """
    return {"status": "ok", "version": VERSION, "environment": settings.APP_ENV}


# Registra automáticamente todos los routers de app/api/
registrar_routers(app)


# Permite arrancar también con:  python main.py   (igual que uvicorn main:app --reload)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.APP_PORT, reload=True)
