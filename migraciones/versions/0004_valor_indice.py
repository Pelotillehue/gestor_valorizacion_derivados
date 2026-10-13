"""Tabla fixing pasa a llamarse valor_indice

Revisión: 0004
Anterior: 0003
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarda el nivel diario de índices como el ICP o el SOFR, no tasas fijadas por período.
    """!
    @brief Aplica la revisión 0004: renombra la tabla `fixing` a `valor_indice`.
    """
    op.rename_table('fixing', 'valor_indice')
    op.execute('ALTER TABLE valor_indice RENAME CONSTRAINT fixing_pkey TO valor_indice_pkey')


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0004 y deja el esquema como estaba antes.
    """
    op.execute('ALTER TABLE valor_indice RENAME CONSTRAINT valor_indice_pkey TO fixing_pkey')
    op.rename_table('valor_indice', 'fixing')
