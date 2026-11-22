# tests/test_cotizacion.py
# Pruebas unitarias de las reglas de negocio de la HU-17 (RN-061 a RN-066 y aprobación En revisión).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.aprobacion import Aprobacion
from app.domain.comparativo import Comparativo
from app.domain.cotizacion import Cotizacion, hoy_utc
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.material import Categoria, Material
from app.domain.presupuesto import Presupuesto
from app.domain.proveedor import Proveedor
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.solicitud import Solicitud, SolicitudDetalle
from app.domain.usuario import Usuario
from app.repositories.cotizacion_repository import CotizacionRepository
from app.schemas.cotizacion import CotizacionCreate
from app.services.cotizacion_service import CotizacionService


def con(*ids) -> CotizacionCreate:
    return CotizacionCreate(comparativo_ids=list(ids))


class PruebaCotizacion(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba:
        #   proyecto 27 (presupuesto 250 millones) y proyecto 28 (presupuesto 10 millones)
        #   solicitud 305 (proyecto 27, pendiente), 306 (proyecto 28, pendiente), 307 (anulada)
        #   comparativos:
        #     1: sol 305, material 1, proveedor 8, 300 × 28.500   (seleccionado)
        #     2: sol 305, material 2, proveedor 8, 150 × 26.000   (seleccionado)
        #     3: sol 305, material 3, proveedor 11, 10 × 1.000    (otro proveedor)
        #     4: sol 306, material 1, proveedor 8, 1000 × 28.500  (otro proyecto, sin saldo)
        #     5: sol 305, material 4, sin seleccionar
        #     6: sol 307, material 1, proveedor 8                 (solicitud anulada)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        usuario = Usuario(id=1, nombre_completo="Carla Díaz", tipo_documento="CC",
                          numero_documento="100001", correo="carla@construpro.co",
                          telefono="3001234567", contrasena_hash="x",
                          rol=Rol(id=2, nombre="Coordinador"))

        def proyecto(pid, presupuesto):
            return Proyecto(id=pid, nombre=f"Proyecto {pid}", cliente="Inversiones Andinas S.A.S.",
                            fecha_inicio=date(2026, 11, 1), fecha_fin_estimada=date(2027, 12, 15),
                            responsable=usuario, direccion="Cra 27", ciudad="Bucaramanga",
                            presupuesto=Presupuesto(presupuesto_total=presupuesto,
                                                    fecha_aprobacion=date(2026, 11, 1)))

        cat = Categoria(id=4, nombre="Cementos")
        materiales = [Material(id=i, nombre=f"Material {i}", unidad="bulto", categoria=cat,
                               precio_referencia=1000) for i in (1, 2, 3, 4)]

        def solicitud(sid, pid, estado, materiales_):
            s = Solicitud(id=sid, proyecto_id=pid, solicitante=usuario, estado=estado)
            s.detalle = [SolicitudDetalle(material_id=m, cantidad=c) for m, c in materiales_]
            return s

        def comparativo(cid, sid, mid, cantidad, proveedor=None, precio=None):
            return Comparativo(id=cid, solicitud_id=sid, material_id=mid, unidad="bulto",
                               cantidad=cantidad, precio_minimo=precio or 1, precio_maximo=precio or 1,
                               estado="seleccionado" if proveedor else "abierto",
                               proveedor_seleccionado_id=proveedor, precio_seleccionado=precio,
                               ahorro=0 if proveedor else None)

        self.db.add_all([usuario, proyecto(27, 250000000), proyecto(28, 10000000), *materiales,
                         Proveedor(id=8, razon_social="Ferretería El Constructor", nit="900123456-7",
                                   contacto="C", telefono="6076543210", correo="a@b.co"),
                         Proveedor(id=11, razon_social="Distribuidora Santander", nit="800987654-1",
                                   contacto="D", telefono="6076543211", correo="c@d.co")])
        self.db.flush()
        self.db.add_all([
            solicitud(305, 27, "pendiente", [(1, 300), (2, 150), (3, 10), (4, 5)]),
            solicitud(306, 28, "pendiente", [(1, 1000)]),
            solicitud(307, 27, "anulada", [(1, 5)]),
        ])
        self.db.flush()
        self.db.add_all([
            comparativo(1, 305, 1, 300, 8, 28500), comparativo(2, 305, 2, 150, 8, 26000),
            comparativo(3, 305, 3, 10, 11, 1000), comparativo(4, 306, 1, 1000, 8, 28500),
            comparativo(5, 305, 4, 5), comparativo(6, 307, 1, 5, 8, 28500),
        ])
        self.db.commit()
        self.servicio = CotizacionService(CotizacionRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Generar (caso 1, RN-062 y RN-063) ─────────────────

    def test_generar_calcula_subtotal_iva_y_total(self):
        c = self.servicio.generar(con(1, 2))
        self.assertEqual(c.estado, "Generada")
        self.assertEqual((c.proyecto_id, c.proveedor_id), ("27", "8"))
        self.assertEqual([(d.material_id, d.cantidad, d.precio_unitario, d.subtotal) for d in c.detalle],
                         [("1", 300, 28500.0, 8550000.0), ("2", 150, 26000.0, 3900000.0)])
        self.assertEqual(c.subtotal, 12450000.0)
        self.assertEqual(c.impuestos, 2365500.0)        # 19 %
        self.assertEqual(c.total, c.subtotal + c.impuestos)
        self.assertEqual(c.vigente_hasta, (hoy_utc() + timedelta(days=15)).isoformat())
        self.assertIsNone(c.aprobacion)

    def test_rn061_un_solo_proveedor_y_un_solo_proyecto(self):
        for ids in ((1, 3), (1, 4)):    # 3: otro proveedor; 4: otro proyecto
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.generar(con(*ids))
            self.assertEqual(ctx.exception.regla, "RN-061")

    def test_rn063_comparativo_sin_seleccionar_o_con_solicitud_no_pendiente(self):
        for cid in (5, 6):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.generar(con(cid))
            self.assertEqual(ctx.exception.regla, "RN-063")

    def test_un_comparativo_no_va_en_dos_cotizaciones_activas(self):
        primera = self.servicio.generar(con(1, 2))
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.generar(con(2))
        self.servicio.anular(int(primera.cotizacion_id))
        self.assertEqual(self.servicio.generar(con(2)).estado, "Generada")  # anulada: se libera

    def test_comparativo_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.generar(con(1, 999))

    # ── Enviar (caso 2, RN-065 y RN-066) ──────────────────

    def test_enviar_crea_la_aprobacion_en_revision(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        c = self.servicio.enviar(cid, usuario_id="1")
        self.assertEqual(c.estado, "Enviada")
        self.assertEqual(c.aprobacion.estado, "En revisión")
        self.assertEqual(c.aprobacion.monto, c.total)
        self.assertEqual(self.db.get(Aprobacion, 1).enviado_por_id, 1)

    def test_rn065_cotizacion_vencida_no_se_envia(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        self.db.get(Cotizacion, cid).vigente_hasta = hoy_utc() - timedelta(days=1)
        self.db.commit()
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.enviar(cid, usuario_id="1")
        self.assertEqual(ctx.exception.regla, "RN-065")

    def test_rn066_total_mayor_que_el_saldo(self):
        cid = int(self.servicio.generar(con(4)).cotizacion_id)   # 33,9 millones vs 10 millones
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.enviar(cid, usuario_id="1")
        self.assertEqual(ctx.exception.codigo, "NEG_PRESUPUESTO_INSUFICIENTE")
        self.assertEqual(self.servicio.obtener(cid).estado, "Generada")

    def test_solo_se_envia_una_vez(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        self.servicio.enviar(cid, usuario_id="1")
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.enviar(cid, usuario_id="1")

    # ── Anular (caso 3, RN-064) ───────────────────────────

    def test_rn064_no_se_anula_una_cotizacion_aprobada(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        self.db.get(Cotizacion, cid).estado = "Aprobada"           # lo hará la HU-20
        self.db.commit()
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.anular(cid)
        self.assertEqual(ctx.exception.regla, "RN-064")
        self.assertEqual(ctx.exception.codigo, "NEG_COTIZACION_APROBADA")
        self.assertEqual(ctx.exception.mensaje_general,
                         "La cotización ya fue aprobada y no puede anularse.")

    def test_anular_una_enviada_cancela_su_aprobacion(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        self.servicio.enviar(cid, usuario_id="1")
        c = self.servicio.anular(cid)
        self.assertEqual(c.estado, "Anulada")
        self.assertEqual(c.aprobacion.estado, "Anulada")

    def test_no_se_anula_dos_veces(self):
        cid = int(self.servicio.generar(con(1, 2)).cotizacion_id)
        self.servicio.anular(cid)
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.anular(cid)

    # ── Consultas y respuesta sin datos ───────────────────

    def test_cotizacion_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(1042)

    def test_listar_sin_datos_devuelve_arreglo_vacio(self):
        items, paginacion = self.servicio.listar(27, None, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listar_filtra_por_proyecto_y_estado(self):
        self.servicio.generar(con(1, 2))
        self.servicio.generar(con(4))
        items, paginacion = self.servicio.listar(27, "generada", 1, 20)
        self.assertEqual([c.proyecto_id for c in items], ["27"])
        self.assertEqual(paginacion["total_registros"], 1)


if __name__ == "__main__":
    unittest.main()
