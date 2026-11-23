# app/schemas/aprobacion.py
# Esquemas Pydantic de la HU-20: la decisión (entrada) y la aprobación (salida).
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.respuestas import fecha_iso
from app.domain.aprobacion import DECISION_APROBADA, DECISION_RECHAZADA, Aprobacion


# ── ENTRADA ───────────────────────────────────────────────

class DecisionDatos(BaseModel):
    """PATCH /api/v1/aprobaciones/{aprobacion_id}. El motivo es obligatorio al rechazar (RN-077)."""
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"decision": "aprobada"},
        {"decision": "rechazada", "motivo": "El proveedor no garantiza la entrega a tiempo."},
    ]})

    decision: str = Field(..., description="aprobada | rechazada")
    motivo: Optional[str] = Field(None, max_length=500, description="Obligatorio si se rechaza (RN-077)")

    @field_validator("decision")
    @classmethod
    def validar_decision(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in (DECISION_APROBADA, DECISION_RECHAZADA):
            raise ValueError("La decisión debe ser 'aprobada' o 'rechazada'.")
        return v


# ── SALIDA ────────────────────────────────────────────────

class AprobacionResponse(BaseModel):
    """Campos del ejemplo del issue, más el monto enviado y la fecha de envío."""
    aprobacion_id: str
    cotizacion_id: str
    proyecto_id: str
    estado: str                          # En revisión | Aprobada | Rechazada | Anulada
    monto: float                         # total de la cotización enviada a aprobación
    aprobador_id: Optional[str]          # null mientras está en revisión
    rol_aprobador: Optional[str]
    monto_autorizado: Optional[float]    # RN-079 (null si se rechazó o aún no se decide)
    moneda: str = "COP"
    fecha_envio: Optional[str]
    fecha_decision: Optional[str]
    motivo_rechazo: Optional[str]

    @classmethod
    def desde_modelo(cls, a: Aprobacion) -> "AprobacionResponse":
        return cls(
            aprobacion_id=str(a.id),
            cotizacion_id=str(a.cotizacion_id),
            proyecto_id=str(a.cotizacion.proyecto_id),
            estado=a.estado,
            monto=float(a.monto),
            aprobador_id=None if a.aprobador_id is None else str(a.aprobador_id),
            rol_aprobador=a.rol_aprobador,
            monto_autorizado=None if a.monto_autorizado is None else float(a.monto_autorizado),
            fecha_envio=fecha_iso(a.fecha_envio),
            fecha_decision=fecha_iso(a.fecha_decision),
            motivo_rechazo=a.motivo_rechazo,
        )
