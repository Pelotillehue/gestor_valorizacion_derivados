"""!
@package reporte_pnl_realizado
@brief Página P&L Realizado: P&L de los FX Forward que vencieron en un período, por contraparte, calzados y descalzados.

Usa `GET /cartera/pnl-realizado`. Cada forward se liquida con el spot de su fecha de pago.
"""

from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from comun import api, reporte_pnl
from comun.formato import FECHA_INICIAL, columna_numero, numero

st.title("P&L Realizado")
st.caption(
    "P&L de los FX Forward que vencieron en el período: lo recibido menos lo pagado, en CLP al tipo de "
    "cambio de la fecha de pago (si ese día no tiene publicación, el del día hábil anterior). Es el "
    "mismo resultado en compensación y en entrega física. Por ahora no incluye swaps vencidos."
)

c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
st.session_state["fecha_proceso"] = fecha
desde = c2.date_input("Vencimientos desde", value=date(fecha.year, 1, 1), max_value=fecha, format="DD-MM-YYYY")
perspectiva = c3.segmented_control(
    "Perspectiva",
    ["Institución", "Cliente"],
    default="Institución",
    help="Institución: el P&L de la cartera propia. Cliente: el mismo P&L con el signo invertido.",
) or "Institución"

try:
    resultado = api.cartera_pnl_realizado(api.url_base(), fecha, desde)
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

con_error = [o for o in resultado["operaciones"] if o["pnl"] is None]
if con_error:
    st.warning(
        f"{len(con_error)} operaciones no se pudieron liquidar: "
        + "; ".join(f"{o['deal_number']}: {o['error']}" for o in con_error[:5])
    )
detalle = reporte_pnl.detalle_realizado(resultado["operaciones"], perspectiva == "Cliente")
if detalle.empty:
    st.info(f"No hay FX Forward vencidos entre el {desde:%d-%m-%Y} y el {fecha:%d-%m-%Y}.")
    st.stop()
tabla = reporte_pnl.resumen_realizado(detalle)

calzadas, descalzadas = tabla["Calzadas"].sum(), tabla["Descalzadas"].sum()
n_calzadas = int((detalle["Estado calce"] == "Calzada").sum())
m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "P&L realizado (CLP)", numero(calzadas + descalzadas, 0), delta=f"{len(detalle)} operaciones", delta_color="off", delta_arrow="off"
)
m2.metric("Calzadas", numero(calzadas, 0), delta=f"{n_calzadas} operaciones", delta_color="off", delta_arrow="off")
m3.metric(
    "Descalzadas", numero(descalzadas, 0), delta=f"{len(detalle) - n_calzadas} operaciones", delta_color="off", delta_arrow="off"
)
m4.metric("Contrapartes", numero(len(tabla)))

d1, _ = st.columns([1, 4])
d1.download_button(
    "Excel",
    partial(reporte_pnl.excel_realizado, tabla, detalle, desde, fecha, perspectiva),
    file_name=f"pnl_realizado_{desde:%Y%m%d}_{fecha:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table:",
    width="stretch",
)

st.subheader("Por contraparte")
total = pd.DataFrame(
    [{"Rut Contraparte": "", "Contraparte": "Total", "Operaciones": tabla["Operaciones"].sum(),
      "Calzadas": calzadas, "Descalzadas": descalzadas, "Total": calzadas + descalzadas}]
)  # fmt: skip
st.dataframe(
    pd.concat([tabla, total], ignore_index=True).round(0),
    hide_index=True,
    width="stretch",
    height=min(36 * (len(tabla) + 2) + 3, 640),
    column_config={
        "Calzadas": columna_numero(0, "P&L calzadas"),
        "Descalzadas": columna_numero(0, "P&L descalzadas"),
        "Total": columna_numero(0, "P&L realizado total"),
    },
)

st.subheader("Detalle por operación")
contraparte = st.selectbox("Contraparte", ["Todas", *tabla["Contraparte"]])
filas = detalle if contraparte == "Todas" else detalle[detalle["Contraparte"] == contraparte]
fechas = st.column_config.DateColumn(format="DD-MM-YYYY")
st.dataframe(
    filas.sort_values(["Vencimiento", "Folio"]).round({"Monto recibe": 0, "Monto paga": 0, "P&L realizado": 0}),
    hide_index=True,
    width="stretch",
    column_config={
        "Negociación": fechas,
        "Vencimiento": fechas,
        "Fecha tipo de cambio": fechas,
        "Monto recibe": columna_numero(0),
        "Monto paga": columna_numero(0),
        "P&L realizado": columna_numero(0),
    },
)
