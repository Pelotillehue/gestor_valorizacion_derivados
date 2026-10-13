"""!
@package inicio
@brief Punto de entrada de la app Streamlit del Valorizador de Derivados.

Define el menú (secciones Cartera, Mercado, Reportes y Archivos), el logo y la barra lateral
con la dirección de la API, su estado de conexión y el botón para volver a leer los datos.

Uso, con la API corriendo en otra terminal, desde la carpeta del proyecto:
@code
streamlit run app/inicio.py
@endcode

La app no accede a la base de datos: todo lo lee y escribe a través de la API, con el cliente
de @ref comun.api.
"""

from pathlib import Path

import streamlit as st

from comun import api

## Carpeta con las imágenes de la app.
CARPETA_ASSETS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Valorizador de Derivados", page_icon="📈", layout="wide")

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

paginas = st.navigation(
    {
        "Cartera": [
            st.Page("paginas/operaciones_fx.py", title="Operaciones FX Forward", icon=":material/swap_horiz:", default=True),
            st.Page("paginas/operaciones_irs.py", title="Operaciones Interest Rate Swap", icon=":material/swap_horiz:"),
            st.Page("paginas/operaciones_ccs.py", title="Operaciones Cross Currency Swap", icon=":material/swap_horiz:"),
            st.Page("paginas/mtm.py", title="MtM de cartera", icon=":material/calculate:"),
            st.Page("paginas/vencimientos.py", title="Vencimientos", icon=":material/event:"),
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
        ],
        "Archivos": [
            st.Page("paginas/carga.py", title="Carga de operaciones", icon=":material/upload_file:"),
        ],
    },
    expanded=True,
)

with st.sidebar:
    st.session_state.setdefault("api_url", api.URL_POR_DEFECTO)
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
