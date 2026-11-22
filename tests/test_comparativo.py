# tests/test_comparativo.py
# Pruebas unitarias de las reglas de negocio de la HU-16 (RN-056 a RN-060, RN-034,
# solicitud pendiente, filtros y "foto" de las ofertas).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

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
from app.domain.presupuesto import Presupuesto
from app.domain.proveedor import Proveedor
from app.domain.proveedor_material import ProveedorMaterial
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.solicitud import Solicitud, SolicitudDetalle
from app.domain.usuario import Usuario
from app.repositories.comparativo_repository import ComparativoRepository
from app.schemas.comparativo import ComparativoCreate, SeleccionDatos
from app.services.comparativo_service import ComparativoService


def pedir(material_id, solicitud_id=1) -> ComparativoCreate:
    return ComparativoCreate(solicitud_id=solicitud_id, material_id=material_id)


def elegir(proveedor_id, justificacion=None) -> SeleccionDatos:
    return SeleccionDatos(proveedor_id=proveedor_id, justificacion=justificacion)


class PruebaComparativo(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba:
        #   materiales: 1 cemento (2 ofertas), 2 varilla (1 oferta), 3 inactivo,
        #               4 bloque (no está en la solicitud), 5 arena (3 ofertas)
        #   proveedores: 1, 2 y 3 activos; 4 inactivo (su oferta no cuenta)
        #   solicitud 1 pendiente con los materiales 1, 2, 3 y 5; solicitud 2 anulada
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        residente = Usuario(id=1, nombre_completo="Laura Díaz", tipo_documento="CC",
                            numero_documento="100001", correo="laura@construpro.co",
                            telefono="3001234567", contrasena_hash="x",
                            rol=Rol(id=2, nombre="Coordinador"))
        proyecto = Proyecto(id=27, nombre="Torre Cabecera", cliente="Inversiones Andinas S.A.S.",
                            fecha_inicio=date(2026, 11, 1), fecha_fin_estimada=date(2027, 12, 15),
                            responsable=residente, direccion="Cra 27 # 45-10", ciudad="Bucaramanga",
                            presupuesto=Presupuesto(presupuesto_total=250000000,
                                                    fecha_aprobacion=date(2026, 11, 1)))
        cat = Categoria(id=4, nombre="Cementos")

        def material(mid, nombre, unidad="bulto", estado="activo"):
            return Material(id=mid, nombre=nombre, unidad=unidad, categoria=cat,
                            precio_referencia=1000, estado=estado)

        def proveedor(pid, estado="activo"):
            return Proveedor(id=pid, razon_social=f"Proveedor {pid}", nit=f"90012345{pid}-1",
                             contacto="Contacto", telefono="6076543210", correo=f"p{pid}@c.co",
                             estado=estado)

        def oferta(pid, mid, precio, dias, disponible=True):
            return ProveedorMaterial(proveedor_id=pid, material_id=mid, precio=precio,
                                     dias_entrega=dias, disponible=disponible)

        def solicitud(sid, estado, materiales):
            s = Solicitud(id=sid, proyecto=proyecto, solicitante=residente, estado=estado)
            s.detalle = [SolicitudDetalle(material_id=m, cantidad=c) for m, c in materiales]
            return s

        self.db.add_all([
            residente, proyecto,
            material(1, "Cemento gris tipo I 50 kg"), material(2, "Varilla 1/2", "unidad"),
            material(3, "Cemento blanco", estado="inactivo"), material(4, "Bloque #5", "unidad"),
            material(5, "Arena de río", "m3"),
            proveedor(1), proveedor(2), proveedor(3), proveedor(4, "inactivo"),
            oferta(1, 1, 28500, 3), oferta(2, 1, 27900, 5), oferta(4, 1, 20000, 2),
            oferta(1, 2, 32000, 4),
            oferta(1, 3, 40000, 3), oferta(2, 3, 41000, 3),
            oferta(1, 4, 2500, 2), oferta(2, 4, 2400, 2),
            oferta(1, 5, 50000, 3), oferta(2, 5, 48000, 7), oferta(3, 5, 45000, 2, disponible=False),
        ])
        self.db.flush()
        self.db.add_all([
            solicitud(1, "pendiente", [(1, 300), (2, 150), (3, 10), (5, 20)]),
            solicitud(2, "anulada", [(1, 50)]),
        ])
        self.db.commit()
        self.servicio = ComparativoService(ComparativoRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Generar (caso 1) ───────────────────────────────────

    def test_generar_ordena_de_menor_a_mayor_precio(self):
        c = self.servicio.generar(pedir(1))
        self.assertEqual([o.proveedor_id for o in c.ofertas], ["2", "1"])  # el 4 está inactivo
        self.assertEqual([o.precio for o in c.ofertas], [27900.0, 28500.0])
        self.assertEqual((c.precio_minimo, c.precio_maximo), (27900.0, 28500.0))
        self.assertEqual((c.unidad, c.cantidad, c.moneda), ("bulto", 300, "COP"))
        self.assertEqual(c.estado, "abierto")
        self.assertIsNone(c.proveedor_seleccionado_id)

    def test_rn056_un_solo_proveedor(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.generar(pedir(2))
        self.assertEqual(ctx.exception.regla, "RN-056")
        self.assertEqual(ctx.exception.codigo, "NEG_COMPARATIVO_INSUFICIENTE")
        self.assertEqual(ctx.exception.campo, "material_id")

    def test_rn057_material_que_no_esta_en_la_solicitud(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.generar(pedir(4))
        self.assertEqual(ctx.exception.regla, "RN-057")

    def test_rn034_material_inactivo(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.generar(pedir(3))
        self.assertEqual(ctx.exception.regla, "RN-034")

    def test_solicitud_no_pendiente(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.generar(pedir(1, solicitud_id=2))
        self.assertEqual(ctx.exception.campo, "solicitud_id")

    def test_no_se_repite_el_comparativo_del_mismo_material(self):
        self.servicio.generar(pedir(1))
        with self.assertRaises(RecursoDuplicadoError):
            self.servicio.generar(pedir(1))

    def test_solicitud_o_material_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.generar(pedir(1, solicitud_id=999))
        self.assertEqual(ctx.exception.campo, "solicitud_id")
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.generar(pedir(999))
        self.assertEqual(ctx.exception.campo, "material_id")

    def test_el_comparativo_guarda_la_foto_de_las_ofertas(self):
        c = self.servicio.generar(pedir(1))
        self.db.query(ProveedorMaterial).filter_by(proveedor_id=2, material_id=1).update(
            {"precio": 99999})
        self.db.commit()
        self.assertEqual(self.servicio.obtener(int(c.comparativo_id)).precio_minimo, 27900.0)

    # ── Consultar, ordenar y filtrar ───────────────────────

    def test_filtros_disponible_dias_max_y_orden(self):
        c = self.servicio.generar(pedir(5))
        cid = int(c.comparativo_id)
        self.assertEqual([o.proveedor_id for o in c.ofertas], ["3", "2", "1"])
        solo_disp = self.servicio.obtener(cid, disponible=True)
        self.assertEqual([o.proveedor_id for o in solo_disp.ofertas], ["2", "1"])
        rapidos = self.servicio.obtener(cid, dias_max=5)
        self.assertEqual([o.proveedor_id for o in rapidos.ofertas], ["3", "1"])
        por_dias = self.servicio.obtener(cid, orden="dias_entrega")
        self.assertEqual([o.proveedor_id for o in por_dias.ofertas], ["3", "1", "2"])
        self.assertEqual(solo_disp.precio_minimo, 45000.0)  # los filtros no cambian el resumen

    def test_filtros_sin_resultados_devuelven_arreglo_vacio(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        c = self.servicio.obtener(cid, dias_max=1)       # ninguna entrega en 1 día o menos
        self.assertEqual(c.ofertas, [])
        self.assertEqual(c.precio_minimo, 27900.0)

    def test_comparativo_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(999)

    # ── Seleccionar (caso 2, RN-058 a RN-060) ──────────────

    def test_seleccionar_el_mas_barato_guarda_el_ahorro(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        c = self.servicio.seleccionar(cid, elegir(2))
        self.assertEqual(c.estado, "seleccionado")
        self.assertEqual(c.proveedor_seleccionado_id, "2")
        self.assertEqual(c.precio_seleccionado, 27900.0)
        self.assertEqual(c.ahorro, 600.0)               # RN-060: 28500 − 27900
        self.assertEqual(c.ahorro_total, 180000.0)      # 600 × 300 bultos
        self.assertIsNotNone(c.fecha_seleccion)

    def test_rn059_el_mas_caro_exige_justificacion(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        for justificacion in (None, "   "):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.seleccionar(cid, elegir(1, justificacion))
            self.assertEqual(ctx.exception.regla, "RN-059")
        c = self.servicio.seleccionar(cid, elegir(1, "Entrega en 3 días, la obra no puede esperar."))
        self.assertEqual(c.ahorro, 0.0)

    def test_rn058_proveedor_fuera_del_comparativo(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        for proveedor_id in (3, 4):   # 3 no ofrece cemento; 4 está inactivo
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.seleccionar(cid, elegir(proveedor_id))
            self.assertEqual(ctx.exception.regla, "RN-058")

    def test_solo_se_selecciona_una_vez(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        self.servicio.seleccionar(cid, elegir(2))
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.seleccionar(cid, elegir(1, "Cambio de opinión"))

    def test_no_se_selecciona_si_la_solicitud_ya_no_esta_pendiente(self):
        cid = int(self.servicio.generar(pedir(1)).comparativo_id)
        self.db.get(Solicitud, 1).estado = "anulada"
        self.db.commit()
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.seleccionar(cid, elegir(2))


if __name__ == "__main__":
    unittest.main()
    