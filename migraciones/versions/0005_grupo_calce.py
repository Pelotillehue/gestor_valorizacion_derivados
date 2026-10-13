"""Grupo de calce de la operación

Revisión: 0005
Anterior: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Operaciones con el mismo grupo se cubren entre sí; nulo si está descalzada.
    """!
    @brief Aplica la revisión 0005: agrega a `operacion` el grupo de calce.
    """
    op.add_column('operacion', sa.Column('grupo_calce', sa.String(length=30), nullable=True))
    op.create_index(op.f('ix_operacion_grupo_calce'), 'operacion', ['grupo_calce'], unique=False)


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0005 y deja el esquema como estaba antes.
    """
    op.drop_index(op.f('ix_operacion_grupo_calce'), table_name='operacion')
    op.drop_column('operacion', 'grupo_calce')
