import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "CONSTRUCTPRO")
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_DEBUG: bool = os.getenv("APP_DEBUG", "False").lower() == "true"
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

    # HU-02 Autenticación con token (JWT)
    # La clave por defecto solo sirve para desarrollo: en otro ambiente se define en el .env.
    JWT_SECRETO: str = os.getenv("JWT_SECRETO", "clave-de-desarrollo-construpro-cambiar-en-produccion")
    JWT_MINUTOS_ACCESO: int = int(os.getenv("JWT_MINUTOS_ACCESO", "60"))          # RN-008
    DIAS_TOKEN_RENOVACION: int = int(os.getenv("DIAS_TOKEN_RENOVACION", "7"))
    MAX_INTENTOS_FALLIDOS: int = int(os.getenv("MAX_INTENTOS_FALLIDOS", "5"))     # RN-007
    MINUTOS_BLOQUEO: int = int(os.getenv("MINUTOS_BLOQUEO", "15"))                # RN-007


settings = Settings()
