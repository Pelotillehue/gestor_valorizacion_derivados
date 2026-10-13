"""!
@package mercado_indices
@brief Página Índices: historia del ICP y del SOFR índice, con la tasa overnight implícita.
"""

import altair as alt
import pandas as pd
import streamlit as st

from comun import api
from comun.formato import COLOR_SERIE, NOMBRES_INDICE, columna_numero, en_espanol, numero, rango_fechas

st.title("Índices")
st.caption(
    "Nivel publicado de cada índice overnight, el que usa el valorizador para el interés devengado "
    "de las patas flotantes. La tasa implícita es la tasa overnight anualizada que se desprende "
    "de dos publicaciones consecutivas, en base ACT/360 lineal; como el índice se publica con pocos "
    "decimales, esa tasa muestra pequeñas oscilaciones de redondeo."
)

try:
    disponibles = {s["nombre"]: s for s in api.resumen_mercado(api.url_base())["indices"]}
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()
if not disponibles:
    st.info("No hay índices cargados. Se cargan con `python scripts/cargar_indices.py --fecha AAAA-MM-DD`.")
    st.stop()

c1, c2 = st.columns([2, 2])
indice = c1.segmented_control(
    "Índice", list(disponibles), default=next(iter(disponibles)), format_func=lambda i: NOMBRES_INDICE.get(i, i)
) or next(iter(disponibles))
serie = disponibles[indice]
with c2:
    desde, hasta = rango_fechas(
        "Rango de fechas", pd.Timestamp(serie["desde"]).date(), pd.Timestamp(serie["hasta"]).date(), f"rango_{indice}"
    )

valores = api.serie_indice(api.url_base(), indice, desde, hasta)
if len(valores) < 2:
    st.info("Hay menos de dos valores en ese rango.")
    st.stop()

datos = pd.DataFrame({"Fecha": pd.to_datetime(list(valores)), "Valor": list(valores.values())}).sort_values("Fecha")
dias = datos["Fecha"].diff().dt.days
datos["Tasa implícita (%)"] = (datos["Valor"] / datos["Valor"].shift() - 1) * 360 / dias * 100

primero, ultimo = datos.iloc[0], datos.iloc[-1]
dias_periodo = (ultimo["Fecha"] - primero["Fecha"]).days
m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Último valor ({ultimo['Fecha']:%d-%m-%Y})", numero(ultimo["Valor"], 2 if ultimo["Valor"] > 100 else 8))
m2.metric("Variación del período", f"{numero((ultimo['Valor'] / primero['Valor'] - 1) * 100, 4)}%")
m3.metric(
    "Tasa promedio del período",
    f"{numero((ultimo['Valor'] / primero['Valor'] - 1) * 360 / dias_periodo * 100, 4)}%",
    help="Anualizada en base ACT/360 lineal entre la primera y la última fecha del rango.",
)
m4.metric("Publicaciones", numero(len(datos)))

base = alt.Chart(datos).encode(x=alt.X("Fecha:T", title=None, axis=alt.Axis(format="%d-%m-%Y", labelAngle=0)))
nivel = base.mark_line(color=COLOR_SERIE, strokeWidth=2).encode(
    y=alt.Y("Valor:Q", title="Valor del índice", scale=alt.Scale(zero=False), axis=alt.Axis(format=",.2~f")),
    tooltip=[alt.Tooltip("Fecha:T", format="%d-%m-%Y"), alt.Tooltip("Valor:Q", format=",.8~f")],
)
tasa = base.mark_line(color=COLOR_SERIE, strokeWidth=2, interpolate="step-after").encode(
    y=alt.Y("Tasa implícita (%):Q", scale=alt.Scale(zero=False), axis=alt.Axis(format=",.3f")),
    tooltip=[alt.Tooltip("Fecha:T", format="%d-%m-%Y"), alt.Tooltip("Tasa implícita (%):Q", format=",.4f")],
)
st.subheader("Valor del índice")
st.altair_chart(en_espanol(nivel.properties(height=320)), width="stretch")
st.subheader("Tasa overnight implícita")
st.altair_chart(en_espanol(tasa.properties(height=240)), width="stretch")

st.subheader("Valores")
st.dataframe(
    datos.sort_values("Fecha", ascending=False),
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        "Fecha": st.column_config.DateColumn(format="DD-MM-YYYY"),
        "Valor": columna_numero(8 if ultimo["Valor"] < 100 else 2),
        "Tasa implícita (%)": columna_numero(4),
    },
)
