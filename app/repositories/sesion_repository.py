# app/repositories/sesion_repository.py
# CAPA REPOSITORIO - HU-02: solo guarda y consulta usuarios y sesiones. Sin reglas, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.sesion import Sesion, hash_token
from app.domain.usuario import Usuario


class SesionRepository:

    def __init__(self, db: Session):
        self.db = db

    def obtener_usuario_por_correo(self, correo: str) -> Optional[Usuario]:
        return self.db.scalar(select(Usuario).where(func.lower(Usuario.correo) == correo.lower()))

    def obtener_sesion(self, sesion_id: int) -> Optional[Sesion]:
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
