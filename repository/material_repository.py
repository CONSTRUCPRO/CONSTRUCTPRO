# repository/material_repository.py
# CAPA REPOSITORIO: única responsabilidad = guardar y recuperar.
# Sin lógica de negocio aquí (esa va en el servicio).

from typing import Optional
from domain.material import Material


class MaterialRepository:

    # Categorías de ejemplo, hasta que se haga la HU-08 (categorías)
    CATEGORIAS = {
        1: "Agregados",
        2: "Acero",
        3: "Ladrillos y bloques",
        4: "Cemento y cal",
        5: "Pinturas",
    }

    def __init__(self):
        # Almacén en memoria: lista de objetos Material
        self._datos: list[Material] = []
        self._siguiente_id: int = 1

        # Datos de ejemplo para arrancar el sistema
        self._seed()

    def _seed(self):
        """Carga materiales de ejemplo."""
        iniciales = [
            ("Cemento Gris", "bulto", 4, 32000),
            ("Varilla Corrugada 3/8", "unidad", 2, 28500),
            ("Arena de Río", "m3", 1, 85000),
            ("Ladrillo Tolete", "unidad", 3, 950),
            ("Pintura Vinilo Blanco", "galon", 5, 74900),
        ]
        for nombre, unidad, categoria_id, precio in iniciales:
            self.crear(nombre, unidad, categoria_id, precio)

    # ── Consultas ──────────────────────────────────────────

    def listar(self, categoria_id: Optional[int] = None,
               nombre: Optional[str] = None) -> list[Material]:
        resultado = self._datos
        if categoria_id is not None:
            resultado = [m for m in resultado if m.categoria_id == categoria_id]
        if nombre:
            resultado = [m for m in resultado if nombre.lower() in m.nombre.lower()]
        return list(resultado)

    def obtener_por_id(self, id: int) -> Optional[Material]:
        return next((m for m in self._datos if m.id == id), None)

    def existe_duplicado(self, nombre: str, unidad: str, categoria_id: int,
                         excluir_id: Optional[int] = None) -> bool:
        """Apoya la RN-031: mismo nombre + unidad dentro de una categoría."""
        return any(
            m.nombre.lower() == nombre.lower()
            and m.unidad == unidad
            and m.categoria_id == categoria_id
            and m.id != excluir_id
            for m in self._datos
        )

    def categoria_existe(self, categoria_id: int) -> bool:
        return categoria_id in self.CATEGORIAS

    # ── Escritura ──────────────────────────────────────────

    def crear(self, nombre: str, unidad: str, categoria_id: int,
              precio_referencia: float) -> Material:
        nuevo = Material(
            id=self._siguiente_id,
            nombre=nombre,
            unidad=unidad,
            categoria_id=categoria_id,
            precio_referencia=precio_referencia,
        )  # el constructor valida RN-032 y RN-033
        self._datos.append(nuevo)
        self._siguiente_id += 1
        return nuevo

    def actualizar(self, id: int, nombre: str, unidad: str, categoria_id: int,
                   precio_referencia: float) -> Optional[Material]:
        actual = self.obtener_por_id(id)
        if not actual:
            return None
        editado = Material(id, nombre, unidad, categoria_id,
                           precio_referencia, estado=actual.estado)
        self._datos[self._datos.index(actual)] = editado
        return editado


# Instancia única compartida (Singleton simple)
material_repository = MaterialRepository()