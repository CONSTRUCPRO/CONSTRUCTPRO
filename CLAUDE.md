# Contexto del proyecto CONSTRUCTPRO (para el asistente de Alejandro)

> Este documento lo preparó el asistente de Jaime para que ambos asistentes trabajen con
> las mismas decisiones. Si algo aquí contradice lo que ves en el repositorio, el
> repositorio manda: avísale a tu usuario y verifica antes de actuar.

## 1. Proyecto y equipo

- **Proyecto:** ConstruPro: API REST (FastAPI) para gestionar el abastecimiento de materiales
  de obras de construcción. Asignatura Web Services, UTS, docente Edward Villamizar.
- **Equipo:** Jaime Almeida (GitHub `JM-WATF`) y Diego Alejandro Ayala (GitHub `Alejandro2223`).
- **Repositorio:** `CONSTRUCPRO/CONSTRUCTPRO` (organización CONSTRUCPRO).
- **Fuentes de verdad, en este orden:**
  1. Los issues de GitHub de cada historia de usuario (HU): endpoints, JSON esperado,
     casos de prueba y Definición de Hecho.
  2. El documento del parcial "ConstruPro": reglas de negocio RN-001 a RN-140 (Componente E),
     catálogo de códigos de error (Tabla 57) y sobre JSON estándar (Componente F).
  3. Las guías del profesor. La guía **setup-entorno** define la estructura del proyecto.
     Las guías del **taller FastAPI** (carpetas en la raíz, datos en memoria) eran un ejercicio
     de aprendizaje y **no** son la estructura del proyecto.

## 2. Reparto de historias de usuario (Sprint 1)

| Jaime (JM-WATF) | Alejandro (Alejandro2223) |
|---|---|
| #3 HU-03 Roles y Permisos | #6 HU-09 Catálogo de Materiales |
| #2 HU-01 Gestión de Usuarios | #7 HU-10 Gestión de Proveedores |
| #1 HU-02 Autenticación con Token | #8 HU-11 Relación Material–Proveedor |
| #4 HU-05 Gestión de Proyectos | #9 HU-12 Registro de Solicitud de Materiales |
| #5 HU-06 Presupuesto del Proyecto | #10 HU-16 Comparativo de Precios |
| #12 HU-20 Decisión de Aprobación | #11 HU-17 Generación de Cotización |
| #13 HU-21 Generación de Orden de Compra | #14 HU-23 Registro y Control de Pagos |
| | #15 HU-29 Entradas y Salidas de Inventario |

Orden de trabajo de Jaime: base común → HU-03 → HU-01 → HU-02 → HU-05 → HU-06 → HU-20 → HU-21.

**Dependencias cruzadas (hay que coordinarlas):**
- HU-12 (solicitudes, Alejandro) necesita **proyectos** (HU-05, Jaime) para RN-041 (proyecto activo).
- HU-20 (aprobación, Jaime) necesita **cotizaciones** (HU-17, Alejandro).
- HU-21 (orden de compra, Jaime) necesita **proveedores** (HU-10, Alejandro) para RN-039.
- HU-23 (pagos, Alejandro) necesita **órdenes de compra** (HU-21, Jaime).
- Todas las HU usan la **base común** (sección 5) y, al final, la autenticación de HU-02.

## 3. Ramas y flujo de trabajo (obligatorio)

- `main` y `staging`: solo para entregas. Nunca se trabaja ni se hace push directo ahí.
- `testing`: rama donde el compañero prueba las HU ya integradas. Solo recibe PR desde `development`.
- `development`: integración. **No se hace push directo**: todo entra por pull request.
- Una rama por HU, que sale de `development` actualizado:
  `feature/hu-XX-nombre-corto` (ej.: `feature/hu-09-materiales`).

Ciclo de cada HU:
1. `git checkout development` + `git pull` → `git checkout -b feature/hu-XX-...`
2. Programar con commits pequeños y claros, en español.
3. `git push -u origin feature/hu-XX-...` → abrir el PR hacia `development` con "Refs #N" en la descripción.
4. El **otro integrante** revisa el PR (código, pruebas unitarias y migración) y hace el merge a
   `development`, borrando la rama de la HU.
5. Se abre el PR **`development` → `testing`** y se fusiona (sin borrar `development`). Puede llevar
   varias HU juntas.
6. El otro integrante **prueba en la rama `testing`** (`git checkout testing`, `git pull`,
   `pip install -r requirements.txt`, `alembic upgrade head`, `uvicorn main:app --reload`) siguiendo
   los "Casos de Prueba Funcional" del issue, con pantallazos en `/docs` (Swagger). Si algo falla, se
   corrige con una rama nueva desde `development` y se repite el ciclo.
7. Si las pruebas pasan, la HU queda en Done.

**Acuerdo vigente:** las pruebas funcionales cruzadas (paso 6) **se hacen al final**, todas juntas. Por
ahora cada HU se lleva hasta `testing` y su tarjeta queda en la columna Testing.

Columnas del tablero (GitHub Project). Las tarjetas se mueven a mano:
- **Todo** → **In Progress** (rama creada)
- → **Gestión de integración**: desde que se abre el PR a `development` hasta que la HU llega a `testing`
- → **Testing**: la HU ya está en `testing`, esperando la prueba del compañero
- → **Done**: pruebas aprobadas con pantallazos

Forma de trabajo de Jaime con su asistente: por defecto el asistente **no escribe en el repo**; le pasa
el código y los comandos explicados, y Jaime los copia, pega y ejecuta. Cuando Jaime lo delega, el
asistente escribe y hace commits/PR con la cuenta de Jaime, **sin líneas de coautor** (solo debe quedar
el registro de Jaime). Respeta la preferencia de tu propio usuario.

## 4. Arquitectura acordada

Stack: Python, FastAPI, Pydantic v2, SQLAlchemy 2.x, **SQLite** (`DATABASE_URL` en `.env`), Alembic, Uvicorn.

```
main.py                    # crea la app; registra routers automáticamente
app/
  core/                    # config.py (settings), database.py (engine, SessionLocal, Base, get_db)
  api/                     # routers: <modulo>_router.py con una variable `router`
  schemas/                 # Pydantic: <modulo>.py con XxxCreate / XxxUpdate / XxxResponse
  services/                # casos de uso: <modulo>_service.py (sin FastAPI, sin HTTP)
  repositories/            # acceso a datos con Session de SQLAlchemy: <modulo>_repository.py
  domain/                  # modelos SQLAlchemy (heredan de Base) + reglas de negocio + excepciones
alembic/                   # migraciones; env.py importa solo todos los módulos de app/domain/
```

Reglas de la arquitectura:
- **Registro automático de routers:** `app/api/__init__.py` importa todos los módulos de `app/api/`
  y registra los que tengan una variable `router`. **No se toca `main.py`** para agregar módulos.
- **Modelos y Alembic:** cada modelo SQLAlchemy va en `app/domain/<modulo>.py` y hereda de
  `app.core.database.Base`. Alembic los detecta solo.
- **Las reglas de negocio (RN-xxx) viven en el dominio** (métodos de la entidad o funciones de dominio)
  y se disparan desde el servicio. El router no decide nada, y el repositorio no valida reglas.
- **El servicio no importa FastAPI ni lanza HTTPException.** Lanza excepciones de dominio
  (sección 5) y la capa API las traduce a HTTP.
- **Rutas:** prefijo `/api/v1/<recurso>` en plural y kebab-case (`/api/v1/ordenes-compra`), tal como
  aparecen en cada issue.
- **Convenciones JSON (Componente F):** campos en snake_case y en español, ids devueltos como
  **texto** con sufijo `_id` (`material_id`, no `id`), fechas ISO 8601 UTC, dinero con 2 decimales
  más el campo `moneda: "COP"`, campos vacíos como `null` (no se omiten), colecciones siempre como
  arreglo y paginación en `meta.paginacion`.
- **Nunca se suben** `.env`, `dev.db`, `venv/` ni `__pycache__/` (ya están en `.gitignore`).

## 5. Base común (integrada en `development`, PR #18)

Todas las HU la usan. **No crear versiones propias de esto.** Si el nombre exacto de una función
cambia, manda el código del repo.

- `app/domain/excepciones.py`: conserva los nombres y el orden de parámetros de las excepciones de
  Alejandro y agrega las que faltaban. **El servicio y el dominio lanzan estas excepciones; nunca HTTPException.**

  | Excepción | HTTP | Código por defecto | Firma |
  |---|---|---|---|
  | `ReglaNegocioError` | 422 | `NEG_REGLA_INCUMPLIDA` | `(regla, mensaje, campo=None, codigo=None, mensaje_general=None)` |
  | `RecursoNoEncontradoError` | 404 | `REC_NO_ENCONTRADO` | `(mensaje, campo=None)` |
  | `RecursoDuplicadoError` | 409 | `REC_DUPLICADO` | `(regla, mensaje, campo=None)` |
  | `ConflictoEstadoError` | 409 | `NEG_CONFLICTO_ESTADO` | `(regla, mensaje, campo=None, codigo=None, mensaje_general=None)` |
  | `PermisoDenegadoError` | 403 | `AUT_SIN_PERMISO` | `(mensaje, regla=None, campo="rol", codigo=None)` |
  | `NoAutenticadoError` | 401 | `AUT_CREDENCIALES_INVALIDAS` | `(mensaje, campo=None, codigo=None)` |

  Con `codigo=` se usa un código específico del catálogo, por ejemplo
  `ReglaNegocioError("RN-122", "...", codigo="NEG_STOCK_INSUFICIENTE")`. El mensaje general sale solo
  de `CATALOGO_MENSAJES` (Tabla 57). `NEG_REGLA_INCUMPLIDA` y `NEG_CONFLICTO_ESTADO` son genéricos,
  agregados para las reglas que no tienen un código propio.
- `app/core/respuestas.py`: `respuesta_exitosa(datos=None, mensaje="...", paginacion=None)` arma el
  sobre `{exito, codigo, mensaje, datos, errores, meta{timestamp, version, peticion_id, paginacion}}`.
  `construir_paginacion(pagina, por_pagina, total_registros)` arma `meta.paginacion`.
  `fecha_iso(valor)` formatea fechas: datetime → `"2026-09-14T15:04:32Z"`, date → `"2026-09-14"`, None → None.
- `app/schemas/respuesta.py`: `Respuesta[T]`, el modelo Pydantic genérico del sobre, para Swagger.
  Se usa así: `@router.post("", response_model=Respuesta[MaterialResponse], status_code=201)` y
  `response_model=Respuesta[list[MaterialResponse]]`.
- `app/core/errores.py`: `registrar_manejadores(app)`, que se llama una vez en `main.py`. Convierte en sobre
  estándar las excepciones de negocio, la validación de Pydantic (422 `VAL_CAMPO_REQUERIDO` o
  `VAL_FORMATO_INVALIDO`, y 400 si el JSON viene mal formado; si un validador lanza
  `ValueError("mensaje en español")`, ese texto llega al cliente), los 404 de ruta y los errores inesperados
  (500 `ERR_INTERNO`, con el detalle solo en el log junto al `peticion_id`). También pone el encabezado
  `X-Peticion-Id`. **Los routers no llevan try/except**: llaman al servicio y devuelven `respuesta_exitosa(...)`.
- `app/core/seguridad.py` (**HU-02, ya con JWT**): `obtener_usuario_actual` lee el encabezado
  `Authorization: Bearer <token>` (en Swagger: botón **Authorize**), valida firma y vigencia (RN-008),
  que la sesión siga abierta (tabla `sesiones`, logout), que el usuario esté activo (RN-006) y su
  `version_sesion` (RN-009), y devuelve `UsuarioActual(usuario_id, rol, sesion_id)` con el **rol vigente
  de la BD** (RN-010). `requiere_rol("Director", regla="RN-022")` y `requiere_permiso("Modulo", "accion")`
  responden 403 si no corresponde. **El encabezado temporal `X-Rol` ya no existe.** Login:
  `POST /api/v1/auth/login` (también `/refresh` y `/logout`). La migración de la HU-02 crea el usuario
  inicial `admin@construpro.co` / `Admin2026` (rol Administrador) para el primer login.

  ```python
  @router.post("", response_model=Respuesta[MaterialResponse], status_code=201)
  def crear_material(datos: MaterialCreate,
                     db: Session = Depends(get_db),
                     usuario: UsuarioActual = Depends(obtener_usuario_actual)):
      material = MaterialService(MaterialRepository(db)).crear(datos)
      return respuesta_exitosa(material, "Material registrado correctamente.")
  ```

**Migraciones de Alembic, para no chocar:** antes de generar una migración, hacer pull de
`development`. Si al integrar quedan dos "heads" (`alembic heads` muestra dos), se resuelve con
`alembic merge heads -m "merge"`. Cada PR incluye su propia migración.

## 6. Estado del proyecto (actualizado el 23-11-2026)

El código del taller que estaba en la raíz (`api/`, `service/`, `domain/`, `repository/`) **ya se eliminó**
en el PR de la HU-09. Todo vive en `app/`.

| HU | Responsable | Estado | PR |
|---|---|---|---|
| Base del proyecto, schemas y base común | Jaime | En `development` y `testing` | #16, #17, #18 |
| HU-03 Roles y Permisos (#3) | Jaime | En `testing` | #19 |
| HU-09 Catálogo de Materiales (#6) | Alejandro | En `testing` | #20 |
| HU-10 Gestión de Proveedores (#7) | Alejandro | En `testing` | #21 |
| HU-01 Gestión de Usuarios (#2) | Jaime | En `testing` | #23 |
| HU-11 Relación Material–Proveedor (#8) | Alejandro | En `testing` | #24 |
| HU-05 Gestión de Proyectos (#4) | Jaime | En `testing` | #28 |
| HU-06 Presupuesto del Proyecto (#5) | Jaime | En `testing` | #30 |
| HU-02 Autenticación con Token (#1) | Jaime | En `testing` | #32 |
| HU-12 Registro de Solicitud de Materiales (#9) | Alejandro | En `testing` | #35 |
| HU-16 Comparativo de Precios (#10) | Alejandro | En `testing` | #37 |
| HU-17 Generación de Cotización (#11) | Alejandro | En `testing` | #39 |
| HU-20 Decisión de Aprobación (#12) | Jaime | PR abierto | — |

PR de `development` → `testing`: #22, #25, #29, #31, #34, #36, #38 y #40 (uno por cada integración).

**Migraciones (un solo head):** `a3f1c9e2b7d4` HU-03 → `246dbe7806b2` HU-09 → `c6694196e06d` HU-10 →
`173f32cdf2cd` HU-01 → `9dcb06782bba` HU-11 → `e4a0a96d3d9a` permisos Coordinador → `02a74136ff30` HU-05 →
`4a68f0bd7455` HU-06 → `323d9a89d28e` HU-02 → `7fb1455f410f` HU-12 → `6e5fa281e3b8` HU-16 →
`a7acae97448c` HU-17 → `f2c2575f005d` HU-20. Antes de generar una migración nueva, hacer pull de
`development` para colgarla del último head.

**Tablas que usan otras HU** (no reimplementar sus reglas: llamar a los métodos del dominio):

| Tabla | PK | Estado | Métodos útiles |
|---|---|---|---|
| `roles`, `permisos_rol` | `id` | `activo` / `inactivo` | `Rol.tiene_permiso(modulo, accion)`; en routers `requiere_permiso("Modulo", "accion")` |
| `usuarios` | `id` | `activo` / `inactivo` | `Usuario.verificar_contrasena()` (para la HU-02), `version_sesion` (RN-009) |
| `categorias`, `materiales` | `id` | `activo` / `inactivo` | `Material.verificar_disponible()` (RN-034, para HU-12 y HU-17) |
| `proveedores` | `id` | `activo` / `inactivo` | `Proveedor.verificar_puede_recibir_ordenes()` (RN-039, para HU-21) |
| `proveedor_material` | `id` | `disponible` (bool) | Base del comparativo de precios (HU-16) |
| `proyectos` | `id` | `activo` / `suspendido` / `finalizado` | `Proyecto.verificar_admite_solicitudes()` (RN-041, RN-020, RN-021), `verificar_editable()` (RN-019) |
| `presupuestos` | `id` (uno por proyecto) | — | `proyecto.presupuesto`: `verificar_saldo()` (RN-066), `comprometer()` (RN-068), `liberar()` (RN-069), `ejecutar()` (pagos, HU-23) |
| `solicitudes`, `solicitud_detalles` | `id` | `pendiente` / `anulada` | `Solicitud.es_pendiente()`, `verificar_pendiente()` |
| `comparativos`, `comparativo_ofertas` | `id` | `abierto` / `seleccionado` | Foto de ofertas; `ahorro` (RN-060) |
| `cotizaciones`, `cotizacion_detalles` | `id` | `Generada` / `Enviada` / `Aprobada` / `Rechazada` / `Anulada` | Origen de la orden de compra (HU-21): la cotización `Aprobada` trae proveedor y detalle |
| `aprobaciones` | `id` | `En revisión` / `Aprobada` / `Rechazada` / `Anulada` | Creada en la HU-17 y ampliada en la HU-20 (aprobador, rol, monto autorizado, fecha, motivo) |

**Pendientes conocidos:**
1. `ProveedorRepository.contar_ordenes_abiertas()` devuelve 0 de forma fija (`PENDIENTE HU-21`). Jaime
   lo implementa en la HU-21 para activar la RN-040.
2. Permisos del Coordinador: resuelto (PR #27 y #33). Materiales, proveedores y ofertas usan
   `requiere_permiso("Materiales", ...)`.
3. Formato del sobre: el Componente F del parcial y todos los issues usan `exito`, `codigo`, `mensaje`,
   `datos`, `errores` y `meta`. Alejandro recuerda que el profesor pidió `success`/`message`/`data`.
   **No se cambia nada hasta tener la plantilla exacta del profesor.** Si cambia, se hace solo en la base
   común (`app/core/respuestas.py`, `app/schemas/respuesta.py`, `app/core/errores.py`) y en los
   ejemplos de error de Swagger de los routers.
4. Siguientes HU: Jaime → HU-21 Orden de Compra (desbloquea la HU-23 de Alejandro).
   Alejandro → HU-29 (Inventario) y HU-23 (Pagos, cuando exista la HU-21).
5. Tope de aprobación del Coordinador (RN-076): `TOPE_APROBACION_COORDINADOR` en `.env`
   (10.000.000 COP por defecto). Por encima solo aprueba el Director.

**Notas de entorno:**
- Después de un pull que cambie `requirements.txt`: `pip install -r requirements.txt` (con el venv activo)
  y luego `alembic upgrade head`.
- En ramas feature, usar `git pull --no-edit` para que no se abra el editor del mensaje de merge.
- Si git dice "Deletion of directory ... failed" (OneDrive), responder `n`.
- Si VS Code dice "couldn't find remote ref feature/...", es que el PR ya se fusionó y se borró la rama:
  `git checkout development` + `git pull origin development` + `git branch -d feature/...`.

## 7. Al empezar cada sesión

1. `git checkout development` + `git pull` para ver lo que integró el compañero (y, si cambió
   `requirements.txt` o hay migraciones nuevas, `pip install -r requirements.txt` + `alembic upgrade head`).
2. Revisar los PR abiertos: el compañero puede estar esperando una revisión.
3. Leer el issue de la HU antes de programar.

## 8. Patrón de referencia: así se escribe TODO módulo

Es un módulo de ejemplo ("Herramienta"), probado de punta a punta con la base común: migración de
Alembic, 201, 409, 422, 403, 404, 204 y paginación. **No existe en el proyecto.** Es la plantilla:
cada HU replica esta forma, con sus propias entidades, reglas RN-xxx, códigos y rutas del issue.
Los RN-XXX/YYY/ZZZ del ejemplo son marcadores.

Puntos clave del patrón:
- La entidad SQLAlchemy contiene sus reglas como métodos (`validar_precio`, `actualizar_precio`).
- El esquema de salida tiene `desde_modelo(...)`, que convierte la entidad: id → `xxx_id` como texto,
  Decimal → float, fechas con `fecha_iso`, y agrega `moneda`.
- El repositorio recibe la `Session` y no valida reglas. `listar` devuelve `(items, total)` para paginar en la BD.
- El servicio recibe el repositorio, valida y orquesta, y devuelve esquemas de salida. Solo lanza excepciones de dominio.
- El router crea el servicio con `Depends(obtener_servicio)`, protege con `obtener_usuario_actual` o
  `requiere_rol(...)` y devuelve `respuesta_exitosa(...)`. Sin try/except.
- Dinero: `Numeric(14, 2)` en la BD. Fechas: `DateTime` guardado en UTC.
- Migración: `alembic revision --autogenerate -m "crea tabla xxx"` y luego `alembic upgrade head`.
  Revisar el archivo generado en `alembic/versions/` antes de hacer commit.

### `app/domain/herramienta.py`

```python
# app/domain/herramienta.py
# CAPA DOMINIO: la entidad (tabla) y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.excepciones import ConflictoEstadoError, ReglaNegocioError


class Herramienta(Base):
    __tablename__ = "herramientas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    precio_referencia: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    estado: Mapped[str] = mapped_column(String(20), default="activo")
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # ── Reglas de negocio de la entidad ───────────────────
    @staticmethod
    def validar_precio(precio: float) -> None:
        if precio <= 0:  # RN-XXX
            raise ReglaNegocioError("RN-XXX", "El precio de referencia debe ser mayor que cero.",
                                    campo="precio_referencia")

    def actualizar_precio(self, nuevo: float) -> None:
        if self.estado == "inactivo":
            raise ConflictoEstadoError("RN-YYY", "No se puede modificar una herramienta inactiva.",
                                       campo="estado")
        self.validar_precio(nuevo)
        self.precio_referencia = Decimal(str(round(nuevo, 2)))

    def inactivar(self) -> None:
        self.estado = "inactivo"
```

### `app/schemas/herramienta.py`

```python
# app/schemas/herramienta.py
# Esquemas Pydantic: validan la ENTRADA y definen la forma de la SALIDA (datos del sobre).
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.herramienta import Herramienta


class HerramientaCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    precio_referencia: float

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return v.strip()


class PrecioUpdate(BaseModel):
    precio_referencia: float


class HerramientaResponse(BaseModel):
    herramienta_id: str          # ids SIEMPRE como texto y con sufijo _id
    nombre: str
    precio_referencia: float
    moneda: str = "COP"          # dinero SIEMPRE acompañado de la moneda
    estado: str
    fecha_registro: Optional[str]  # ISO 8601 UTC

    @classmethod
    def desde_modelo(cls, h: Herramienta) -> "HerramientaResponse":
        return cls(
            herramienta_id=str(h.id),
            nombre=h.nombre,
            precio_referencia=float(h.precio_referencia),
            estado=h.estado,
            fecha_registro=fecha_iso(h.fecha_registro),
        )
```

### `app/repositories/herramienta_repository.py`

```python
# app/repositories/herramienta_repository.py
# CAPA REPOSITORIO: solo guarda y consulta. Sin reglas de negocio, sin HTTP.
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.herramienta import Herramienta


class HerramientaRepository:

    def __init__(self, db: Session):
        self.db = db

    def obtener_por_id(self, herramienta_id: int) -> Optional[Herramienta]:
        return self.db.get(Herramienta, herramienta_id)

    def existe_nombre(self, nombre: str, excluir_id: Optional[int] = None) -> bool:
        consulta = select(Herramienta.id).where(func.lower(Herramienta.nombre) == nombre.lower())
        if excluir_id is not None:
            consulta = consulta.where(Herramienta.id != excluir_id)
        return self.db.scalar(consulta) is not None

    def listar(self, estado: Optional[str], nombre: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[Herramienta], int]:
        consulta = select(Herramienta)
        if estado:
            consulta = consulta.where(Herramienta.estado == estado)
        if nombre:
            consulta = consulta.where(Herramienta.nombre.ilike(f"%{nombre}%"))
        total = self.db.scalar(select(func.count()).select_from(consulta.subquery()))
        items = self.db.scalars(
            consulta.order_by(Herramienta.id).offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).all()
        return list(items), total

    def guardar(self, herramienta: Herramienta) -> Herramienta:
        self.db.add(herramienta)
        self.db.commit()
        self.db.refresh(herramienta)
        return herramienta
```

### `app/services/herramienta_service.py`

```python
# app/services/herramienta_service.py
# CAPA SERVICIO: orquesta los casos de uso. No importa FastAPI ni lanza HTTPException:
# lanza excepciones de dominio y la capa API (app/core/errores.py) las traduce.
from typing import Optional

from app.core.respuestas import construir_paginacion
from app.domain.excepciones import RecursoDuplicadoError, RecursoNoEncontradoError
from app.domain.herramienta import Herramienta
from app.repositories.herramienta_repository import HerramientaRepository
from app.schemas.herramienta import HerramientaCreate, HerramientaResponse, PrecioUpdate


class HerramientaService:

    def __init__(self, repo: HerramientaRepository):
        self.repo = repo  # inyección de dependencia

    def _buscar(self, herramienta_id: int) -> Herramienta:
        h = self.repo.obtener_por_id(herramienta_id)
        if not h:
            raise RecursoNoEncontradoError(
                f"No existe una herramienta con el identificador {herramienta_id}.",
                campo="herramienta_id")
        return h

    def crear(self, datos: HerramientaCreate) -> HerramientaResponse:
        if self.repo.existe_nombre(datos.nombre):
            raise RecursoDuplicadoError("RN-ZZZ", f"Ya existe la herramienta '{datos.nombre}'.",
                                        campo="nombre")
        Herramienta.validar_precio(datos.precio_referencia)        # regla del dominio
        h = Herramienta(nombre=datos.nombre, precio_referencia=datos.precio_referencia)
        return HerramientaResponse.desde_modelo(self.repo.guardar(h))

    def obtener(self, herramienta_id: int) -> HerramientaResponse:
        return HerramientaResponse.desde_modelo(self._buscar(herramienta_id))

    def listar(self, estado: Optional[str], nombre: Optional[str],
               pagina: int, por_pagina: int) -> tuple[list[HerramientaResponse], dict]:
        items, total = self.repo.listar(estado, nombre, pagina, por_pagina)
        return ([HerramientaResponse.desde_modelo(h) for h in items],
                construir_paginacion(pagina, por_pagina, total))

    def actualizar_precio(self, herramienta_id: int, datos: PrecioUpdate) -> HerramientaResponse:
        h = self._buscar(herramienta_id)
        h.actualizar_precio(datos.precio_referencia)              # regla del dominio
        return HerramientaResponse.desde_modelo(self.repo.guardar(h))

    def inactivar(self, herramienta_id: int) -> None:
        h = self._buscar(herramienta_id)
        h.inactivar()
        self.repo.guardar(h)
```

### `app/api/herramienta_router.py`

```python
# app/api/herramienta_router.py
# CAPA API: recibe la petición, llama al servicio y devuelve el sobre estándar.
# Sin try/except (los errores los convierte app/core/errores.py) y sin lógica de negocio.
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.respuestas import respuesta_exitosa
from app.core.seguridad import UsuarioActual, obtener_usuario_actual, requiere_rol
from app.repositories.herramienta_repository import HerramientaRepository
from app.schemas.herramienta import HerramientaCreate, HerramientaResponse, PrecioUpdate
from app.schemas.respuesta import Respuesta
from app.services.herramienta_service import HerramientaService

router = APIRouter(prefix="/api/v1/herramientas", tags=["Herramientas"])


def obtener_servicio(db: Session = Depends(get_db)) -> HerramientaService:
    return HerramientaService(HerramientaRepository(db))


@router.post("", response_model=Respuesta[HerramientaResponse],
             status_code=status.HTTP_201_CREATED,
             summary="Registrar herramienta")
def crear(datos: HerramientaCreate,
          servicio: HerramientaService = Depends(obtener_servicio),
          usuario: UsuarioActual = Depends(requiere_rol("Administrador", "Coordinador"))):
    return respuesta_exitosa(servicio.crear(datos), "Herramienta registrada correctamente.")


@router.get("", response_model=Respuesta[list[HerramientaResponse]],
            summary="Consultar herramientas (paginado)")
def listar(estado: Optional[str] = None,
           nombre: Optional[str] = None,
           pagina: int = Query(1, ge=1),
           por_pagina: int = Query(10, ge=1, le=100),
           servicio: HerramientaService = Depends(obtener_servicio),
           usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    items, paginacion = servicio.listar(estado, nombre, pagina, por_pagina)
    return respuesta_exitosa(items, "Consulta realizada correctamente.", paginacion)


@router.get("/{herramienta_id}", response_model=Respuesta[HerramientaResponse],
            summary="Detalle de una herramienta")
def obtener(herramienta_id: int,
            servicio: HerramientaService = Depends(obtener_servicio),
            usuario: UsuarioActual = Depends(obtener_usuario_actual)):
    return respuesta_exitosa(servicio.obtener(herramienta_id), "Consulta realizada correctamente.")


@router.patch("/{herramienta_id}/precio", response_model=Respuesta[HerramientaResponse],
              summary="Actualizar precio de referencia")
def actualizar_precio(herramienta_id: int, datos: PrecioUpdate,
                      servicio: HerramientaService = Depends(obtener_servicio),
                      usuario: UsuarioActual = Depends(requiere_rol("Administrador", "Coordinador"))):
    return respuesta_exitosa(servicio.actualizar_precio(herramienta_id, datos),
                             "Precio actualizado correctamente.")


@router.patch("/{herramienta_id}/inactivar", status_code=status.HTTP_204_NO_CONTENT,
              summary="Inactivar herramienta")
def inactivar(herramienta_id: int,
              servicio: HerramientaService = Depends(obtener_servicio),
              usuario: UsuarioActual = Depends(requiere_rol("Administrador"))):
    servicio.inactivar(herramienta_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

