"""!
@package valorizador.main
@brief Punto de entrada de la API FastAPI.

Crea la aplicación, registra los routers de @ref valorizador.api y traduce los errores de
@ref valorizador.errores a respuestas HTTP. Todos los endpoints salvo `/salud` y
`/auth/login` exigen el token de @ref valorizador.api.autenticacion.

Para ejecutarla, desde la carpeta del proyecto:
@code
uvicorn valorizador.main:app --reload
@endcode
La documentación interactiva queda en `http://localhost:8000/docs`.
"""

import re

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from valorizador import errores
from valorizador.api import autenticacion, cartera, contrapartes, mercado, operaciones

## Aplicación FastAPI que sirve todos los endpoints.
app = FastAPI(
    title="Valorizador de Derivados",
    description="Valorización de FX Forward, IR Swap y CC Swap con QC Financial.",
    version="0.1.0",
)

app.include_router(autenticacion.router)
## Todos los routers de datos exigen un token de sesión, ver @ref valorizador.api.autenticacion.usuario_actual.
_protegido = [Depends(autenticacion.usuario_actual)]
app.include_router(contrapartes.router, dependencies=_protegido)
app.include_router(operaciones.router, dependencies=_protegido)
app.include_router(mercado.router, dependencies=_protegido)
app.include_router(cartera.router, dependencies=_protegido)

## Código HTTP de cada error del dominio. Los que no están aquí responden 400.
_CODIGOS = {
    errores.OperacionNoEncontrada: 404,
    errores.OperacionDuplicada: 409,
    errores.ContraparteNoEncontrada: 404,
    errores.ContraparteDuplicada: 409,
    errores.OperacionNoValorizable: 409,
    errores.DatoMercadoFaltante: 422,
    errores.DatoInvalido: 422,
}


@app.exception_handler(errores.ErrorValorizador)
def _error_de_dominio(_: Request, error: errores.ErrorValorizador) -> JSONResponse:
    """!
    @brief Manejador global de los errores del dominio.

    @param _ Solicitud que originó el error (no se usa).
    @param error Excepción del dominio lanzada por un repositorio o por el motor.
    @return Respuesta JSON `{"detail": mensaje}` con el código que corresponde según `_CODIGOS`.
    """
    codigo = _CODIGOS.get(type(error), 400)
    return JSONResponse(status_code=codigo, content={"detail": str(error)})


@app.get("/salud", tags=["Sistema"], summary="Verifica que la API responde")
def salud() -> dict[str, str]:
    """!
    @brief Verifica que la API responde. Lo usa la app Streamlit para mostrar el estado de conexión.
    @return `{"estado": "ok"}`.
    """
    return {"estado": "ok"}


## Comandos Doxygen que no aportan a la documentación interactiva de la API.
_LINEAS_DOXYGEN = re.compile(r"^\s*@(param|return|throws|package|file|see|note)\b")


def texto_openapi(texto: str) -> str:
    """!
    @brief Adapta un docstring Doxygen para mostrarlo en `/docs`.

    FastAPI y Pydantic usan los docstrings de los endpoints y de los modelos como descripción
    en OpenAPI. Esta función quita el marcador `!`, las líneas de parámetros y retornos (que
    OpenAPI ya describe por su cuenta), el comando `@brief` y las referencias `@ref`.
    @param texto Docstring tal como lo entrega FastAPI.
    @return Texto en Markdown simple.
    """
    if not texto.lstrip().startswith("!"):
        return texto
    lineas = [l for l in texto.lstrip()[1:].splitlines() if not _LINEAS_DOXYGEN.match(l)]
    limpio = "\n".join(lineas).replace("@brief ", "").replace("@code", "```").replace("@endcode", "```")
    return re.sub(r"@ref\s+([\w.]*\w)", lambda m: f"`{m.group(1).rsplit('.', 1)[-1]}`", limpio).strip()


def _limpiar(nodo):
    """!
    @brief Recorre el esquema OpenAPI y adapta cada descripción con @ref valorizador.main.texto_openapi.
    @param nodo Diccionario, lista o valor del esquema.
    @return El mismo nodo, modificado en el lugar.
    """
    if isinstance(nodo, dict):
        for clave, valor in nodo.items():
            if clave == "description" and isinstance(valor, str):
                nodo[clave] = texto_openapi(valor)
            else:
                _limpiar(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            _limpiar(valor)
    return nodo


def _openapi() -> dict:
    """!
    @brief Genera el esquema OpenAPI una vez, con las descripciones adaptadas, y lo guarda en la aplicación.
    @return Esquema OpenAPI.
    """
    if app.openapi_schema is None:
        esquema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        app.openapi_schema = _limpiar(esquema)
    return app.openapi_schema


app.openapi = _openapi
