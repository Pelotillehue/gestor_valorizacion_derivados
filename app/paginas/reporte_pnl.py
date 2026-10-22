"""!
@package reporte_pnl
@brief Página P&L No Realizado: P&L no realizado de las operaciones vigentes, calzadas y descalzadas, y control de garantías.

Usa `GET /cartera/mtm` y `GET /cartera/garantias`. El Excel agrega en el bloque liquidado el
P&L realizado del año (`GET /cartera/pnl-realizado`). Los archivos Excel y PDF los arma
@ref comun.reporte_pnl.
"""

from datetime import date
from functools import partial

import altair as alt
import pandas as pd
import streamlit as st

from comun import api, reporte_pnl
from comun.formato import FECHA_INICIAL, PRODUCTOS, columna_numero, en_espanol, escala, numero

st.title("P&L No Realizado")
# st.caption(
    #"MtM de las operaciones vigentes agrupado por contraparte"
    #"Una operación está **calzada** cuando "
    #"tiene un grupo de calce, es decir, otra u otras operaciones la cubren en el mismo monto y "
    #"vencimiento; si no, está **descalzada**. Las operaciones ya vencidas están en **P&L Realizado**. "
    #"Hay **llamado a constituir garantías** cuando la exposición de la contraparte supera su monto de línea; "
    #"se llama por el exceso o por el MTA, el mayor de los dos."
# )

c1, c2, c3 = st.columns([1.2, 2.4, 1.6])
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
st.session_state["fecha_proceso"] = fecha
productos = c2.multiselect("Productos", list(PRODUCTOS.values()), placeholder="Todos")
perspectiva = c3.segmented_control(
    "Perspectiva",
    ["Institución", "Cliente"],
    default="Institución",
    help="Institución: el MtM de la cartera propia. Cliente: el mismo P&L con el signo invertido, "
    "como lo ve la contraparte; una operación es calzada sólo si su calce es con la misma contraparte.",
) or "Institución"

try:
    cartera = api.cartera_mtm(api.url_base(), fecha, "CLP")
    garantias = api.cartera_garantias(api.url_base(), fecha)
    inicio_anio = date(fecha.year, 1, 1)
    realizado = api.cartera_pnl_realizado(api.url_base(), fecha, inicio_anio)
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

operaciones = cartera["operaciones"]
if productos:
    elegidos = {k for k, v in PRODUCTOS.items() if v in productos}
    operaciones = [o for o in operaciones if o["producto"] in elegidos]
sin_valor = [o for o in operaciones if o["mtm"] is None]
detalle = reporte_pnl.detalle(operaciones, perspectiva == "Cliente")
tabla = reporte_pnl.resumen(detalle, garantias["contrapartes"])

if tabla.empty:
    st.info("No hay operaciones valorizadas con esos filtros.")
    st.stop()
if productos or perspectiva == "Cliente":
    st.info(
        "El control de garantías no depende de los filtros: usa todas las operaciones vigentes de cada "
        "contraparte, desde la perspectiva de la institución."
    )
if sin_valor:
    st.warning(
        f"{len(sin_valor)} operaciones no se pudieron valorizar y no están en el reporte. "
        "El motivo está en la página MtM de cartera."
    )

# ------------------------------------------------------------------------ totales
calzadas, descalzadas = tabla["Calzadas"].sum(), tabla["Descalzadas"].sum()
n_calzadas = int((detalle["Estado calce"] == "Calzada").sum())
llamados = tabla[tabla["Situación"] == reporte_pnl.LLAMADO]
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("P&L no realizado (CLP)", numero(calzadas + descalzadas, 0))
m2.metric("Calzadas", numero(calzadas, 0), delta=f"{n_calzadas} operaciones", delta_color="off", delta_arrow="off")
m3.metric(
    "Descalzadas", numero(descalzadas, 0), delta=f"{len(detalle) - n_calzadas} operaciones", delta_color="off", delta_arrow="off"
)
m4.metric("Contrapartes", numero(len(tabla)))
m5.metric(
    "Llamados a garantías",
    numero(len(llamados)),
    delta=f"{numero(llamados['Monto a llamar'].sum(), 0)} CLP" if len(llamados) else None,
    delta_color="off",
    delta_arrow="off",
)

texto_productos = ", ".join(productos) if productos else "todos"
# El P&L realizado sólo considera FX Forward: se incluye si ese producto está en el filtro.
liquidadas = realizado["operaciones"] if not productos or PRODUCTOS["FX_FORWARD"] in productos else []
liquidado = reporte_pnl.resumen_realizado(reporte_pnl.detalle_realizado(liquidadas, perspectiva == "Cliente"))
d1, d2, _ = st.columns([1, 1, 3])
d1.download_button(
    "Excel",
    partial(reporte_pnl.excel, tabla, detalle, fecha, perspectiva, texto_productos, liquidado, inicio_anio),
    file_name=f"pnl_no_realizado_{fecha:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table:",
    width="stretch",
)
d2.download_button(
    "PDF",
    partial(reporte_pnl.pdf, tabla, fecha, perspectiva, texto_productos),
    file_name=f"pnl_no_realizado_{fecha:%Y%m%d}.pdf",
    mime="application/pdf",
    icon=":material/picture_as_pdf:",
    width="stretch",
)

# ------------------------------------------------------------------------- tabla
st.subheader("Por contraparte")
o1, o2 = st.columns([3, 1.4])
orden = o1.segmented_control(
    "Ordenar por", ["Contraparte", "P&L total", "Monto a llamar"], default="Contraparte"
) or "Contraparte"
solo_llamados = o2.toggle("Sólo con llamado", disabled=llamados.empty)
vista = llamados if solo_llamados else tabla
vista = {
    "Contraparte": vista,
    "P&L total": vista.sort_values("Total"),
    "Monto a llamar": vista.sort_values("Monto a llamar", ascending=False),
}[orden]
total = pd.DataFrame(
    [{"Rut Contraparte": "", "Contraparte": "Total", "Operaciones": vista["Operaciones"].sum(),
      "Calzadas": vista["Calzadas"].sum(), "Descalzadas": vista["Descalzadas"].sum(), "Total": vista["Total"].sum(),
      "Situación": f"{(vista['Situación'] == reporte_pnl.LLAMADO).sum()} llamados",
      "Monto a llamar": vista["Monto a llamar"].sum()}]
)  # fmt: skip
montos = columna_numero(0)
config = {
    "Calzadas": columna_numero(0, "P&L calzadas"),
    "Descalzadas": columna_numero(0, "P&L descalzadas"),
    "Total": columna_numero(0, "P&L no realizado total"),
    "Monto Línea (CLP)": montos,
    "MTA (CLP)": montos,
    "Exceso sobre línea": montos,
    "Monto a llamar": montos,
}


def _resaltar_llamado(fila: pd.Series) -> list[str]:
    """!
    @brief Estilo de fila: la situación en rojo cuando hay llamado a garantía.
    @param fila Fila de la tabla.
    @return Un estilo CSS por columna.
    """
    estilo = "color: #d03b3b; font-weight: 600" if fila["Situación"] == reporte_pnl.LLAMADO else ""
    return [estilo if c == "Situación" else "" for c in fila.index]


st.dataframe(
    pd.concat([vista, total], ignore_index=True).round(0).style.apply(_resaltar_llamado, axis=1),
    hide_index=True, width="stretch", column_config=config, height=min(38 * (len(vista) + 2), 640),
    column_order=["Rut Contraparte", "Contraparte", "Situación", "Operaciones", "Calzadas", "Descalzadas", "Total",
                  "Monto Línea (CLP)", "MTA (CLP)", "Exceso sobre línea", "Monto a llamar"],
)  # fmt: skip

# ------------------------------------------------------------------------ gráfico
st.subheader("P&L por contraparte")
divisor, unidad = escala(tabla[["Calzadas", "Descalzadas"]].abs().max().max())
largo = tabla.melt(id_vars="Contraparte", value_vars=["Calzadas", "Descalzadas"], var_name="Tipo", value_name="P&L")
largo["valor"] = largo["P&L"] / divisor
orden_y = tabla.sort_values("Total", ascending=False)["Contraparte"].tolist()
grafico = (
    alt.Chart(largo)
    .mark_bar(cornerRadius=2, stroke="white", strokeWidth=1)
    .encode(
        y=alt.Y("Contraparte:N", sort=orden_y, title=None, axis=alt.Axis(labelLimit=240, labelOverlap=False)),
        x=alt.X("sum(valor):Q", title=f"P&L no realizado ({unidad} de CLP)", axis=alt.Axis(format=",.0f")),
        color=alt.Color(
            "Tipo:N",
            scale=alt.Scale(domain=["Calzadas", "Descalzadas"], range=["#2a78d6", "#eb6834"]),
            legend=alt.Legend(orient="top", title=None),
        ),
        tooltip=[
            alt.Tooltip("Contraparte:N"),
            alt.Tooltip("Tipo:N"),
            alt.Tooltip("sum(P&L):Q", title="P&L (CLP)", format=",.0f"),
        ],
    )
    .properties(height=max(26 * len(tabla), 200))
)
regla = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="#8a8984").encode(x="x:Q")
st.altair_chart(en_espanol(grafico + regla), width="stretch")

# ------------------------------------------------------------------- detalle
st.subheader("Detalle por operación")
contraparte = st.selectbox("Contraparte", ["Todas", *tabla["Contraparte"]])
filas = detalle if contraparte == "Todas" else detalle[detalle["Contraparte"] == contraparte]
st.dataframe(
    filas.sort_values(["Contraparte", "Estado calce", "Folio"]).round({"P&L no realizado": 0}),
    hide_index=True,
    width="stretch",
    column_config={"Vencimiento": st.column_config.DateColumn(format="DD-MM-YYYY"), "P&L no realizado": montos},
)
