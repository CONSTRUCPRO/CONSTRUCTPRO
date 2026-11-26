# tests/test_usuario.py
# Pruebas unitarias de las reglas de negocio de la HU-01 (RN-001 a RN-005, RN-009)
# y de la RN-012 (roles con usuarios). Usan una BD SQLite en memoria: no tocan dev.db.
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
    ReglaNegocioError,
)
from app.domain.rol import Rol
from app.repositories.rol_repository import RolRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.api.schemas.rol import EstadoRolUpdate
from app.api.schemas.usuario import (
    EstadoUsuarioUpdate,
    RolUsuarioUpdate,
    UsuarioCreate,
    UsuarioUpdate,
)
from app.services.rol_service import RolService
from app.services.usuario_service import UsuarioService


def datos(**cambios) -> UsuarioCreate:
    base = {"nombre_completo": "Laura Gómez", "tipo_documento": "CC",
            "numero_documento": "1098765432", "correo": "laura@construpro.co",
            "telefono": "3001234567", "contrasena": "Construpro2026", "rol_id": 2}
    base.update(cambios)
    return UsuarioCreate(**base)


def perfil(**cambios) -> UsuarioUpdate:
    base = {"nombre_completo": "Laura Gómez", "tipo_documento": "CC",
            "numero_documento": "1098765432", "correo": "laura@construpro.co",
            "telefono": "3001234567"}
    base.update(cambios)
    return UsuarioUpdate(**base)


class PruebaUsuario(unittest.TestCase):

    def setUp(self):
        # BD nueva y vacía para cada prueba, con algunos roles
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            Rol(id=1, nombre="Administrador"),
            Rol(id=2, nombre="Coordinador"),
            Rol(id=5, nombre="Auxiliar"),
            Rol(id=6, nombre="Antiguo", estado="inactivo"),
        ])
        self.db.commit()
        self.repo = UsuarioRepository(self.db)
        self.servicio = UsuarioService(self.repo)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # ── Registro ───────────────────────────────────────────

    def test_registrar_usuario_valido_queda_activo_y_sin_contrasena(self):
        u = self.servicio.crear(datos())
        self.assertEqual(u.usuario_id, "1")
        self.assertEqual(u.estado, "activo")
        self.assertEqual(u.rol, "Coordinador")
        salida = u.model_dump()
        self.assertNotIn("contrasena", salida)
        self.assertNotIn("contrasena_hash", salida)

    # ── RN-001 ─────────────────────────────────────────────

    def test_rn001_no_repite_correo_sin_importar_mayusculas(self):
        self.servicio.crear(datos())
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.crear(datos(correo="LAURA@construpro.co", numero_documento="555555"))
        self.assertEqual(ctx.exception.regla, "RN-001")
        self.assertEqual(ctx.exception.campo, "correo")

    def test_rn001_no_repite_documento(self):
        self.servicio.crear(datos())
        with self.assertRaises(RecursoDuplicadoError) as ctx:
            self.servicio.crear(datos(correo="otra@construpro.co"))
        self.assertEqual(ctx.exception.campo, "numero_documento")

    def test_rn001_editar_conservando_sus_propios_datos_no_es_duplicado(self):
        self.servicio.crear(datos())
        u = self.servicio.editar(1, perfil(nombre_completo="Laura Gómez Ruiz"))
        self.assertEqual(u.nombre_completo, "Laura Gómez Ruiz")
        self.assertIsNotNone(u.fecha_actualizacion)

    def test_rn001_editar_con_correo_de_otro_usuario_es_duplicado(self):
        self.servicio.crear(datos())
        self.servicio.crear(datos(correo="pedro@construpro.co", numero_documento="80000001"))
        with self.assertRaises(RecursoDuplicadoError):
            self.servicio.editar(2, perfil(correo="laura@construpro.co",
                                           numero_documento="80000001"))

    # ── RN-002 ─────────────────────────────────────────────

    def test_rn002_rol_inexistente(self):
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.crear(datos(rol_id=99))
        self.assertEqual(ctx.exception.regla, "RN-002")
        self.assertEqual(ctx.exception.campo, "rol_id")

    def test_rn002_rol_inactivo(self):
        with self.assertRaises(ReglaNegocioError):
            self.servicio.crear(datos(rol_id=6))

    def test_rn002_rol_es_obligatorio(self):
        base = datos().model_dump()
        del base["rol_id"]
        with self.assertRaises(ValidationError):
            UsuarioCreate(**base)

    def test_cambiar_rol(self):
        self.servicio.crear(datos())
        u = self.servicio.cambiar_rol(1, RolUsuarioUpdate(rol_id=5))
        self.assertEqual(u.rol, "Auxiliar")
        with self.assertRaises(ReglaNegocioError):
            self.servicio.cambiar_rol(1, RolUsuarioUpdate(rol_id=6))

    # ── RN-003 ─────────────────────────────────────────────

    def test_rn003_contrasena_cifrada_y_verificable(self):
        self.servicio.crear(datos())
        usuario = self.repo.obtener_por_id(1)
        self.assertNotEqual(usuario.contrasena_hash, "Construpro2026")
        self.assertTrue(usuario.contrasena_hash.startswith("$2"))   # formato bcrypt
        self.assertTrue(usuario.verificar_contrasena("Construpro2026"))
        self.assertFalse(usuario.verificar_contrasena("otra-clave1"))

    def test_contrasena_debil_es_rechazada(self):
        with self.assertRaises(ValidationError):
            datos(contrasena="corta1")
        with self.assertRaises(ValidationError):
            datos(contrasena="sololetras")

    # ── RN-004 y RN-009 ────────────────────────────────────

    def test_rn004_no_puede_inactivar_su_propia_cuenta(self):
        self.servicio.crear(datos())
        with self.assertRaises(ReglaNegocioError) as ctx:
            self.servicio.cambiar_estado(1, EstadoUsuarioUpdate(estado="inactivo"),
                                         usuario_actual_id="1")
        self.assertEqual(ctx.exception.regla, "RN-004")

    def test_rn009_inactivar_invalida_sesiones(self):
        self.servicio.crear(datos())
        self.servicio.cambiar_estado(1, EstadoUsuarioUpdate(estado="inactivo"),
                                     usuario_actual_id="99")
        usuario = self.repo.obtener_por_id(1)
        self.assertEqual(usuario.estado, "inactivo")
        self.assertEqual(usuario.version_sesion, 1)

    def test_mismo_estado_es_conflicto(self):
        self.servicio.crear(datos())
        with self.assertRaises(ConflictoEstadoError):
            self.servicio.cambiar_estado(1, EstadoUsuarioUpdate(estado="activo"), None)

    def test_estado_invalido(self):
        with self.assertRaises(ValidationError):
            EstadoUsuarioUpdate(estado="borrado")

    # ── RN-012 (HU-03, depende de usuarios) ────────────────

    def test_rn012_no_inactiva_rol_con_usuarios_activos(self):
        self.servicio.crear(datos(rol_id=5))
        roles = RolService(RolRepository(self.db))
        with self.assertRaises(ConflictoEstadoError) as ctx:
            roles.cambiar_estado(5, EstadoRolUpdate(estado="inactivo"))
        self.assertEqual(ctx.exception.regla, "RN-012")

    def test_rn012_si_inactiva_rol_sin_usuarios_activos(self):
        self.servicio.crear(datos(rol_id=5))
        self.servicio.cambiar_estado(1, EstadoUsuarioUpdate(estado="inactivo"), None)
        roles = RolService(RolRepository(self.db))
        self.assertEqual(roles.cambiar_estado(5, EstadoRolUpdate(estado="inactivo")).estado,
                         "inactivo")

    # ── Consultas ──────────────────────────────────────────

    def test_usuario_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(99)

    def test_listado_vacio(self):
        usuarios, paginacion = self.servicio.listar(None, None, None, 1, 20)
        self.assertEqual(usuarios, [])
        self.assertEqual(paginacion["total_registros"], 0)

    def test_listado_paginado_y_filtrado(self):
        for i in range(3):
            self.servicio.crear(datos(correo=f"u{i}@construpro.co",
                                      numero_documento=f"7000000{i}",
                                      rol_id=2 if i < 2 else 5))
        usuarios, paginacion = self.servicio.listar(None, None, None, 1, 2)
        self.assertEqual(len(usuarios), 2)
        self.assertEqual(paginacion["total_registros"], 3)
        self.assertEqual(paginacion["total_paginas"], 2)
        solo_rol5, _ = self.servicio.listar(None, 5, None, 1, 20)
        self.assertEqual([u.rol for u in solo_rol5], ["Auxiliar"])

    # ── Validación de formato (caso 5 del issue) ───────────

    def test_formato_un_error_por_campo(self):
        base = datos().model_dump()
        del base["numero_documento"]
        base["correo"] = "laura-construpro.co"
        with self.assertRaises(ValidationError) as ctx:
            UsuarioCreate(**base)
        campos = {e["loc"][0] for e in ctx.exception.errors()}
        self.assertEqual(campos, {"numero_documento", "correo"})


if __name__ == "__main__":
    unittest.main()
