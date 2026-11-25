# tests/test_pago.py
# Pruebas unitarias de las reglas de negocio de la HU-23 (RN-091 a RN-095, presupuesto y RN-084).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.aprobacion import Aprobacion
from app.domain.cotizacion import Cotizacion
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.orden_compra import OrdenCompra
from app.domain.pago import Pago, hoy_colombia
from app.domain.presupuesto import Presupuesto
from app.domain.proveedor import Proveedor
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.usuario import Usuario
from app.repositories.orden_compra_repository import OrdenCompraRepository
from app.repositories.pago_repository import PagoRepository
from app.api.schemas.pago import AnulacionPago, PagoCreate
from app.services.pago_service import PagoService


def pago(monto=7000000, orden=8891, **cambios) -> PagoCreate:
    datos = {"orden_compra_id": orden, "monto": monto, "metodo_pago": "transferencia",
             "fecha_pago": hoy_colombia().isoformat(), "referencia_pasarela": "PSE-558812"}
    datos.update(cambios)
    return PagoCreate(**datos)


class PruebaPago(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba. Proyecto 27 con 14.815.500 comprometidos (la orden aprobada).
        #   orden 8891: confirmada, valor 14.815.500 (ejemplo del issue)
        #   orden 8892: emitida (todavía no la confirma el proveedor)
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        usuario = Usuario(id=1, nombre_completo="Ana Tesorera", tipo_documento="CC",
                          numero_documento="100001", correo="ana@construpro.co",
                          telefono="3001234567", contrasena_hash="x",
                          rol=Rol(id=1, nombre="Administrador"))
        self.presupuesto = Presupuesto(presupuesto_total=250000000, comprometido=14815500 * 2,
                                       ejecutado=0, fecha_aprobacion=date(2026, 11, 1))
        self.db.add_all([
            usuario,
            Proyecto(id=27, nombre="Torre Cabecera", cliente="Andinas", fecha_inicio=date(2026, 11, 1),
                     fecha_fin_estimada=date(2027, 12, 15), responsable=usuario,
                     direccion="Cra 27", ciudad="Bucaramanga", presupuesto=self.presupuesto),
            Proveedor(id=8, razon_social="Ferretería El Constructor", nit="900123456-7",
                      contacto="C", telefono="6076543210", correo="a@b.co"),
        ])
        self.db.flush()

        def orden(oid, cid, estado):
            cot = Cotizacion(id=cid, proyecto_id=27, proveedor_id=8, estado="Aprobada",
                             subtotal=12450000, impuestos=2365500, total=14815500,
                             vigente_hasta=date(2026, 12, 31))
            apr = Aprobacion(id=cid, cotizacion=cot, estado="Aprobada", monto=14815500,
                             monto_autorizado=14815500)
            return [cot, apr, OrdenCompra(id=oid, aprobacion=apr, cotizacion_id=cid, proveedor_id=8,
                                          proyecto_id=27, estado=estado, subtotal=12450000,
                                          impuestos=2365500, valor_total=14815500)]

        self.db.add_all([*orden(8891, 1, "confirmada"), *orden(8892, 2, "emitida")])
        self.db.commit()
        self.servicio = PagoService(PagoRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Registrar (caso 1) ────────────────────────────────

    def test_registrar_pago_calcula_el_saldo(self):
        p = self.servicio.registrar(pago(), usuario_id="1")
        self.assertEqual(p.monto, 7000000.0)
        self.assertEqual(p.moneda, "COP")
        self.assertEqual(p.valor_orden, 14815500.0)
        self.assertEqual(p.total_pagado, 7000000.0)
        self.assertEqual(p.saldo_pendiente, 7815500.0)
        self.assertEqual(p.estado, "registrado")
        self.assertEqual(p.registrado_por_id, "1")
        self.assertRegex(p.numero_transaccion, r"^TX-\d{8}-00001$")

    def test_pagar_pasa_el_valor_de_comprometido_a_ejecutado(self):
        self.servicio.registrar(pago(), usuario_id="1")
        self.db.refresh(self.presupuesto)
        self.assertEqual(self.presupuesto.ejecutado, Decimal("7000000.00"))
        self.assertEqual(self.presupuesto.comprometido, Decimal(14815500 * 2 - 7000000))

    # ── RN-091 (caso 3) ───────────────────────────────────

    def test_rn091_no_se_paga_mas_que_el_saldo(self):
        self.servicio.registrar(pago(), usuario_id="1")
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.registrar(pago(9000000), usuario_id="1")
        self.assertEqual(ctx.exception.regla, "RN-091")
        self.assertEqual(ctx.exception.codigo, "NEG_PAGO_EXCEDE_ORDEN")
        self.assertEqual(ctx.exception.mensaje,
                         "El saldo pendiente de la orden 8891 es 7.815.500,00 COP.")

    def test_rn091_se_puede_pagar_exactamente_el_saldo(self):
        self.servicio.registrar(pago(), usuario_id="1")
        p = self.servicio.registrar(pago(7815500), usuario_id="1")
        self.assertEqual(p.saldo_pendiente, 0.0)

    # ── RN-092, RN-093, RN-095 y monto ────────────────────

    def test_rn092_solo_ordenes_confirmadas(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.registrar(pago(orden=8892), usuario_id="1")
        self.assertEqual(ctx.exception.regla, "RN-092")

    def test_rn093_metodo_y_fecha_obligatorios(self):
        for cambios, campo in (({"metodo_pago": None}, "metodo_pago"),
                               ({"metodo_pago": "bitcoin"}, "metodo_pago"),
                               ({"fecha_pago": None}, "fecha_pago"),
                               ({"fecha_pago": (hoy_colombia() + timedelta(days=1)).isoformat()},
                                "fecha_pago")):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.registrar(pago(**cambios), usuario_id="1")
            self.assertEqual((ctx.exception.regla, ctx.exception.campo), ("RN-093", campo))

    def test_rn095_moneda_de_la_orden(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.registrar(pago(moneda="USD"), usuario_id="1")
        self.assertEqual(ctx.exception.regla, "RN-095")

    def test_monto_mayor_que_cero(self):
        for monto in (0, -100):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.registrar(pago(monto), usuario_id="1")
            self.assertEqual(ctx.exception.campo, "monto")

    def test_orden_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.registrar(pago(orden=999), usuario_id="1")

    # ── Consultar (caso 2) ────────────────────────────────

    def test_pagos_de_la_orden_con_total_y_saldo(self):
        self.servicio.registrar(pago(), usuario_id="1")
        self.servicio.registrar(pago(800000), usuario_id="1")
        r = self.servicio.pagos_de_orden(8891)
        self.assertEqual(len(r.pagos), 2)
        self.assertEqual(r.total_pagado, 7800000.0)
        self.assertEqual(r.saldo_pendiente, 7015500.0)

    def test_orden_sin_pagos_devuelve_lista_vacia(self):
        r = self.servicio.pagos_de_orden(8891)
        self.assertEqual(r.pagos, [])
        self.assertEqual((r.total_pagado, r.saldo_pendiente), (0.0, 14815500.0))

    # ── Anular (caso 4, RN-094) ───────────────────────────

    def test_anular_el_mismo_dia_revierte_el_pago(self):
        pid = int(self.servicio.registrar(pago(), usuario_id="1").pago_id)
        p = self.servicio.anular(pid, AnulacionPago(motivo="Pago duplicado"))
        self.assertEqual(p.estado, "anulado")
        self.assertEqual(p.motivo_anulacion, "Pago duplicado")
        self.assertEqual((p.total_pagado, p.saldo_pendiente), (0.0, 14815500.0))
        self.db.refresh(self.presupuesto)
        self.assertEqual(self.presupuesto.ejecutado, Decimal("0.00"))
        self.assertEqual(len(self.servicio.pagos_de_orden(8891).pagos), 1)  # queda la traza

    def test_rn094_no_se_anula_un_pago_de_ayer(self):
        pid = int(self.servicio.registrar(pago(), usuario_id="1").pago_id)
        self.db.get(Pago, pid).fecha_registro = datetime.now(timezone.utc) - timedelta(days=1)
        self.db.commit()
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.anular(pid, AnulacionPago())
        self.assertEqual(ctx.exception.regla, "RN-094")

    def test_rn094_el_dia_se_mide_en_hora_de_colombia(self):
        pid = int(self.servicio.registrar(pago(), usuario_id="1").pago_id)
        p = self.db.get(Pago, pid)
        p.fecha_registro = datetime(2026, 11, 24, 0, 20)     # 24 en UTC = 23 a las 7:20 p. m. en Colombia
        with self.assertRaises(ConflictoEstadoError):
            p.anular(None, date(2026, 11, 24))
        p.anular(None, date(2026, 11, 23))                    # mismo día en Colombia: se anula
        self.assertEqual(p.estado, "anulado")

    def test_no_se_anula_dos_veces(self):
        pid = int(self.servicio.registrar(pago(), usuario_id="1").pago_id)
        self.servicio.anular(pid, AnulacionPago())
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.anular(pid, AnulacionPago())

    # ── RN-084 (HU-21): la orden con pagos no se anula ────

    def test_contar_pagos_activa_la_rn084_de_la_orden(self):
        repo = OrdenCompraRepository(self.db)
        self.assertEqual(repo.contar_pagos(8891), 0)
        pid = int(self.servicio.registrar(pago(), usuario_id="1").pago_id)
        self.assertEqual(repo.contar_pagos(8891), 1)
        self.servicio.anular(pid, AnulacionPago())
        self.assertEqual(repo.contar_pagos(8891), 0)             # los anulados no cuentan


if __name__ == "__main__":
    unittest.main()
