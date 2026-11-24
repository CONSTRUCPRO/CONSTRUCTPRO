# app/repositories/sesion_repository.py
# CAPA REPOSITORIO - HU-02: solo guarda y consulta usuarios y sesiones. Sin reglas, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.sesion import Sesion, hash_token
from app.domain.usuario import Usuario


class SesionRepository:
    """
    Acceso a datos de sesiones (y la búsqueda del usuario al hacer login): solo consulta y guarda en la BD.
    No valida reglas de negocio ni sabe de HTTP; eso es del dominio y del servicio.
    """

    def __init__(self, db: Session):
        """
        Recibe la sesión de BD de la petición; todas las consultas de este repositorio la usan.
        """
        self.db = db

    def obtener_usuario_por_correo(self, correo: str) -> Optional[Usuario]:
        """El usuario con ese correo sin importar mayúsculas, o None."""
        return self.db.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.lower()))

    def obtener_sesion(self, sesion_id: int) -> Optional[Sesion]:
        """La sesión con ese id, o None si no existe (db.get busca por llave primaria)."""
        return self.db.get(Sesion, sesion_id)

    def obtener_por_token_renovacion(self, token: str) -> Optional[Sesion]:
        """Busca por el hash del token (el token en sí nunca se guarda)."""
        return self.db.scalar(select(Sesion).where(Sesion.token_renovacion_hash == hash_token(token)))

    def guardar(self, *objetos) -> None:
        """Guarda uno o varios objetos (usuario y sesión) en la misma transacción."""
        for objeto in objetos:
            self.db.add(objeto)
        self.db.commit()
        for objeto in objetos:
            self.db.refresh(objeto)
