# app/schemas/comparativo.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# Las reglas RN-056 a RN-060 NO van aquí: van en el dominio, para que el error llegue con su regla.
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.respuestas import fecha_iso
from app.domain.comparativo import Comparativo, ComparativoOferta


def _dinero(valor) -> Optional[float]:
    return None if valor is None else float(valor)


# ── ENTRADA ───────────────────────────────────────────────

class ComparativoCreate(BaseModel):
    """Datos para generar el comparativo de un material de una solicitud (POST)."""
    model_config = ConfigDict(json_schema_extra={"example": {"solicitud_id": 1, "material_id": 1}})

    solicitud_id: int = Field(..., description="Solicitud pendiente que pide el material")
    material_id: int = Field(..., description="Material de la solicitud que se va a comparar")


class SeleccionDatos(BaseModel):
    """Oferta elegida (PATCH .../seleccion)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "proveedor_id": 2,
        "justificacion": None,
    }})

    proveedor_id: int = Field(..., description="Proveedor cuya oferta se elige (RN-058)")
    justificacion: Optional[str] = Field(
        None, max_length=500,
        description="Obligatoria si no se elige la oferta de menor precio (RN-059)")


# ── SALIDA ────────────────────────────────────────────────

class OfertaComparativoResponse(BaseModel):
    proveedor_id: str
    precio: float
    disponible: bool
    dias_entrega: int

    @classmethod
    def desde_modelo(cls, o: ComparativoOferta) -> "OfertaComparativoResponse":
        return cls(proveedor_id=str(o.proveedor_id), precio=float(o.precio),
                   disponible=o.disponible, dias_entrega=o.dias_entrega)


class ComparativoResponse(BaseModel):
    comparativo_id: str
    solicitud_id: str
    material_id: str
    unidad: str
    cantidad: int
    moneda: str = "COP"
    ofertas: list[OfertaComparativoResponse]
    precio_minimo: float
    precio_maximo: float
    estado: str                                    # abierto | seleccionado
    proveedor_seleccionado_id: Optional[str]       # null mientras no se elija
    precio_seleccionado: Optional[float]
    ahorro: Optional[float]                        # por unidad (RN-060)
    ahorro_total: Optional[float]                  # ahorro × cantidad
    justificacion: Optional[str]
    fecha_registro: Optional[str]
    fecha_seleccion: Optional[str]

    @classmethod
    def desde_modelo(cls, c: Comparativo,
                     ofertas: Optional[list[ComparativoOferta]] = None) -> "ComparativoResponse":
        """`ofertas` permite mostrar la lista ya filtrada u ordenada (GET); si no, van todas."""
        return cls(
            comparativo_id=str(c.id),
            solicitud_id=str(c.solicitud_id),
            material_id=str(c.material_id),
            unidad=c.unidad,
            cantidad=c.cantidad,
            ofertas=[OfertaComparativoResponse.desde_modelo(o)
                     for o in (c.ofertas if ofertas is None else ofertas)],
            precio_minimo=float(c.precio_minimo),
            precio_maximo=float(c.precio_maximo),
            estado=c.estado,
            proveedor_seleccionado_id=(None if c.proveedor_seleccionado_id is None
                                       else str(c.proveedor_seleccionado_id)),
            precio_seleccionado=_dinero(c.precio_seleccionado),
            ahorro=_dinero(c.ahorro),
            ahorro_total=_dinero(c.ahorro_total),
            justificacion=c.justificacion,
            fecha_registro=fecha_iso(c.fecha_registro),
            fecha_seleccion=fecha_iso(c.fecha_seleccion),
        )
