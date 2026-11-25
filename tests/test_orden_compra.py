# tests/test_orden_compra.py
# Pruebas unitarias de la HU-21 Orden de Compra (RN-039, RN-069, RN-081 a RN-084, RN-086, RN-089,
# RN-092) y de las reglas que activa en otras HU: RN-040 (proveedor) y RN-025 (proyecto).
# Incluye las pruebas de la revisión general: cierre automático de la orden (RN-087) y
# solicitud con cotización aprobada (RN-045).
# BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.comparativo import Comparativo
from app.domain.excepciones import ConflictoEstadoError, RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.material import Categoria, Material
from app.domain.presupuesto import Presupuesto
from app.domain.proveedor import Proveedor
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.solicitud import Solicitud, SolicitudDetalle
from app.domain.usuario import Usuario
from app.repositories.aprobacion_repository import AprobacionRepository
from app.repositories.cotizacion_repository import CotizacionRepository
from app.repositories.inventario_repository import InventarioRepository
from app.repositories.orden_compra_repository import OrdenCompraRepository
from app.repositories.pago_repository import PagoRepository
from app.repositories.proveedor_repository import ProveedorRepository
from app.repositories.proyecto_repository import ProyectoRepository
from app.api.schemas.aprobacion import DecisionDatos
from app.api.schemas.cotizacion import CotizacionCreate
from app.api.schemas.orden_compra import AnulacionDatos, OrdenCompraCreate
from app.api.schemas.pago import AnulacionPago, PagoCreate
from app.api.schemas.solicitud import SolicitudUpdate
from app.api.schemas.proveedor import EstadoProveedorUpdate
from app.api.schemas.proyecto import EstadoProyectoUpdate
from app.services.aprobacion_service import AprobacionService
from app.services.cotizacion_service import CotizacionService
from app.services.inventario_service import InventarioService
from app.services.orden_compra_service import OrdenCompraService
from app.services.pago_service import PagoService
from app.services.proveedor_service import ProveedorService
from app.services.proyecto_service import ProyectoService
from app.repositories.solicitud_repository import SolicitudRepository
from app.services.solicitud_service import SolicitudService

COORDINADOR, DIRECTOR = "2", "3"


def orden(aprobacion_id: int) -> OrdenCompraCreate:
    return OrdenCompraCreate(aprobacion_id=aprobacion_id)


class PruebaOrdenCompra(unittest.TestCase):

    def setUp(self):
        # Proyecto 27 (presupuesto 250 M), proveedor 8. Solicitud 305 con dos materiales:
        #   comparativo 1: 300 x 28.500 = 8.550.000    comparativo 2: 150 x 26.000 = 3.900.000
        # Cotización con ambos: subtotal 12.450.000 + IVA 2.365.500 = 14.815.500 (ejemplo del issue).
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        coord, director = Rol(id=2, nombre="Coordinador"), Rol(id=3, nombre="Director")

        def usuario(uid, nombre, rol):
            return Usuario(id=uid, nombre_completo=nombre, tipo_documento="CC", numero_documento=f"10000{uid}",
                           correo=f"u{uid}@construpro.co", telefono="3001234567", contrasena_hash="x", rol=rol)

        empleado = usuario(1, "Pedro Obra", Rol(id=4, nombre="Empleado"))
        responsable = usuario(4, "Ana Pardo", director)
        cat = Categoria(id=4, nombre="Cementos")
        self.db.add_all([empleado, usuario(2, "Carla Díaz", coord), usuario(3, "Mario Ruiz", director), responsable,
                         Proyecto(id=27, nombre="Torre Cabecera", cliente="Andinas", fecha_inicio=date(2026, 11, 1),
                                  fecha_fin_estimada=date(2027, 12, 15), responsable=responsable,
                                  direccion="Cra 27", ciudad="Bucaramanga",
                                  presupuesto=Presupuesto(presupuesto_total=250000000, comprometido=0,
                                                          ejecutado=0, fecha_aprobacion=date(2026, 11, 1))),
                         *[Material(id=i, nombre=f"Material {i}", unidad="bulto", categoria=cat,
                                    precio_referencia=1000) for i in (1, 2)],
                         Proveedor(id=8, razon_social="Ferretería El Constructor", nit="900123456-7",
                                   contacto="C", telefono="6076543210", correo="a@b.co")])
        self.db.flush()
        s = Solicitud(id=305, proyecto_id=27, solicitante_id=1, estado="pendiente")
        s.detalle = [SolicitudDetalle(material_id=1, cantidad=300), SolicitudDetalle(material_id=2, cantidad=150)]
        self.db.add(s)
        self.db.flush()
        for cid, mid, cant, precio in [(1, 1, 300, 28500), (2, 2, 150, 26000)]:
            self.db.add(Comparativo(id=cid, solicitud_id=305, material_id=mid, unidad="bulto", cantidad=cant,
                                    precio_minimo=precio, precio_maximo=precio, estado="seleccionado",
                                    proveedor_seleccionado_id=8, precio_seleccionado=precio, ahorro=0))
        self.db.commit()
        self.cotizaciones = CotizacionService(CotizacionRepository(self.db))
        self.aprobaciones = AprobacionService(AprobacionRepository(self.db))
        self.servicio = OrdenCompraService(OrdenCompraRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def compra(self, aprobar=True) -> int:
        """Cotización con los dos comparativos, enviada (y aprobada por el director). Devuelve la aprobación."""
        c = self.cotizaciones.generar(CotizacionCreate(comparativo_ids=[1, 2]))
        aid = int(self.cotizaciones.enviar(int(c.cotizacion_id), COORDINADOR).aprobacion.aprobacion_id)
        if aprobar:
            self.aprobaciones.decidir(aid, DecisionDatos(decision="aprobada"), DIRECTOR)
        return aid

    def comprometido(self) -> float:
        return float(self.db.get(Proyecto, 27).presupuesto.comprometido)

    # ── Caso 1: generar (RN-082) ───────────────────────────

    def test_generar_copia_exactamente_lo_aprobado(self):
        o = self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.assertEqual(o.estado, "emitida")
        self.assertEqual((o.aprobacion_id, o.cotizacion_id, o.proveedor_id, o.proyecto_id), ("1", "1", "8", "27"))
        self.assertEqual(o.valor_total, 14815500.00)                    # = monto autorizado
        self.assertEqual((o.subtotal, o.impuestos), (12450000.00, 2365500.00))
        self.assertEqual([(d.material_id, d.cantidad, d.precio_unitario, d.subtotal) for d in o.detalle],
                         [("1", 300, 28500.0, 8550000.0), ("2", 150, 26000.0, 3900000.0)])

    # ── Caso 3: RN-081 ─────────────────────────────────────

    def test_rn081_compra_no_aprobada(self):
        aid = self.compra(aprobar=False)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.generar(orden(aid), COORDINADOR)
        self.assertEqual((ctx.exception.regla, ctx.exception.codigo), ("RN-081", "NEG_COMPRA_NO_APROBADA"))
        self.assertIn("'En revisión'", ctx.exception.mensaje)

    def test_aprobacion_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.generar(orden(999), COORDINADOR)

    # ── Caso 4: RN-083 ─────────────────────────────────────

    def test_rn083_una_sola_orden_por_cotizacion(self):
        aid = self.compra()
        self.servicio.generar(orden(aid), COORDINADOR)
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.generar(orden(aid), COORDINADOR)
        self.assertEqual(ctx.exception.regla, "RN-083")
        self.servicio.anular(1, AnulacionDatos())                     # anulada sigue contando
        with self.assertRaises(RecursoDuplicadoError):
            self.servicio.generar(orden(aid), COORDINADOR)

    # ── RN-039 ─────────────────────────────────────────────

    def test_rn039_proveedor_inactivo(self):
        aid = self.compra()
        self.db.get(Proveedor, 8).estado = "inactivo"
        self.db.commit()
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.generar(orden(aid), COORDINADOR)
        self.assertEqual(ctx.exception.regla, "RN-039")

    # ── Caso 2: anular libera el presupuesto ───────────────

    def test_anular_registra_motivo_y_libera_el_presupuesto(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.assertEqual(self.comprometido(), 14815500.00)               # comprometido al aprobar (HU-20)
        o = self.servicio.anular(1, AnulacionDatos(motivo=" El proyecto canceló la compra. "))
        self.assertEqual(o.estado, "anulada")
        self.assertEqual(o.motivo_anulacion, "El proyecto canceló la compra.")
        self.assertIsNotNone(o.fecha_anulacion)
        self.assertEqual(self.comprometido(), 0.0)                       # RN-069

    # ── Caso 5: RN-084 ─────────────────────────────────────

    def test_rn084_no_anula_con_pagos_o_envios(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.repo.contar_pagos = lambda orden_id: 1             # simula un pago (HU-23)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.anular(1, AnulacionDatos())
        self.assertEqual(ctx.exception.regla, "RN-084")
        self.servicio.repo.contar_pagos = lambda orden_id: 0
        self.servicio.repo.contar_envios = lambda orden_id: 2            # o un envío (Logística)
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.anular(1, AnulacionDatos())
        self.assertEqual(self.comprometido(), 14815500.00)               # no se liberó nada

    # ── Estados: RN-086, RN-089 y RN-092 ───────────────────

    def test_confirmar_y_verificar_pagable(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        modelo = self.servicio.repo.obtener_por_id(1)
        with self.assertRaises(ConflictoEstadoError) as ctx:             # emitida: aún no se paga
            modelo.verificar_pagable()
        self.assertEqual(ctx.exception.regla, "RN-092")
        o = self.servicio.confirmar(1)
        self.assertEqual(o.estado, "confirmada")
        self.assertIsNotNone(o.fecha_confirmacion)
        modelo.verificar_pagable()                                      # confirmada: sí
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.confirmar(1)
        self.assertEqual(ctx.exception.regla, "RN-086")

    def test_rn089_orden_anulada_no_cambia(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.anular(1, AnulacionDatos())
        for accion in (lambda: self.servicio.anular(1, AnulacionDatos()), lambda: self.servicio.confirmar(1)):
            with self.assertRaises(ConflictoEstadoError) as ctx:
                accion()
            self.assertEqual(ctx.exception.regla, "RN-089")
        self.assertEqual(self.comprometido(), 0.0)                       # no se liberó dos veces

    # ── Reglas activadas en otras HU ───────────────────────

    def test_rn040_proveedor_con_orden_abierta_no_se_inactiva(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        proveedores = ProveedorService(ProveedorRepository(self.db))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            proveedores.cambiar_estado(8, EstadoProveedorUpdate(estado="inactivo"))
        self.assertEqual(ctx.exception.regla, "RN-040")
        self.servicio.anular(1, AnulacionDatos())
        proveedores.cambiar_estado(8, EstadoProveedorUpdate(estado="inactivo"))   # ya no tiene abiertas

    def test_rn025_proyecto_con_orden_abierta_no_se_finaliza(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        proyectos = ProyectoService(ProyectoRepository(self.db))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            proyectos.cambiar_estado(27, EstadoProyectoUpdate(estado="finalizado"))
        self.assertEqual(ctx.exception.regla, "RN-025")
        self.servicio.anular(1, AnulacionDatos())
        self.assertEqual(proyectos.cambiar_estado(27, EstadoProyectoUpdate(estado="finalizado")).estado,
                         "finalizado")

    # ── Consultas ──────────────────────────────────────────

    def test_consultar_y_listar(self):
        self.assertEqual(self.servicio.listar(None, None, None, 1, 20)[0], [])     # sin datos
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.assertEqual(self.servicio.obtener(1).proveedor, "Ferretería El Constructor")
        self.assertEqual(len(self.servicio.listar(27, 8, "emitida", 1, 20)[0]), 1)
        self.assertEqual(len(self.servicio.listar(None, None, "anulada", 1, 20)[0]), 0)
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(999)

    # ── Revisión general: cierre de la orden (RN-087) y RN-045 ─────────

    def pagar(self, monto: float):
        return PagoService(PagoRepository(self.db)).registrar(
            PagoCreate(orden_compra_id=1, monto=monto, metodo_pago="transferencia",
                       fecha_pago=date.today()), "5")

    def recibir(self):
        return InventarioService(InventarioRepository(self.db)).registrar_recepcion(1, "1")

    def test_rn087_se_cierra_al_pagar_todo_despues_de_recibir(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.confirmar(1)
        self.recibir()
        self.pagar(10000000)                                             # pago parcial
        self.assertEqual(self.servicio.obtener(1).estado, "confirmada")
        self.pagar(4815500)                                              # completa el valor
        o = self.servicio.obtener(1)
        self.assertEqual(o.estado, "cerrada")
        self.assertIsNotNone(o.fecha_cierre)

    def test_rn087_se_cierra_al_recibir_si_ya_estaba_pagada(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.confirmar(1)
        self.pagar(14815500)
        self.assertEqual(self.servicio.obtener(1).estado, "confirmada")  # falta la recepción
        self.assertEqual(self.recibir().estado, "cerrada")

    def test_orden_cerrada_libera_proyecto_y_proveedor(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.confirmar(1)
        self.recibir()
        self.pagar(14815500)
        # Ya no cuenta como abierta: RN-025 y RN-040 dejan finalizar e inactivar
        ProveedorService(ProveedorRepository(self.db)).cambiar_estado(
            8, EstadoProveedorUpdate(estado="inactivo"))
        self.assertEqual(ProyectoService(ProyectoRepository(self.db)).cambiar_estado(
            27, EstadoProyectoUpdate(estado="finalizado")).estado, "finalizado")

    def test_rn089_no_se_anula_un_pago_de_orden_cerrada(self):
        self.servicio.generar(orden(self.compra()), COORDINADOR)
        self.servicio.confirmar(1)
        self.recibir()
        pago = self.pagar(14815500)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            PagoService(PagoRepository(self.db)).anular(int(pago.pago_id), AnulacionPago())
        self.assertEqual(ctx.exception.regla, "RN-089")

    def test_rn045_solicitud_con_cotizacion_aprobada_no_se_modifica(self):
        solicitudes = SolicitudService(SolicitudRepository(self.db))
        self.compra(aprobar=False)                                      # en revisión: aún se puede
        self.assertFalse(SolicitudRepository(self.db).tiene_cotizacion_aprobada(305))
        self.aprobaciones.decidir(1, DecisionDatos(decision="aprobada"), DIRECTOR)
        with self.assertRaises(ConflictoEstadoError) as ctx:
            solicitudes.editar(305, SolicitudUpdate(detalle=[{"material_id": 1, "cantidad": 5}]), "1")
        self.assertEqual(ctx.exception.regla, "RN-045")
        with self.assertRaises(ConflictoEstadoError) as ctx:
            solicitudes.anular(305, "1")
        self.assertEqual(ctx.exception.regla, "RN-045")


if __name__ == "__main__":
    unittest.main()
