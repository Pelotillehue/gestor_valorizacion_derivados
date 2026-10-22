"""!
@package inicio
@brief Punto de entrada de la app Streamlit del Valorizador de Derivados.

Pide usuario y clave antes de mostrar cualquier página: los valida la API contra la tabla
`usuario` y entrega un token que la app guarda en la sesión de Streamlit y en una cookie del
navegador (@ref comun.sesion). Así, al actualizar la página o abrir otra pestaña, la sesión se
retoma sin volver a pedir las credenciales mientras el token siga vigente. Luego define el menú
(secciones Cartera, Mercado, Reportes y Archivos), el logo y la barra lateral con el usuario,
la dirección de la API, su estado de conexión y el botón para volver a leer los datos.

Uso, con la API corriendo en otra terminal, desde la carpeta del proyecto:
@code
streamlit run app/inicio.py
@endcode

La app no accede a la base de datos: todo lo lee y escribe a través de la API, con el cliente
de @ref comun.api.
"""

from pathlib import Path

import httpx
import streamlit as st

from comun import api, sesion

## Carpeta con las imágenes de la app.
CARPETA_ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Gestor de Cartera de Derivados", page_icon="📈", layout="wide")

## Logo que se muestra arriba del menú lateral.
LOGO = CARPETA_ASSETS / "logo.png"
## Versión cuadrada del logo para el menú colapsado. Es opcional: si no existe se usa el logo.
ICONO = CARPETA_ASSETS / "icono.png"
if LOGO.exists():
    st.logo(str(LOGO), size="large", icon_image=str(ICONO) if ICONO.exists() else None)
    # "large" deja el logo en 32 px de alto. Se agranda a 52 px: el espacio del logo en el menú
    # lateral mide 200 px de ancho, y con la proporción de logo.png no cabe más sin deformarlo.
    st.html(
        """<style>
        [data-testid="stSidebarLogo"] { height: 3.25rem; width: auto; max-width: 100%; object-fit: contain; }
        </style>"""
    )

st.session_state.setdefault("api_url", api.URL_POR_DEFECTO)

## Claves de `st.session_state` que identifican la sesión iniciada.
CLAVES_SESION = ("token", "usuario", "nombre")


def cerrar_sesion() -> None:
    """!
    @brief Olvida la sesión en esta pestaña y marca la cookie para borrarla en la siguiente ejecución.

    También impide retomarla desde la cookie: Streamlit sigue entregando las cookies que el
    navegador envió al conectarse la pestaña, aunque después se borren.
    """
    for clave in CLAVES_SESION:
        st.session_state.pop(clave, None)
    st.session_state["sesion_cerrada"] = True
    st.session_state["borrar_cookie"] = True


def retomar_sesion() -> None:
    """!
    @brief Retoma la sesión guardada en la cookie si la API confirma que el token sigue vigente.

    Si la API rechaza el token, marca la cookie para borrarla. Si la API no responde, la deja,
    para retomarla cuando vuelva.
    """
    token = sesion.token_guardado()
    if not token:
        return
    try:
        datos = api.datos_sesion(token)
    except httpx.HTTPError:
        return
    if datos is None:
        st.session_state["sesion_cerrada"] = True
        st.session_state["borrar_cookie"] = True
        return
    st.session_state.update(token=token, usuario=datos["usuario"], nombre=datos.get("nombre"))


def pantalla_login(aviso: str | None = None) -> None:
    """!
    @brief Formulario de inicio de sesión. Si las credenciales son válidas guarda el token y recarga la app.
    @param aviso Mensaje opcional sobre la sesión anterior, por ejemplo que venció.
    """
    _, centro, _ = st.columns([1.1, 1, 1.1])
    with centro:
        st.subheader("Gestor de Cartera de Derivados", anchor=False)
        if aviso:
            st.warning(aviso)
        with st.form("login"):
            usuario = st.text_input("Usuario", placeholder="correo@empresa.cl")
            clave = st.text_input("Clave", type="password")
            ingresar = st.form_submit_button("Ingresar", type="primary", icon=":material/login:", width="stretch")
        with st.expander("Dirección de la API"):
            # Sin key: el campo de la barra lateral usa la key "api_url" y Streamlit borra el
            # estado de un widget que deja de mostrarse.
            st.session_state["api_url"] = st.text_input(
                "Dirección de la API", value=st.session_state["api_url"], label_visibility="collapsed"
            )
        if ingresar:
            try:
                datos = api.login(usuario, clave)
            except api.ErrorAPI as e:
                st.error("Usuario o clave incorrectos." if e.codigo == 401 else api.texto_error(e))
            except Exception as e:
                st.error(api.texto_error(e))
            else:
                st.session_state.update(
                    token=datos["token"], usuario=datos["usuario"], nombre=datos.get("nombre"),
                    guardar_cookie=datos.get("vence") or "",
                )
                st.session_state.pop("sesion_cerrada", None)
                st.rerun()


if not st.session_state.get("token") and not st.session_state.get("sesion_cerrada"):
    retomar_sesion()
if st.session_state.pop("borrar_cookie", False):
    sesion.borrar()
if not st.session_state.get("token"):
    pantalla_login()
    st.stop()
if not api.sesion_vigente():
    cerrar_sesion()
    sesion.borrar()
    st.session_state.pop("borrar_cookie", None)
    pantalla_login("La sesión venció o ya no es válida. Ingrese nuevamente.")
    st.stop()
if "guardar_cookie" in st.session_state:
    sesion.guardar(st.session_state["token"], st.session_state.pop("guardar_cookie") or None)

paginas = st.navigation(
    {
        "Cartera": [
            st.Page("paginas/operaciones_fx.py", title="Operaciones FX Forward", icon=":material/swap_horiz:", default=True),
            st.Page("paginas/operaciones_irs.py", title="Operaciones Interest Rate Swap", icon=":material/swap_horiz:"),
            st.Page("paginas/operaciones_ccs.py", title="Operaciones Cross Currency Swap", icon=":material/swap_horiz:"),
            st.Page("paginas/mtm.py", title="MtM de cartera", icon=":material/calculate:"),
            st.Page("paginas/vencimientos.py", title="Calendario de Flujos", icon=":material/event:"),
            st.Page("paginas/contrapartes.py", title="Contrapartes", icon=":material/groups:"),
        ],
        "Mercado": [
            st.Page("paginas/mercado_indices.py", title="Índices", icon=":material/show_chart:"),
            st.Page("paginas/mercado_fx.py", title="Tipos de cambio y UF", icon=":material/currency_exchange:"),
            st.Page("paginas/mercado_curvas.py", title="Curvas", icon=":material/stacked_line_chart:"),
        ],
        "Reportes": [
            st.Page("paginas/reporte_pnl.py", title="P&L No Realizado", icon=":material/account_balance:"),
            st.Page("paginas/reporte_pnl_realizado.py", title="P&L Realizado", icon=":material/paid:"),
            st.Page("paginas/reportes.py", title="Listado de Operaciones Vigentes", icon=":material/download:"),
            st.Page("paginas/reporte_basilea.py", title="Reportes FX Fwd", icon=":material/policy:"),
        ],
        "Archivos": [
            st.Page("paginas/carga.py", title="Carga de operaciones", icon=":material/upload_file:"),
        ],
    },
    expanded=True,
)

with st.sidebar:
    st.caption(f":material/person: {st.session_state.get('nombre') or st.session_state['usuario']}")
    if st.button("Cerrar sesión", icon=":material/logout:", width="stretch"):
        cerrar_sesion()
        api.limpiar_cache()
        st.rerun()
    st.text_input("Dirección de la API", key="api_url")
    if api.salud():
        st.caption(":green[●] API conectada")
    else:
        st.caption(":red[●] API sin respuesta")
        st.caption("Levántela con `uvicorn valorizador.main:app` desde la carpeta del proyecto.")
    if st.button("Volver a leer datos", icon=":material/refresh:", width="stretch"):
        api.limpiar_cache()
        st.rerun()

paginas.run()
