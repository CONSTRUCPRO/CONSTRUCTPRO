# tests/test_inventario.py
# Pruebas unitarias de las reglas de negocio de la HU-29 (recepción, RN-121, RN-122, RN-112,
# RN-084 con la recepción y cantidades mayores que cero).
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

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
from app.domain.material import Categoria, Material
from app.domain.orden_compra import OrdenCompra, OrdenDetalle
from app.domain.presupuesto import Presupuesto
from app.domain.proveedor import Proveedor
from app.domain.proyecto import Proyecto
from app.domain.rol import Rol
from app.domain.usuario import Usuario
from app.repositories.inventario_repository import InventarioRepository
from app.repositories.orden_compra_repository import OrdenCompraRepository
from app.api.schemas.inventario import EntradaCreate, SalidaCreate
from app.services.inventario_service import InventarioService


def salida(cantidad=40, material=115, proyecto=27, motivo="Fundición placa piso 3") -> SalidaCreate:
    return SalidaCreate(proyecto_id=proyecto, material_id=material, cantidad=cantidad, motivo=motivo)


class PruebaInventario(unittest.TestCase):

    def setUp(self):
        # BD nueva para cada prueba. Proyecto 27, almacenista 15.
        #   orden 8891: confirmada, 300 bultos del material 115 y 150 unidades del 204
        #   orden 8892: emitida (el proveedor todavía no confirma)
        #   orden 8893: anulada
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        almacenista = Usuario(id=15, nombre_completo="Pedro Obra", tipo_documento="CC",
                              numero_documento="100015", correo="pedro@construpro.co",
                              telefono="3001234567", contrasena_hash="x",
                              rol=Rol(id=4, nombre="Empleado"))
        cat = Categoria(id=4, nombre="Cementos")
        self.db.add_all([
            almacenista,
            Proyecto(id=27, nombre="Torre Cabecera", cliente="Andinas", fecha_inicio=date(2026, 11, 1),
                     fecha_fin_estimada=date(2027, 12, 15), responsable=almacenista,
                     direccion="Cra 27", ciudad="Bucaramanga",
                     presupuesto=Presupuesto(presupuesto_total=250000000, comprometido=0, ejecutado=0,
                                             fecha_aprobacion=date(2026, 11, 1))),
            Material(id=115, nombre="Cemento gris tipo I 50 kg", unidad="bulto", categoria=cat,
                     precio_referencia=28500),
            Material(id=204, nombre='Varilla corrugada 1/2" x 6 m', unidad="unidad", categoria=cat,
                     precio_referencia=26000),
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
            o = OrdenCompra(id=oid, aprobacion=apr, cotizacion_id=cid, proveedor_id=8,
                            proyecto_id=27, estado=estado, subtotal=12450000, impuestos=2365500,
                            valor_total=14815500)
            o.detalle = [OrdenDetalle(material_id=115, cantidad=300, precio_unitario=28500,
                                      subtotal=8550000),
                         OrdenDetalle(material_id=204, cantidad=150, precio_unitario=26000,
                                      subtotal=3900000)]
            return [cot, apr, o]

        self.db.add_all([*orden(8891, 1, "confirmada"), *orden(8892, 2, "emitida"),
                         *orden(8893, 3, "anulada")])
        self.db.commit()
        self.servicio = InventarioService(InventarioRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _recibir_y_entrar(self):
        self.servicio.registrar_recepcion(8891, usuario_id="15")
        return self.servicio.registrar_entrada(EntradaCreate(orden_compra_id=8891), usuario_id="15")

    # ── Recepción (RN-112, RN-089) ────────────────────────

    def test_registrar_recepcion_guarda_fecha_y_responsable(self):
        r = self.servicio.registrar_recepcion(8891, usuario_id="15")
        self.assertEqual(r.recibida_por_id, "15")
        self.assertIsNotNone(r.fecha_recepcion)
        self.assertEqual(r.estado, "confirmada")       # los estados de la HU-21 no cambian

    def test_recepcion_solo_de_ordenes_confirmadas_y_una_vez(self):
        for orden_id in (8892, 8893):                   # emitida; anulada (RN-089)
            with self.assertRaises(ConflictoEstadoError):
                self.servicio.registrar_recepcion(orden_id, usuario_id="15")
        self.servicio.registrar_recepcion(8891, usuario_id="15")
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.registrar_recepcion(8891, usuario_id="15")

    def test_rn112_la_recepcion_exige_responsable(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.registrar_recepcion(8891, usuario_id=None)
        self.assertEqual(ctx.exception.regla, "RN-112")

    def test_rn084_una_orden_recibida_no_se_anula(self):
        repo = OrdenCompraRepository(self.db)
        self.assertEqual(repo.contar_envios(8891), 0)
        self.servicio.registrar_recepcion(8891, usuario_id="15")
        self.assertEqual(repo.contar_envios(8891), 1)

    # ── Entrada (caso 1 y caso 3, RN-121) ─────────────────

    def test_entrada_suma_las_cantidades_de_la_orden(self):
        e = self._recibir_y_entrar()
        self.assertEqual(len(e.movimientos), 2)
        cemento = e.movimientos[0]
        self.assertEqual((cemento.tipo, cemento.material_id, cemento.cantidad), ("entrada", "115", 300))
        self.assertEqual((cemento.existencia_anterior, cemento.existencia_actual), (0, 300))
        self.assertEqual(cemento.orden_compra_id, "8891")        # documento de origen
        self.assertEqual(cemento.responsable_id, "15")
        items, _ = self.servicio.existencias(27, 1, 20)
        self.assertEqual([(i.material_id, i.existencia) for i in items], [("115", 300), ("204", 150)])
        self.assertTrue(all(i.fecha_actualizacion for i in items))

    def test_rn121_sin_recepcion_no_hay_entrada(self):
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.registrar_entrada(EntradaCreate(orden_compra_id=8891), usuario_id="15")
        self.assertEqual(ctx.exception.regla, "RN-121")
        self.assertEqual(ctx.exception.codigo, "NEG_RECEPCION_NO_CONFIRMADA")

    def test_una_orden_entra_una_sola_vez(self):
        self._recibir_y_entrar()
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.registrar_entrada(EntradaCreate(orden_compra_id=8891), usuario_id="15")

    def test_entrada_de_orden_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.registrar_entrada(EntradaCreate(orden_compra_id=999), usuario_id="15")

    # ── Salida (caso 2 y caso 4, RN-122) ──────────────────

    def test_salida_descuenta_la_existencia(self):
        self._recibir_y_entrar()
        s = self.servicio.registrar_salida(salida(40), usuario_id="15")
        self.assertEqual((s.tipo, s.cantidad, s.unidad), ("salida", 40, "bulto"))
        self.assertEqual((s.existencia_anterior, s.existencia_actual), (300, 260))
        self.assertEqual(s.motivo, "Fundición placa piso 3")
        self.assertIsNone(s.orden_compra_id)

    def test_rn122_no_sale_mas_de_lo_que_hay(self):
        self._recibir_y_entrar()
        self.servicio.registrar_salida(salida(40), usuario_id="15")
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.registrar_salida(salida(400), usuario_id="15")
        self.assertEqual(ctx.exception.regla, "RN-122")
        self.assertEqual(ctx.exception.codigo, "NEG_STOCK_INSUFICIENTE")
        self.assertEqual(ctx.exception.mensaje, "Se solicitaron 400 bultos y solo hay 260 disponibles.")

    def test_rn122_material_sin_inventario(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.registrar_salida(salida(1), usuario_id="15")
        self.assertEqual(ctx.exception.regla, "RN-122")

    def test_cantidad_mayor_que_cero(self):
        self._recibir_y_entrar()
        for cantidad in (0, -5):
            with self.assertRaises(ReglaNegocioError) as ctx:
                self.servicio.registrar_salida(salida(cantidad), usuario_id="15")
            self.assertEqual(ctx.exception.campo, "cantidad")

    def test_salida_de_proyecto_o_material_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.registrar_salida(salida(proyecto=99), usuario_id="15")
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.registrar_salida(salida(material=999), usuario_id="15")

    # ── Consultas y respuesta sin datos ───────────────────

    def test_proyecto_sin_inventario_devuelve_lista_vacia(self):
        items, paginacion = self.servicio.existencias(27, 1, 20)
        self.assertEqual(items, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_movimientos_quedan_para_la_trazabilidad(self):
        self._recibir_y_entrar()
        self.servicio.registrar_salida(salida(40), usuario_id="15")
        items, paginacion = self.servicio.movimientos(27, 115, None, 1, 20)
        self.assertEqual([(m.tipo, m.cantidad) for m in items], [("salida", 40), ("entrada", 300)])
        salidas, _ = self.servicio.movimientos(27, None, "salida", 1, 20)
        self.assertEqual(len(salidas), 1)


if __name__ == "__main__":
    unittest.main()
