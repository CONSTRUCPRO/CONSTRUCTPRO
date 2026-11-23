# app/domain/aprobacion.py
# CAPA DOMINIO: la entidad (tabla) Aprobacion y SUS reglas de negocio.
#
# Origen: la HU-17 (Alejandro) creó la versión mínima. Al enviar una cotización se abre su
# aprobación en estado "En revisión" (Aprobacion.abrir).
# HU-20 (Jaime, Decisión de Aprobación) la amplía: aprobador, rol, monto autorizado, fecha y
# motivo de la decisión, y las reglas:
#   RN-066  No se aprueba una compra que supere el saldo disponible del proyecto.
#   RN-068  Al aprobar, el valor se compromete en el presupuesto del proyecto (HU-06).
#   RN-073  Nadie aprueba una compra que él mismo solicitó o envió (403 NEG_SEGREGACION_FUNCIONES).
#   RN-076  Por encima del tope definido solo decide el Director; el Coordinador decide hasta el tope.
#   RN-077  Todo rechazo registra obligatoriamente el motivo.
#   RN-078  Una aprobación ya decidida no puede modificarse.
#   RN-079  Se registran el aprobador, la fecha y el monto autorizado.
# Al decidir, también cambia el estado de la cotización (Aprobada / Rechazada); con eso la
# cotización aprobada ya no se puede anular (RN-064, HU-17).
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.cotizacion import ESTADO_APROBADA as COTIZACION_APROBADA
from app.domain.cotizacion import ESTADO_RECHAZADA as COTIZACION_RECHAZADA
from app.domain.cotizacion import Cotizacion
from app.domain.excepciones import ConflictoEstadoError, PermisoDenegadoError, ReglaNegocioError
from app.domain.presupuesto import formato_cop
from app.domain.usuario import Usuario

ESTADO_EN_REVISION = "En revisión"
ESTADO_APROBADA = "Aprobada"      # HU-20
ESTADO_RECHAZADA = "Rechazada"    # HU-20
ESTADO_ANULADA = "Anulada"        # la cotización se anuló mientras estaba en revisión

DECISION_APROBADA = "aprobada"
DECISION_RECHAZADA = "rechazada"

ROL_DIRECTOR = "director"


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Aprobacion(Base):
    __tablename__ = "aprobaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_EN_REVISION)
    monto: Mapped[Decimal] = mapped_column(Numeric(16, 2))        # total de la cotización
    enviado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    fecha_envio: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=_ahora_utc
    )
    # ── Decisión (HU-20, RN-079) ──────────────────────────
    aprobador_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    rol_aprobador: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    monto_autorizado: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    fecha_decision: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    motivo_rechazo: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    cotizacion: Mapped[Cotizacion] = relationship()

    @classmethod
    def abrir(cls, cotizacion: Cotizacion, enviado_por_id: Optional[int]) -> "Aprobacion":
        """Crea la aprobación En revisión por el total de la cotización enviada."""
        return cls(cotizacion=cotizacion, estado=ESTADO_EN_REVISION, monto=cotizacion.total,
                   enviado_por_id=enviado_por_id)

    def esta_en_revision(self) -> bool:
        return self.estado == ESTADO_EN_REVISION

    def cancelar(self) -> None:
        """Si la cotización se anula mientras está en revisión, la aprobación queda Anulada."""
        if self.esta_en_revision():
            self.estado = ESTADO_ANULADA

    # ── Reglas de la decisión (HU-20) ─────────────────────

    def verificar_pendiente(self) -> None:
        """RN-078: una aprobación ya decidida (o anulada) no puede modificarse (409)."""
        if not self.esta_en_revision():
            raise ConflictoEstadoError(
                "RN-078", f"La aprobación {self.id} ya está en estado '{self.estado}' y no puede "
                          f"modificarse.", campo="estado")

    def verificar_segregacion(self, aprobador: Usuario, solicitantes: set[int]) -> None:
        """RN-073: el aprobador no puede ser quien solicitó los materiales o envió la cotización."""
        if aprobador.id in solicitantes or aprobador.id == self.enviado_por_id:
            raise PermisoDenegadoError(
                f"El usuario {aprobador.nombre_completo} solicitó o envió esta compra y no "
                f"puede decidir sobre ella.",
                regla="RN-073", campo="aprobador_id", codigo="NEG_SEGREGACION_FUNCIONES")

    def verificar_nivel(self, aprobador: Usuario, tope: Decimal) -> None:
        """RN-076: por encima del tope solo decide el Director (403)."""
        rol = aprobador.rol.nombre
        if self.monto > tope and rol.lower() != ROL_DIRECTOR:
            raise PermisoDenegadoError(
                f"El rol {rol} no puede aprobar compras superiores a {formato_cop(tope)}.",
                regla="RN-076", campo="aprobador_id")

    def decidir(self, decision: str, aprobador: Usuario, motivo: Optional[str],
                solicitantes: set[int], tope: Decimal) -> None:
        """
        Registra la decisión (aprobada o rechazada) y actualiza la cotización.
        Orden: RN-078 (409) → RN-073 y RN-076 (403) → RN-077 / RN-066 (422).
        """
        self.verificar_pendiente()                                        # RN-078
        self.verificar_segregacion(aprobador, solicitantes)               # RN-073
        self.verificar_nivel(aprobador, tope)                             # RN-076
        motivo = (motivo or "").strip() or None
        if decision == DECISION_RECHAZADA:
            if not motivo:                                                # RN-077
                raise ReglaNegocioError(
                    "RN-077", "Todo rechazo debe registrar el motivo.", campo="motivo")
            # FUN-077 pide liberar el compromiso: aquí no hay nada que liberar, porque el
            # presupuesto solo se compromete al aprobar (la HU-17 solo valida el saldo al enviar).
            self.estado = ESTADO_RECHAZADA
            self.cotizacion.estado = COTIZACION_RECHAZADA
            self.monto_autorizado = None
            self.motivo_rechazo = motivo
        else:
            presupuesto = self.cotizacion.proyecto.presupuesto
            if presupuesto is None:                                       # RN-021 (HU-06)
                raise ReglaNegocioError(
                    "RN-021", f"El proyecto '{self.cotizacion.proyecto.nombre}' no tiene "
                              f"presupuesto asignado.", campo="proyecto_id")
            presupuesto.comprometer(float(self.monto))                    # RN-066 y RN-068
            self.estado = ESTADO_APROBADA
            self.cotizacion.estado = COTIZACION_APROBADA
            self.monto_autorizado = self.monto
            self.motivo_rechazo = None
        self.aprobador_id = aprobador.id                                  # RN-079
        self.rol_aprobador = aprobador.rol.nombre
        self.fecha_decision = _ahora_utc()
