"""!
@package valorizador.db.base
@brief Conexión a PostgreSQL: motor, fábrica de sesiones y dependencia de FastAPI.

La cadena de conexión viene de @ref valorizador.config.Configuracion.database_url. Cada
solicitud HTTP abre su propia sesión con @ref valorizador.db.base.obtener_sesion y la cierra al terminar.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from valorizador.config import configuracion


class Base(DeclarativeBase):
    """!
    @brief Clase base declarativa de todos los modelos ORM de @ref valorizador.db.modelos.
    """


## Motor SQLAlchemy con un pool de conexiones a la base configurada. `pool_pre_ping`
## descarta conexiones caídas antes de usarlas.
motor = create_engine(configuracion.database_url, pool_pre_ping=True)
## Fábrica de sesiones. `expire_on_commit=False` deja los objetos usables después del commit.
SesionLocal = sessionmaker(bind=motor, expire_on_commit=False)


def obtener_sesion() -> Iterator[Session]:
    """!
    @brief Dependencia de FastAPI que entrega una sesión por solicitud.

    Si el endpoint termina sin error hace commit; si lanza una excepción hace rollback. En ambos
    casos cierra la sesión. Los tests la reemplazan por una sesión sobre la base de pruebas.
    @return Generador que entrega una única sesión.
    """
    sesion = SesionLocal()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()
