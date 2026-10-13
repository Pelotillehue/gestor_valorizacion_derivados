"""Usuarios de la app

Revisión: 0008
Anterior: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """!
    @brief Aplica la revisión 0008: crea la tabla `usuario`. Los usuarios se crean con `scripts/crear_usuario.py`.
    """
    op.create_table(
        'usuario',
        sa.Column('email', sa.String(length=100), primary_key=True),
        sa.Column('nombre', sa.String(length=100), nullable=True),
        sa.Column('hash_clave', sa.String(length=200), nullable=False),
        sa.Column('activo', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ultimo_ingreso', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0008 y deja el esquema como estaba antes.
    """
    op.drop_table('usuario')
