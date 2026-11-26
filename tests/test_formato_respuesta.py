# tests/test_formato_respuesta.py
# Pruebas del formato de respuesta pedido por el docente (issue #54): toda respuesta con cuerpo
# tiene exactamente las claves message, data y success, en ese orden.
#
# Estas pruebas pasan por la app completa (middleware, routers, manejadores de errores), como
# una petición real, pero sin levantar el servidor: se llama a la app ASGI directamente.
# Usan una BD SQLite en memoria: no tocan dev.db.
# Ejecutar desde la raíz del proyecto:  python -m unittest discover -s tests -v
import asyncio
import json
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.schemas.material import MaterialResponse
from app.api.schemas.respuesta import Pagina, Respuesta
from app.core.database import Base, get_db
from app.core.respuestas import construir_paginacion, respuesta_error, respuesta_exitosa
from app.domain.material import Categoria
from app.domain.rol import PermisoRol, Rol
from app.domain.usuario import Usuario
from main import app

CLAVES = ["message", "data", "success"]


def llamar(metodo: str, ruta: str, cuerpo=None, token: str = None, crudo: bytes = None):
    """
    Hace una petición a la app sin servidor (protocolo ASGI) y devuelve
    (código HTTP, encabezados, JSON de la respuesta o None si no tiene cuerpo).
    """
    ruta, _, consulta = ruta.partition("?")
    datos = crudo if crudo is not None else (json.dumps(cuerpo).encode() if cuerpo is not None else b"")
    encabezados = [(b"host", b"prueba"), (b"content-type", b"application/json")]
    if token:
        encabezados.append((b"authorization", f"Bearer {token}".encode()))
    alcance = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
               "method": metodo, "scheme": "http", "path": ruta, "raw_path": ruta.encode(),
               "query_string": consulta.encode(), "root_path": "", "headers": encabezados,
               "client": ("prueba", 1), "server": ("prueba", 80)}

    async def ejecutar():
        mensajes, leido = [], False

        async def recibir():
            nonlocal leido
            if not leido:
                leido = True
                return {"type": "http.request", "body": datos, "more_body": False}
            return {"type": "http.disconnect"}

        async def enviar(mensaje):
            mensajes.append(mensaje)

        await app(alcance, recibir, enviar)
        return mensajes

    mensajes = asyncio.run(ejecutar())
    inicio = next(m for m in mensajes if m["type"] == "http.response.start")
    cuerpo_resp = b"".join(m.get("body", b"") for m in mensajes if m["type"] == "http.response.body")
    encabezados_resp = {k.decode().lower(): v.decode() for k, v in inicio["headers"]}
    return inicio["status"], encabezados_resp, (json.loads(cuerpo_resp) if cuerpo_resp else None)


class PruebaFuncionesDelSobre(unittest.TestCase):
    """Las funciones de app/core/respuestas.py, sin pasar por HTTP."""

    def test_exito_tiene_solo_las_tres_claves_en_orden(self):
        r = respuesta_exitosa({"material_id": "5"}, "Listo.")
        self.assertEqual(list(r), CLAVES)
        self.assertEqual(r, {"message": "Listo.", "data": {"material_id": "5"}, "success": True})

    def test_listado_paginado_va_dentro_de_data(self):
        r = respuesta_exitosa([{"material_id": "5"}], "Consulta.", construir_paginacion(1, 10, 23))
        self.assertEqual(list(r["data"]), ["registros", "paginacion"])
        self.assertEqual(r["data"]["paginacion"],
                         {"pagina": 1, "por_pagina": 10, "total_registros": 23, "total_paginas": 3})

    def test_error_lleva_codigo_y_errores_en_data(self):
        r = respuesta_error("REC_DUPLICADO", "Ya existe.")
        self.assertEqual(list(r), CLAVES)
        self.assertFalse(r["success"])
        self.assertEqual(r["data"], {"codigo": "REC_DUPLICADO", "errores": []})  # siempre arreglo

    def test_modelo_de_swagger_respeta_el_orden_del_docente(self):
        paginado = respuesta_exitosa([], "Consulta.", construir_paginacion(1, 10, 0))
        modelo = Respuesta[Pagina[MaterialResponse]].model_validate(paginado)
        self.assertEqual(list(modelo.model_dump()), CLAVES)


class PruebaFormatoEnLaApi(unittest.TestCase):
    """Peticiones completas a la app, con una BD en memoria en lugar de dev.db."""

    @classmethod
    def setUpClass(cls):
        # StaticPool: una sola conexión, así todos los hilos de FastAPI ven la misma BD en memoria
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                   poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        with Session(cls.engine) as db:
            rol = Rol(nombre="Coordinador", permisos=[
                PermisoRol(modulo="Materiales", accion="consultar"),
                PermisoRol(modulo="Materiales", accion="crear")])
            db.add_all([rol, Categoria(id=4, nombre="Cementos"),
                        Usuario.registrar("Laura Gómez", "CC", "1098765432", "laura@construpro.co",
                                          "3001234567", "Construpro2026", rol)])
            db.commit()

        def bd_de_prueba():
            db = Session(cls.engine)
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = bd_de_prueba
        _, _, login = llamar("POST", "/api/v1/auth/login",
                             {"correo": "laura@construpro.co", "contrasena": "Construpro2026"})
        cls.login = login
        cls.token = login["data"]["token_acceso"]

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_db, None)
        cls.engine.dispose()

    def crear_material(self, nombre: str, **extra):
        cuerpo = {"nombre": nombre, "unidad": "bulto", "categoria_id": 4, "precio_referencia": 28500}
        cuerpo.update(extra)
        return llamar("POST", "/api/v1/materiales", cuerpo, token=self.token)

    def verificar_error(self, respuesta, http: int, codigo: str):
        """Revisa la forma de un error: success false y el código del catálogo en data."""
        estado, encabezados, cuerpo = respuesta
        self.assertEqual(estado, http)
        self.assertEqual(list(cuerpo), CLAVES)
        self.assertFalse(cuerpo["success"])
        self.assertEqual(cuerpo["data"]["codigo"], codigo)
        self.assertIsInstance(cuerpo["data"]["errores"], list)
        self.assertIn("x-peticion-id", encabezados)       # el rastreo sigue en el encabezado
        return cuerpo

    # ── Respuestas exitosas (casos 1, 2 y 3 del issue) ─────

    def test_login_exitoso(self):
        self.assertEqual(list(self.login), CLAVES)
        self.assertTrue(self.login["success"])
        for campo in ("usuario_id", "rol", "token_acceso", "token_renovacion", "expira_en"):
            self.assertIn(campo, self.login["data"])

    def test_registro_exitoso_es_201(self):
        estado, _, cuerpo = self.crear_material("Arena de río")
        self.assertEqual(estado, 201)
        self.assertEqual(list(cuerpo), CLAVES)
        self.assertEqual(cuerpo["message"], "Material registrado correctamente.")
        self.assertIsInstance(cuerpo["data"]["material_id"], str)

    def test_consulta_paginada(self):
        for nombre in ("Gravilla 1/2", "Ladrillo tolete", "Varilla 3/8"):
            self.crear_material(nombre)
        estado, _, cuerpo = llamar("GET", "/api/v1/materiales?pagina=1&por_pagina=2", token=self.token)
        self.assertEqual(estado, 200)
        self.assertEqual(list(cuerpo), CLAVES)
        self.assertEqual(len(cuerpo["data"]["registros"]), 2)
        paginacion = cuerpo["data"]["paginacion"]
        self.assertEqual((paginacion["pagina"], paginacion["por_pagina"]), (1, 2))
        self.assertGreaterEqual(paginacion["total_registros"], 3)

    def test_raiz_usa_el_sobre_y_health_no_cambia(self):
        _, _, raiz = llamar("GET", "/")
        self.assertEqual(list(raiz), CLAVES)
        _, _, salud = llamar("GET", "/health")
        self.assertEqual(list(salud), ["status", "version", "environment"])   # guía de setup

    # ── Errores (casos 4 a 8 del issue) ─────────────────────

    def test_campo_obligatorio_faltante_es_422(self):
        respuesta = llamar("POST", "/api/v1/materiales",
                           {"nombre": "Cal", "unidad": "bulto", "categoria_id": 4}, token=self.token)
        cuerpo = self.verificar_error(respuesta, 422, "VAL_CAMPO_REQUERIDO")
        self.assertEqual(cuerpo["data"]["errores"][0]["campo"], "precio_referencia")

    def test_registro_duplicado_es_409(self):
        self.crear_material("Cemento blanco")
        cuerpo = self.verificar_error(self.crear_material("Cemento blanco"), 409, "REC_DUPLICADO")
        self.assertEqual(cuerpo["data"]["errores"][0]["regla"], "RN-031")

    def test_sin_token_es_401(self):
        cuerpo = self.verificar_error(llamar("GET", "/api/v1/materiales"), 401,
                                      "AUT_CREDENCIALES_INVALIDAS")
        self.assertEqual(cuerpo["data"]["errores"][0]["campo"], "Authorization")

    def test_recurso_inexistente_es_404(self):
        self.verificar_error(llamar("GET", "/api/v1/materiales/99999", token=self.token),
                             404, "REC_NO_ENCONTRADO")

    def test_json_mal_formado_es_400(self):
        self.verificar_error(llamar("POST", "/api/v1/materiales", crudo=b'{"nombre": "Arena",',
                                    token=self.token), 400, "VAL_FORMATO_INVALIDO")

    def test_ruta_inexistente_y_metodo_no_permitido(self):
        self.verificar_error(llamar("GET", "/api/v1/no-existe"), 404, "REC_NO_ENCONTRADO")
        self.verificar_error(llamar("DELETE", "/api/v1/materiales"), 405, "VAL_FORMATO_INVALIDO")

    def test_error_inesperado_es_500_sin_detalles_tecnicos(self):
        manejador = app.exception_handlers[Exception]
        peticion = Request({"type": "http", "method": "GET", "path": "/api/v1/materiales",
                            "headers": [], "query_string": b""})
        # Igual que en la app real, el manejador se ejecuta mientras se atiende la excepción
        try:
            raise RuntimeError("detalle interno de la BD")
        except RuntimeError as exc:
            with self.assertLogs("construpro", level="ERROR") as log:   # el detalle va al log
                respuesta = asyncio.run(manejador(peticion, exc))
        self.assertIn("detalle interno de la BD", "\n".join(log.output))
        cuerpo = json.loads(respuesta.body)
        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(list(cuerpo), CLAVES)
        self.assertEqual(cuerpo["data"]["codigo"], "ERR_INTERNO")
        self.assertNotIn("detalle interno", respuesta.body.decode())

    # ── Documentación (Swagger) ─────────────────────────────

    def test_ejemplos_de_error_de_swagger_usan_el_formato_nuevo(self):
        ejemplos = [r["content"]["application/json"]["example"]
                    for ruta in app.openapi()["paths"].values()
                    for operacion in ruta.values()
                    for r in operacion.get("responses", {}).values()
                    if "example" in r.get("content", {}).get("application/json", {})]
        self.assertGreater(len(ejemplos), 0)
        for ejemplo in ejemplos:
            self.assertEqual(list(ejemplo), CLAVES)
            self.assertFalse(ejemplo["success"])


if __name__ == "__main__":
    unittest.main()
