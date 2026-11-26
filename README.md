# CONSTRUCTPRO

API REST de **ConstruPro** para gestionar el abastecimiento de materiales de obras de construcción:
proyectos y presupuesto, catálogo de materiales y proveedores, solicitudes, comparativo de precios,
cotizaciones, aprobaciones, órdenes de compra, pagos e inventario.

Asignatura Web Services (UTS) · Equipo: Jaime Almeida (`JM-WATF`) y Diego Alejandro Ayala (`Alejandro2223`).

## Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python ≥ 3.10 (desarrollado con 3.12) |
| Framework | FastAPI |
| Validación | Pydantic v2 |
| ORM | SQLAlchemy 2.x |
| Migraciones | Alembic |
| Base de datos | SQLite (`dev.db`) |
| Servidor | Uvicorn |
| Autenticación | JWT (PyJWT) y contraseñas con bcrypt |

## Puesta en marcha (guía de setup)

### 01. Verificar Python
```bash
python --version        # 3.10 o superior
```

### 02 y 03. Crear y activar el entorno virtual
```bash
python -m venv venv
venv\Scripts\Activate.ps1        # Windows (PowerShell)
venv\Scripts\activate.bat        # Windows (CMD)
source venv/bin/activate         # macOS / Linux
```
El prompt debe empezar con `(venv)`.

### 04. Instalar las dependencias
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 05. Estructura del proyecto (arquitectura de capas)
```
main.py                  punto de entrada: crea la app y registra los routers
app/
  api/                   capa API: routers (endpoints HTTP)
    schemas/             esquemas Pydantic de entrada (XxxCreate) y salida (XxxResponse)
  services/              capa Servicio: casos de uso y orquestación
  domain/                capa Dominio: modelos (tablas) y reglas de negocio (RN-xxx)
  repositories/          capa Repositorio: acceso a datos con SQLAlchemy
  core/                  configuración, base de datos, seguridad, errores y sobre de respuesta
alembic/                 migraciones de la base de datos
tests/                   pruebas unitarias
```
Flujo de una petición: **router → servicio → dominio (reglas) ↔ repositorio (datos)**. El router no
tiene lógica de negocio y el servicio no conoce HTTP: lanza excepciones de dominio que
`app/core/errores.py` convierte en la respuesta de error.

### 06. Variables de entorno
```bash
copy .env.example .env      # Windows
cp .env.example .env        # macOS / Linux
```
El `.env` no se sube al repositorio. Variables principales: `APP_NAME`, `APP_ENV`, `DATABASE_URL`,
`SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` y `TOPE_APROBACION_COORDINADOR`.

### Crear la base de datos (migraciones)
```bash
alembic upgrade head
```
La migración de la HU-02 crea el usuario inicial **`admin@construpro.co` / `Admin2026`** (rol
Administrador). Cambiar esa contraseña fuera de desarrollo.

### 07. Ejecutar el servidor
```bash
uvicorn main:app --reload
# o bien
python main.py
```

### 08. Verificar
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check:
  ```bash
  curl -s http://localhost:8000/health
  {"status": "ok", "version": "1.0.0", "environment": "development"}
  ```

## Usar la API
1. En `/docs`, ejecutar `POST /api/v1/auth/login` con el usuario inicial.
2. Copiar `token_acceso`, pulsar **Authorize** (candado) y pegarlo.
3. Con el administrador se crean los demás usuarios y roles (`POST /api/v1/usuarios`).

### Formato de las respuestas
Todas las respuestas tienen exactamente tres claves: `message`, `data` y `success`.

```json
{ "message": "Material registrado correctamente.", "data": { "material_id": "5", "nombre": "Cemento" }, "success": true }
```

- **Consulta paginada:** `data` trae `registros` (la lista) y `paginacion` (`pagina`, `por_pagina`,
  `total_registros`, `total_paginas`).
- **Error:** `success` es `false` y `data` trae `codigo` (catálogo de errores) y `errores`
  (`campo`, `codigo`, `mensaje`, `regla`).
- Cada respuesta trae el encabezado `X-Peticion-Id`, que permite encontrar en el log el detalle de un error.
- `/health` es un chequeo técnico y responde como indica la guía de setup.

## Ciclo de una compra
solicitud → comparativo de precios → cotización → enviar a aprobación → aprobar → orden de compra →
confirmar → pagos y recepción → entrada al inventario. Con el pago completo y la recepción, la orden
queda `cerrada`.

## Pruebas unitarias
```bash
python -m unittest discover -s tests -v
```

## Flujo de trabajo del equipo
Rama por historia `feature/hu-XX-...` → PR a `development` (lo revisa y fusiona el compañero) → PR de
`development` a `testing` → pruebas funcionales → `main` para la entrega. El detalle está en `CLAUDE.md`.
