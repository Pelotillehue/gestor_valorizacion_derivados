"""!
@package env
@brief Entorno de Alembic. Usa la misma configuración (`DATABASE_URL`) y los mismos modelos que la aplicación.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from valorizador.config import configuracion
from valorizador.db import modelos  # noqa: F401  registra las tablas en Base.metadata
from valorizador.db.base import Base

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

metadatos = Base.metadata


def migrar_sin_conexion() -> None:
    """!
    @brief Genera el SQL de las migraciones sin conectarse a la base (`alembic upgrade --sql`).
    """
    context.configure(url=configuracion.database_url, target_metadata=metadatos, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def migrar_con_conexion() -> None:
    """!
    @brief Aplica las migraciones sobre la base configurada en `DATABASE_URL`.
    """
    motor = create_engine(configuracion.database_url)
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=metadatos)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    migrar_sin_conexion()
else:
    migrar_con_conexion()
