# tests/test_presupuesto.py
# Pruebas unitarias de la HU-06 (saldo, RN-023, RN-019) y de los métodos que usarán
# otras HU (RN-066, RN-068, RN-069). BD SQLite en memoria: no tocan dev.db.
# El control de rol (RN-022) está en el router y se prueba de punta a punta en Swagger.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.presupuesto import Presupuesto, formato_cop
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.usuario import Usuario
from app.repositories.presupuesto_repository import PresupuestoRepository
from app.api.schemas.presupuesto import PresupuestoDatos
from app.services.presupuesto_service import PresupuestoService


def monto(valor: float) -> PresupuestoDatos:
    return PresupuestoDatos(presupuesto_total=valor)


class PruebaPresupuesto(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba, con un responsable y dos proyectos
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        director = Usuario(id=1, nombre_completo="Mario Ruiz", tipo_documento="CC",
                           numero_documento="100001", correo="mario@construpro.co",
                           telefono="3001234567", contrasena_hash="x",
                           rol=Rol(id=3, nombre="Director"))

        def proyecto(pid, nombre, estado="activo"):
            return Proyecto(id=pid, nombre=nombre, cliente="Inversiones Andinas S.A.S.",
                            fecha_inicio=date(2026, 11, 1), fecha_fin_estimada=date(2027, 12, 15),
                            responsable=director, estado=estado)

        self.db.add_all([proyecto(27, "Torre Cabecera Etapa 2"),
                         proyecto(28, "Bodega Norte", estado="finalizado")])
        self.db.commit()
        self.servicio = PresupuestoService(PresupuestoRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _comprometer_y_ejecutar(self, comprometido: float, ejecutado: float) -> None:
        """Simula lo que harán la HU-20 (comprometer) y la HU-23 (ejecutar)."""
        p = self.db.get(Proyecto, 27).presupuesto
        p.comprometer(comprometido + ejecutado)
        p.ejecutar(ejecutado)
        self.db.commit()

    # ── Asignar (caso 1) ───────────────────────────────────

    def test_asignar_presupuesto_saldo_igual_al_total(self):
        r = self.servicio.asignar(27, monto(250000000), usuario_id="1")
        self.assertEqual(r.proyecto_id, "27")
        self.assertEqual(r.moneda, "COP")
        self.assertEqual(r.saldo_disponible, 250000000.00)
        self.assertEqual(r.comprometido, 0.0)
        self.assertEqual(r.fecha_aprobacion, date.today().isoformat())

    def test_no_se_asigna_dos_veces(self):
        self.servicio.asignar(27, monto(250000000), None)
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.asignar(27, monto(1000), None)

    def test_monto_debe_ser_mayor_que_cero(self):
        with self.assertRaises(ValidationError):
            monto(0)
        with self.assertRaises(ValidationError):
            monto(-5)

    def test_moneda_solo_cop(self):
        with self.assertRaises(ValidationError):
            PresupuestoDatos(presupuesto_total=1000, moneda="USD")

    def test_proyecto_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.asignar(999, monto(1000), None)

    def test_rn019_proyecto_finalizado_no_recibe_presupuesto(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.asignar(28, monto(1000), None)
        self.assertEqual(ctx.exception.regla, "RN-019")

    # ── Consultar (caso 2) ─────────────────────────────────

    def test_saldo_disponible_cumple_la_formula(self):
        self.servicio.asignar(27, monto(250000000), None)
        self._comprometer_y_ejecutar(comprometido=14815500, ejecutado=30000000)
        r = self.servicio.consultar(27)
        self.assertEqual(r.comprometido, 14815500.00)
        self.assertEqual(r.ejecutado, 30000000.00)
        self.assertEqual(r.saldo_disponible, 205184500.00)
        self.assertEqual(r.saldo_disponible, r.presupuesto_total - r.comprometido - r.ejecutado)

    def test_consultar_sin_presupuesto_es_404(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.consultar(27)

    # ── Actualizar (caso 4, RN-023) ────────────────────────

    def test_actualizar_presupuesto(self):
        self.servicio.asignar(27, monto(250000000), None)
        r = self.servicio.actualizar(27, monto(300000000), "1")
        self.assertEqual(r.presupuesto_total, 300000000.00)
        self.assertEqual(r.saldo_disponible, 300000000.00)

    def test_rn023_no_baja_de_lo_comprometido_y_ejecutado(self):
        self.servicio.asignar(27, monto(250000000), None)
        self._comprometer_y_ejecutar(comprometido=14815500, ejecutado=30000000)
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.actualizar(27, monto(40000000), None)
        self.assertEqual(ctx.exception.regla, "RN-023")
        self.assertEqual(ctx.exception.codigo, "NEG_PRESUPUESTO_INSUFICIENTE")
        self.assertEqual(ctx.exception.mensaje,
                         "El proyecto tiene 44.815.500,00 COP comprometidos y ejecutados.")
        self.assertEqual(self.servicio.consultar(27).presupuesto_total, 250000000.00)

    def test_rn023_si_permite_igualar_lo_comprometido_y_ejecutado(self):
        self.servicio.asignar(27, monto(250000000), None)
        self._comprometer_y_ejecutar(comprometido=14815500, ejecutado=30000000)
        r = self.servicio.actualizar(27, monto(44815500), None)
        self.assertEqual(r.saldo_disponible, 0.0)

    def test_actualizar_sin_presupuesto_es_404(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.actualizar(27, monto(1000), None)

    # ── Métodos para otras HU (RN-066, RN-068, RN-069) ─────

    def test_rn066_compra_no_supera_el_saldo(self):
        p = Presupuesto.asignar(1000000, None)
        p.comprometer(600000)
        with self.assertRaises(ReglaNegocioError) as ctx:
            p.comprometer(500000)                       # saldo 400.000
        self.assertEqual(ctx.exception.regla, "RN-066")
        self.assertEqual(ctx.exception.codigo, "NEG_PRESUPUESTO_INSUFICIENTE")

    def test_rn069_liberar_devuelve_el_saldo(self):
        p = Presupuesto.asignar(1000000, None)
        p.comprometer(600000)
        p.liberar(600000)
        self.assertEqual(float(p.saldo_disponible), 1000000.0)

    def test_ejecutar_pasa_de_comprometido_a_ejecutado(self):
        p = Presupuesto.asignar(1000000, None)
        p.comprometer(600000)
        p.ejecutar(600000)
        self.assertEqual(float(p.comprometido), 0.0)
        self.assertEqual(float(p.ejecutado), 600000.0)
        self.assertEqual(float(p.saldo_disponible), 400000.0)

    def test_formato_colombiano(self):
        self.assertEqual(formato_cop(44815500), "44.815.500,00 COP")


if __name__ == "__main__":
    unittest.main()
