# tests/test_solicitud.py
# Pruebas unitarias de las reglas de negocio de la HU-12 (RN-041, RN-020, RN-021, RN-034,
# RN-042, RN-043, RN-044 y estado pendiente).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    NoAutenticadoError,
    PermisoDenegadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.material import Categoria, Material
from app.domain.presupuesto import Presupuesto
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.usuario import Usuario
from app.repositories.solicitud_repository import SolicitudRepository
from app.api.schemas.solicitud import SolicitudCreate, SolicitudUpdate
from app.services.solicitud_service import SolicitudService


def nueva(proyecto_id=27, detalle=None) -> SolicitudCreate:
    if detalle is None:
        detalle = [{"material_id": 1, "cantidad": 300}, {"material_id": 2, "cantidad": 150}]
    return SolicitudCreate(proyecto_id=proyecto_id, detalle=detalle)


def cambio(detalle) -> SolicitudUpdate:
    return SolicitudUpdate(detalle=detalle)


class PruebaSolicitud(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba:
        #   usuarios: 1 responsable del proyecto, 2 residente (solicitante), 3 otro, 4 inactivo
        #   proyectos: 27 listo; 28 suspendido; 29 sin ubicación; 30 sin presupuesto
        #   materiales: 1 y 2 activos, 3 inactivo
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        coordinador = Rol(id=2, nombre="Coordinador")

        def usuario(uid, nombre, estado="activo"):
            return Usuario(id=uid, nombre_completo=nombre, tipo_documento="CC",
                           numero_documento=f"10000{uid}", correo=f"u{uid}@construpro.co",
                           telefono="3001234567", contrasena_hash="x", rol=coordinador,
                           estado=estado)

        responsable, residente = usuario(1, "Mario Ruiz"), usuario(2, "Laura Díaz")

        def proyecto(pid, estado="activo", ubicacion=True, presupuesto=True):
            p = Proyecto(id=pid, nombre=f"Proyecto {pid}", cliente="Inversiones Andinas S.A.S.",
                         fecha_inicio=date(2026, 11, 1), fecha_fin_estimada=date(2027, 12, 15),
                         responsable=responsable, estado=estado)
            if ubicacion:
                p.direccion, p.ciudad = "Cra 27 # 45-10", "Bucaramanga"
            if presupuesto:
                p.presupuesto = Presupuesto(presupuesto_total=250000000,
                                            fecha_aprobacion=date(2026, 11, 1))
            return p

        cementos = Categoria(id=4, nombre="Cementos")
        acero = Categoria(id=2, nombre="Acero")
        self.db.add_all([
            responsable, residente, usuario(3, "Pedro Gil"), usuario(4, "Ana Inactiva", "inactivo"),
            proyecto(27), proyecto(28, estado="suspendido"),
            proyecto(29, ubicacion=False), proyecto(30, presupuesto=False),
            Material(id=1, nombre="Cemento gris tipo I 50 kg", unidad="bulto",
                     categoria=cementos, precio_referencia=28500),
            Material(id=2, nombre='Varilla corrugada 1/2" x 6 m', unidad="unidad",
                     categoria=acero, precio_referencia=32000),
            Material(id=3, nombre="Cemento blanco", unidad="bulto", categoria=cementos,
                     precio_referencia=40000, estado="inactivo"),
        ])
        self.db.commit()
        self.servicio = SolicitudService(SolicitudRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Crear (caso 1) ─────────────────────────────────────

    def test_crear_solicitud_queda_pendiente_con_dos_lineas(self):
        s = self.servicio.crear(nueva(), usuario_id="2")
        self.assertEqual(s.solicitud_id, "1")
        self.assertEqual(s.estado, "pendiente")
        self.assertEqual(s.solicitante_id, "2")
        self.assertEqual(s.proyecto_id, "27")
        self.assertEqual(len(s.detalle), 2)
        self.assertEqual(s.detalle[0].nombre, "Cemento gris tipo I 50 kg")
        self.assertEqual(s.detalle[0].unidad, "bulto")
        self.assertEqual(s.detalle[1].cantidad, 150)

    def test_crear_sin_usuario_o_con_usuario_inactivo(self):
        for usuario_id in (None, "abc", "99", "4"):
            with self.assertRaises(NoAutenticadoError):
                self.servicio.crear(nueva(), usuario_id=usuario_id)

    # ── RN-041, RN-020, RN-021 (proyecto) ─────────────────

    def test_rn041_proyecto_suspendido(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(nueva(proyecto_id=28), usuario_id="2")
        self.assertEqual(ctx.exception.regla, "RN-041")
        self.assertEqual(ctx.exception.codigo, "NEG_PROYECTO_NO_ACTIVO")

    def test_rn020_y_rn021_proyecto_sin_ubicacion_o_presupuesto(self):
        for proyecto_id, regla in ((29, "RN-020"), (30, "RN-021")):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.crear(nueva(proyecto_id=proyecto_id), usuario_id="2")
            self.assertEqual(ctx.exception.regla, regla)

    def test_proyecto_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.crear(nueva(proyecto_id=999), usuario_id="2")
        self.assertEqual(ctx.exception.campo, "proyecto_id")

    # ── RN-042, RN-043, RN-034 (detalle) ──────────────────

    def test_rn042_sin_lineas_o_cantidad_cero(self):
        for detalle in ([], [{"material_id": 1, "cantidad": 0}],
                        [{"material_id": 1, "cantidad": 10}, {"material_id": 2, "cantidad": -5}]):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.crear(nueva(detalle=detalle), usuario_id="2")
            self.assertEqual(ctx.exception.regla, "RN-042")

    def test_rn043_material_repetido(self):
        detalle = [{"material_id": 1, "cantidad": 300}, {"material_id": 1, "cantidad": 20}]
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(nueva(detalle=detalle), usuario_id="2")
        self.assertEqual(ctx.exception.regla, "RN-043")
        self.assertEqual(ctx.exception.campo, "detalle.1.material_id")

    def test_rn034_material_inactivo_o_inexistente(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.crear(nueva(detalle=[{"material_id": 3, "cantidad": 5}]), usuario_id="2")
        self.assertEqual(ctx.exception.regla, "RN-034")
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.crear(nueva(detalle=[{"material_id": 999, "cantidad": 5}]), usuario_id="2")

    # ── Editar (RN-044 y pendiente) ───────────────────────

    def test_editar_por_el_solicitante_reemplaza_el_detalle(self):
        self.servicio.crear(nueva(), usuario_id="2")
        s = self.servicio.editar(1, cambio([{"material_id": 1, "cantidad": 320}]), usuario_id="2")
        self.assertEqual([(d.material_id, d.cantidad) for d in s.detalle], [("1", 320)])
        self.assertIsNotNone(s.fecha_actualizacion)

    def test_editar_por_el_responsable_del_proyecto(self):
        self.servicio.crear(nueva(), usuario_id="2")
        s = self.servicio.editar(1, cambio([{"material_id": 2, "cantidad": 10},
                                            {"material_id": 1, "cantidad": 5}]), usuario_id="1")
        self.assertEqual(sorted((d.material_id, d.cantidad) for d in s.detalle),
                         [("1", 5), ("2", 10)])

    def test_rn044_otro_usuario_no_puede_editar_ni_anular(self):
        self.servicio.crear(nueva(), usuario_id="2")
        with self.assertRaises(PermisoDenegadoError) as ctx:
            self.servicio.editar(1, cambio([{"material_id": 1, "cantidad": 1}]), usuario_id="3")
        self.assertEqual(ctx.exception.regla, "RN-044")
        with self.assertRaises(PermisoDenegadoError):
            self.servicio.anular(1, usuario_id="3")

    def test_rn042_y_rn043_tambien_al_editar(self):
        self.servicio.crear(nueva(), usuario_id="2")
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.editar(1, cambio([]), usuario_id="2")
        self.assertEqual(ctx.exception.regla, "RN-042")
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.editar(1, cambio([{"material_id": 2, "cantidad": 1},
                                            {"material_id": 2, "cantidad": 2}]), usuario_id="2")
        self.assertEqual(ctx.exception.regla, "RN-043")

    # ── Anular (caso 2) ───────────────────────────────────

    def test_anular_solicitud_pendiente(self):
        self.servicio.crear(nueva(), usuario_id="2")
        s = self.servicio.anular(1, usuario_id="2")
        self.assertEqual(s.estado, "anulada")

    def test_no_se_edita_ni_anula_si_no_esta_pendiente(self):
        self.servicio.crear(nueva(), usuario_id="2")
        self.servicio.anular(1, usuario_id="2")
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.editar(1, cambio([{"material_id": 1, "cantidad": 1}]), usuario_id="2")
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.anular(1, usuario_id="1")

    # ── Consultas y respuesta sin datos ───────────────────

    def test_solicitud_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(999)

    def test_listar_sin_datos_devuelve_arreglo_vacio(self):
        items, paginacion = self.servicio.listar(27, None, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listar_filtra_por_estado(self):
        self.servicio.crear(nueva(), usuario_id="2")
        self.servicio.crear(nueva(), usuario_id="2")
        self.servicio.anular(1, usuario_id="2")
        items, paginacion = self.servicio.listar(27, "pendiente", 1, 20)
        self.assertEqual([s.solicitud_id for s in items], ["2"])
        self.assertEqual(paginacion["total_registros"], 1)


if __name__ == "__main__":
    unittest.main()
