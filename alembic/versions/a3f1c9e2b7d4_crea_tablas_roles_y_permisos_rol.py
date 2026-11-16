"""HU-03: crea tablas roles y permisos_rol y carga los roles por defecto

Revision ID: a3f1c9e2b7d4
Revises:
Create Date: 2026-11-16 17:15:00

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9e2b7d4'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TODAS = ["crear", "consultar", "editar", "inactivar", "aprobar", "anular"]
MODULOS = ["Usuarios", "Proyectos", "Materiales", "Solicitudes", "Cotizaciones",
           "Aprobaciones", "Ordenes de compra", "Pagos", "Logistica", "Inventario", "Reportes"]

# Roles por defecto (HU-03, Definición de Hecho) con sus permisos iniciales.
ROLES_INICIALES = [
    (1, "Administrador", "Administra usuarios, roles y la configuración del sistema.",
     {m: TODAS for m in MODULOS}),
    (2, "Coordinador", "Coordina las compras de la obra y aprueba compras hasta su tope.",
     {"Proyectos": ["consultar", "editar"], "Materiales": ["consultar"],
      "Solicitudes": ["crear", "consultar", "editar"],
      "Cotizaciones": ["crear", "consultar", "editar"],
      "Aprobaciones": ["consultar", "aprobar"],
      "Ordenes de compra": ["crear", "consultar", "anular"],
      "Inventario": ["consultar"], "Reportes": ["consultar"]}),
    (3, "Director", "Dirige los proyectos, asigna presupuestos y aprueba compras de mayor monto.",
     {"Usuarios": ["consultar"], "Proyectos": ["crear", "consultar", "editar"],
      "Materiales": ["consultar"], "Solicitudes": ["consultar"], "Cotizaciones": ["consultar"],
      "Aprobaciones": ["consultar", "aprobar"], "Ordenes de compra": ["consultar"],
      "Pagos": ["consultar"], "Inventario": ["consultar"], "Reportes": ["consultar"]}),
    (4, "Empleado", "Personal de obra: registra solicitudes y movimientos de inventario.",
     {"Materiales": ["consultar"], "Solicitudes": ["crear", "consultar"],
      "Inventario": ["crear", "consultar"]}),
]


def upgrade() -> None:
    """Upgrade schema."""
    roles = op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('descripcion', sa.String(length=255), nullable=True),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('fecha_registro', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nombre')
    )
    permisos_rol = op.create_table('permisos_rol',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rol_id', sa.Integer(), nullable=False),
    sa.Column('modulo', sa.String(length=40), nullable=False),
    sa.Column('accion', sa.String(length=20), nullable=False),
    sa.ForeignKeyConstraint(['rol_id'], ['roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('rol_id', 'modulo', 'accion', name='uq_permiso_rol')
    )

    # Datos iniciales: los 4 roles del sistema y sus permisos.
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    op.bulk_insert(roles, [
        {"id": rol_id, "nombre": nombre, "descripcion": descripcion,
         "estado": "activo", "fecha_registro": ahora}
        for rol_id, nombre, descripcion, _ in ROLES_INICIALES
    ])
    op.bulk_insert(permisos_rol, [
        {"rol_id": rol_id, "modulo": modulo, "accion": accion}
        for rol_id, _, _, permisos in ROLES_INICIALES
        for modulo, acciones in permisos.items()
        for accion in acciones
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('permisos_rol')
    op.drop_table('roles')
