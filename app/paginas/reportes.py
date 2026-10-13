"""!
@package reportes
@brief Página Listado de Operaciones Vigentes: operaciones vigentes a la fecha de proceso, en Excel y PDF por producto, con su MtM si se pide.
"""

from functools import partial

import streamlit as st

from comun import api, reportes
from comun.formato import FECHA_INICIAL, MONEDAS, PRODUCTOS, columna_numero, numero

st.title("Listado de Operaciones Vigentes")
st.caption(
    "Operaciones vigentes a la fecha de proceso (ya negociadas y aún no vencidas), con sus datos, un reporte "
    "por familia de producto."
)

try:
    operaciones = api.operaciones(api.url_base())
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

c1, c2, c3 = st.columns([1.2, 1.6, 1], vertical_alignment="bottom")
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
st.session_state["fecha_proceso"] = fecha
incluir_mtm = c2.toggle("Incluir el MtM de cada operación", value=True)
# Vigentes a la fecha de proceso: ya negociadas y con vencimiento posterior.
fecha_txt = fecha.isoformat()
operaciones = [o for o in operaciones if o["fecha_negociacion"] <= fecha_txt < o["fecha_vencimiento"]]
moneda = None
mtm = {}
if incluir_mtm:
    moneda = c3.selectbox("Moneda", MONEDAS)
    try:
        cartera = api.cartera_mtm(api.url_base(), fecha, moneda)
    except Exception as e:
        st.error(api.texto_error(e))
        st.stop()
    mtm = {o["deal_number"]: o["mtm"] for o in cartera["operaciones"]}
    sin_valor = sum(1 for v in mtm.values() if v is None)
    if sin_valor:
        st.caption(
            f"{numero(sin_valor)} operaciones no se pudieron valorizar en esa fecha y quedan con el MtM vacío. "
            "El motivo está en la página MtM de cartera."
        )

for producto, nombre in PRODUCTOS.items():
    tabla = reportes.tabla_familia(producto, operaciones, mtm, moneda)
    cantidad = sum(1 for o in operaciones if o["producto"] == producto)
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="center")
        c1.markdown(f"**{nombre}**  \n{numero(cantidad)} operaciones vigentes")
        if not cantidad:
            continue
        sufijo = f"_{fecha:%Y%m%d}"
        c2.download_button(
            "Excel",
            partial(reportes.excel, producto, tabla, fecha if incluir_mtm else None, moneda),
            file_name=f"operaciones_{producto.lower()}{sufijo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            icon=":material/table:",
            width="stretch",
            key=f"xlsx_{producto}",
        )
        c3.download_button(
            "PDF",
            partial(reportes.pdf, producto, tabla, fecha if incluir_mtm else None, moneda),
            file_name=f"operaciones_{producto.lower()}{sufijo}.pdf",
            mime="application/pdf",
            icon=":material/picture_as_pdf:",
            width="stretch",
            key=f"pdf_{producto}",
        )
        with st.expander("Vista previa"):
            config = {c: st.column_config.DateColumn(format="DD-MM-YYYY") for c in reportes.COLUMNAS_FECHA}
            config |= {c: columna_numero(0) for c in tabla.columns if c in reportes.COLUMNAS_MONTO or c.startswith("MtM")}
            config["Precio pactado"] = columna_numero(4)
            st.dataframe(tabla.head(200), hide_index=True, width="stretch", column_config=config)
