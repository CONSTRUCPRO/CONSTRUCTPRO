# tests/test_aprobacion.py
# Pruebas unitarias de la HU-20 Decisión de Aprobación (RN-066, RN-068, RN-073, RN-076 a RN-079)
# y de su efecto en la cotización (RN-064 de la HU-17). BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date, datetime, timezone

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.comparativo import Comparativo
from app.domain.excepciones import (
    ConflictoEstadoError,
    PermisoDenegadoError,
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
from app.repositories.aprobacion_repository import AprobacionRepository
from app.repositories.cotizacion_repository import CotizacionRepository
from app.api.schemas.aprobacion import DecisionDatos
from app.api.schemas.cotizacion import CotizacionCreate
from app.services.aprobacion_service import AprobacionService
from app.services.cotizacion_service import CotizacionService

# Usuarios: 1 solicitante (Empleado), 2 coordinador que envía la cotización,
#           3 otro coordinador, 4 director, 5 otro director.
SOLICITANTE, ENVIA, COORDINADOR, DIRECTOR, DIRECTOR_2 = "1", "2", "3", "4", "5"


def decision(valor, motivo=None) -> DecisionDatos:
    return DecisionDatos(decision=valor, motivo=motivo)


class PruebaAprobacion(unittest.TestCase):

    def setUp(self):
        # Proyecto 27 (presupuesto 250 millones) y 28 (presupuesto 12 millones).
        # Comparativos seleccionados (proveedor 8):
        #   1: sol 305, material 1, 300 x 28.500 -> total con IVA 10.174.500 (supera el tope de 10 M)
        #   2: sol 305, material 2, 150 x 26.000 -> total con IVA  4.641.000 (dentro del tope)
        #   3: sol 306, material 1, 300 x 28.500 -> total con IVA 10.174.500 (proyecto 28)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        empleado, coordinador, director = (Rol(id=4, nombre="Empleado"), Rol(id=2, nombre="Coordinador"),
                                           Rol(id=3, nombre="Director"))

        def usuario(uid, nombre, rol):
            return Usuario(id=uid, nombre_completo=nombre, tipo_documento="CC", numero_documento=f"10000{uid}",
                           correo=f"u{uid}@construpro.co", telefono="3001234567", contrasena_hash="x", rol=rol)

        usuarios = [usuario(1, "Pedro Obra", empleado), usuario(2, "Carla Díaz", coordinador),
                    usuario(3, "Luis Mora", coordinador), usuario(4, "Mario Ruiz", director),
                    usuario(5, "Ana Pardo", director)]

        def proyecto(pid, presupuesto):
            return Proyecto(id=pid, nombre=f"Proyecto {pid}", cliente="Inversiones Andinas S.A.S.",
                            fecha_inicio=date(2026, 11, 1), fecha_fin_estimada=date(2027, 12, 15),
                            responsable=usuarios[3], direccion="Cra 27", ciudad="Bucaramanga",
                            presupuesto=Presupuesto(presupuesto_total=presupuesto, comprometido=0, ejecutado=0,
                                                    fecha_aprobacion=date(2026, 11, 1)))

        cat = Categoria(id=4, nombre="Cementos")
        self.db.add_all([*usuarios, proyecto(27, 250000000), proyecto(28, 12000000),
                         *[Material(id=i, nombre=f"Material {i}", unidad="bulto", categoria=cat,
                                    precio_referencia=1000) for i in (1, 2)],
                         Proveedor(id=8, razon_social="Ferretería El Constructor", nit="900123456-7",
                                   contacto="C", telefono="6076543210", correo="a@b.co")])
        self.db.flush()
        for sid, pid, lineas in [(305, 27, [(1, 300), (2, 150)]), (306, 28, [(1, 300)])]:
            s = Solicitud(id=sid, proyecto_id=pid, solicitante_id=1, estado="pendiente")
            s.detalle = [SolicitudDetalle(material_id=m, cantidad=c) for m, c in lineas]
            self.db.add(s)
        self.db.flush()
        for cid, sid, mid, cant, precio in [(1, 305, 1, 300, 28500), (2, 305, 2, 150, 26000), (3, 306, 1, 300, 28500)]:
            self.db.add(Comparativo(id=cid, solicitud_id=sid, material_id=mid, unidad="bulto", cantidad=cant,
                                    precio_minimo=precio, precio_maximo=precio, estado="seleccionado",
                                    proveedor_seleccionado_id=8, precio_seleccionado=precio, ahorro=0))
        self.db.commit()
        self.cotizaciones = CotizacionService(CotizacionRepository(self.db))
        self.servicio = AprobacionService(AprobacionRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def enviar(self, comparativo_id: int) -> int:
        """Genera y envía la cotización (HU-17); devuelve el id de la aprobación En revisión."""
        c = self.cotizaciones.generar(CotizacionCreate(comparativo_ids=[comparativo_id]))
        enviada = self.cotizaciones.enviar(int(c.cotizacion_id), ENVIA)
        return int(enviada.aprobacion.aprobacion_id)

    def presupuesto(self, proyecto_id: int) -> Presupuesto:
        return self.db.get(Proyecto, proyecto_id).presupuesto

    # ── Caso 1: el director aprueba ────────────────────────

    def test_director_aprueba_y_se_compromete_el_presupuesto(self):
        aid = self.enviar(1)
        r = self.servicio.decidir(aid, decision("aprobada"), DIRECTOR)
        self.assertEqual(r.estado, "Aprobada")
        self.assertEqual((r.aprobador_id, r.rol_aprobador), (DIRECTOR, "Director"))   # RN-079
        self.assertEqual(r.monto_autorizado, 10174500.00)
        self.assertIsNotNone(r.fecha_decision)
        self.assertIsNone(r.motivo_rechazo)
        self.assertEqual(self.cotizaciones.obtener(1).estado, "Aprobada")
        self.assertEqual(float(self.presupuesto(27).comprometido), 10174500.00)        # RN-068

    # ── Caso 2: rechazo con motivo ─────────────────────────

    def test_rechazo_con_motivo(self):
        aid = self.enviar(2)
        r = self.servicio.decidir(aid, decision("rechazada", "  Entrega muy demorada.  "), COORDINADOR)
        self.assertEqual(r.estado, "Rechazada")
        self.assertEqual(r.motivo_rechazo, "Entrega muy demorada.")
        self.assertIsNone(r.monto_autorizado)
        self.assertEqual(self.cotizaciones.obtener(1).estado, "Rechazada")
        self.assertEqual(float(self.presupuesto(27).comprometido), 0.0)     # nada comprometido

    # ── Caso 3 y RN-076: tope del coordinador ──────────────

    def test_rn076_coordinador_no_supera_el_tope(self):
        aid = self.enviar(1)                                                # 10.174.500 > 10 M
        with self.assertRaises(PermisoDenegadoError) as ctx:
            self.servicio.decidir(aid, decision("aprobada"), COORDINADOR)
        self.assertEqual(ctx.exception.regla, "RN-076")
        self.assertEqual(ctx.exception.campo, "aprobador_id")
        self.assertIn("10.000.000,00 COP", ctx.exception.mensaje)
        self.assertEqual(self.servicio.obtener(aid).estado, "En revisión")

    def test_rn076_coordinador_aprueba_dentro_del_tope(self):
        aid = self.enviar(2)                                                # 4.641.000 <= 10 M
        self.assertEqual(self.servicio.decidir(aid, decision("aprobada"), COORDINADOR).rol_aprobador,
                         "Coordinador")

    # ── Caso 4: RN-077 ─────────────────────────────────────

    def test_rn077_rechazo_sin_motivo(self):
        aid = self.enviar(2)
        for motivo in (None, "   "):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.decidir(aid, decision("rechazada", motivo), DIRECTOR)
            self.assertEqual(ctx.exception.regla, "RN-077")

    # ── Caso 5: RN-078 ─────────────────────────────────────

    def test_rn078_decision_definitiva(self):
        aid = self.enviar(2)
        self.servicio.decidir(aid, decision("aprobada"), DIRECTOR)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.decidir(aid, decision("rechazada", "cambio de opinión"), DIRECTOR_2)
        self.assertEqual(ctx.exception.regla, "RN-078")

    def test_rn078_aprobacion_de_cotizacion_anulada(self):
        aid = self.enviar(2)
        self.cotizaciones.anular(1)                                         # la aprobación queda Anulada
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.decidir(aid, decision("aprobada"), DIRECTOR)

    # ── RN-073: segregación de funciones ───────────────────

    def test_rn073_quien_envio_la_compra_no_la_decide(self):
        aid = self.enviar(2)
        with self.assertRaises(PermisoDenegadoError) as ctx:
            self.servicio.decidir(aid, decision("aprobada"), ENVIA)
        self.assertEqual((ctx.exception.regla, ctx.exception.codigo), ("RN-073", "NEG_SEGREGACION_FUNCIONES"))

    def test_rn073_quien_solicito_los_materiales_no_la_decide(self):
        aid = self.enviar(2)
        with self.assertRaises(PermisoDenegadoError) as ctx:
            self.servicio.decidir(aid, decision("aprobada"), SOLICITANTE)
        self.assertEqual(ctx.exception.codigo, "NEG_SEGREGACION_FUNCIONES")

    # ── RN-066: saldo al aprobar ───────────────────────────

    def test_rn066_no_aprueba_si_ya_no_hay_saldo(self):
        aid = self.enviar(3)                                    # proyecto 28: 10,17 M de 12 M
        self.presupuesto(28).comprometer(5000000)               # otra compra se lleva parte del saldo
        self.db.commit()
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.decidir(aid, decision("aprobada"), DIRECTOR)
        self.assertEqual((ctx.exception.regla, ctx.exception.codigo), ("RN-066", "NEG_PRESUPUESTO_INSUFICIENTE"))
        self.db.rollback()
        self.assertEqual(self.servicio.obtener(aid).estado, "En revisión")

    # ── Efecto en la cotización: RN-064 de la HU-17 ────────

    def test_cotizacion_aprobada_ya_no_se_anula(self):
        aid = self.enviar(2)
        self.servicio.decidir(aid, decision("aprobada"), DIRECTOR)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.cotizaciones.anular(1)
        self.assertEqual(ctx.exception.regla, "RN-064")

    def test_cotizacion_rechazada_si_se_puede_anular(self):
        aid = self.enviar(2)
        self.servicio.decidir(aid, decision("rechazada", "Muy caro"), DIRECTOR)
        self.assertEqual(self.cotizaciones.anular(1).estado, "Anulada")

    # ── Consultas ──────────────────────────────────────────

    def test_listar_en_revision_por_defecto(self):
        self.enviar(1)
        self.enviar(2)
        en_revision, pag = self.servicio.listar(None, None, 1, 20)
        self.assertEqual([a.estado for a in en_revision], ["En revisión", "En revisión"])
        self.assertEqual(pag["total_registros"], 2)
        self.servicio.decidir(2, decision("aprobada"), DIRECTOR)
        self.assertEqual(len(self.servicio.listar(None, 27, 1, 20)[0]), 1)
        self.assertEqual(len(self.servicio.listar("Aprobada", None, 1, 20)[0]), 1)

    def test_historico_solo_decididas_y_filtros(self):
        self.assertEqual(self.servicio.historico(27, None, None, None, 1, 20)[0], [])   # sin datos
        a1, a2, a3 = self.enviar(1), self.enviar(2), self.enviar(3)
        self.servicio.decidir(a1, decision("aprobada"), DIRECTOR)
        self.servicio.decidir(a2, decision("rechazada", "Muy caro"), DIRECTOR_2)
        historico, pag = self.servicio.historico(27, None, None, None, 1, 20)
        self.assertEqual({h.estado for h in historico}, {"Aprobada", "Rechazada"})
        self.assertEqual(pag["total_registros"], 2)                          # a3 sigue En revisión
        solo_director_2, _ = self.servicio.historico(None, 5, None, None, 1, 20)
        self.assertEqual([h.aprobacion_id for h in solo_director_2], [str(a2)])
        hoy = datetime.now(timezone.utc).date()          # la decisión se guarda en UTC
        self.assertEqual(len(self.servicio.historico(None, None, hoy, hoy, 1, 20)[0]), 2)

    def test_aprobacion_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.decidir(999, decision("aprobada"), DIRECTOR)

    def test_decision_invalida(self):
        with self.assertRaises(ValidationError):
            DecisionDatos(decision="tal vez")


if __name__ == "__main__":
    unittest.main()
