# app/schemas/pago.py
# Esquemas Pydantic: validan la FORMA de la entrada y definen la forma de la SALIDA
# (lo que va dentro de "datos" en el sobre estándar).
# Las reglas RN-091 a RN-095 NO van aquí: van en el dominio, para que el error llegue con su regla.
# Por eso metodo_pago y fecha_pago son opcionales aquí: si faltan, el dominio responde RN-093.
from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.orden_compra import OrdenCompra
from app.domain.pago import Pago


# ── ENTRADA ───────────────────────────────────────────────

class PagoCreate(BaseModel):
    """Datos del pago de una orden de compra (POST)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "orden_compra_id": 1,
        "monto": 7000000.00,
        "moneda": "COP",
        "metodo_pago": "transferencia",
        "fecha_pago": "2026-11-23",
        "referencia_pasarela": "PSE-558812",
    }})

    orden_compra_id: int = Field(..., description="Orden de compra confirmada (RN-092)")
    monto: float = Field(..., description="Valor pagado en COP; no supera el saldo de la orden (RN-091)")
    moneda: Optional[str] = Field("COP", description="Debe ser la de la orden: COP (RN-095)")
    metodo_pago: Optional[str] = Field(
        None, description="transferencia | pse | consignacion | cheque | tarjeta | efectivo (RN-093)")
    fecha_pago: Optional[date] = Field(None, description="Fecha del pago, no futura (RN-093)")
    referencia_pasarela: Optional[str] = Field(
        None, max_length=60, description="Referencia que entrega la pasarela o el banco")

    @field_validator("metodo_pago")
    @classmethod
    def normalizar_metodo(cls, v: Optional[str]) -> Optional[str]:
        """El método se compara en minúscula y sin espacios ('PSE ' -> 'pse')."""
        return v.strip().lower() if v else v


class AnulacionPago(BaseModel):
    """Motivo opcional de la anulación (PATCH .../anular)."""
    model_config = ConfigDict(json_schema_extra={"example": {"motivo": "Pago duplicado"}})

    motivo: Optional[str] = Field(None, max_length=500, description="Motivo de la anulación")


# ── SALIDA ────────────────────────────────────────────────

class PagoBase(BaseModel):
    """Los datos de un pago tal como salen en las respuestas."""

    pago_id: str
    orden_compra_id: str
    monto: float
    moneda: str
    metodo_pago: str
    numero_transaccion: Optional[str]
    referencia_pasarela: Optional[str]
    fecha_pago: Optional[str]           # fecha ISO (RN-093)
    estado: str                         # registrado | anulado
    registrado_por_id: Optional[str]
    fecha_registro: Optional[str]
    fecha_anulacion: Optional[str]
    motivo_anulacion: Optional[str]

    @classmethod
    def _campos(cls, p: Pago) -> dict:
        """
        Convierte el modelo en el diccionario de campos; lo reutilizan desde_modelo y con_saldo.
        """
        return dict(
            pago_id=str(p.id), orden_compra_id=str(p.orden_compra_id), monto=float(p.monto),
            moneda=p.moneda, metodo_pago=p.metodo_pago, numero_transaccion=p.numero_transaccion,
            referencia_pasarela=p.referencia_pasarela, fecha_pago=fecha_iso(p.fecha_pago),
            estado=p.estado,
            registrado_por_id=None if p.registrado_por_id is None else str(p.registrado_por_id),
            fecha_registro=fecha_iso(p.fecha_registro), fecha_anulacion=fecha_iso(p.fecha_anulacion),
            motivo_anulacion=p.motivo_anulacion,
        )

    @classmethod
    def desde_modelo(cls, p: Pago) -> "PagoBase":
        """
        Convierte el modelo de BD de un pago en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).
        """
        return cls(**cls._campos(p))


class PagoResponse(PagoBase):
    """Respuesta del POST y del anular: el pago más el estado de cuenta de la orden."""
    valor_orden: float
    total_pagado: float
    saldo_pendiente: float

    @classmethod
    def con_saldo(cls, p: Pago, total_pagado: Decimal) -> "PagoResponse":
        """Agrega al pago el estado de cuenta de la orden: valor, total pagado y saldo pendiente."""
        valor = p.orden.valor_total
        return cls(**cls._campos(p), valor_orden=float(valor), total_pagado=float(total_pagado),
                   saldo_pendiente=float(valor - total_pagado))


class PagosOrdenResponse(BaseModel):
    """GET /ordenes-compra/{id}/pagos: los pagos de la orden y su estado de cuenta."""
    orden_compra_id: str
    estado_orden: str
    moneda: str = "COP"
    valor_orden: float
    total_pagado: float               # solo pagos vigentes (no anulados)
    saldo_pendiente: float
    pagos: list[PagoBase]             # todos, incluidos los anulados (trazabilidad)

    @classmethod
    def desde_modelo(cls, orden: OrdenCompra, pagos: list[Pago],
                     total_pagado: Decimal) -> "PagosOrdenResponse":
        """
        Convierte el modelo de BD de los pagos de una orden en la respuesta de la API: ids como texto con sufijo
        _id, dinero como float con su moneda y fechas en ISO 8601 (convenciones del Componente F).

        Incluye el estado de la orden y su saldo pendiente.
        """
        return cls(orden_compra_id=str(orden.id), estado_orden=orden.estado,
                   valor_orden=float(orden.valor_total), total_pagado=float(total_pagado),
                   saldo_pendiente=float(orden.valor_total - total_pagado),
                   pagos=[PagoBase.desde_modelo(p) for p in pagos])
