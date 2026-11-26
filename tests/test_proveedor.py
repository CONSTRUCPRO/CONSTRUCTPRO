# tests/test_proveedor.py
# Pruebas unitarias de las reglas de negocio de la HU-10 (RN-036, RN-039, RN-040
# y formato de NIT, teléfono y correo).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoDuplicadoError,
    RecursoNoEncontradoError,
)
from app.domain.proveedor import Proveedor
from app.repositories.proveedor_repository import ProveedorRepository
from app.api.schemas.proveedor import EstadoProveedorUpdate, ProveedorCreate, ProveedorUpdate
from app.services.proveedor_service import ProveedorService


def datos(**cambios) -> ProveedorCreate:
    base = {"razon_social": "Ferretería El Constructor S.A.S.", "nit": "900123456-7",
            "contacto": "Carlos Pérez", "telefono": "6076543210",
            "correo": "ventas@elconstructor.co"}
    base.update(cambios)
    return ProveedorCreate(**base)


class RepositorioConOrdenesAbiertas(ProveedorRepository):
    """Simula que el proveedor tiene una orden 'emitida' (la tabla llega con la HU-21)."""

    def contar_ordenes_abiertas(self, proveedor_id: int) -> int:
        return 1


class PruebaProveedor(unittest.TestCase):

    def setUp(self):
        # BD nueva y vacía para cada prueba
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.servicio = ProveedorService(ProveedorRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Registro ───────────────────────────────────────────

    def test_registrar_proveedor_valido_queda_activo(self):
        p = self.servicio.crear(datos())
        self.assertEqual(p.proveedor_id, "1")
        self.assertEqual(p.estado, "activo")
        self.assertEqual(p.nit, "900123456-7")
        self.assertIsNone(p.fecha_actualizacion)

    # ── RN-036 ─────────────────────────────────────────────

    def test_rn036_nit_repetido(self):
        self.servicio.crear(datos())
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.crear(datos(razon_social="Otra empresa", nit="900.123.456-7"))
        self.assertEqual(ctx.exception.regla, "RN-036")
        self.assertEqual(ctx.exception.campo, "nit")
        self.assertEqual(ctx.exception.codigo, "REC_DUPLICADO")

    def test_rn036_editar_no_choca_consigo_mismo_pero_si_con_otro(self):
        self.servicio.crear(datos())
        otro = self.servicio.crear(datos(nit="800987654-1"))
        editado = self.servicio.editar(1, ProveedorUpdate(**datos(contacto="Ana Gómez").model_dump()))
        self.assertEqual(editado.contacto, "Ana Gómez")
        with self.assertRaises(RecursoDuplicadoError):
            self.servicio.editar(int(otro.proveedor_id), ProveedorUpdate(**datos().model_dump()))

    # ── Formato de NIT, teléfono y correo ──────────────────

    def test_formato_correo_invalido(self):
        for correo in ("ventas", "ventas@", "ventas@dominio", "ven tas@dominio.co"):
            with self.assertRaises(ValidationError):
                datos(correo=correo)

    def test_formato_telefono_invalido(self):
        for telefono in ("123", "60765abc10", "1234567890123456"):
            with self.assertRaises(ValidationError):
                datos(telefono=telefono)

    def test_formato_nit_invalido(self):
        for nit in ("900123456", "abc-1", "900123456-77"):
            with self.assertRaises(ValidationError):
                datos(nit=nit)

    def test_normaliza_nit_telefono_y_correo(self):
        d = datos(nit="900.123.456-7", telefono="(607) 654-3210", correo=" Ventas@ElConstructor.co ")
        self.assertEqual(d.nit, "900123456-7")
        self.assertEqual(d.telefono, "6076543210")
        self.assertEqual(d.correo, "ventas@elconstructor.co")

    # ── RN-040 ─────────────────────────────────────────────

    def test_rn040_inactivar_sin_ordenes_abiertas(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        self.assertEqual(self.servicio.obtener(1).estado, "inactivo")

    def test_rn040_no_inactiva_con_ordenes_abiertas(self):
        self.servicio.crear(datos())
        servicio = ProveedorService(RepositorioConOrdenesAbiertas(self.db))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        self.assertEqual(ctx.exception.regla, "RN-040")
        self.assertEqual(self.servicio.obtener(1).estado, "activo")

    def test_reactivar_proveedor_inactivo(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="activo"))
        self.assertEqual(self.servicio.obtener(1).estado, "activo")

    def test_inactivar_dos_veces_es_conflicto(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))

    # ── RN-039 ─────────────────────────────────────────────

    def test_rn039_proveedor_inactivo_no_recibe_ordenes(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        proveedor = self.db.get(Proveedor, 1)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            proveedor.verificar_puede_recibir_ordenes()
        self.assertEqual(ctx.exception.regla, "RN-039")

    # ── Consultas y respuesta sin datos ───────────────────────

    def test_proveedor_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(999)

    def test_listar_sin_datos_devuelve_arreglo_vacio(self):
        items, paginacion = self.servicio.listar("activo", None, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listar_filtra_por_estado_y_pagina(self):
        for i in range(25):
            self.servicio.crear(datos(nit=f"9001234{i:02d}-1"))
        self.servicio.cambiar_estado(1, EstadoProveedorUpdate(estado="inactivo"))
        items, paginacion = self.servicio.listar("activo", None, 2, 20)
        self.assertEqual(len(items), 4)
        self.assertTrue(all(p.estado == "activo" for p in items))
        self.assertEqual(paginacion["total_registros"], 24)
        self.assertEqual(paginacion["total_paginas"], 2)


if __name__ == "__main__":
    unittest.main()
