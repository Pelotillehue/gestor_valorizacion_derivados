"""!
@package mtm
@brief Página MtM de cartera: MtM de toda la cartera vigente a una fecha, con totales por producto y por contraparte.

Usa `GET /cartera/mtm`. Si ninguna operación se puede valorizar, muestra los motivos agrupados.
"""


import altair as alt
import pandas as pd
import streamlit as st

from comun import api
from comun.formato import COLOR_PRODUCTO, FECHA_INICIAL, MODALIDADES, MONEDAS, PRODUCTOS, columna_numero, en_espanol, escala, numero, rut

st.title("MtM de cartera")

c1, c2, _ = st.columns([1.2, 1, 3])
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
moneda = c2.selectbox("Moneda", MONEDAS, index=0)
st.session_state["fecha_proceso"] = fecha

try:
    cartera = api.cartera_mtm(api.url_base(), fecha, moneda)
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

if not cartera["operaciones"]:
    st.info("No hay operaciones vigentes.")
    st.stop()

valorizadas = [o for o in cartera["operaciones"] if o["mtm"] is not None]
if not valorizadas:
    motivos = pd.Series([o["error"] for o in cartera["operaciones"]]).value_counts()
    st.error(
        f"Ninguna operación se pudo valorizar al {fecha:%d-%m-%Y}. Lo más probable es que falten datos de "
        "mercado para esa fecha (revise la sección Mercado). Motivos:\n\n"
        + "\n".join(f"- {motivo} ({n} operaciones)" for motivo, n in motivos.items())
    )
    st.stop()

# ---------------------------------------------------------------------- totales
totales = pd.DataFrame(cartera["totales"])
totales["Producto"] = totales["producto"].map(PRODUCTOS)
divisor, unidad = escala(totales["mtm"].abs().max())
totales["valor"] = totales["mtm"] / divisor

columnas = st.columns(len(totales) + 1)
con_error_total = int(totales["con_error"].sum())
columnas[0].metric(
    f"MtM total ({moneda})",
    numero(cartera["mtm_total"], 0),
    help="Suma de las operaciones valorizadas. Las que no se pudieron valorizar no suman.",
)
for columna, fila in zip(columnas[1:], totales.itertuples()):
    columna.metric(
        fila.Producto,
        numero(fila.mtm, 0),
        delta=f"{fila.con_error} sin valorizar" if fila.con_error else f"{fila.valorizadas} valorizadas",
        delta_color="inverse" if fila.con_error else "off",
        delta_arrow="off",
    )

if con_error_total:
    st.warning(
        f"{numero(con_error_total)} de {numero(len(cartera['operaciones']))} operaciones no se pudieron valorizar "
        "y no están en los totales. El motivo está al final de la página."
    )

grafico = (
    alt.Chart(totales)
    .mark_bar(cornerRadiusEnd=4, height=28)
    .encode(
        y=alt.Y("Producto:N", sort=list(PRODUCTOS.values()), title=None, axis=alt.Axis(labelLimit=220)),
        x=alt.X("valor:Q", title=f"MtM ({unidad} de {moneda})", axis=alt.Axis(format=",.0f", grid=True)),
        color=alt.Color(
            "Producto:N",
            scale=alt.Scale(domain=list(COLOR_PRODUCTO), range=list(COLOR_PRODUCTO.values())),
            legend=None,
        ),
        tooltip=[
            alt.Tooltip("Producto:N"),
            alt.Tooltip("mtm:Q", title=f"MtM ({moneda})", format=",.0f"),
            alt.Tooltip("operaciones:Q", title="Operaciones"),
            alt.Tooltip("valorizadas:Q", title="Valorizadas"),
            alt.Tooltip("con_error:Q", title="Sin valorizar"),
        ],
    )
    .properties(height=60 * len(totales) + 30)
)
regla = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#8a8984").encode(x="x:Q")
st.altair_chart(en_espanol(grafico + regla), width="stretch")

# -------------------------------------------------------------- por operación
st.subheader("Por operación")
detalle = pd.DataFrame(cartera["operaciones"])
detalle["Producto"] = detalle["producto"].map(PRODUCTOS)
detalle["Modalidad"] = detalle["modalidad_liquidacion"].map(MODALIDADES)
detalle["Vencimiento"] = pd.to_datetime(detalle["fecha_vencimiento"])
detalle["Rut Contraparte"] = detalle["rut_contraparte"].map(rut)
detalle = detalle.rename(columns={"deal_number": "Folio", "contraparte": "Contraparte", "mtm": f"MtM ({moneda})"})
# Las operaciones sin valorizar traen MtM nulo; to_numeric lo deja como NaN para poder redondear.
detalle[f"MtM ({moneda})"] = pd.to_numeric(detalle[f"MtM ({moneda})"]).round(0)

f1, f2, f3 = st.columns([2, 2, 1.5])
productos = f1.multiselect("Producto", list(PRODUCTOS.values()), placeholder="Todos")
contrapartes = f2.multiselect("Contraparte", sorted(detalle["Contraparte"].dropna().unique()), placeholder="Todas")
solo = f3.segmented_control("Mostrar", ["Todas", "Valorizadas", "Sin valorizar"], default="Todas")

vista = detalle
if productos:
    vista = vista[vista["Producto"].isin(productos)]
if contrapartes:
    vista = vista[vista["Contraparte"].isin(contrapartes)]
if solo == "Valorizadas":
    vista = vista[vista["error"].isna()]
elif solo == "Sin valorizar":
    vista = vista[vista["error"].notna()]

st.caption(f"{numero(len(vista))} operaciones · MtM {numero(vista[f'MtM ({moneda})'].sum(), 0)} {moneda}")
st.dataframe(
    vista[["Folio", "Producto", "Rut Contraparte", "Contraparte", "Modalidad", "Vencimiento", f"MtM ({moneda})", "error"]].rename(
        columns={"error": "Motivo sin valorizar"}
    ).fillna({"Motivo sin valorizar": ""}),
    hide_index=True,
    width="stretch",
    height=420,
    column_config={
        "Vencimiento": st.column_config.DateColumn(format="DD-MM-YYYY"),
        f"MtM ({moneda})": columna_numero(0),
    },
)

por_contraparte = (
    detalle.pivot_table(index="Contraparte", columns="Producto", values=f"MtM ({moneda})", aggfunc="sum", fill_value=0)
    .reindex(columns=[p for p in PRODUCTOS.values() if p in set(detalle["Producto"])])
)
por_contraparte["Total"] = por_contraparte.sum(axis=1)
with st.expander("MtM por contraparte"):
    st.dataframe(
        por_contraparte,
        width="stretch",
        column_config={c: columna_numero(0) for c in por_contraparte.columns},
    )

# ------------------------------------------------------------------ sin valorizar
errores = detalle[detalle["error"].notna()]
if len(errores):
    with st.expander(f"Motivos de las {numero(len(errores))} operaciones sin valorizar"):
        motivos = errores["error"].str.replace(r" para la fecha \d{4}-\d{2}-\d{2}", "", regex=True)
        st.dataframe(
            pd.crosstab(motivos.rename("Motivo"), errores["Producto"]),
            width="stretch",
        )
        st.caption(
            "Las patas flotantes necesitan el valor de su índice en la fecha de proceso y en el inicio "
            "del cupón vigente. Se cargan con scripts/cargar_indices.py o con POST /mercado/indices."
        )
