"""Maestro de contrapartes con RUT, línea y MTA

La operación deja de guardar el nombre de la contraparte y pasa a apuntar a su RUT. Las
contrapartes que ya existían se crean con un RUT ficticio, línea y MTA en cero.

Revisión: 0006
Anterior: 0005
"""
import re

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def _dv(cuerpo: int) -> str:
    """!
    @brief Dígito verificador de un RUT (copia local, para que la migración no dependa del código de la aplicación).
    @param cuerpo Parte numérica.
    @return Dígito verificador.
    """
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def _rut_ficticio(nombre: str, orden: int) -> str:
    # Mismo RUT que asignan los generadores de cartera a "Contraparte Dummy NN".
    """!
    @brief RUT ficticio para una contraparte existente.

    A "Contraparte Dummy NN" le asigna el mismo RUT que los generadores de cartera; a las demás, uno correlativo desde 99.000.001.
    @param nombre Nombre de la contraparte.
    @param orden Posición del nombre en orden alfabético.
    @return RUT normalizado.
    """
    dummy = re.fullmatch(r"Contraparte Dummy (\d+)", nombre)
    cuerpo = 76_000_000 + int(dummy.group(1)) * 104_729 if dummy else 99_000_000 + orden
    return f"{cuerpo}-{_dv(cuerpo)}"


def upgrade() -> None:
    """!
    @brief Aplica la revisión 0006: crea el maestro `contraparte` y cambia el nombre de la contraparte de la operación por su RUT.
    """
    op.create_table(
        'contraparte',
        sa.Column('rut', sa.String(length=12), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('monto_linea', sa.Float(), server_default='0', nullable=False),
        sa.Column('mta', sa.Float(), server_default='0', nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('rut', name='contraparte_pkey'),
        sa.UniqueConstraint('nombre', name='contraparte_nombre_key'),
    )
    op.add_column('operacion', sa.Column('rut_contraparte', sa.String(length=12), nullable=True))
    op.create_index(op.f('ix_operacion_rut_contraparte'), 'operacion', ['rut_contraparte'], unique=False)
    op.create_foreign_key(
        'operacion_rut_contraparte_fkey', 'operacion', 'contraparte',
        ['rut_contraparte'], ['rut'], onupdate='CASCADE',
    )

    conexion = op.get_bind()
    nombres = conexion.execute(
        sa.text("SELECT DISTINCT contraparte FROM operacion WHERE contraparte IS NOT NULL ORDER BY 1")
    ).scalars().all()
    for orden, nombre in enumerate(nombres, start=1):
        rut = _rut_ficticio(nombre, orden)
        conexion.execute(sa.text("INSERT INTO contraparte (rut, nombre) VALUES (:rut, :nombre)"), {"rut": rut, "nombre": nombre})
        conexion.execute(
            sa.text("UPDATE operacion SET rut_contraparte = :rut WHERE contraparte = :nombre"), {"rut": rut, "nombre": nombre}
        )
    op.drop_column('operacion', 'contraparte')


def downgrade() -> None:
    """!
    @brief Revierte la revisión 0006 y deja el esquema como estaba antes.
    """
    op.add_column('operacion', sa.Column('contraparte', sa.String(length=100), nullable=True))
    op.execute(
        "UPDATE operacion o SET contraparte = c.nombre FROM contraparte c WHERE c.rut = o.rut_contraparte"
    )
    op.drop_constraint('operacion_rut_contraparte_fkey', 'operacion', type_='foreignkey')
    op.drop_index(op.f('ix_operacion_rut_contraparte'), table_name='operacion')
    op.drop_column('operacion', 'rut_contraparte')
    op.drop_table('contraparte')
