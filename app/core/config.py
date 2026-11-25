# app/core/config.py
# CONFIGURACIÓN CENTRAL. Lee las variables del archivo .env (que no se sube a git) y las deja en
# un solo objeto `settings`. Cualquier archivo hace `from app.core.config import settings` en vez
# de repetir os.getenv. Cada valor tiene uno por defecto pensado para desarrollo; el .env.example
# muestra todas las variables que se pueden cambiar.
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Todas las opciones de la aplicación en un solo lugar.

    - Aplicación: nombre, ambiente (development / production), modo debug y puerto.
    - DATABASE_URL: a qué base de datos conectarse (SQLite en desarrollo).
    - JWT_* y DIAS_TOKEN_RENOVACION: firma y duración de los tokens (HU-02, RN-008).
    - MAX_INTENTOS_FALLIDOS y MINUTOS_BLOQUEO: bloqueo por contraseña errada (RN-007).
    - TOPE_APROBACION_COORDINADOR: monto hasta el que aprueba un Coordinador (RN-076).
    """

    APP_NAME: str = os.getenv("APP_NAME", "CONSTRUCTPRO")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_DEBUG: bool = os.getenv("APP_DEBUG", "False").lower() == "true"
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

    # HU-02 Autenticación con token (JWT)
    # La clave por defecto solo sirve para desarrollo: en otro ambiente se define en el .env.
    # Se aceptan los nombres de la guía de setup del profesor (SECRET_KEY y
    # ACCESS_TOKEN_EXPIRE_MINUTES) y, si no están, los nombres que usamos antes (JWT_SECRETO y
    # JWT_MINUTOS_ACCESO). Así nadie tiene que cambiar su .env.
    JWT_SECRETO: str = (os.getenv("SECRET_KEY") or os.getenv("JWT_SECRETO")
                        or "clave-de-desarrollo-construpro-cambiar-en-produccion")
    JWT_MINUTOS_ACCESO: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
                                  or os.getenv("JWT_MINUTOS_ACCESO") or "60")       # RN-008
    DIAS_TOKEN_RENOVACION: int = int(os.getenv("DIAS_TOKEN_RENOVACION", "7"))
    MAX_INTENTOS_FALLIDOS: int = int(os.getenv("MAX_INTENTOS_FALLIDOS", "5"))     # RN-007
    MINUTOS_BLOQUEO: int = int(os.getenv("MINUTOS_BLOQUEO", "15"))                # RN-007

    # HU-20 Decisión de aprobación (RN-076): por encima de este monto solo aprueba el Director.
    TOPE_APROBACION_COORDINADOR: float = float(os.getenv("TOPE_APROBACION_COORDINADOR", "10000000"))


settings = Settings()
