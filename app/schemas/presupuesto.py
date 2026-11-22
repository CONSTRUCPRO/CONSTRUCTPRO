# app/schemas/presupuesto.py
# Esquemas Pydantic de la HU-06: validan la entrada y definen la salida.
# El monto debe ser mayor que cero: si no, 422 VAL_FORMATO_INVALIDO con el mensaje en español.
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.presupuesto import MONEDA, Presupuesto


# ── ENTRADA ───────────────────────────────────────────────

class PresupuestoDatos(BaseModel):
    """POST (asignar) y PUT (actualizar) reciben lo mismo."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "presupuesto_total": 250000000.00,
        "moneda": "COP",
    }})

    presupuesto_total: float = Field(..., description="Monto total en COP, mayor que cero")
    moneda: str = Field(MONEDA, description="Siempre COP")

    @field_validator("presupuesto_total")
    @classmethod
    def validar_monto(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("El presupuesto debe ser mayor que cero.")
        if v >= 10 ** 14:
            raise ValueError("El presupuesto supera el valor máximo permitido.")
        return round(v, 2)

    @field_validator("moneda")
    @classmethod
    def validar_moneda(cls, v: str) -> str:
        v = v.strip().upper()
        if v != MONEDA:
            raise ValueError("La moneda del presupuesto debe ser COP.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class PresupuestoResponse(BaseModel):
    """Forma exacta del ejemplo del issue."""
    proyecto_id: str
    moneda: str = MONEDA
    presupuesto_total: float
    comprometido: float
    ejecutado: float
    saldo_disponible: float        # presupuesto_total - comprometido - ejecutado
    fecha_aprobacion: str          # AAAA-MM-DD

    @classmethod
    def desde_modelo(cls, p: Presupuesto) -> "PresupuestoResponse":
        return cls(
            proyecto_id=str(p.proyecto_id),
            presupuesto_total=float(p.presupuesto_total),
            comprometido=float(p.comprometido),
            ejecutado=float(p.ejecutado),
            saldo_disponible=float(p.saldo_disponible),
            fecha_aprobacion=fecha_iso(p.fecha_aprobacion),
        )
