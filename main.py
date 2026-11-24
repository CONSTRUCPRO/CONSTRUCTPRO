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
    return respuesta_exitosa({"nombre": settings.APP_NAME, "documentacion": "/docs"},
                             "ConstruPro está funcionando.")


@app.get("/health", tags=["Estado del servicio"], summary="Verificar que el servicio responde")
def salud():
    return respuesta_exitosa({"estado": "ok", "version": "1.0.0", "ambiente": settings.APP_ENV},
                             "El servicio está disponible.")


# Registra automáticamente todos los routers de app/api/
registrar_routers(app)
