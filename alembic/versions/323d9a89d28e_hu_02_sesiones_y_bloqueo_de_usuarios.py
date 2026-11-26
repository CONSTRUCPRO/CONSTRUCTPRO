"""HU-02 sesiones y bloqueo de usuarios

Revision ID: 323d9a89d28e
Revises: 4a68f0bd7455
Create Date: 2026-11-22 11:30:00.000000

- Crea la tabla sesiones (logout invalida el token, RN-008/RN-009).
- Agrega a usuarios los campos del bloqueo por intentos fallidos (RN-007).
- Crea el usuario administrador inicial, para poder hacer el primer login:
      correo:     admin@construpro.co
      contraseña: Admin2026   (o la que se defina en ADMIN_CONTRASENA_INICIAL del .env)
  Solo se crea si existe el rol Administrador y no hay ya un usuario con ese correo.
"""
import os
from datetime import datetime, timezone
from typing import Sequence, Union

import bcrypt
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '323d9a89d28e'
down_revision: Union[str, Sequence[str], None] = '4a68f0bd7455'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_CORREO = "admin@construpro.co"
ADMIN_DOCUMENTO = "1000000001"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('sesiones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('token_renovacion_hash', sa.String(length=64), nullable=False),
    sa.Column('version_sesion', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('expira_renovacion', sa.DateTime(), nullable=False),
    sa.Column('fecha_inicio', sa.DateTime(), nullable=False),
    sa.Column('fecha_cierre', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_renovacion_hash')
    )
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        # server_default="0": los usuarios que ya existen quedan con 0 intentos
        batch_op.add_column(sa.Column('intentos_fallidos', sa.Integer(), nullable=False,
                                      server_default="0"))
        batch_op.add_column(sa.Column('bloqueado_hasta', sa.DateTime(), nullable=True))

    # ── Administrador inicial ─────────────────────────────
    conexion = op.get_bind()
    rol_id = conexion.execute(
        sa.text("SELECT id FROM roles WHERE lower(nombre) = 'administrador'")).scalar()
    ya_existe = conexion.execute(
        sa.text("SELECT 1 FROM usuarios WHERE lower(correo) = :correo OR numero_documento = :doc"),
        {"correo": ADMIN_CORREO, "doc": ADMIN_DOCUMENTO}).scalar()
    if rol_id is not None and not ya_existe:
        contrasena = os.getenv("ADMIN_CONTRASENA_INICIAL", "Admin2026")
        conexion.execute(
            sa.text("INSERT INTO usuarios (nombre_completo, tipo_documento, numero_documento, correo, "
                    "telefono, contrasena_hash, rol_id, estado, version_sesion, intentos_fallidos, "
                    "fecha_registro) VALUES (:nombre, 'CC', :doc, :correo, '3000000000', :hash, "
                    ":rol_id, 'activo', 0, 0, :fecha)"),
            {"nombre": "Administrador ConstruPro", "doc": ADMIN_DOCUMENTO, "correo": ADMIN_CORREO,
             "hash": bcrypt.hashpw(contrasena.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
             "rol_id": rol_id, "fecha": datetime.now(timezone.utc).replace(tzinfo=None)})


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('sesiones')
    op.execute(sa.text(f"DELETE FROM usuarios WHERE lower(correo) = '{ADMIN_CORREO}' "
                       f"AND numero_documento = '{ADMIN_DOCUMENTO}'"))
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('bloqueado_hasta')
        batch_op.drop_column('intentos_fallidos')
