"""!
@package vencimientos
@brief Página Vencimientos: flujos futuros de la cartera en CLP, por período y producto.

Usa `GET /cartera/flujos`. Permite filtrar por modalidad, por componente (nocional o
intereses) y por horizonte, y agrupar por mes, trimestre o año.
"""


import altair as alt
import pandas as pd
import streamlit as st

from comun import api
from comun.formato import COLOR_PRODUCTO, FECHA_INICIAL, MODALIDADES, PRODUCTOS, columna_numero, en_espanol, escala, numero, rut
from comun.vista_operaciones import moneda as moneda_visible
from comun.plantilla import a_excel

st.title("Calendario de Flujos")
st.caption(
    "Todos los flujos futuros de las operaciones vigentes: el monto de cada forward y los cupones y "
    "nocionales de cada swap, en CLP al spot de la fecha de proceso. Los cupones flotantes se proyectan "
    "con la curva de cada pata. Positivo lo que se recibe y negativo lo que se paga."
)

## Horizonte de vencimientos que se muestra, desde la fecha de proceso.
HORIZONTES = {
    "1 mes": pd.DateOffset(months=1),
    "3 meses": pd.DateOffset(months=3),
    "6 meses": pd.DateOffset(months=6),
    "1 año": pd.DateOffset(years=1),
    "2 años": pd.DateOffset(years=2),
    "5 años": pd.DateOffset(years=5),
    "Todo": None,
}
## Horizontes cortos, en que el gráfico va día a día.
HORIZONTES_DIARIOS = {"1 mes", "3 meses", "6 meses"}

c1, c5, c2 = st.columns([1.2, 1.2, 2.6])
c3, c4, _ = st.columns([1.8, 1.8, 1.4])
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
st.session_state["fecha_proceso"] = fecha
horizonte = c5.selectbox("Horizonte", list(HORIZONTES), index=list(HORIZONTES).index("2 años"))
diario = horizonte in HORIZONTES_DIARIOS
agrupacion = c2.segmented_control(
    "Agrupar por",
    ["Mes", "Trimestre", "Año"],
    default="Mes",
    disabled=diario,
    help="Con horizonte de 6 meses o menos, los vencimientos se muestran por día." if diario else None,
)
modalidad = c3.segmented_control("Modalidad", ["Todas", *MODALIDADES.values()], default="Todas")
componente = c4.segmented_control(
    "Componente",
    ["Todo", "Nocional", "Intereses"],
    default="Todo",
    help="Nocional: montos de los forwards y amortizaciones de los swaps. Intereses: cupones de los swaps.",
)

try:
    resultado = api.cartera_flujos(api.url_base(), fecha)
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

if resultado["errores"]:
    st.warning(
        f"{len(resultado['errores'])} operaciones no se pudieron proyectar y se omitieron: "
        + "; ".join(f"{d}: {m}" for d, m in list(resultado["errores"].items())[:5])
    )

flujos = pd.DataFrame(resultado["flujos"])
if flujos.empty:
    st.info("No hay flujos posteriores a la fecha de proceso.")
    st.stop()

flujos["Producto"] = flujos["producto"].map(PRODUCTOS)
flujos["Modalidad"] = flujos["modalidad_liquidacion"].map(MODALIDADES)
flujos["Vencimiento"] = pd.to_datetime(flujos["fecha_pago"])
flujos["Rut Contraparte"] = flujos["rut_contraparte"].map(rut)
flujos["Moneda"] = flujos["moneda"].map(moneda_visible)
# Cada flujo se separa en nocional e intereses para poder filtrar por componente.
flujos["monto"] = flujos["flujo_clp"]
if componente == "Nocional":
    flujos["monto"] = flujos["amortizacion"] * flujos["tipo_cambio"]
elif componente == "Intereses":
    flujos["monto"] = flujos["interes"] * flujos["tipo_cambio"]
flujos = flujos[flujos["monto"].abs() > 1e-6]
flujos["sentido"] = flujos["monto"].map(lambda m: "RECIBE" if m > 0 else "PAGA")

if modalidad and modalidad != "Todas":
    flujos = flujos[flujos["Modalidad"] == modalidad]
if HORIZONTES[horizonte] is not None:
    flujos = flujos[flujos["Vencimiento"] <= pd.Timestamp(fecha) + HORIZONTES[horizonte]]

if flujos.empty:
    st.info("No hay flujos con esos filtros.")
    st.stop()

if diario:
    flujos["Período"] = flujos["Vencimiento"].dt.strftime("%Y-%m-%d")
elif agrupacion == "Año":
    flujos["Período"] = flujos["Vencimiento"].dt.year.astype(str)
elif agrupacion == "Trimestre":
    flujos["Período"] = flujos["Vencimiento"].dt.year.astype(str) + "-T" + flujos["Vencimiento"].dt.quarter.astype(str)
else:
    flujos["Período"] = flujos["Vencimiento"].dt.strftime("%Y-%m")

productos_presentes = [p for p in PRODUCTOS.values() if p in set(flujos["Producto"])]
escala_color = alt.Scale(domain=productos_presentes, range=[COLOR_PRODUCTO[p] for p in productos_presentes])


def grafico(datos: pd.DataFrame, moneda: str, divisor: float, unidad: str) -> alt.LayerChart:
    """!
    @brief Barras apiladas por producto y línea del neto de cada período.
    @param datos Flujos filtrados, con la columna Período.
    @param moneda Moneda de los montos.
    @param divisor Divisor de los montos (miles o millones).
    @param unidad Nombre de la unidad.
    @return Gráfico Altair.
    """
    titulo = f"{unidad} de {moneda}"

    por_producto = datos.groupby(["Período", "Producto", "sentido"], as_index=False)["monto"].sum()
    por_producto["valor"] = por_producto["monto"] / divisor
    por_producto["Sentido"] = por_producto["sentido"].map({"RECIBE": "Recibe", "PAGA": "Paga"})
    neto = datos.groupby("Período", as_index=False)["monto"].sum()
    neto["valor"] = neto["monto"] / divisor
    neto["serie"] = "Neto del día" if diario else "Neto del período"
    periodos = sorted(datos["Período"].unique())

    if diario:
        # Período viene como AAAA-MM-DD para ordenar; en el eje y el tooltip se muestra DD-MM.
        for tabla in (por_producto, neto):
            tabla["Fecha"] = pd.to_datetime(tabla["Período"]).dt.strftime("%d-%m-%Y")
        eje_x = alt.X(
            "Período:O",
            sort=periodos,
            title=None,
            axis=alt.Axis(
                labelAngle=-45 if len(periodos) > 12 else 0,
                labelOverlap=True,
                labelExpr="slice(datum.value, 8, 10) + '-' + slice(datum.value, 5, 7)",
            ),
        )
        campo_tooltip = alt.Tooltip("Fecha:N", title="Fecha de pago")
    else:
        eje_x = alt.X("Período:O", sort=periodos, title=None, axis=alt.Axis(labelAngle=-45 if len(periodos) > 12 else 0))
        campo_tooltip = alt.Tooltip("Período:O")
    barras = (
        alt.Chart(por_producto)
        .mark_bar(cornerRadius=2, stroke="white", strokeWidth=1)
        .encode(
            x=eje_x,
            y=alt.Y("sum(valor):Q", title=titulo, axis=alt.Axis(format=",.0f")),
            color=alt.Color("Producto:N", scale=escala_color, legend=alt.Legend(orient="top", title=None)),
            order=alt.Order("Producto:N"),
            tooltip=[
                campo_tooltip,
                alt.Tooltip("Producto:N"),
                alt.Tooltip("Sentido:N"),
                alt.Tooltip("sum(valor):Q", title=titulo, format=",.1f"),
            ],
        )
    )
    linea_neta = (
        alt.Chart(neto)
        .mark_line(color="#8a8984", strokeWidth=2, point=alt.OverlayMarkDef(size=60, filled=True, color="#8a8984"))
        .encode(
            x=eje_x,
            y=alt.Y("valor:Q"),
            opacity=alt.Opacity("serie:N", legend=alt.Legend(orient="top", title=None, symbolType="stroke")),
            tooltip=[campo_tooltip, alt.Tooltip("valor:Q", title=f"Neto ({titulo})", format=",.1f")],
        )
    )
    cero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8a8984", strokeWidth=1).encode(y="y:Q")
    return en_espanol((barras + cero + linea_neta).properties(height=420))


recibe, paga = flujos.loc[flujos["monto"] > 0, "monto"].sum(), flujos.loc[flujos["monto"] < 0, "monto"].sum()
divisor, unidad = escala(max(recibe, -paga))
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Recibe ({unidad} de CLP)", numero(recibe / divisor, 0), help=f"{numero(recibe, 0)} CLP")
k2.metric(f"Paga ({unidad} de CLP)", numero(paga / divisor, 0), help=f"{numero(paga, 0)} CLP")
k3.metric(f"Neto ({unidad} de CLP)", numero((recibe + paga) / divisor, 0), help=f"{numero(recibe + paga, 0)} CLP")
k4.metric("Operaciones", numero(flujos["deal_number"].nunique()))
st.altair_chart(grafico(flujos, "CLP", divisor, unidad), width="stretch")

tabla = flujos.pivot_table(index="Período", columns="Producto", values="monto", aggfunc="sum", fill_value=0)
tabla = tabla.reindex(columns=[p for p in productos_presentes if p in tabla.columns])
tabla["Neto"] = tabla.sum(axis=1)
tabla["Acumulado"] = tabla["Neto"].cumsum()
tabla = tabla.round(0)
with st.expander("Tabla por período (CLP)"):
    st.dataframe(
        tabla,
        width="stretch",
        column_config={c: columna_numero(0) for c in tabla.columns},
    )

with st.expander("Detalle por operación"):
    detalle = flujos.assign(Sentido=flujos["rec_pay"].map({"RECIBE": "Recibe", "PAGA": "Paga"}))[
        ["deal_number", "Producto", "Rut Contraparte", "contraparte", "Modalidad", "numero_pata", "Sentido",
         "Vencimiento", "Período", "Moneda", "amortizacion", "interes", "flujo", "tipo_cambio", "monto"]
    ].rename(columns={
        "deal_number": "Folio", "contraparte": "Contraparte", "numero_pata": "Pata", "Vencimiento": "Fecha pago",
        "amortizacion": "Nocional", "interes": "Interés", "flujo": "Flujo", "tipo_cambio": "Tipo de cambio",
        "monto": "Monto (CLP)",
    })  # fmt: skip
    detalle = detalle.sort_values(["Fecha pago", "Folio", "Pata"]).round(
        {"Nocional": 0, "Interés": 2, "Flujo": 2, "Tipo de cambio": 2, "Monto (CLP)": 0}
    )
    st.dataframe(
        detalle,
        hide_index=True,
        width="stretch",
        column_config={
            "Fecha pago": st.column_config.DateColumn(format="DD-MM-YYYY"),
            "Nocional": columna_numero(0),
            **{c: columna_numero(2) for c in ("Interés", "Flujo")},
            "Tipo de cambio": columna_numero(2),
            "Monto (CLP)": columna_numero(0),
        },
    )
    st.download_button(
        "Descargar detalle en Excel",
        a_excel(detalle.assign(**{"Fecha pago": detalle["Fecha pago"].dt.date}), "Flujos"),
        file_name=f"flujos_{fecha:%Y%m%d}.xlsx",
        icon=":material/download:",
    )
