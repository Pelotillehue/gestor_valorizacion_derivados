"""!
@package contrapartes
@brief Página Contrapartes: maestro de contrapartes con RUT, nombre, monto de línea y MTA.

La tabla es editable; los cambios se guardan con `PATCH /contrapartes/{rut}`. Un formulario
permite dar de alta contrapartes nuevas con `POST /contrapartes`.
"""

import pandas as pd
import streamlit as st

from comun import api
from comun.formato import numero, rut

st.title("Contrapartes")
st.caption(
    #"Una operación se asocia a su contraparte por el RUT. El **monto de línea** es la exposición a favor "
    #"de la institución que se acepta sin garantías, y el **MTA** el monto mínimo de transferencia: "
    #"si la exposición supera la línea, se llama por el exceso o por el MTA, el mayor de los dos. Ambos en CLP."
)

try:
    contrapartes = api.contrapartes(api.url_base())
    operaciones = api.operaciones(api.url_base())
except Exception as e:
    st.error(api.texto_error(e))
    st.stop()

vigentes = pd.Series([o.get("rut_contraparte") for o in operaciones]).value_counts()
tabla = pd.DataFrame(
    [
        {
            "rut": c["rut"],
            "Rut Contraparte": rut(c["rut"]),
            "Nombre": c["nombre"],
            "Operaciones vigentes": int(vigentes.get(c["rut"], 0)),
            "Monto Línea (CLP)": c["monto_linea"],
            "MTA (CLP)": c["mta"],
        }
        for c in contrapartes
    ],
    columns=["rut", "Rut Contraparte", "Nombre", "Operaciones vigentes", "Monto Línea (CLP)", "MTA (CLP)"],
)

m1, m2, m3 = st.columns(3)
m1.metric("Contrapartes", numero(len(tabla)))
m2.metric("Con operaciones vigentes", numero(int((tabla["Operaciones vigentes"] > 0).sum())))
m3.metric("Líneas otorgadas (CLP)", numero(tabla["Monto Línea (CLP)"].sum(), 0))

st.caption("Edite el nombre, la línea o el MTA en la tabla y guarde los cambios.")
editada = st.data_editor(
    tabla,
    hide_index=True,
    width="stretch",
    height=min(38 * (len(tabla) + 1), 640),
    disabled=["Rut Contraparte", "Operaciones vigentes"],
    column_order=["Rut Contraparte", "Nombre", "Operaciones vigentes", "Monto Línea (CLP)", "MTA (CLP)"],
    column_config={
        "Monto Línea (CLP)": st.column_config.NumberColumn(format="localized", min_value=0, step=1_000_000),
        "MTA (CLP)": st.column_config.NumberColumn(format="localized", min_value=0, step=1_000_000),
    },
    key="editor_contrapartes",
)

## Columna de la tabla editable → campo de la API.
CAMPOS = {"Nombre": "nombre", "Monto Línea (CLP)": "monto_linea", "MTA (CLP)": "mta"}
cambios = {}
for (_, original), (_, nueva) in zip(tabla.iterrows(), editada.iterrows()):
    diferencias = {}
    for columna, campo in CAMPOS.items():
        if nueva[columna] != original[columna] and not pd.isna(nueva[columna]):
            valor = nueva[columna]
            diferencias[campo] = valor.strip() if isinstance(valor, str) else float(valor)
    if diferencias:
        cambios[original["rut"]] = diferencias

if st.button(f"Guardar cambios ({len(cambios)})", icon=":material/save:", disabled=not cambios, type="primary"):
    errores = []
    for rut_contraparte, diferencias in cambios.items():
        try:
            api.modificar_contraparte(rut_contraparte, diferencias)
        except Exception as e:
            errores.append(f"{rut(rut_contraparte)}: {api.texto_error(e)}")
    api.limpiar_cache()
    if errores:
        st.error("No se guardaron:\n\n" + "\n\n".join(errores))
    else:
        st.success(f"Se guardaron {len(cambios)} contrapartes.")
        st.rerun()

with st.expander("Nueva contraparte", icon=":material/person_add:"):
    with st.form("nueva_contraparte", clear_on_submit=True):
        f1, f2 = st.columns([1, 2])
        nuevo_rut = f1.text_input("RUT", placeholder="76.123.456-0")
        nombre = f2.text_input("Nombre")
        f3, f4 = st.columns(2)
        linea = f3.number_input("Monto Línea (CLP)", min_value=0.0, step=1_000_000.0, format="%.0f")
        mta = f4.number_input("MTA (CLP)", min_value=0.0, step=1_000_000.0, format="%.0f")
        if st.form_submit_button("Crear", icon=":material/add:"):
            try:
                creada = api.crear_contraparte({"rut": nuevo_rut, "nombre": nombre, "monto_linea": linea, "mta": mta})
                api.limpiar_cache()
                st.success(f"Contraparte {creada['nombre']} creada con RUT {rut(creada['rut'])}.")
            except Exception as e:
                st.error(api.texto_error(e))
