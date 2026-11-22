# tests/test_proyecto.py
# Pruebas unitarias de las reglas de negocio de la HU-05 (RN-016 a RN-019, RN-024, RN-025)
# y del método que usará la HU-12 (RN-020, RN-041). BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import date

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.domain.excepciones import (
    ConflictoEstadoError,
    RecursoDuplicadoError,
    RecursoNoEncontradoError,
    ReglaNegocioError,
)
from app.domain.rol import Rol
from app.domain.usuario import Usuario
from app.repositories.proyecto_repository import ProyectoRepository
from app.schemas.proyecto import (
    EstadoProyectoUpdate,
    ProyectoCreate,
    ProyectoUpdate,
    ResponsableUpdate,
    UbicacionDatos,
)
from app.services.proyecto_service import ProyectoService


def datos(**cambios) -> ProyectoCreate:
    base = {"nombre": "Torre Cabecera Etapa 2", "cliente": "Inversiones Andinas S.A.S.",
            "descripcion": "Edificio residencial de 12 pisos", "fecha_inicio": "2026-11-01",
            "fecha_fin_estimada": "2027-12-15", "responsable_id": 1}
    base.update(cambios)
    return ProyectoCreate(**base)


def generales(**cambios) -> ProyectoUpdate:
    base = {"nombre": "Torre Cabecera Etapa 2", "cliente": "Inversiones Andinas S.A.S.",
            "descripcion": "Edificio residencial de 14 pisos", "fecha_inicio": "2026-11-01",
            "fecha_fin_estimada": "2028-03-30"}
    base.update(cambios)
    return ProyectoUpdate(**base)


UBICACION = UbicacionDatos(direccion="Cra 35 # 48-20", ciudad="Bucaramanga",
                           latitud=7.1193, longitud=-73.1227)


class PruebaProyecto(unittest.TestCase):

    def setUp(self):
        # BD nueva y vacía para cada prueba, con roles y usuarios
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        coordinador, director, empleado = (Rol(id=2, nombre="Coordinador"),
                                           Rol(id=3, nombre="Director"),
                                           Rol(id=4, nombre="Empleado"))

        def usuario(uid, nombre, rol, estado="activo"):
            # El hash no importa en estas pruebas (no se prueba el login aquí)
            return Usuario(id=uid, nombre_completo=nombre, tipo_documento="CC",
                           numero_documento=f"10000{uid}", correo=f"u{uid}@construpro.co",
                           telefono="3001234567", contrasena_hash="x", rol=rol, estado=estado)

        self.db.add_all([
            usuario(1, "Laura Gómez", coordinador),
            usuario(2, "Mario Ruiz", director),
            usuario(3, "Pedro Obra", empleado),
            usuario(4, "Ana Retirada", coordinador, estado="inactivo"),
        ])
        self.db.commit()
        self.servicio = ProyectoService(ProyectoRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Registro ───────────────────────────────────────────

    def test_registrar_proyecto_valido_queda_activo(self):
        p = self.servicio.crear(datos(ubicacion=UBICACION.model_dump()))
        self.assertEqual(p.proyecto_id, "1")
        self.assertEqual(p.estado, "activo")
        self.assertEqual(p.fecha_inicio, "2026-11-01")
        self.assertEqual(p.responsable_id, "1")
        self.assertEqual(p.ubicacion.ciudad, "Bucaramanga")

    def test_registrar_sin_ubicacion_la_deja_en_null(self):
        p = self.servicio.crear(datos())
        self.assertIsNone(p.ubicacion)

    # ── RN-016 ─────────────────────────────────────────────

    def test_rn016_responsable_inexistente(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(datos(responsable_id=99))
        self.assertEqual(ctx.exception.regla, "RN-016")

    def test_rn016_responsable_inactivo(self):
        with self.assertRaises(ReglaNegocioError):
            self.servicio.crear(datos(responsable_id=4))

    def test_rn016_responsable_debe_ser_coordinador_o_director(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(datos(responsable_id=3))   # Empleado
        self.assertEqual(ctx.exception.campo, "responsable_id")
        self.assertEqual(self.servicio.crear(datos(responsable_id=2)).responsable, "Mario Ruiz")

    # ── RN-017 ─────────────────────────────────────────────

    def test_rn017_fecha_fin_anterior_a_inicio(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(datos(fecha_inicio="2027-01-10", fecha_fin_estimada="2026-12-31"))
        self.assertEqual(ctx.exception.regla, "RN-017")
        self.assertEqual(ctx.exception.codigo, "VAL_FORMATO_INVALIDO")
        self.assertEqual(ctx.exception.campo, "fecha_fin_estimada")

    def test_rn017_tambien_al_editar(self):
        self.servicio.crear(datos())
        with self.assertRaises(ReglaNegocioError):
            self.servicio.editar(1, generales(fecha_fin_estimada="2026-01-01"))

    # ── RN-018 ─────────────────────────────────────────────

    def test_rn018_nombre_unico_por_cliente(self):
        self.servicio.crear(datos())
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.crear(datos(nombre="TORRE cabecera etapa 2"))
        self.assertEqual(ctx.exception.regla, "RN-018")

    def test_rn018_mismo_nombre_con_otro_cliente_si_se_permite(self):
        self.servicio.crear(datos())
        p = self.servicio.crear(datos(cliente="Constructora del Norte"))
        self.assertEqual(p.proyecto_id, "2")

    def test_rn018_editar_conservando_su_nombre_no_es_duplicado(self):
        self.servicio.crear(datos())
        p = self.servicio.editar(1, generales())
        self.assertEqual(p.descripcion, "Edificio residencial de 14 pisos")
        self.assertIsNotNone(p.fecha_actualizacion)

    # ── RN-019 ─────────────────────────────────────────────

    def test_rn019_finalizado_no_se_edita(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="finalizado"))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.editar(1, generales())
        self.assertEqual(ctx.exception.regla, "RN-019")
        self.assertEqual(self.servicio.obtener(1).descripcion, "Edificio residencial de 12 pisos")
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.registrar_ubicacion(1, UBICACION)
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.asignar_responsable(1, ResponsableUpdate(responsable_id=2))

    # ── Ubicación y responsable ────────────────────────────

    def test_registrar_ubicacion(self):
        self.servicio.crear(datos())
        p = self.servicio.registrar_ubicacion(1, UBICACION)
        self.assertEqual(p.ubicacion.ciudad, "Bucaramanga")
        self.assertEqual(p.ubicacion.latitud, 7.1193)

    def test_coordenadas_fuera_de_rango(self):
        with self.assertRaises(ValidationError):
            UbicacionDatos(direccion="Cra 35 # 48-20", ciudad="Bucaramanga", latitud=120)

    def test_asignar_responsable(self):
        self.servicio.crear(datos())
        p = self.servicio.asignar_responsable(1, ResponsableUpdate(responsable_id=2))
        self.assertEqual(p.responsable_id, "2")
        with self.assertRaises(ReglaNegocioError):
            self.servicio.asignar_responsable(1, ResponsableUpdate(responsable_id=4))

    # ── Estado: RN-024 y RN-025 ────────────────────────────

    def test_suspender_y_reactivar(self):
        self.servicio.crear(datos())
        self.assertEqual(self.servicio.cambiar_estado(
            1, EstadoProyectoUpdate(estado="suspendido")).estado, "suspendido")
        self.assertEqual(self.servicio.cambiar_estado(
            1, EstadoProyectoUpdate(estado="activo")).estado, "activo")

    def test_rn024_finalizado_no_vuelve_a_activo(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="finalizado"))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="activo"))
        self.assertEqual(ctx.exception.regla, "RN-024")

    def test_rn025_no_finaliza_con_compromisos_abiertos(self):
        self.servicio.crear(datos())
        self.servicio.repo.contar_compromisos_abiertos = lambda proyecto_id: 2   # simula HU-21
        with self.assertRaises(ConflictoEstadoError) as ctx:
            self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="finalizado"))
        self.assertEqual(ctx.exception.regla, "RN-025")

    def test_mismo_estado_es_conflicto(self):
        self.servicio.crear(datos())
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="activo"))

    def test_estado_invalido(self):
        with self.assertRaises(ValidationError):
            EstadoProyectoUpdate(estado="cerrado")

    # ── Para la HU-12: RN-041 y RN-020 ─────────────────────

    def test_rn041_y_rn020_admite_solicitudes(self):
        self.servicio.crear(datos())
        proyecto = self.servicio.repo.obtener_por_id(1)
        with self.assertRaises(ReglaNegocioError) as ctx:        # sin ubicación
            proyecto.verificar_admite_solicitudes()
        self.assertEqual(ctx.exception.regla, "RN-020")
        self.servicio.registrar_ubicacion(1, UBICACION)
        proyecto.verificar_admite_solicitudes()                   # activo y con ubicación: OK
        self.servicio.cambiar_estado(1, EstadoProyectoUpdate(estado="suspendido"))
        with self.assertRaises(ReglaNegocioError) as ctx:
            proyecto.verificar_admite_solicitudes()
        self.assertEqual(ctx.exception.regla, "RN-041")
        self.assertEqual(ctx.exception.codigo, "NEG_PROYECTO_NO_ACTIVO")

    # ── Consultas ──────────────────────────────────────────

    def test_proyecto_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError) as ctx:
            self.servicio.obtener(999)
        self.assertEqual(ctx.exception.codigo, "REC_NO_ENCONTRADO")

    def test_listado_vacio(self):
        proyectos, paginacion = self.servicio.listar(None, None, None, None, 1, 20)
        self.assertEqual(proyectos, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listado_filtrado_por_estado_y_ciudad(self):
        self.servicio.crear(datos(ubicacion=UBICACION.model_dump()))
        self.servicio.crear(datos(nombre="Bodega Norte"))
        self.servicio.crear(datos(nombre="Casa Campestre",
                                  ubicacion={"direccion": "Km 5 via Giron", "ciudad": "Girón"}))
        en_bucaramanga, paginacion = self.servicio.listar(None, "bucaramanga", None, None, 1, 20)
        self.assertEqual([p.nombre for p in en_bucaramanga], ["Torre Cabecera Etapa 2"])
        self.assertEqual(paginacion["total_registros"], 1)
        self.servicio.cambiar_estado(2, EstadoProyectoUpdate(estado="suspendido"))
        activos, _ = self.servicio.listar("activo", None, None, None, 1, 20)
        self.assertEqual(len(activos), 2)
        _, pag = self.servicio.listar(None, None, None, None, 1, 2)
        self.assertEqual(pag["total_paginas"], 2)


if __name__ == "__main__":
    unittest.main()
