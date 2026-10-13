"""Código de la curva en curva_vertice

Revisión: 0002
Anterior: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Se agrega nula, se completa con el código de la curva y luego se exige.
    """!
    @brief Aplica la revisión 0002: agrega a `curva_vertice` el código de su curva.
    """
    op.add_column('curva_vertice', sa.Column('codigo', sa.String(length=50), nullable=True))
    op.execute(
        "UPDATE curva_vertice SET codigo = curva.codigo FROM curva WHERE curva.id = curva_vertice.curva_id"
    )
    op.alter_column('curva_vertice', 'codigo', nullable=False)


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0002 y deja el esquema como estaba antes.
    """
    op.drop_column('curva_vertice', 'codigo')
