"""Tipo de amortización de las patas con cupones

Revisión: 0007
Anterior: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """!
    @brief Aplica la revisión 0007: agrega a `pata` el tipo de amortización y deja BULLET en las patas con cupones.
    """
    op.add_column('pata', sa.Column('tipo_amortizacion', sa.String(length=15), nullable=True))
    op.execute("UPDATE pata SET tipo_amortizacion = 'BULLET' WHERE tipo <> 'SIMPLE'")


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0007 y deja el esquema como estaba antes.
    """
    op.drop_column('pata', 'tipo_amortizacion')
