"""!
@package reporte_basilea
@brief Página Reportes FX Fwd Basilea: resumen, detalle Basilea y líneas de los FX Forward vigentes.

Usa `GET /cartera/forwards-basilea`, `GET /cartera/garantias` y `GET /contrapartes`. Sigue la
planilla "Operaciones Forward Basilea" con la información de cartera y contrapartes disponible.
"""

from functools import partial

import pandas as pd
import streamlit as st

from comun import api, reporte_basilea
from comun.formato import FECHA_INICIAL, columna_numero, numero
from comun.reporte_pnl import LLAMADO

st.title("Reportes FX Forward")
st.caption(
    "FX Forward vigentes a la fecha de proceso. La moneda principal es la extranjera (USD o EUR) o la UF: "
    "**Compra** si la institución la recibe y **Venta** si la entrega."
)

c1, _ = st.columns([1, 3])
fecha = c1.date_input("Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
st.session_state["fecha_proceso"] = fecha

try:
    resultado = api.cartera_forwards_basilea(api.url_base(), fecha)
    garantias = api.cartera_garantias(api.url_base(), fecha)["contrapartes"]
    contrapartes = api.contrapartes(api.url_base())
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

datos = reporte_basilea.detalle(resultado["operaciones"])
if datos.empty:
    st.info(f"No hay FX Forward vigentes al {fecha:%d-%m-%Y}.")
    st.stop()
con_error = datos[datos["Error"] != ""]
if len(con_error):
    st.warning(
        f"{len(con_error)} forwards no se pudieron valorizar y no suman valor razonable: "
        + "; ".join(f"{f}: {e}" for f, e in zip(con_error["Folio"].head(5), con_error["Error"].head(5)))
    )
cuadros = reporte_basilea.resumen(datos)
tabla_lineas = reporte_basilea.lineas(contrapartes, garantias, datos)

vr = datos["Valor Razonable"]
m1, m2, m3, m4 = st.columns(4)
m1.metric("Forwards vigentes", numero(len(datos)))
m2.metric("Valor razonable (CLP)", numero(vr.sum(), 0))
m3.metric("Utilidad (CLP)", numero(vr[vr > 0].sum(), 0), delta=f"{int((vr > 0).sum())} operaciones", delta_color="off", delta_arrow="off")
m4.metric("Pérdida (CLP)", numero(vr[vr <= 0].sum(), 0), delta=f"{int((vr <= 0).sum())} operaciones", delta_color="off", delta_arrow="off")

d1, d2, _ = st.columns([1, 1, 3])
d1.download_button(
    "Excel",
    partial(reporte_basilea.excel, datos, cuadros, tabla_lineas, fecha),
    file_name=f"forwards_basilea_{fecha:%Y%m%d}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    icon=":material/table:",
    width="stretch",
)
d2.download_button(
    "PDF",
    partial(reporte_basilea.pdf, datos, cuadros, tabla_lineas, fecha),
    file_name=f"forwards_basilea_{fecha:%Y%m%d}.pdf",
    mime="application/pdf",
    icon=":material/picture_as_pdf:",
    width="stretch",
)

fechas = st.column_config.DateColumn(format="DD-MM-YYYY")


def _config(tabla: pd.DataFrame) -> dict:
    """!
    @brief Formato de columnas: montos sin decimales, tasas y tipo de cambio con cuatro, fechas DD-MM-AAAA.
    @param tabla Tabla a mostrar.
    @return `column_config` para `st.dataframe`.
    """
    config = {}
    for columna in tabla.columns:
        if pd.api.types.is_datetime64_any_dtype(tabla[columna]):
            config[columna] = fechas
        elif columna == "Tipo de Cambio" or "(%)" in columna:
            config[columna] = columna_numero(4)
        elif pd.api.types.is_numeric_dtype(tabla[columna]):
            config[columna] = columna_numero(0)
    return config


resumen, basilea, lineas = st.tabs(["Resumen", "Detalle", "Líneas"])

with resumen:
    for titulo, tabla in cuadros:
        st.markdown(f"**{titulo}**")
        # Fechas como texto para que la fila de subtotal de cada tipo de forward quede en blanco.
        vista = tabla.assign(
            **{c: tabla[c].dt.strftime("%d-%m-%Y").fillna("") for c in tabla.columns if pd.api.types.is_datetime64_any_dtype(tabla[c])}
        )
        st.dataframe(
            vista, hide_index=True, width="content", height=36 * (len(vista) + 1) + 3, column_config=_config(vista)
        )

with basilea:
    vista = datos.drop(columns=["Error"]) if con_error.empty else datos
    st.dataframe(
        vista, hide_index=True, width="stretch", height=min(36 * (len(vista) + 1) + 3, 640), column_config=_config(vista)
    )

with lineas:
    st.caption(
        "Exposición total y situación consideran todas las operaciones vigentes de la contraparte, como el control "
        "de garantías; el valor razonable y las posiciones netas (compras menos ventas en moneda principal), sólo "
        "sus FX Forward. Uso de línea: exposición positiva sobre el monto de línea."
    )
    solo_con_fwd = st.toggle("Sólo contrapartes con forwards vigentes", value=True)
    vista = tabla_lineas[tabla_lineas["Forwards Vigentes"] > 0] if solo_con_fwd else tabla_lineas

    def _resaltar(fila: pd.Series) -> list[str]:
        """!
        @brief Estilo de fila: la situación en rojo cuando hay llamado a garantía.
        @param fila Fila de la tabla.
        @return Un estilo CSS por columna.
        """
        estilo = "color: #d03b3b; font-weight: 600" if fila["Situación"] == LLAMADO else ""
        return [estilo if c == "Situación" else "" for c in fila.index]

    config = _config(vista) | {"Uso de Línea (%)": columna_numero(1)}
    st.dataframe(
        vista.style.apply(_resaltar, axis=1),
        hide_index=True,
        width="stretch",
        height=min(36 * (len(vista) + 1) + 3, 640),
        column_config=config,
    )
