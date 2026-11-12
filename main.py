from fastapi import FastAPI

from app.api import registrar_routers
from app.core.config import settings

app = FastAPI(title=settings.APP_NAME)


@app.get("/")
def root():
    return {"message": "CONSTRUCTPRO funcionando"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": settings.APP_ENV,
    }


# Registra automáticamente todos los routers de app/api/
registrar_routers(app)
