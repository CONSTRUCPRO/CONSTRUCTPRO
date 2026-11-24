# app/core/database.py
# CONEXIÓN A LA BASE DE DATOS (SQLAlchemy 2.x).
#   engine        -> la conexión a la BD indicada en DATABASE_URL.
#   SessionLocal  -> "fábrica" de sesiones; una sesión es la conversación con la BD durante
#                    una petición (consultas, cambios y el commit final).
#   Base          -> clase de la que heredan TODOS los modelos de app/domain/ (cada uno es una tabla).
#   get_db        -> dependencia de FastAPI que entrega una sesión a cada petición y la cierra.
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite necesita esto para funcionar con FastAPI (varios hilos)
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

# autocommit=False: nada queda guardado hasta que el repositorio hace commit().
# autoflush=False: SQLAlchemy no manda cambios a la BD por su cuenta antes de cada consulta.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """
    Clase base de la que heredan TODOS los modelos (tablas).

    Al heredar de Base, cada clase de app/domain/ queda registrada en Base.metadata; Alembic
    lee esa metadata para generar las migraciones y las pruebas la usan para crear las tablas
    en una BD en memoria.
    """
    pass


def get_db():
    """
    Dependencia de FastAPI: abre una sesión por petición y la cierra al terminar.

    Se usa así en los routers: `db: Session = Depends(get_db)`. Como es un generador (yield),
    FastAPI ejecuta el bloque finally cuando termina la petición, incluso si hubo un error.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
