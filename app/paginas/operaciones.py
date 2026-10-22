"""Listado de operaciones vigentes con filtros, y detalle y MtM de una operación."""

from functools import partial

import pandas as pd
import streamlit as st

from comun import api
from comun.formato import FECHA_INICIAL, MODALIDADES, MONEDAS, PRODUCTOS, numero, patas_planas, resumen_operaciones, rut
from comun.plantilla import a_excel

st.title("Operaciones")

try:
    operaciones = api.operaciones(api.url_base())
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

if not operaciones:
    st.info("No hay operaciones vigentes. Cárguelas en **Carga de operaciones**.")
    st.stop()

resumen = resumen_operaciones(operaciones)
resumen[["Nocional recibe", "Nocional paga"]] = resumen[["Nocional recibe", "Nocional paga"]].round(2)

# --------------------------------------------------------------------------- filtros
c1, c2, c3, c4 = st.columns([2, 2, 2, 1.4])
productos = c1.multiselect("Producto", list(PRODUCTOS.values()), placeholder="Todos")
contrapartes = c2.multiselect("Contraparte", sorted(resumen["Contraparte"].unique()), placeholder="Todas")
modalidades = c3.multiselect("Modalidad", list(MODALIDADES.values()), placeholder="Todas")
buscar = c4.text_input("Deal", placeholder="Buscar…")

filtrado = resumen
if productos:
    filtrado = filtrado[filtrado["Producto"].isin(productos)]
if contrapartes:
    filtrado = filtrado[filtrado["Contraparte"].isin(contrapartes)]
if modalidades:
    filtrado = filtrado[filtrado["Modalidad"].isin(modalidades)]
if buscar:
    filtrado = filtrado[filtrado["Deal"].str.contains(buscar.strip(), case=False, regex=False)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Operaciones", numero(len(filtrado)))
for columna, nombre in zip((m2, m3, m4), PRODUCTOS.values()):
    columna.metric(nombre, numero(int((filtrado["Producto"] == nombre).sum())))

montos = st.column_config.NumberColumn(format="localized")
seleccion = st.dataframe(
    filtrado.drop(columns=["Estado"]),
    hide_index=True,
    width="stretch",
    height=380,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Negociación": st.column_config.DateColumn(format="DD-MM-YYYY"),
        "Vencimiento": st.column_config.DateColumn(format="DD-MM-YYYY"),
        "Nocional recibe": montos,
        "Nocional paga": montos,
    },
    key="tabla_operaciones",
)

elegidas = {o["deal_number"]: o for o in operaciones if o["deal_number"] in set(filtrado["Deal"])}


def _formato_carga(deals: tuple[str, ...]) -> bytes:
    return a_excel(patas_planas([elegidas[d] for d in deals]))


st.download_button(
    "Descargar lo filtrado en formato de carga",
    partial(_formato_carga, tuple(elegidas)),
    file_name="operaciones.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/download:",
    help="Una fila por pata, con las mismas columnas que la plantilla de carga.",
)

# --------------------------------------------------------------------------- detalle
st.divider()
filas = seleccion.selection.rows
if not filas:
    st.caption("Seleccione una fila de la tabla para ver el detalle de la operación y su MtM.")
    st.stop()

deal = filtrado.iloc[filas[0]]["Deal"]
op = elegidas[deal]
st.subheader(f"Operación {deal}")

d1, d2, d3, d4, d5 = st.columns(5)
d1.markdown(f"**Producto**  \n{PRODUCTOS[op['producto']]}")
d2.markdown(f"**Contraparte**  \n{op.get('contraparte') or '—'}  \n{rut(op.get('rut_contraparte'))}")
d3.markdown(f"**Modalidad**  \n{MODALIDADES[op['modalidad_liquidacion']]}")
d4.markdown(f"**Negociación**  \n{pd.Timestamp(op['fecha_negociacion']):%d-%m-%Y}")
d5.markdown(f"**Vencimiento**  \n{pd.Timestamp(op['fecha_vencimiento']):%d-%m-%Y}")

ETIQUETAS = {
    "rec_pay": "Recibe / paga", "tipo": "Tipo", "moneda": "Moneda", "nocional": "Nocional",
    "curva_descuento": "Curva de descuento", "fecha_pago": "Fecha de pago", "fecha_inicio": "Inicio",
    "fecha_fin": "Fin", "periodicidad": "Periodicidad", "stub": "Stub", "ajuste_fecha": "Ajuste de fecha",
    "calendario": "Calendario", "lag_pago": "Lag de pago", "intercambia_nocional": "Intercambia nocional",
    "fraccion_anio": "Fracción de año", "factor_capitalizacion": "Capitalización", "tasa": "Tasa",
    "indice": "Índice", "curva_proyeccion": "Curva de proyección", "spread": "Spread", "gearing": "Gearing",
    "decimales_tasa": "Decimales de la tasa",
}  # fmt: skip


def _mostrar(campo: str, valor) -> str:
    if valor is None:
        return ""
    if campo == "nocional":
        return numero(valor, 2)
    if campo in ("tasa", "spread"):
        return f"{numero(valor * 100, 4)}%"
    if campo.startswith("fecha"):
        return f"{pd.Timestamp(valor):%d-%m-%Y}"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


patas_op = sorted(op["patas"], key=lambda p: p["numero"])
campos = [c for c in ETIQUETAS if any(p.get(c) is not None for p in patas_op)]
st.dataframe(
    pd.DataFrame(
        {f"Pata {p['numero']}": [_mostrar(c, p.get(c)) for c in campos] for p in patas_op},
        index=[ETIQUETAS[c] for c in campos],
    ),
    width="stretch",
)

st.markdown("**MtM**")
v1, v2, v3 = st.columns([1.2, 1, 3])
fecha = v1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
moneda = v2.selectbox("Moneda", MONEDAS, index=0)
st.session_state["fecha_proceso"] = fecha

try:
    resultado = api.mtm(deal, fecha, moneda, detalle=True)
except Exception as e:
    st.warning(f"No se pudo valorizar: {api.texto_error(e)}")
    st.stop()

st.metric(f"MtM en {moneda}", numero(resultado["mtm"], 0))
for pata in resultado["patas"]:
    with st.expander(
        f"Pata {pata['numero']} · {pata['rec_pay'].capitalize()} {pata['moneda']} · "
        f"valor presente {numero(pata['valor_presente'], 2)} {pata['moneda']} = "
        f"{numero(pata['valor_presente_convertido'], 0)} {moneda}"
    ):
        # monto_descontado sigue en la respuesta de la API (lo usa el calendario de flujos), pero no se muestra.
        flujos = pd.DataFrame(pata["flujos"]).drop(columns="monto_descontado", errors="ignore")
        st.dataframe(flujos, hide_index=True, width="stretch")
