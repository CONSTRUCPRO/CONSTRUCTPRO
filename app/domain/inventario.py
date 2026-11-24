# app/domain/inventario.py
# CAPA DOMINIO: las entidades (tablas) Inventario y MovimientoInventario y SUS reglas de negocio.
# No importa FastAPI. Las reglas lanzan excepciones de app.domain.excepciones.
#
# Inventario guarda la existencia actual de cada material en cada proyecto.
# MovimientoInventario guarda cada entrada o salida con su existencia anterior y actual
# (trazabilidad): tipo, material, cantidad, fecha, motivo, responsable y documento de origen.
#
# Reglas de la HU-29:
#   RN-121  El inventario solo se actualiza con la recepción confirmada de la orden
#           (OrdenCompra.verificar_recibida(), app/domain/orden_compra.py).
#   RN-122  No se registran salidas mayores que la existencia disponible.
#   Las cantidades deben ser mayores que cero.
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.excepciones import ReglaNegocioError
from app.domain.material import Material

TIPO_ENTRADA = "entrada"
TIPO_SALIDA = "salida"

# Plural de las unidades del catálogo (HU-09) para los mensajes: "400 bultos", "3 m3".
_PLURALES = {"bulto": "bultos", "tonelada": "toneladas", "unidad": "unidades",
             "galon": "galones", "litro": "litros", "rollo": "rollos"}


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def en_plural(unidad: str, cantidad: int) -> str:
    return unidad if cantidad == 1 else _PLURALES.get(unidad, unidad)


def validar_cantidad(cantidad: int) -> None:
    """Las cantidades de los movimientos deben ser mayores que cero (422)."""
    if cantidad <= 0:
        raise ReglaNegocioError(
            None, "La cantidad debe ser mayor que cero.", campo="cantidad")


class Inventario(Base):
    """Existencia de un material en un proyecto (tabla inventarios)."""
    __tablename__ = "inventarios"
    __table_args__ = (
        UniqueConstraint("proyecto_id", "material_id", name="uq_inventario_proyecto_material"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    existencia: Mapped[int] = mapped_column(Integer, default=0)
    fecha_actualizacion: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    material: Mapped[Material] = relationship()

    # ── Reglas de negocio ─────────────────────────────────

    def sumar(self, cantidad: int) -> tuple[int, int]:
        """Entrada: suma la cantidad. Devuelve (existencia anterior, existencia actual)."""
        validar_cantidad(cantidad)
        anterior = self.existencia or 0
        self.existencia = anterior + cantidad
        self.fecha_actualizacion = _ahora_utc()
        return anterior, self.existencia

    def descontar(self, cantidad: int) -> tuple[int, int]:
        """Salida: RN-122, no se saca más de lo que hay (422). Devuelve (anterior, actual)."""
        validar_cantidad(cantidad)
        anterior = self.existencia or 0
        if cantidad > anterior:                                            # RN-122
            unidad = self.material.unidad
            raise ReglaNegocioError(
                "RN-122", f"Se solicitaron {cantidad} {en_plural(unidad, cantidad)} y solo hay "
                          f"{anterior} disponibles.",
                campo="cantidad", codigo="NEG_STOCK_INSUFICIENTE")
        self.existencia = anterior - cantidad
        self.fecha_actualizacion = _ahora_utc()
        return anterior, self.existencia


class MovimientoInventario(Base):
    """Cada entrada o salida del inventario (tabla movimientos_inventario)."""
    __tablename__ = "movimientos_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))                      # entrada | salida
    proyecto_id: Mapped[int] = mapped_column(ForeignKey("proyectos.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materiales.id"))
    cantidad: Mapped[int] = mapped_column(Integer)
    existencia_anterior: Mapped[int] = mapped_column(Integer)
    existencia_actual: Mapped[int] = mapped_column(Integer)
    motivo: Mapped[str] = mapped_column(String(200))
    responsable_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Documento de origen: la orden de compra recibida (solo en las entradas)
    orden_compra_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ordenes_compra.id"), nullable=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=_ahora_utc)

    material: Mapped[Material] = relationship()

    @classmethod
    def registrar(cls, tipo: str, inventario: Inventario, cantidad: int, motivo: str,
                  responsable_id: Optional[int],
                  orden_compra_id: Optional[int] = None) -> "MovimientoInventario":
        """Aplica el movimiento al inventario (sumar o descontar) y deja la traza."""
        if tipo == TIPO_ENTRADA:
            anterior, actual = inventario.sumar(cantidad)
        else:
            anterior, actual = inventario.descontar(cantidad)              # RN-122
        return cls(tipo=tipo, proyecto_id=inventario.proyecto_id,
                   material_id=inventario.material_id, material=inventario.material,
                   cantidad=cantidad, existencia_anterior=anterior, existencia_actual=actual,
                   motivo=motivo, responsable_id=responsable_id, orden_compra_id=orden_compra_id)
