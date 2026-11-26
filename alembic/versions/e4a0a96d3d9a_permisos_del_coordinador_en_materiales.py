"""Permisos del Coordinador en Materiales

Revision ID: e4a0a96d3d9a
Revises: 9dcb06782bba
Create Date: 2026-11-22 10:02:22.233932

El coordinador de compras registra, edita e inactiva materiales y proveedores
(HU-09, HU-10 y HU-11), pero la migración de la HU-03 solo le daba "consultar"
en el módulo Materiales. Los proveedores pertenecen al mismo módulo (MODULO-03),
así que usan estos mismos permisos.

No se edita la migración a3f1c9e2b7d4 porque ya está aplicada en las BD del equipo.
Solo agrega los permisos que falten, así que se puede aplicar aunque alguien ya los
haya asignado a mano con PUT /api/v1/roles/{rol_id}/permisos.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a0a96d3d9a'
down_revision: Union[str, Sequence[str], None] = '9dcb06782bba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROL = "Coordinador"
MODULO = "Materiales"
ACCIONES_NUEVAS = ("crear", "editar", "inactivar")


def upgrade() -> None:
    """Agrega crear, editar e inactivar en Materiales al rol Coordinador."""
    conexion = op.get_bind()
    rol_id = conexion.execute(
        sa.text("SELECT id FROM roles WHERE lower(nombre) = lower(:nombre)"),
        {"nombre": ROL},
    ).scalar()
    if rol_id is None:  # BD sin los roles por defecto: no hay nada que ampliar
        return
    for accion in ACCIONES_NUEVAS:
        ya_existe = conexion.execute(
            sa.text("SELECT 1 FROM permisos_rol "
                    "WHERE rol_id = :rol_id AND modulo = :modulo AND accion = :accion"),
            {"rol_id": rol_id, "modulo": MODULO, "accion": accion},
        ).scalar()
        if not ya_existe:
            conexion.execute(
                sa.text("INSERT INTO permisos_rol (rol_id, modulo, accion) "
                        "VALUES (:rol_id, :modulo, :accion)"),
                {"rol_id": rol_id, "modulo": MODULO, "accion": accion},
            )


def downgrade() -> None:
    """Quita los permisos agregados (el Coordinador vuelve a solo consultar Materiales)."""
    conexion = op.get_bind()
    rol_id = conexion.execute(
        sa.text("SELECT id FROM roles WHERE lower(nombre) = lower(:nombre)"),
        {"nombre": ROL},
    ).scalar()
    if rol_id is None:
        return
    for accion in ACCIONES_NUEVAS:
        conexion.execute(
            sa.text("DELETE FROM permisos_rol "
                    "WHERE rol_id = :rol_id AND modulo = :modulo AND accion = :accion"),
            {"rol_id": rol_id, "modulo": MODULO, "accion": accion},
        )
