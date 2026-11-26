# tests/test_material.py
# Pruebas unitarias de las reglas de negocio de la HU-09 (RN-031 a RN-035).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoDuplicadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.material import Categoria, Material
from app.repositories.material_repository import MaterialRepository
from app.api.schemas.material import EstadoUpdate, MaterialCreate, MaterialUpdate, PrecioUpdate
from app.services.material_service import MaterialService


def datos(**cambios) -> MaterialCreate:
    base = {"nombre": "Cemento gris tipo I 50 kg", "unidad": "bulto",
            "categoria_id": 4, "precio_referencia": 28500}
    base.update(cambios)
    return MaterialCreate(**base)


class PruebaMaterial(unittest.TestCase):

    def setUp(self):
        # BD nueva y vacía para cada prueba
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Categoria(id=1, nombre="Agregados"),
            Categoria(id=4, nombre="Cementos"),
            Categoria(id=9, nombre="Descontinuada", estado="inactivo"),
        ])
        self.db.commit()
        self.servicio = MaterialService(MaterialRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Registro ───────────────────────────────────────────

    def test_registrar_material_valido_queda_activo(self):
        m = self.servicio.crear(datos())
        self.assertEqual(m.material_id, "1")
        self.assertEqual(m.estado, "activo")
        self.assertEqual(m.categoria, "Cementos")
        self.assertEqual(m.moneda, "COP")

    # ── RN-031 ─────────────────────────────────────────────

    def test_rn031_no_repite_nombre_y_unidad_en_la_categoria(self):
        self.servicio.crear(datos())
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.crear(datos(nombre="CEMENTO GRIS TIPO I 50 KG"))
        self.assertEqual(ctx.exception.regla, "RN-031")
        self.assertEqual(ctx.exception.codigo, "REC_DUPLICADO")

    def test_rn031_permite_mismo_nombre_con_otra_unidad_o_categoria(self):
        self.servicio.crear(datos())
        self.servicio.crear(datos(unidad="kg"))
        self.servicio.crear(datos(categoria_id=1))
        _, paginacion = self.servicio.listar(None, None, None, 1, 20)
        self.assertEqual(paginacion["total_registros"], 3)

    def test_rn031_editar_no_choca_consigo_mismo_pero_si_con_otro(self):
        self.servicio.crear(datos())
        otro = self.servicio.crear(datos(nombre="Cemento blanco"))
        self.servicio.editar(1, MaterialUpdate(**datos(precio_referencia=29000).model_dump()))
        with self.assertRaises(RecursoDuplicadoError):
            self.servicio.editar(int(otro.material_id), MaterialUpdate(**datos().model_dump()))

    # ── RN-032 ─────────────────────────────────────────────

    def test_rn032_unidad_invalida(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(datos(unidad="caja"))
        self.assertEqual(ctx.exception.regla, "RN-032")
        self.assertEqual(ctx.exception.campo, "unidad")

    def test_rn032_categoria_inexistente_o_inactiva(self):
        for categoria_id in (99, 9):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.crear(datos(categoria_id=categoria_id))
            self.assertEqual(ctx.exception.regla, "RN-032")
            self.assertEqual(ctx.exception.campo, "categoria_id")

    # ── RN-033 ─────────────────────────────────────────────

    def test_rn033_precio_cero_o_negativo_al_registrar(self):
        for precio in (0, -100):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.crear(datos(precio_referencia=precio))
            self.assertEqual(ctx.exception.regla, "RN-033")

    def test_rn033_actualizar_precio_a_cero(self):
        self.servicio.crear(datos())
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.actualizar_precio(1, PrecioUpdate(precio_referencia=0))
        self.assertEqual(ctx.exception.regla, "RN-033")

    def test_actualizar_precio_redondea_a_dos_decimales(self):
        self.servicio.crear(datos())
        m = self.servicio.actualizar_precio(1, PrecioUpdate(precio_referencia=30000.456))
        self.assertEqual(m.precio_referencia, 30000.46)

    # ── RN-034 ─────────────────────────────────────────────

    def test_rn034_material_inactivo_no_esta_disponible(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoUpdate(estado="inactivo"))
        material = self.db.get(Material, 1)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            material.verificar_disponible()
        self.assertEqual(ctx.exception.regla, "RN-034")

    # ── RN-035 ─────────────────────────────────────────────

    def test_rn035_se_inactiva_y_se_puede_reactivar(self):
        self.servicio.crear(datos())
        self.assertEqual(self.servicio.cambiar_estado(1, EstadoUpdate(estado="inactivo")).estado, "inactivo")
        self.assertEqual(self.servicio.cambiar_estado(1, EstadoUpdate(estado="activo")).estado, "activo")

    def test_rn035_inactivar_dos_veces_es_conflicto(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoUpdate(estado="inactivo"))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.cambiar_estado(1, EstadoUpdate(estado="inactivo"))
        self.assertEqual(ctx.exception.regla, "RN-035")

    # ── Consultas y respuesta sin datos ───────────────────────

    def test_material_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(999)

    def test_listar_sin_datos_devuelve_arreglo_vacio(self):
        items, paginacion = self.servicio.listar(4, None, None, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listar_filtra_por_categoria_y_pagina(self):
        for i in range(25):
            self.servicio.crear(datos(nombre=f"Cemento {i}"))
        self.servicio.crear(datos(nombre="Arena", unidad="m3", categoria_id=1))
        items, paginacion = self.servicio.listar(4, None, None, 2, 20)
        self.assertEqual(len(items), 5)
        self.assertTrue(all(m.categoria_id == "4" for m in items))
        self.assertEqual(paginacion["total_registros"], 25)
        self.assertEqual(paginacion["total_paginas"], 2)


if __name__ == "__main__":
    unittest.main()
