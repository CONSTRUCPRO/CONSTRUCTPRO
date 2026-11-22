# tests/test_autenticacion.py
# Pruebas unitarias de la HU-02: login, renovación, logout y validación del token en cada
# petición (RN-003, RN-006 a RN-010). BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import unittest
from datetime import timedelta

import jwt
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base
from app.core.seguridad import obtener_usuario_actual
from app.core.tokens import ALGORITMO, leer_token_acceso
from app.domain.excepciones import NoAutenticadoError
from app.domain.rol import Rol
from app.domain.sesion import Sesion, hash_token
from app.domain.usuario import Usuario, ahora_utc_sin_zona
from app.repositories.sesion_repository import SesionRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import LoginDatos, RenovarDatos
from app.schemas.usuario import EstadoUsuarioUpdate
from app.services.auth_service import AuthService
from app.services.usuario_service import UsuarioService


def credenciales(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class PruebaAutenticacion(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.coordinador, self.director = Rol(id=2, nombre="Coordinador"), Rol(id=3, nombre="Director")
        laura = Usuario.registrar("Laura Gómez", "CC", "1098765432", "laura@construpro.co",
                                  "3001234567", "Construpro2026", self.coordinador)
        inactivo = Usuario.registrar("Ana Retirada", "CC", "2000002", "ana@construpro.co",
                                     "3001234567", "Construpro2026", self.coordinador)
        inactivo.estado = "inactivo"
        self.db.add_all([laura, inactivo])
        self.db.commit()
        self.servicio = AuthService(SesionRepository(self.db))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def login(self, correo="laura@construpro.co", contrasena="Construpro2026"):
        return self.servicio.iniciar_sesion(LoginDatos(correo=correo, contrasena=contrasena))

    # ── Login (casos 1, 3 y 4) ─────────────────────────────

    def test_login_correcto_entrega_tokens_sin_contrasena(self):
        r = self.login(correo="LAURA@construpro.co")
        self.assertEqual(r.rol, "Coordinador")
        self.assertTrue(r.token_acceso and r.token_renovacion and r.expira_en)
        self.assertNotIn("contrasena", r.model_dump())
        carga = leer_token_acceso(r.token_acceso)                     # RN-008: lleva usuario y rol
        self.assertEqual((carga["sub"], carga["rol"]), ("1", "Coordinador"))
        sesion = self.db.get(Sesion, carga["sid"])
        self.assertEqual(sesion.token_renovacion_hash, hash_token(r.token_renovacion))  # solo el hash

    def test_contrasena_errada_es_401(self):
        with self.assertRaises(NoAutenticadoError) as ctx:
            self.login(contrasena="Otra-clave1")
        self.assertEqual(ctx.exception.codigo, "AUT_CREDENCIALES_INVALIDAS")
        self.assertEqual(ctx.exception.campo, "contrasena")

    def test_correo_inexistente_da_el_mismo_error(self):
        with self.assertRaises(NoAutenticadoError) as ctx:
            self.login(correo="nadie@construpro.co")
        self.assertEqual(ctx.exception.mensaje,
                         "Las credenciales enviadas no coinciden con ningún usuario activo.")

    def test_rn006_usuario_inactivo_no_entra(self):
        with self.assertRaises(NoAutenticadoError) as ctx:
            self.login(correo="ana@construpro.co")
        self.assertEqual(ctx.exception.codigo, "AUT_USUARIO_INACTIVO")
        self.assertEqual(ctx.exception.regla, "RN-006")

    # ── RN-007 bloqueo ─────────────────────────────────────

    def test_rn007_cinco_intentos_fallidos_bloquean_la_cuenta(self):
        for _ in range(settings.MAX_INTENTOS_FALLIDOS):
            with self.assertRaises(NoAutenticadoError):
                self.login(contrasena="Mala-clave1")
        with self.assertRaises(NoAutenticadoError) as ctx:          # ni con la correcta
            self.login()
        self.assertEqual(ctx.exception.regla, "RN-007")
        usuario = self.db.get(Usuario, 1)
        usuario.bloqueado_hasta = ahora_utc_sin_zona() - timedelta(seconds=1)   # pasa el tiempo
        self.db.commit()
        self.assertEqual(self.login().usuario_id, "1")

    def test_rn007_un_ingreso_correcto_reinicia_el_conteo(self):
        for _ in range(settings.MAX_INTENTOS_FALLIDOS - 1):
            with self.assertRaises(NoAutenticadoError):
                self.login(contrasena="Mala-clave1")
        self.login()
        self.assertEqual(self.db.get(Usuario, 1).intentos_fallidos, 0)

    # ── Validación del token en cada petición (caso 5) ─────

    def test_token_valido_identifica_al_usuario(self):
        r = self.login()
        actual = obtener_usuario_actual(credenciales(r.token_acceso), self.db)
        self.assertEqual((actual.usuario_id, actual.rol), ("1", "Coordinador"))

    def test_sin_token_es_401(self):
        with self.assertRaises(NoAutenticadoError):
            obtener_usuario_actual(None, self.db)

    def test_token_vencido_o_alterado_es_401(self):
        r = self.login()
        carga = leer_token_acceso(r.token_acceso)
        carga["exp"] = carga["iat"] - 10
        vencido = jwt.encode(carga, settings.JWT_SECRETO, algorithm=ALGORITMO)
        with self.assertRaises(NoAutenticadoError) as ctx:
            obtener_usuario_actual(credenciales(vencido), self.db)
        self.assertEqual(ctx.exception.regla, "RN-008")
        with self.assertRaises(NoAutenticadoError):
            obtener_usuario_actual(credenciales(r.token_acceso + "x"), self.db)

    def test_rn010_se_usa_el_rol_vigente(self):
        r = self.login()
        self.db.get(Usuario, 1).rol = self.director        # le cambian el rol después del login
        self.db.commit()
        self.assertEqual(obtener_usuario_actual(credenciales(r.token_acceso), self.db).rol, "Director")

    def test_rn009_inactivar_invalida_los_tokens(self):
        r = self.login()
        UsuarioService(UsuarioRepository(self.db)).cambiar_estado(
            1, EstadoUsuarioUpdate(estado="inactivo"), usuario_actual_id="99")
        with self.assertRaises(NoAutenticadoError) as ctx:
            obtener_usuario_actual(credenciales(r.token_acceso), self.db)
        self.assertEqual(ctx.exception.codigo, "AUT_USUARIO_INACTIVO")
        UsuarioService(UsuarioRepository(self.db)).cambiar_estado(
            1, EstadoUsuarioUpdate(estado="activo"), usuario_actual_id="99")
        with self.assertRaises(NoAutenticadoError) as ctx:     # reactivado: el token viejo no sirve
            obtener_usuario_actual(credenciales(r.token_acceso), self.db)
        self.assertEqual(ctx.exception.regla, "RN-009")

    # ── Renovación (caso 2) y logout ───────────────────────

    def test_refresh_entrega_nuevos_tokens(self):
        r = self.login()
        nuevo = self.servicio.renovar(RenovarDatos(token_renovacion=r.token_renovacion))
        self.assertNotEqual(nuevo.token_renovacion, r.token_renovacion)
        self.assertNotEqual(nuevo.token_acceso, r.token_acceso)      # aunque sea el mismo segundo
        with self.assertRaises(NoAutenticadoError):            # el de renovación anterior ya no sirve
            self.servicio.renovar(RenovarDatos(token_renovacion=r.token_renovacion))

    def test_refresh_con_token_invalido_o_vencido(self):
        r = self.login()
        with self.assertRaises(NoAutenticadoError):
            self.servicio.renovar(RenovarDatos(token_renovacion="token-que-no-existe"))
        sesion = self.db.get(Sesion, leer_token_acceso(r.token_acceso)["sid"])
        sesion.expira_renovacion = ahora_utc_sin_zona() - timedelta(seconds=1)
        self.db.commit()
        with self.assertRaises(NoAutenticadoError) as ctx:
            self.servicio.renovar(RenovarDatos(token_renovacion=r.token_renovacion))
        self.assertEqual(ctx.exception.regla, "RN-008")

    def test_logout_invalida_el_token(self):
        r = self.login()
        actual = obtener_usuario_actual(credenciales(r.token_acceso), self.db)
        self.servicio.cerrar_sesion(actual.sesion_id)
        with self.assertRaises(NoAutenticadoError):
            obtener_usuario_actual(credenciales(r.token_acceso), self.db)
        with self.assertRaises(NoAutenticadoError):
            self.servicio.renovar(RenovarDatos(token_renovacion=r.token_renovacion))


if __name__ == "__main__":
    unittest.main()
