"""!
@package mercado_fx
@brief Página Tipos de cambio y UF: historia de cada par cargado, con sus estadísticas y tabla de valores.
"""

import altair as alt
import pandas as pd
import streamlit as st

from comun import api
from comun.formato import COLOR_SERIE, columna_numero, en_espanol, numero, rango_fechas

st.title("Tipos de cambio y UF")


def nombre(par: str) -> str:
    """!
    @brief Nombre visible de un par: CLFCLP se muestra como UF.
    @param par Par.
    @return Nombre para mostrar.
    """
    return "UF" if par == "CLFCLP" else par.replace("CLF", "UF")



try:
    disponibles = {s["nombre"]: s for s in api.resumen_mercado(api.url_base())["fx"]}
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()
if not disponibles:
    st.info("No hay tipos de cambio cargados.")
    st.stop()

preferidos = [p for p in ("USDCLP", "CLFCLP") if p in disponibles]
orden = preferidos + sorted(p for p in disponibles if p not in preferidos)
c1, c2 = st.columns([2, 2])
par = c1.selectbox("Par", orden, format_func=nombre)
serie = disponibles[par]
with c2:
    desde, hasta = rango_fechas(
        "Rango de fechas", pd.Timestamp(serie["desde"]).date(), pd.Timestamp(serie["hasta"]).date(), f"rango_{par}"
    )

valores = api.serie_fx(api.url_base(), par, desde, hasta)
if not valores:
    st.info("No hay valores en ese rango.")
    st.stop()

datos = pd.DataFrame({"Fecha": pd.to_datetime(list(valores)), "Valor": list(valores.values())}).sort_values("Fecha")
datos["Variación diaria (%)"] = datos["Valor"].pct_change() * 100
decimales = 2 if datos["Valor"].abs().max() >= 100 else 4

primero, ultimo = datos.iloc[0], datos.iloc[-1]
m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Último ({ultimo['Fecha']:%d-%m-%Y})", numero(ultimo["Valor"], decimales))
m2.metric("Variación del período", f"{numero((ultimo['Valor'] / primero['Valor'] - 1) * 100, 2)}%")
m3.metric("Mínimo", numero(datos["Valor"].min(), decimales))
m4.metric("Máximo", numero(datos["Valor"].max(), decimales))

grafico = (
    alt.Chart(datos)
    .mark_line(color=COLOR_SERIE, strokeWidth=2)
    .encode(
        x=alt.X("Fecha:T", title=None, axis=alt.Axis(format="%d-%m-%Y", labelAngle=0)),
        y=alt.Y("Valor:Q", title=nombre(par), scale=alt.Scale(zero=False), axis=alt.Axis(format=f",.{decimales}f")),
        tooltip=[alt.Tooltip("Fecha:T", format="%d-%m-%Y"), alt.Tooltip("Valor:Q", format=f",.{decimales}f")],
    )
    .properties(height=380)
)
st.altair_chart(en_espanol(grafico), width="stretch")

st.subheader("Valores")
st.dataframe(
    datos.sort_values("Fecha", ascending=False),
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        "Fecha": st.column_config.DateColumn(format="DD-MM-YYYY"),
        "Valor": columna_numero(decimales),
        "Variación diaria (%)": columna_numero(3),
    },
)
