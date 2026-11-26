"""
Esquemas Pydantic (validación de entrada y formato de salida de la API).

Están dentro de la capa API (app/api/schemas), como indica la guía de setup: los schemas definen
qué recibe y qué devuelve cada endpoint, así que pertenecen a la capa que habla HTTP. Los usan
los routers (entrada y response_model) y los servicios (devuelven los XxxResponse).

Convención: un archivo por módulo, por ejemplo:
    app/api/schemas/rol.py       -> RolCreate, RolUpdate, RolResponse
    app/api/schemas/material.py  -> MaterialCreate, MaterialUpdate, MaterialResponse

No registrar nada en este archivo: cada endpoint importa directamente
desde su propio módulo (ej.: from app.api.schemas.material import MaterialCreate).
"""
