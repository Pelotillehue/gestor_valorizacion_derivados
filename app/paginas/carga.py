"""!
@package carga
@brief Página Carga de operaciones: sube un Excel o CSV con una fila por pata y crea o actualiza las operaciones vía la API.

Ofrece la plantilla descargable con la hoja de instrucciones. Cada operación se envía con
`POST /operaciones`; si ya existe y se marca la opción, se actualiza con `PATCH`.
"""

import pandas as pd
import streamlit as st

from comun import api, plantilla
from comun.formato import numero

st.title("Carga de operaciones")
st.caption(
    "Suba un Excel o CSV con **una fila por pata**: cada operación ocupa dos filas con el mismo "
    "folio (columna deal_number). Las columnas son las de la plantilla; las celdas vacías toman el valor por defecto de la API."
)

st.download_button(
    "Descargar plantilla",
    plantilla.plantilla_excel(),
    file_name="plantilla_carga_operaciones.xlsx",
    icon=":material/description:",
    help="Trae un forward y un cross currency swap de ejemplo, y una hoja con la descripción de cada columna.",
)

archivo = st.file_uploader("Archivo de operaciones", type=["xlsx", "xls", "csv"])
if archivo is None:
    st.stop()

try:
    filas = plantilla.leer_archivo(archivo.name, archivo.getvalue())
    operaciones, errores_lectura = plantilla.a_operaciones(filas)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Filas", numero(len(filas)))
c2.metric("Operaciones leídas", numero(len(operaciones)))
c3.metric("Con error de lectura", numero(len(errores_lectura)))

if errores_lectura:
    st.error("Estas operaciones no se cargarán:")
    st.dataframe(
        pd.DataFrame(errores_lectura.items(), columns=["Folio", "Error"]), hide_index=True, width="stretch"
    )

with st.expander("Vista previa del archivo"):
    st.dataframe(filas, hide_index=True, width="stretch")

if not operaciones:
    st.stop()

actualizar = st.checkbox(
    "Actualizar las operaciones que ya existen",
    help="Si no se marca, una operación cuyo folio ya existe se informa y no se toca. "
    "Si se marca, se reemplazan sus datos y sus patas, y la versión anterior queda en el historial. "
    "El producto no se puede cambiar.",
)

if not st.button(f"Cargar {numero(len(operaciones))} operaciones", type="primary", icon=":material/upload:"):
    st.stop()

resultados = []
avance = st.progress(0.0, text="Cargando…")
for i, operacion in enumerate(operaciones, start=1):
    deal = operacion.get("deal_number")
    try:
        api.crear(operacion)
        resultados.append((deal, "Creada", ""))
    except api.ErrorAPI as e:
        if e.codigo == 409 and actualizar:
            cambios = {k: v for k, v in operacion.items() if k not in ("deal_number", "producto")}
            try:
                actual = api.operacion(deal)
                if operacion.get("producto") and operacion["producto"] != actual["producto"]:
                    raise ValueError(f"el producto existente es {actual['producto']} y no se puede cambiar")
                api.modificar(deal, cambios)
                resultados.append((deal, "Actualizada", ""))
            except Exception as e2:
                resultados.append((deal, "Error", api.texto_error(e2)))
        elif e.codigo == 409:
            resultados.append((deal, "Ya existe", "No se modificó"))
        else:
            resultados.append((deal, "Error", api.texto_error(e)))
    except Exception as e:
        resultados.append((deal, "Error", api.texto_error(e)))
    avance.progress(i / len(operaciones), text=f"Cargando… {i} de {len(operaciones)}")
avance.empty()
api.limpiar_cache()

resumen = pd.DataFrame(resultados, columns=["Folio", "Resultado", "Detalle"])
conteo = resumen["Resultado"].value_counts()
r1, r2, r3, r4 = st.columns(4)
r1.metric("Creadas", numero(conteo.get("Creada", 0)))
r2.metric("Actualizadas", numero(conteo.get("Actualizada", 0)))
r3.metric("Ya existían", numero(conteo.get("Ya existe", 0)))
r4.metric("Con error", numero(conteo.get("Error", 0)))
if conteo.get("Error", 0):
    st.error("Algunas operaciones no se cargaron; el detalle está en la tabla.")
else:
    st.success("Carga terminada.")
st.dataframe(resumen, hide_index=True, width="stretch")
