"""Modalidad de liquidación de la operación

Revisión: 0003
Anterior: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Las operaciones ya cargadas quedan como compensación.
    """!
    @brief Aplica la revisión 0003: agrega a `operacion` la modalidad de liquidación.
    """
    op.add_column(
        'operacion',
        sa.Column('modalidad_liquidacion', sa.String(length=20), nullable=False, server_default='COMPENSACION'),
    )


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0003 y deja el esquema como estaba antes.
    """
    op.drop_column('operacion', 'modalidad_liquidacion')
