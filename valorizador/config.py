"""!
@package valorizador.config
@brief Configuración de la aplicación.

Los valores se leen de variables de entorno o del archivo `.env` en la carpeta desde la que
se ejecuta la API. Ver @ref valorizador.config.Configuracion.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracion(BaseSettings):
    """!
    @brief Parámetros de configuración, leídos con pydantic-settings.

    Cada atributo se puede definir en `.env` o como variable de entorno con el mismo nombre en
    mayúsculas, por ejemplo `DATABASE_URL`.
    """

    ## Lee `.env` en UTF-8 e ignora variables que no son de la aplicación.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ## Cadena de conexión SQLAlchemy a la base de datos de trabajo, con el driver psycopg 3.
    ## Ejemplo: `postgresql+psycopg://postgres:clave@localhost:5434/Valorizador`.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/valorizador"
    ## Moneda en que se expresa el MtM cuando la solicitud no indica otra.
    moneda_valorizacion: str = "CLP"
    ## Si es verdadero, todos los endpoints salvo `/salud` y `/auth/login` exigen un token de sesión.
    requerir_autenticacion: bool = True
    ## Clave con que se firman los tokens de sesión. Debe ser larga y aleatoria, y la misma en
    ## todas las instancias de la API. Si no se define, se genera una al iniciar la API.
    clave_secreta: str | None = None
    ## Horas de validez de un token de sesión.
    horas_sesion: float = 12
    ## Base exclusiva para los tests de la API. Los tests borran y recrean sus tablas.
    ## Si no se define, esos tests se omiten.
    database_url_test: str | None = None


## Instancia única de la configuración, compartida por toda la aplicación.
configuracion = Configuracion()
