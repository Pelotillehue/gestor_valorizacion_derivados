"""!
@package comun.api
@brief Cliente HTTP de la API del valorizador. Todas las páginas leen y escriben a través de este módulo.

Usa `httpx`. Las lecturas pesadas se guardan en el caché de Streamlit (`st.cache_data`) por
5 minutos; @ref comun.api.limpiar_cache lo vacía cuando se cargan datos nuevos o se presiona "Volver a
leer datos". La dirección de la API sale de la barra lateral, de la variable de entorno
`VALORIZADOR_API_URL` o, por defecto, `http://localhost:8000`.
"""

import os
from datetime import date

import httpx
import streamlit as st

## Dirección de la API si no se indica otra.
URL_POR_DEFECTO = os.environ.get("VALORIZADOR_API_URL", "http://localhost:8000")
## Operaciones por página al recorrer `GET /operaciones`.
TAMANO_PAGINA = 1000


class ErrorAPI(Exception):
    """!
    @brief Respuesta de error de la API, con su código HTTP y el detalle que entrega.
    """

    def __init__(self, codigo: int, detalle):
        """!
        @brief Crea el error.
        @param codigo Código HTTP.
        @param detalle Campo `detail` de la respuesta: texto o lista de errores de validación.
        """
        self.codigo = codigo
        self.detalle = detalle
        super().__init__(f"{codigo}: {detalle}")


def url_base() -> str:
    """!
    @brief Dirección de la API elegida en la barra lateral.
    @return URL sin barra final.
    """
    return st.session_state.get("api_url", URL_POR_DEFECTO).rstrip("/")


def _http(url: str, timeout: float) -> httpx.Client:
    """!
    @brief Cliente HTTP hacia la API con el token de la sesión de Streamlit, si hay uno.
    @param url Dirección base de la API.
    @param timeout Segundos de espera.
    @return `httpx.Client`.
    """
    token = st.session_state.get("token")
    encabezados = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=url, timeout=timeout, headers=encabezados)


def _cliente() -> httpx.Client:
    """!
    @brief Cliente HTTP con la dirección actual y un tiempo de espera de 5 minutos.
    @return `httpx.Client`.
    """
    return _http(url_base(), 300)


# ------------------------------------------------------------------ sesión


def login(usuario: str, clave: str) -> dict:
    """!
    @brief `POST /auth/login`.
    @param usuario Correo.
    @param clave Clave.
    @return Usuario, nombre, token y vencimiento.
    @throws ErrorAPI 401 si las credenciales no son válidas.
    """
    with httpx.Client(base_url=url_base(), timeout=30) as c:
        return _respuesta(c.post("/auth/login", json={"usuario": usuario, "clave": clave}))


def sesion_vigente() -> bool:
    """!
    @brief Consulta `GET /auth/yo` con el token de la sesión.
    @return Falso sólo si la API rechaza el token (401); si la API no responde, verdadero, para
        no cerrar la sesión por una caída de red.
    """
    try:
        with _cliente() as c:
            return c.get("/auth/yo", timeout=5).status_code != 401
    except httpx.HTTPError:
        return True


def _respuesta(r: httpx.Response):
    """!
    @brief Devuelve el JSON de una respuesta o lanza el error que informa la API.
    @param r Respuesta HTTP.
    @return Cuerpo JSON.
    @throws ErrorAPI Si el código es 400 o mayor.
    """
    if r.status_code >= 400:
        try:
            detalle = r.json().get("detail", r.text)
        except ValueError:
            detalle = r.text
        raise ErrorAPI(r.status_code, detalle)
    return r.json()


def texto_error(error: Exception) -> str:
    """!
    @brief Mensaje legible de un error, incluidos los de validación de FastAPI y los de conexión.
    @param error Excepción capturada.
    @return Texto para mostrar al usuario.
    """
    if isinstance(error, ErrorAPI) and isinstance(error.detalle, list):
        partes = []
        for e in error.detalle:
            lugar = ".".join(str(x) for x in e.get("loc", [])[1:])
            partes.append(f"{lugar}: {e.get('msg')}" if lugar else str(e.get("msg")))
        return "; ".join(partes)
    if isinstance(error, ErrorAPI):
        return str(error.detalle)
    if isinstance(error, httpx.HTTPError):
        return f"No se pudo conectar con la API en {url_base()}"
    return str(error)


def salud() -> bool:
    """!
    @brief Consulta `GET /salud`.
    @return Verdadero si la API responde.
    """
    try:
        with _cliente() as c:
            return c.get("/salud", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


# ------------------------------------------------------------------ operaciones


@st.cache_data(ttl=300, show_spinner="Leyendo operaciones…")
def operaciones(url: str, estado: str | None = "VIGENTE") -> list[dict]:
    """!
    @brief Todas las operaciones, recorriendo las páginas de `GET /operaciones`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param estado Filtro de estado; nada para todas.
    @return Lista de operaciones.
    """
    resultado, desde = [], 0
    with _http(url, 300) as c:
        while True:
            params = {"limite": TAMANO_PAGINA, "desde": desde}
            if estado:
                params["estado"] = estado
            pagina = _respuesta(c.get("/operaciones", params=params))
            resultado.extend(pagina)
            if len(pagina) < TAMANO_PAGINA:
                return resultado
            desde += TAMANO_PAGINA


def operacion(deal_number: str) -> dict:
    """!
    @brief `GET /operaciones/{deal_number}`.
    @param deal_number Folio.
    @return La operación.
    """
    with _cliente() as c:
        return _respuesta(c.get(f"/operaciones/{deal_number}"))


def crear(datos: dict) -> dict:
    """!
    @brief `POST /operaciones`.
    @param datos Cuerpo de la operación.
    @return La operación creada.
    """
    with _cliente() as c:
        return _respuesta(c.post("/operaciones", json=datos))


def modificar(deal_number: str, cambios: dict) -> dict:
    """!
    @brief `PATCH /operaciones/{deal_number}`.
    @param deal_number Folio.
    @param cambios Campos a cambiar.
    @return La operación modificada.
    """
    with _cliente() as c:
        return _respuesta(c.patch(f"/operaciones/{deal_number}", json=cambios))


def mtm(deal_number: str, fecha: date, moneda: str, detalle: bool = True) -> dict:
    """!
    @brief `GET /operaciones/{deal_number}/mtm`.
    @param deal_number Folio.
    @param fecha Fecha de proceso.
    @param moneda Moneda del resultado.
    @param detalle Si incluye los flujos de cada pata.
    @return La valorización.
    """
    with _cliente() as c:
        params = {"fecha": fecha.isoformat(), "moneda": moneda, "detalle": str(detalle).lower()}
        return _respuesta(c.get(f"/operaciones/{deal_number}/mtm", params=params))


def limpiar_cache() -> None:
    """!
    @brief Vacía el caché de todas las lecturas, para volver a pedirlas a la API.
    """
    operaciones.clear()
    contrapartes.clear()
    cartera_garantias.clear()
    cartera_mtm.clear()
    cartera_vencimientos.clear()
    cartera_flujos.clear()
    cartera_pnl_realizado.clear()
    resumen_mercado.clear()
    serie_indice.clear()
    serie_fx.clear()
    historia_curva.clear()


# ----------------------------------------------------------------- contrapartes


@st.cache_data(ttl=300, show_spinner="Leyendo contrapartes…")
def contrapartes(url: str) -> list[dict]:
    """!
    @brief `GET /contrapartes`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @return Lista de contrapartes.
    """
    with _http(url, 60) as c:
        return _respuesta(c.get("/contrapartes"))


def crear_contraparte(datos: dict) -> dict:
    """!
    @brief `POST /contrapartes`.
    @param datos RUT, nombre, línea y MTA.
    @return La contraparte creada.
    """
    with _cliente() as c:
        return _respuesta(c.post("/contrapartes", json=datos))


def modificar_contraparte(rut: str, cambios: dict) -> dict:
    """!
    @brief `PATCH /contrapartes/{rut}`.
    @param rut RUT.
    @param cambios Campos a cambiar.
    @return La contraparte modificada.
    """
    with _cliente() as c:
        return _respuesta(c.patch(f"/contrapartes/{rut}", json=cambios))


# ---------------------------------------------------------------------- cartera


@st.cache_data(ttl=300, show_spinner="Valorizando la cartera…")
def cartera_mtm(url: str, fecha: date, moneda: str) -> dict:
    """!
    @brief `GET /cartera/mtm`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Fecha de proceso.
    @param moneda Moneda del resultado.
    @return MtM de la cartera.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/mtm", params={"fecha": fecha.isoformat(), "moneda": moneda}))


@st.cache_data(ttl=300, show_spinner="Calculando vencimientos…")
def cartera_vencimientos(url: str, fecha: date) -> dict:
    """!
    @brief `GET /cartera/vencimientos`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Fecha de proceso.
    @return Montos al vencimiento.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/vencimientos", params={"fecha": fecha.isoformat()}))


@st.cache_data(ttl=300, show_spinner="Calculando garantías…")
def cartera_garantias(url: str, fecha: date) -> dict:
    """!
    @brief `GET /cartera/garantias`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Fecha de proceso.
    @return Control de garantías por contraparte.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/garantias", params={"fecha": fecha.isoformat()}))


@st.cache_data(ttl=300, show_spinner="Proyectando flujos…")
def cartera_flujos(url: str, fecha: date) -> dict:
    """!
    @brief `GET /cartera/flujos`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Fecha de proceso.
    @return Flujos futuros de la cartera.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/flujos", params={"fecha": fecha.isoformat()}))


@st.cache_data(ttl=300, show_spinner="Valorizando los forwards…")
def cartera_forwards_basilea(url: str, fecha: date) -> dict:
    """!
    @brief `GET /cartera/forwards-basilea`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Fecha de proceso.
    @return Detalle de los FX Forward vigentes con su valor razonable activo y pasivo.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/forwards-basilea", params={"fecha": fecha.isoformat()}))


@st.cache_data(ttl=300, show_spinner="Calculando P&L realizado…")
def cartera_pnl_realizado(url: str, fecha: date, desde: date) -> dict:
    """!
    @brief `GET /cartera/pnl-realizado`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param fecha Último vencimiento incluido.
    @param desde Primer vencimiento incluido.
    @return P&L realizado de los forwards vencidos en el período.
    """
    with _http(url, 600) as c:
        return _respuesta(c.get("/cartera/pnl-realizado", params={"fecha": fecha.isoformat(), "desde": desde.isoformat()}))


def fx(fecha: date) -> dict[str, float]:
    """!
    @brief `GET /mercado/fx?fecha=`.
    @param fecha Fecha.
    @return Diccionario par → valor.
    """
    with _cliente() as c:
        return _respuesta(c.get("/mercado/fx", params={"fecha": fecha.isoformat()}))


# ---------------------------------------------------------------------- mercado


@st.cache_data(ttl=300, show_spinner=False)
def resumen_mercado(url: str) -> dict:
    """!
    @brief `GET /mercado/resumen`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @return Series guardadas con su rango de fechas.
    """
    with _http(url, 60) as c:
        return _respuesta(c.get("/mercado/resumen"))


def _rango(desde: date | None, hasta: date | None) -> dict:
    """!
    @brief Parámetros de consulta `desde` y `hasta`, omitiendo los vacíos.
    @param desde Primera fecha o nada.
    @param hasta Última fecha o nada.
    @return Diccionario de parámetros.
    """
    return {k: v.isoformat() for k, v in (("desde", desde), ("hasta", hasta)) if v}


@st.cache_data(ttl=300, show_spinner="Leyendo valores del índice…")
def serie_indice(url: str, indice: str, desde: date | None = None, hasta: date | None = None) -> dict[str, float]:
    """!
    @brief `GET /mercado/indices/{indice}`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param indice Nombre del índice.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor.
    """
    with _http(url, 60) as c:
        return _respuesta(c.get(f"/mercado/indices/{indice}", params=_rango(desde, hasta)))


@st.cache_data(ttl=300, show_spinner="Leyendo tipos de cambio…")
def serie_fx(url: str, par: str, desde: date | None = None, hasta: date | None = None) -> dict[str, float]:
    """!
    @brief `GET /mercado/fx/{par}`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param par Par.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor.
    """
    with _http(url, 60) as c:
        return _respuesta(c.get(f"/mercado/fx/{par}", params=_rango(desde, hasta)))


@st.cache_data(ttl=300, show_spinner="Leyendo curvas…")
def historia_curva(url: str, codigo: str, desde: date | None = None, hasta: date | None = None) -> list[dict]:
    """!
    @brief `GET /mercado/curvas/{codigo}/historia`.
    @param url Dirección base de la API; forma parte de la clave del caché.
    @param codigo Código de la curva.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Lista de curvas con sus vértices.
    """
    with _http(url, 120) as c:
        return _respuesta(c.get(f"/mercado/curvas/{codigo}/historia", params=_rango(desde, hasta)))
