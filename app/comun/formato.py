"""!
@package comun.formato
@brief Nombres, colores y formato de números y fechas compartidos por las páginas y los reportes.
"""

from datetime import date

import altair as alt
import pandas as pd

## Fecha de proceso que proponen las páginas al abrir: la del mercado demo cargado.
FECHA_INICIAL = date(2026, 8, 17)

## Nombre visible de cada producto.
PRODUCTOS = {"FX_FORWARD": "FX Forward", "IR_SWAP": "IR Swap", "CC_SWAP": "Cross Currency Swap"}
## Nombre visible de cada modalidad de liquidación.
MODALIDADES = {"COMPENSACION": "Compensación", "ENTREGA_FISICA": "Entrega física"}
## Monedas que se ofrecen para expresar el MtM.
MONEDAS = ["CLP", "USD", "CLF", "EUR"]

## Un color fijo por producto, en todas las páginas (paleta categórica validada).
COLOR_PRODUCTO = {"FX Forward": "#2a78d6", "IR Swap": "#eb6834", "Cross Currency Swap": "#1baf7a"}

## Columnas de la operación en la plantilla de carga, en el orden de la API.
COLUMNAS_OPERACION = ["deal_number", "producto", "rut_contraparte", "modalidad_liquidacion", "grupo_calce", "fecha_negociacion"]
## Columnas de una pata en la plantilla de carga, en el orden de la API.
COLUMNAS_PATA = [
    "numero", "tipo", "rec_pay", "moneda", "nocional", "curva_descuento", "fecha_pago", "fecha_inicio",
    "fecha_fin", "periodicidad", "stub", "ajuste_fecha", "calendario", "lag_pago", "tipo_amortizacion", "intercambia_nocional",
    "fraccion_anio", "factor_capitalizacion", "tasa", "indice", "curva_proyeccion", "spread", "gearing",
    "decimales_tasa",
]  # fmt: skip


def rut(valor: str | None) -> str:
    """!
    @brief Formatea un RUT con puntos de miles.
    @param valor RUT normalizado o nada.
    @return Por ejemplo `76.123.456-K`; vacío si no hay RUT.
    """
    if not valor:
        return ""
    cuerpo, dv = valor.split("-")
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"


def columna_numero(decimales: int = 0, etiqueta: str | None = None):
    """!
    @brief Configuración de columna numérica para `st.dataframe` con separadores del navegador.

    Con el navegador en español usa punto de miles y coma decimal. Un formato printf como `%.4f`
    siempre usa punto decimal, por eso se usa `localized` con `step` para fijar los decimales.
    @param decimales Cantidad de decimales que se muestran.
    @param etiqueta Título de la columna, opcional.
    @return `st.column_config.NumberColumn`.
    """
    import streamlit as st

    return st.column_config.NumberColumn(etiqueta, format="localized", step=10**-decimales if decimales else 1)


def en_espanol(grafico):
    """!
    @brief Separador de miles con punto y decimal con coma en los ejes y tooltips de Altair.
    @param grafico Gráfico Altair.
    @return El gráfico configurado.
    """
    return grafico.configure(
        locale=alt.Locale(number=alt.NumberLocale(decimal=",", thousands=".", grouping=[3], currency=["$", ""]))
    )


def escala(maximo: float) -> tuple[float, str]:
    """!
    @brief Divisor y unidad para mostrar montos grandes.
    @param maximo Mayor monto absoluto a mostrar.
    @return (1e6, "millones") desde 100 millones; si no, (1e3, "miles").
    """
    return (1e6, "millones") if abs(maximo) >= 1e8 else (1e3, "miles")


## Escala secuencial de un solo tono, de claro a oscuro, para magnitudes como la tasa de una curva.
ESCALA_AZUL = ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
## Color de una serie única en los gráficos de mercado.
COLOR_SERIE = "#2a78d6"

## Nombre visible de cada índice.
NOMBRES_INDICE = {"ICP": "ICP (Índice Cámara Promedio)", "SOFRINDX": "SOFR índice"}


def rango_fechas(etiqueta: str, desde, hasta, clave: str):
    """!
    @brief Selector de rango de fechas acotado a los datos disponibles.
    @param etiqueta Texto del selector.
    @param desde Primera fecha disponible.
    @param hasta Última fecha disponible.
    @param clave Clave del widget en el estado de la sesión.
    @return Tupla (desde, hasta) elegida.
    """
    import streamlit as st

    valor = st.date_input(etiqueta, value=(desde, hasta), min_value=desde, max_value=hasta, format="DD-MM-YYYY", key=clave)
    if isinstance(valor, (tuple, list)) and len(valor) == 2:
        return valor[0], valor[1]
    return desde, hasta  # mientras se elige la segunda fecha


def numero(valor, decimales: int = 0) -> str:
    """!
    @brief Número con punto de miles y coma decimal, por ejemplo 1.234.567,89.
    @param valor Número.
    @param decimales Cantidad de decimales.
    @return Texto formateado.
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def fecha(valor) -> str:
    """!
    @brief Fecha en formato DD-MM-AAAA.
    @param valor Fecha, texto ISO o nada.
    @return Texto formateado; vacío si no hay fecha.
    """
    if valor is None or valor == "" or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return pd.Timestamp(valor).strftime("%d-%m-%Y")


def tasa_o_indice(pata: dict) -> str:
    """!
    @brief Describe la tasa de una pata.
    @param pata Pata en el formato de la API.
    @return Tasa fija en porcentaje, o el índice con su spread si lo tiene.
    """
    if pata.get("tipo") == "FIJA":
        return f"{numero(pata['tasa'] * 100, 4)}%"
    if pata.get("tipo") == "INDICE_OVERNIGHT":
        spread = pata.get("spread") or 0.0
        return pata["indice"] + (f" + {numero(spread * 100, 4)}%" if spread else "")
    return ""


## Prioridad de las monedas para elegir la moneda base de un par de forward.
_ORDEN_BASE = ["CLF", "EUR", "USD", "CLP"]


def par_forward(patas: list[dict]) -> tuple[str, float]:
    """!
    @brief Par y precio pactado de un forward.

    La base es la primera moneda presente en CLF, EUR, USD, CLP: USDCLP, CLFCLP, EURUSD, CLFUSD.
    @param patas Las dos patas del forward.
    @return Tupla (par, unidades de la moneda cotizada por una de la base).
    """
    por_moneda = {p["moneda"]: p["nocional"] for p in patas}
    monedas = sorted(por_moneda, key=lambda m: _ORDEN_BASE.index(m) if m in _ORDEN_BASE else 99)
    base, cotizada = monedas[0], monedas[1]
    return base + cotizada, por_moneda[cotizada] / por_moneda[base]


def resumen_operaciones(operaciones: list[dict]) -> pd.DataFrame:
    """!
    @brief Una fila por operación con sus datos principales, para listar y filtrar.
    @param operaciones Operaciones de la API.
    @return DataFrame.
    """
    filas = []
    for o in operaciones:
        patas = sorted(o["patas"], key=lambda p: p["numero"])
        recibe = next(p for p in patas if p["rec_pay"] == "RECIBE")
        paga = next(p for p in patas if p["rec_pay"] == "PAGA")
        filas.append(
            {
                "Folio": o["deal_number"],
                "Producto": PRODUCTOS.get(o["producto"], o["producto"]),
                "Rut Contraparte": rut(o.get("rut_contraparte")),
                "Contraparte": o.get("contraparte") or "",
                "Modalidad": MODALIDADES.get(o.get("modalidad_liquidacion"), o.get("modalidad_liquidacion")),
                "Calce": "Calzada" if o.get("grupo_calce") else "Descalzada",
                "Negociación": pd.Timestamp(o["fecha_negociacion"]),
                "Vencimiento": pd.Timestamp(o["fecha_vencimiento"]),
                "Recibe": f"{recibe['moneda']} {tasa_o_indice(recibe)}".strip(),
                "Nocional recibe": recibe["nocional"],
                "Paga": f"{paga['moneda']} {tasa_o_indice(paga)}".strip(),
                "Nocional paga": paga["nocional"],
                "Estado": o["estado"],
            }
        )
    return pd.DataFrame(filas)


def patas_planas(operaciones: list[dict]) -> pd.DataFrame:
    """!
    @brief Una fila por pata con todas las columnas, en el formato de la plantilla de carga.
    @param operaciones Operaciones de la API.
    @return DataFrame con las columnas de @ref comun.formato.COLUMNAS_OPERACION y @ref comun.formato.COLUMNAS_PATA.
    """
    filas = []
    for o in operaciones:
        for p in sorted(o["patas"], key=lambda p: p["numero"]):
            fila = {c: o.get(c) for c in COLUMNAS_OPERACION}
            fila.update({c: p.get(c) for c in COLUMNAS_PATA})
            filas.append(fila)
    return pd.DataFrame(filas, columns=COLUMNAS_OPERACION + COLUMNAS_PATA)
