"""
Excepciones de negocio de ConstruPro.

El dominio y los servicios LANZAN estas excepciones; nunca lanzan HTTPException.
La capa API (app/core/errores.py) las atrapa y las convierte en el sobre JSON
estándar con su código HTTP (Componente F del documento del parcial).

Basadas en las excepciones que escribió Alejandro en el taller de materiales:
se conservan los mismos nombres y el mismo orden de parámetros.
"""
from typing import Optional

# Catálogo de códigos de error (Tabla 57 del parcial) -> mensaje para el usuario.
# Los dos últimos son genéricos, para reglas que no tienen un código propio.
CATALOGO_MENSAJES = {
    "VAL_CAMPO_REQUERIDO": "El campo indicado es obligatorio.",
    "VAL_FORMATO_INVALIDO": "El valor enviado no tiene el formato esperado.",
    "AUT_CREDENCIALES_INVALIDAS": "El correo o la contraseña no son correctos.",
    "AUT_USUARIO_INACTIVO": "La cuenta se encuentra inactiva; contacte al administrador.",
    "AUT_SIN_PERMISO": "Su rol no le permite realizar esta operación.",
    "NEG_PRESUPUESTO_INSUFICIENTE": "El valor de la compra supera el presupuesto disponible del proyecto.",
    "NEG_PROYECTO_NO_ACTIVO": "El proyecto no está activo y no admite nuevas solicitudes.",
    "NEG_SEGREGACION_FUNCIONES": "No puede aprobar una compra que usted mismo solicitó.",
    "NEG_COMPARATIVO_INSUFICIENTE": "Se requieren al menos dos proveedores para comparar.",
    "NEG_COMPRA_NO_APROBADA": "No es posible generar la orden: la compra no está aprobada.",
    "NEG_PAGO_EXCEDE_ORDEN": "El pago supera el valor pendiente de la orden de compra.",
    "NEG_RECEPCION_NO_CONFIRMADA": "El inventario solo puede actualizarse tras confirmar la recepción.",
    "NEG_STOCK_INSUFICIENTE": "No hay existencias suficientes para registrar la salida.",
    "REC_NO_ENCONTRADO": "El recurso solicitado no existe.",
    "REC_DUPLICADO": "Ya existe un registro con ese identificador.",
    "ERR_INTERNO": "Ocurrió un error inesperado. Intente nuevamente.",
    "NEG_REGLA_INCUMPLIDA": "La operación no cumple una regla de negocio.",
    "NEG_CONFLICTO_ESTADO": "El estado actual del recurso no permite esta operación.",
}


class ConstruProError(Exception):
    """
    Base de todos los errores de negocio de ConstruPro.

    - mensaje:         detalle del error (va en errores[0].mensaje).
    - regla:           regla de negocio infringida, ej. "RN-031" (puede ser None).
    - campo:           campo relacionado con el error, ej. "correo" (puede ser None).
    - codigo:          código del catálogo; si no se envía, se usa el de la clase.
    - mensaje_general: reemplaza el mensaje general del catálogo cuando la HU
                       pide uno distinto.
    """
    http_status: int = 500
    codigo: str = "ERR_INTERNO"

    def __init__(self, mensaje: str, regla: Optional[str] = None,
                 campo: Optional[str] = None, codigo: Optional[str] = None,
                 mensaje_general: Optional[str] = None):
        self.mensaje = mensaje
        self.regla = regla
        self.campo = campo
        if codigo:
            self.codigo = codigo
        self.mensaje_general = mensaje_general or CATALOGO_MENSAJES.get(
            self.codigo, CATALOGO_MENSAJES["ERR_INTERNO"]
        )
        super().__init__(mensaje)


class ReglaNegocioError(ConstruProError):
    """Se rompió una regla de negocio (RN-xxx). HTTP 422."""
    http_status = 422
    codigo = "NEG_REGLA_INCUMPLIDA"

    def __init__(self, regla: str, mensaje: str, campo: Optional[str] = None,
                 codigo: Optional[str] = None, mensaje_general: Optional[str] = None):
        super().__init__(mensaje, regla=regla, campo=campo, codigo=codigo,
                         mensaje_general=mensaje_general)


class RecursoNoEncontradoError(ConstruProError):
    """No existe el recurso pedido. HTTP 404, REC_NO_ENCONTRADO."""
    http_status = 404
    codigo = "REC_NO_ENCONTRADO"

    def __init__(self, mensaje: str, campo: Optional[str] = None):
        super().__init__(mensaje, campo=campo)


class RecursoDuplicadoError(ConstruProError):
    """Registro repetido (RN-001, RN-011, RN-031...). HTTP 409, REC_DUPLICADO."""
    http_status = 409
    codigo = "REC_DUPLICADO"

    def __init__(self, regla: str, mensaje: str, campo: Optional[str] = None):
        super().__init__(mensaje, regla=regla, campo=campo)


class ConflictoEstadoError(ConstruProError):
    """El estado actual del recurso impide la operación (ej. RN-081, RN-078). HTTP 409."""
    http_status = 409
    codigo = "NEG_CONFLICTO_ESTADO"

    def __init__(self, regla: str, mensaje: str, campo: Optional[str] = None,
                 codigo: Optional[str] = None, mensaje_general: Optional[str] = None):
        super().__init__(mensaje, regla=regla, campo=campo, codigo=codigo,
                         mensaje_general=mensaje_general)


class PermisoDenegadoError(ConstruProError):
    """El rol del usuario no permite la operación (ej. RN-014, RN-076). HTTP 403."""
    http_status = 403
    codigo = "AUT_SIN_PERMISO"

    def __init__(self, mensaje: str, regla: Optional[str] = None,
                 campo: Optional[str] = "rol", codigo: Optional[str] = None):
        super().__init__(mensaje, regla=regla, campo=campo, codigo=codigo)


class NoAutenticadoError(ConstruProError):
    """No hay usuario autenticado, o sus credenciales/token no sirven. HTTP 401."""
    http_status = 401
    codigo = "AUT_CREDENCIALES_INVALIDAS"

    def __init__(self, mensaje: str, campo: Optional[str] = None,
                 codigo: Optional[str] = None):
        super().__init__(mensaje, campo=campo, codigo=codigo)
