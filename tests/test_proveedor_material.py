# tests/test_proveedor_material.py
# Pruebas unitarias de las reglas de negocio de la HU-11 (relación material–proveedor).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.material import Categoria, Material
from app.domain.proveedor import Proveedor
from app.repositories.proveedor_material_repository import ProveedorMaterialRepository
from app.schemas.proveedor_material import OfertaCreate
from app.services.proveedor_material_service import ProveedorMaterialService


def oferta(**cambios) -> OfertaCreate:
    base = {"material_id": 1, "precio": 28500, "disponible": True, "dias_entrega": 3}
    base.update(cambios)
    return OfertaCreate(**base)


class PruebaProveedorMaterial(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba: 1 categoría, 2 materiales (el 2 inactivo)
        # y 3 proveedores (el 3 inactivo).
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        cementos = Categoria(id=4, nombre="Cementos")
        self.db.add_all([
            cementos,
            Material(id=1, nombre="Cemento gris tipo I 50 kg", unidad="bulto",
                     categoria=cementos, precio_referencia=28500),
            Material(id=2, nombre="Cemento blanco", unidad="bulto",
                     categoria=cementos, precio_referencia=40000, estado="inactivo"),
            Proveedor(id=1, razon_social="Ferretería El Constructor S.A.S.", nit="900123456-7",
                      contacto="Carlos Pérez", telefono="6076543210", correo="a@b.co"),
            Proveedor(id=2, razon_social="Distribuidora Santander Ltda.", nit="800987654-1",
                      contacto="Ana Gómez", telefono="6077654321", correo="c@d.co"),
            Proveedor(id=3, razon_social="Proveedor Inactivo", nit="700111222-3",
                      contacto="Luis Ruiz", telefono="6071112222", correo="e@f.co",
                      estado="inactivo"),
        ])
        self.db.commit()
        self.servicio = ProveedorMaterialService(ProveedorMaterialRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Asociar ────────────────────────────────────────────

    def test_asociar_material_registra_la_oferta(self):
        o, creada = self.servicio.asociar(1, oferta())
        self.assertTrue(creada)
        self.assertEqual(o.proveedor_id, "1")
        self.assertEqual(o.material_id, "1")
        self.assertEqual(o.precio, 28500.0)
        self.assertEqual(o.moneda, "COP")
        self.assertEqual(o.dias_entrega, 3)

    def test_asociar_dos_veces_actualiza_la_oferta(self):
        self.servicio.asociar(1, oferta())
        o, creada = self.servicio.asociar(1, oferta(precio=27000.456, dias_entrega=5,
                                                    disponible=False))
        self.assertFalse(creada)
        self.assertEqual(o.precio, 27000.46)
        self.assertEqual(o.dias_entrega, 5)
        self.assertFalse(o.disponible)
        items, paginacion = self.servicio.proveedores_de_material(1, 1, 20)
        self.assertEqual(paginacion["total_registros"], 1)  # no se duplicó

    # ── RN-038 ─────────────────────────────────────────────

    def test_rn038_precio_cero_o_negativo(self):
        for precio in (0, -100):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.asociar(1, oferta(precio=precio))
            self.assertEqual(ctx.exception.regla, "RN-038")
            self.assertEqual(ctx.exception.campo, "precio")
            self.assertEqual(ctx.exception.codigo, "VAL_FORMATO_INVALIDO")

    def test_rn038_tambien_al_actualizar_la_oferta(self):
        self.servicio.asociar(1, oferta())
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.asociar(1, oferta(precio=-100))
        self.assertEqual(ctx.exception.regla, "RN-038")

    # ── Solo materiales y proveedores activos ──────────────

    def test_no_asocia_a_proveedor_inactivo(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.asociar(3, oferta())
        self.assertEqual(ctx.exception.campo, "proveedor_id")

    def test_no_asocia_material_inactivo(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.asociar(1, oferta(material_id=2))
        self.assertEqual(ctx.exception.campo, "material_id")

    def test_proveedor_o_material_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.asociar(99, oferta())
        self.assertEqual(ctx.exception.campo, "proveedor_id")
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.asociar(1, oferta(material_id=999))
        self.assertEqual(ctx.exception.campo, "material_id")

    # ── Consulta por material ──────────────────────────────

    def test_consulta_devuelve_los_proveedores_del_material(self):
        self.servicio.asociar(1, oferta(precio=28500, dias_entrega=3))
        self.servicio.asociar(2, oferta(precio=27900, dias_entrega=5))
        items, paginacion = self.servicio.proveedores_de_material(1, 1, 20)
        self.assertEqual(len(items), 2)
        self.assertEqual([p.proveedor_id for p in items], ["1", "2"])
        self.assertEqual(items[1].precio, 27900.0)
        self.assertEqual(items[1].dias_entrega, 5)
        self.assertEqual(paginacion["total_registros"], 2)

    def test_consulta_solo_muestra_proveedores_activos(self):
        self.servicio.asociar(1, oferta())
        self.servicio.asociar(2, oferta())
        self.db.get(Proveedor, 2).estado = "inactivo"   # se inactiva después de asociar
        self.db.commit()
        items, _ = self.servicio.proveedores_de_material(1, 1, 20)
        self.assertEqual([p.proveedor_id for p in items], ["1"])

    def test_consulta_material_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.proveedores_de_material(999, 1, 20)

    def test_consulta_sin_proveedores_devuelve_arreglo_vacio(self):
        items, paginacion = self.servicio.proveedores_de_material(1, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)


if __name__ == "__main__":
    unittest.main()
