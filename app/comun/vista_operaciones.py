"""!
@package comun.vista_operaciones
@brief Vista de las operaciones vigentes de un producto: tabla con filtros, detalle de patas y MtM.

La usan las páginas Operaciones FX Forward, Interest Rate Swap y Cross Currency Swap.
"""

from functools import partial

import pandas as pd
import streamlit as st

from comun import api
from comun.formato import (
    FECHA_INICIAL,
    MODALIDADES,
    MONEDAS,
    columna_numero,
    PRODUCTOS,
    numero,
    par_forward,
    patas_planas,
    rut,
)
from comun.plantilla import a_excel

def moneda(codigo: str | None) -> str:
    """!
    @brief Nombre visible de una moneda: la CLF se muestra como UF.
    @param codigo Código ISO o nada.
    @return Nombre para mostrar.
    """
    return "UF" if codigo == "CLF" else (codigo or "")


## Tipo de tasa visible de cada tipo de pata con cupones.
TIPO_TASA = {"FIJA": "Fix", "INDICE_OVERNIGHT": "Float"}
## Título de la página de cada producto.
TITULOS = {"FX_FORWARD": "FX Forward", "IR_SWAP": "Interest Rate Swap", "CC_SWAP": "Cross Currency Swap"}


def _comunes(o: dict) -> dict:
    """!
    @brief Columnas comunes a todos los productos.
    @param o Operación de la API.
    @return Diccionario de columnas.
    """
    return {
        "Folio": o["deal_number"],
        "Rut Contraparte": rut(o.get("rut_contraparte")),
        "Contraparte": o.get("contraparte") or "",
        "Modalidad": MODALIDADES.get(o["modalidad_liquidacion"], o["modalidad_liquidacion"]),
        "Calce": "Calzada" if o.get("grupo_calce") else "Descalzada",
        "Negociación": pd.Timestamp(o["fecha_negociacion"]),
        "Vencimiento": pd.Timestamp(o["fecha_vencimiento"]),
    }


def _patas(o: dict) -> tuple[dict, dict]:
    """!
    @brief Separa las patas de una operación.
    @param o Operación de la API.
    @return Tupla (pata que recibe, pata que paga).
    """
    recibe = next(p for p in o["patas"] if p["rec_pay"] == "RECIBE")
    paga = next(p for p in o["patas"] if p["rec_pay"] == "PAGA")
    return recibe, paga


def tabla_forwards(operaciones: list[dict]) -> pd.DataFrame:
    """!
    @brief Tabla de forwards: montos, curvas de descuento, par y precio pactado.
    @param operaciones Forwards de la API.
    @return DataFrame.
    """
    filas = []
    for o in operaciones:
        recibe, paga = _patas(o)
        par, precio = par_forward(o["patas"])
        filas.append(
            _comunes(o)
            | {
                "Moneda Recibe": moneda(recibe["moneda"]),
                "Monto Recibe": round(recibe["nocional"]),
                "Curva Descuento Recibe": recibe["curva_descuento"],
                "Moneda Paga": moneda(paga["moneda"]),
                "Monto Paga": round(paga["nocional"]),
                "Curva Descuento Paga": paga["curva_descuento"],
                "Par": par.replace("CLF", "UF"),
                "Precio pactado": precio,
            }
        )
    return pd.DataFrame(filas)


def _tasa(pata: dict) -> str:
    """!
    @brief Tasa de una pata de swap.
    @param pata Pata de la API.
    @return Tasa fija en porcentaje, o el nombre del índice.
    """
    if pata["tipo"] == "FIJA":
        return f"{numero(pata['tasa'] * 100, 4)}%"
    return pata.get("indice") or ""


def _lado(pata: dict, lado: str) -> dict:
    """!
    @brief Columnas de un lado de un swap: moneda, nocional, tipo de tasa, tasa, spread y curvas.
    @param pata Pata de la API.
    @param lado `Recibe` o `Paga`, sufijo de las columnas.
    @return Diccionario de columnas.
    """
    return {
        f"Moneda {lado}": moneda(pata["moneda"]),
        f"Nocional {lado}": round(pata["nocional"]),
        f"Tipo Tasa {lado}": TIPO_TASA.get(pata["tipo"], pata["tipo"]),
        f"Tasa {lado}": _tasa(pata),
        f"Spread {lado} (%)": (pata.get("spread") or 0.0) * 100,
        # Sólo las patas flotantes proyectan; una pata fija no tiene curva de proyección.
        f"Curva Proyección {lado}": pata.get("curva_proyeccion") or "",
        f"Curva Descuento {lado}": pata["curva_descuento"],
    }


## Orden de las columnas de la tabla de swaps: cada nocional junto a su moneda, luego tasas y curvas.
ORDEN_SWAPS = [
    "Folio", "Rut Contraparte", "Contraparte",
    "Moneda Recibe", "Nocional Recibe", "Tipo Tasa Recibe", "Tasa Recibe", "Spread Recibe (%)",
    "Curva Proyección Recibe", "Curva Descuento Recibe",
    "Moneda Paga", "Nocional Paga", "Tipo Tasa Paga", "Tasa Paga", "Spread Paga (%)",
    "Curva Proyección Paga", "Curva Descuento Paga",
    "Calce", "Modalidad", "Inicio", "Vencimiento", "Periodicidad", "Negociación",
]  # fmt: skip


def tabla_swaps(operaciones: list[dict]) -> pd.DataFrame:
    """!
    @brief Tabla de swaps: una fila por operación con los datos de cada lado.
    @param operaciones Swaps de la API.
    @return DataFrame.
    """
    filas = []
    for o in operaciones:
        recibe, paga = _patas(o)
        filas.append(
            _comunes(o)
            | {"Inicio": pd.Timestamp(recibe["fecha_inicio"]), "Periodicidad": recibe.get("periodicidad") or ""}
            | _lado(recibe, "Recibe")
            | _lado(paga, "Paga")
        )
    return pd.DataFrame(filas)


## Nombre visible de cada campo en el detalle de patas.
ETIQUETAS = {
    "rec_pay": "Recibe / paga", "tipo": "Tipo", "moneda": "Moneda", "nocional": "Nocional",
    "curva_descuento": "Curva de descuento", "fecha_pago": "Fecha de pago", "fecha_inicio": "Inicio",
    "fecha_fin": "Fin", "periodicidad": "Periodicidad", "stub": "Stub", "ajuste_fecha": "Ajuste de fecha",
    "calendario": "Calendario", "lag_pago": "Lag de pago",
    "tipo_amortizacion": "Tipo de amortización", "intercambia_nocional": "Intercambia nocional",
    "fraccion_anio": "Fracción de año", "factor_capitalizacion": "Capitalización", "tasa": "Tasa",
    "indice": "Índice", "curva_proyeccion": "Curva de proyección", "spread": "Spread", "gearing": "Gearing",
    "decimales_tasa": "Decimales de la tasa",
}  # fmt: skip


def _mostrar(campo: str, valor) -> str:
    """!
    @brief Formatea un campo de una pata para el detalle.
    @param campo Nombre del campo.
    @param valor Valor.
    @return Texto.
    """
    if valor is None:
        return ""
    if campo == "moneda":
        return moneda(valor)
    if campo == "nocional":
        return numero(valor, 0)
    if campo in ("tasa", "spread"):
        return f"{numero(valor * 100, 4)}%"
    if campo.startswith("fecha"):
        return f"{pd.Timestamp(valor):%d-%m-%Y}"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


def _formato_carga(operaciones: list[dict]) -> bytes:
    """!
    @brief Excel de las operaciones en el formato de la plantilla de carga.
    @param operaciones Operaciones de la API.
    @return Contenido del archivo .xlsx.
    """
    return a_excel(patas_planas(operaciones))


def mostrar(producto: str) -> None:
    """!
    @brief Dibuja la página completa de las operaciones de un producto.

    Lee las operaciones con @ref comun.api.operaciones. Por defecto muestra sólo las vigentes a la
    fecha de proceso; además filtra por contraparte, modalidad, calce y folio, y muestra la tabla y, al seleccionar una fila, el detalle de las patas y su MtM con
    @ref comun.api.mtm.
    @param producto Código del producto.
    """
    st.title(f"Operaciones {TITULOS[producto]}")

    try:
        operaciones = api.operaciones(api.url_base())
    except Exception as e:
        st.error(api.texto_error(e))
        st.stop()

    if not operaciones:
        st.info("No hay operaciones vigentes. Cárguelas en **Carga de operaciones**.")
        st.stop()

    operaciones = [o for o in operaciones if o["producto"] == producto]
    if not operaciones:
        st.info(f"No hay operaciones vigentes de {PRODUCTOS[producto]}.")
        st.stop()

    # Vigencia a la fecha de proceso: ya negociada y aún no vencida, como en el MtM de cartera.
    v1, v2, _ = st.columns([1.2, 2, 2.8], vertical_alignment="bottom")
    fecha_proceso = v1.date_input(
        "Fecha de proceso", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY",
        key=f"fecha_vigencia_{producto}",
    )  # fmt: skip
    st.session_state["fecha_proceso"] = fecha_proceso
    solo_vigentes = v2.toggle(
        "Sólo vigentes a la fecha de proceso",
        value=True,
        key=f"solo_vigentes_{producto}",
        help="Negociadas hasta la fecha de proceso y con vencimiento posterior a ella. "
        "Desactívelo para ver también las vencidas y las que aún no comienzan.",
    )
    if solo_vigentes:
        operaciones = [
            o for o in operaciones
            if pd.Timestamp(o["fecha_negociacion"]).date() <= fecha_proceso < pd.Timestamp(o["fecha_vencimiento"]).date()
        ]  # fmt: skip
        if not operaciones:
            st.info(f"No hay operaciones de {PRODUCTOS[producto]} vigentes al {fecha_proceso:%d-%m-%Y}.")
            st.stop()

    resumen = tabla_forwards(operaciones) if producto == "FX_FORWARD" else tabla_swaps(operaciones)

    # --------------------------------------------------------------------------- filtros
    c1, c2, c3, c4 = st.columns([2, 2, 1.4, 1.4])
    contrapartes = c1.multiselect("Contraparte", sorted(resumen["Contraparte"].unique()), placeholder="Todas")
    modalidades = c2.multiselect("Modalidad", list(MODALIDADES.values()), placeholder="Todas")
    calce = c3.segmented_control("Calce", ["Calzada", "Descalzada"])
    buscar = c4.text_input("Folio", placeholder="Buscar…")

    filtrado = resumen
    if calce:
        filtrado = filtrado[filtrado["Calce"] == calce]
    if contrapartes:
        filtrado = filtrado[filtrado["Contraparte"].isin(contrapartes)]
    if modalidades:
        filtrado = filtrado[filtrado["Modalidad"].isin(modalidades)]
    if buscar:
        filtrado = filtrado[filtrado["Folio"].str.contains(buscar.strip(), case=False, regex=False)]

    m1, m2, m3 = st.columns(3)
    m1.metric("Operaciones", numero(len(filtrado)))
    m2.metric("Calzadas", numero(int((filtrado["Calce"] == "Calzada").sum())))
    m3.metric("Descalzadas", numero(int((filtrado["Calce"] == "Descalzada").sum())))

    montos = columna_numero(0)
    fechas = st.column_config.DateColumn(format="DD-MM-YYYY")
    porcentaje = columna_numero(4)
    config = {c: fechas for c in ("Negociación", "Vencimiento", "Fecha pago", "Inicio")}
    config |= {c: montos for c in ("Monto Recibe", "Monto Paga", "Nocional Recibe", "Nocional Paga")}
    config |= {c: porcentaje for c in ("Spread Recibe (%)", "Spread Paga (%)")}
    config["Precio pactado"] = columna_numero(4)
    seleccion = st.dataframe(
        filtrado,
        hide_index=True,
        width="stretch",
        height=min(36 * (len(filtrado) + 1) + 3, 460),
        column_order=ORDEN_SWAPS if producto != "FX_FORWARD" else None,
        on_select="rerun",
        selection_mode="single-row",
        column_config=config,
        key=f"tabla_{producto}",
    )

    elegidas = {o["deal_number"]: o for o in operaciones if o["deal_number"] in set(filtrado["Folio"])}



    st.download_button(
        "Descargar lo filtrado en formato de carga",
        partial(_formato_carga, list(elegidas.values())),
        file_name=f"operaciones_{producto.lower()}.xlsx",
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

    deal = filtrado.iloc[filas[0]]["Folio"]
    op = elegidas[deal]
    st.subheader(f"Operación {deal}")

    d1, d2, d3, d4, d5 = st.columns(5)
    d1.markdown(f"**Calce**  \n{op.get('grupo_calce') or 'Descalzada'}")
    d2.markdown(f"**Contraparte**  \n{op.get('contraparte') or '—'}  \n{rut(op.get('rut_contraparte'))}")
    d3.markdown(f"**Modalidad**  \n{MODALIDADES[op['modalidad_liquidacion']]}")
    d4.markdown(f"**Negociación**  \n{pd.Timestamp(op['fecha_negociacion']):%d-%m-%Y}")
    d5.markdown(f"**Vencimiento**  \n{pd.Timestamp(op['fecha_vencimiento']):%d-%m-%Y}")

    patas_op = sorted(op["patas"], key=lambda p: p["numero"])
    campos = [c for c in ETIQUETAS if any(p.get(c) is not None for p in patas_op)]
    st.dataframe(
        pd.DataFrame(
            {f"Pata {p['numero']}": [_mostrar(c, p.get(c)) for c in campos] for p in patas_op},
            index=[ETIQUETAS[c] for c in campos],
        ),
        width="stretch",
        height=35 * (len(campos) + 1) + 3,
    )

    st.markdown("**MtM**")
    v1, v2, v3 = st.columns([1.2, 1, 3])
    fecha = v1.date_input("Fecha de proceso", key=f"fecha_{producto}", value=st.session_state.get("fecha_proceso", FECHA_INICIAL), format="DD-MM-YYYY")
    moneda_mtm = v2.selectbox("Moneda", MONEDAS, index=0, format_func=moneda, key=f"moneda_{producto}")
    st.session_state["fecha_proceso"] = fecha

    try:
        resultado = api.mtm(deal, fecha, moneda_mtm, detalle=True)
    except Exception as e:
        st.warning(f"No se pudo valorizar: {api.texto_error(e)}")
        st.stop()

    st.metric(f"MtM en {moneda(moneda_mtm)}", numero(resultado["mtm"], 0))
    for pata in resultado["patas"]:
        with st.expander(
            f"Pata {pata['numero']} · {pata['rec_pay'].capitalize()} {moneda(pata['moneda'])} · "
            f"valor presente {numero(pata['valor_presente'], 0)} {moneda(pata['moneda'])} = "
            f"{numero(pata['valor_presente_convertido'], 0)} {moneda(moneda_mtm)}"
        ):
            st.dataframe(pd.DataFrame(pata["flujos"]), hide_index=True, width="stretch")
