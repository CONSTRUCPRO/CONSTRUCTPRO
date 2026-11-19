"""
Esquemas Pydantic (validación de entrada y formato de salida de la API).

Convención: un archivo por módulo, por ejemplo:
    app/schemas/rol.py       -> RolCreate, RolUpdate, RolResponse
    app/schemas/material.py  -> MaterialCreate, MaterialUpdate, MaterialResponse

No registrar nada en este archivo: cada endpoint importa directamente
desde su propio módulo (ej.: from app.schemas.material import MaterialCreate).
"""
