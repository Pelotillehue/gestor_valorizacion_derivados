"""!
@package mercado_curvas
@brief Página Curvas: superficie 3D de la historia de una curva cero, comparación de fechas y tabla de vértices.

Lee `GET /mercado/curvas/{codigo}/historia` e interpola cada fecha a una grilla común de plazos.
"""

import altair as alt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from comun import api
from comun.formato import ESCALA_AZUL, en_espanol, numero, rango_fechas

## Plazos en días a los que se interpola cada fecha para dibujar la superficie.
GRILLA_DIAS = [1, 7, 30, 60, 90, 180, 270, 365, 545, 730, 1095, 1460, 1825, 2555, 3650, 5475, 7300, 9125, 10950]
## Colores de las hasta tres curvas que se comparan.
COLORES_FECHAS = ["#2a78d6", "#eb6834", "#1baf7a"]

st.title("Curvas")
st.caption(
    "Curvas cero cargadas, con su tasa en porcentaje. La superficie muestra la tasa de cada plazo "
    "en cada fecha; como los vértices cambian de una fecha a otra, se interpolan linealmente a una "
    "grilla común de plazos."
)

try:
    disponibles = {s["nombre"]: s for s in api.resumen_mercado(api.url_base())["curvas"]}
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()
if not disponibles:
    st.info("No hay curvas cargadas.")
    st.stop()

c1, c2 = st.columns([2, 2])
codigo = c1.selectbox("Curva", list(disponibles))
serie = disponibles[codigo]
with c2:
    desde, hasta = rango_fechas(
        "Rango de fechas", pd.Timestamp(serie["desde"]).date(), pd.Timestamp(serie["hasta"]).date(), f"rango_{codigo}"
    )

historia = api.historia_curva(api.url_base(), codigo, desde, hasta)
if not historia:
    st.info("No hay curvas en ese rango.")
    st.stop()

vertices = pd.DataFrame(
    [
        {"Fecha": pd.Timestamp(c["fecha"]), "Plazo (días)": v["plazo_dias"], "Tasa (%)": v["tasa"] * 100}
        for c in historia
        for v in c["vertices"]
    ]
)
fechas = sorted(vertices["Fecha"].unique())
convencion = f"{historia[-1]['fraccion_anio']} {historia[-1]['factor_capitalizacion']}"

# ------------------------------------------------------------------- superficie
por_fecha = {f: g.sort_values("Plazo (días)") for f, g in vertices.groupby("Fecha")}
plazo_min = max(g["Plazo (días)"].min() for g in por_fecha.values())
plazo_max = min(g["Plazo (días)"].max() for g in por_fecha.values())
grilla = [d for d in GRILLA_DIAS if plazo_min <= d <= plazo_max] or [plazo_min, plazo_max]
superficie = np.array([np.interp(grilla, g["Plazo (días)"], g["Tasa (%)"]) for g in por_fecha.values()])

st.subheader("Superficie histórica")
figura = go.Figure(
    go.Surface(
        x=[d / 365 for d in grilla],
        y=[pd.Timestamp(f).to_pydatetime() for f in por_fecha],
        z=superficie,
        colorscale=[[i / (len(ESCALA_AZUL) - 1), c] for i, c in enumerate(ESCALA_AZUL)],
        colorbar=dict(title="Tasa (%)", tickformat=".2f"),
        hovertemplate="Plazo %{x:.2f} años<br>Fecha %{y|%d-%m-%Y}<br>Tasa %{z:.4f}%<extra></extra>",
    )
)
figura.update_layout(
    height=620,
    margin=dict(l=0, r=0, t=10, b=0),
    separators=",.",
    scene=dict(
        xaxis=dict(title="Plazo (años)"),
        yaxis=dict(title="Fecha", tickformat="%m-%Y"),
        zaxis=dict(title="Tasa (%)", tickformat=".2f"),
        camera=dict(eye=dict(x=1.6, y=-1.6, z=0.8)),
    ),
)
st.plotly_chart(figura, width="stretch")
st.caption(
    f"{len(fechas)} fechas entre {fechas[0]:%d-%m-%Y} y {fechas[-1]:%d-%m-%Y}; plazos de "
    f"{grilla[0]} a {grilla[-1]} días. Tasas en convención {convencion}. Se puede rotar y acercar con el mouse."
)

# ---------------------------------------------------------- curva de una fecha
st.subheader("Curva por fecha")
elegidas = st.multiselect(
    "Fechas a comparar (hasta 3)",
    fechas,
    default=[fechas[0], fechas[-1]] if len(fechas) > 1 else fechas,
    max_selections=3,
    format_func=lambda f: f"{pd.Timestamp(f):%d-%m-%Y}",
)
if elegidas:
    curvas = vertices[vertices["Fecha"].isin(elegidas)].copy()
    curvas["Plazo (años)"] = curvas["Plazo (días)"] / 365
    curvas["Etiqueta"] = curvas["Fecha"].dt.strftime("%d-%m-%Y")
    etiquetas = [f"{pd.Timestamp(f):%d-%m-%Y}" for f in sorted(elegidas)]
    grafico = (
        alt.Chart(curvas)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=36, filled=True))
        .encode(
            x=alt.X("Plazo (años):Q", axis=alt.Axis(format=",.0f")),
            y=alt.Y("Tasa (%):Q", scale=alt.Scale(zero=False), axis=alt.Axis(format=",.2f")),
            color=alt.Color(
                "Etiqueta:N",
                title="Fecha",
                scale=alt.Scale(domain=etiquetas, range=COLORES_FECHAS[: len(etiquetas)]),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("Etiqueta:N", title="Fecha"),
                alt.Tooltip("Plazo (días):Q", format=",.0f"),
                alt.Tooltip("Tasa (%):Q", format=",.4f"),
            ],
        )
        .properties(height=360)
    )
    st.altair_chart(en_espanol(grafico), width="stretch")

    st.subheader("Vértices")
    st.caption("Tasas en %. Una celda vacía indica que la curva de esa fecha no tiene ese vértice.")
    tabla = curvas.pivot_table(index="Plazo (días)", columns="Etiqueta", values="Tasa (%)").reindex(columns=etiquetas)
    tabla = tabla.map(lambda v: numero(v, 4))
    tabla.insert(0, "Plazo (años)", [numero(d / 365, 2) for d in tabla.index])
    st.dataframe(tabla, width="stretch", height=360)

with st.expander("Superficie en tabla (tasas interpoladas, %)"):
    tabla_superficie = pd.DataFrame(superficie, index=[f"{pd.Timestamp(f):%d-%m-%Y}" for f in por_fecha], columns=grilla)
    tabla_superficie.index.name = "Fecha"
    tabla_superficie.columns = [f"{d} d" for d in grilla]
    st.dataframe(tabla_superficie.iloc[::-1].map(lambda v: numero(v, 4)), width="stretch")
