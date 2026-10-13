"""!
@package comun.reporte_pnl
@brief Reporte de P&L no realizado por contraparte, separado en operaciones calzadas y descalzadas.

Sigue el formato de la hoja Resumen del cuadro de performance: un bloque de P&L liquidado,
otro de P&L por liquidar y los totales generales. Como la cartera sólo tiene operaciones
vigentes, el bloque liquidado va en cero. Agrega el control de garantías de cada contraparte:
su línea, su MTA y su situación.
"""

import io
from xml.sax.saxutils import escape
from datetime import date, datetime

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from comun.formato import MODALIDADES, PRODUCTOS, numero, rut

## Color de los encabezados.
AZUL = "1C5CAB"
## Formato Excel de montos: sin decimales y negativos en rojo.
FORMATO_MONTO = "#,##0_ ;[Red]\\-#,##0\\ "


LLAMADO, DENTRO = "Llamado a Garantía", "Dentro de Límite"
## Color de los llamados a garantía.
ROJO = "C00000"
## Columnas del bloque de control de garantías.
COLUMNAS_GARANTIA = ["Monto Línea (CLP)", "MTA (CLP)", "Exceso sobre línea", "Situación", "Monto a llamar"]


def detalle(operaciones: list[dict], perspectiva_contraparte: bool) -> pd.DataFrame:
    """!
    @brief Una fila por operación valorizada, con su P&L desde la perspectiva elegida.
    @param operaciones Operaciones de `GET /cartera/mtm`.
    @param perspectiva_contraparte Si es verdadero, invierte el signo (P&L del cliente).
    @return DataFrame.
    """
    signo = -1 if perspectiva_contraparte else 1
    filas = [
        {
            "Rut Contraparte": rut(o.get("rut_contraparte")),
            "Contraparte": o.get("contraparte") or "(sin contraparte)",
            "Folio": o["deal_number"],
            "Producto": PRODUCTOS.get(o["producto"], o["producto"]),
            "Modalidad": MODALIDADES.get(o["modalidad_liquidacion"], o["modalidad_liquidacion"]),
            "Estado calce": "Calzada" if o.get("grupo_calce") else "Descalzada",
            "Grupo de calce": o.get("grupo_calce") or "",
            "Vencimiento": pd.Timestamp(o["fecha_vencimiento"]),
            "P&L no realizado": signo * o["mtm"],
        }
        for o in operaciones
        if o["mtm"] is not None
    ]
    return pd.DataFrame(filas)


def resumen(detalle_ops: pd.DataFrame, garantias: list[dict]) -> pd.DataFrame:
    """!
    @brief Una fila por contraparte: P&L de calzadas, de descalzadas y total, y su control de garantías.
    @param detalle_ops Resultado de @ref comun.reporte_pnl.detalle.
    @param garantias Respuesta de `GET /cartera/garantias`: exposición de cada contraparte con todas sus operaciones vigentes, desde la perspectiva de la institución.
    @return DataFrame ordenado por contraparte.
    """
    columnas = ["Rut Contraparte", "Contraparte", "Operaciones", "Calzadas", "Descalzadas", "Total", *COLUMNAS_GARANTIA]
    if detalle_ops.empty:
        return pd.DataFrame(columns=columnas)
    claves = ["Rut Contraparte", "Contraparte"]
    tabla = detalle_ops.pivot_table(
        index=claves, columns="Estado calce", values="P&L no realizado", aggfunc="sum", fill_value=0.0
    ).reindex(columns=["Calzada", "Descalzada"], fill_value=0.0)
    tabla.columns = ["Calzadas", "Descalzadas"]
    tabla["Total"] = tabla["Calzadas"] + tabla["Descalzadas"]
    tabla.insert(0, "Operaciones", detalle_ops.groupby(claves).size())
    tabla = tabla.reset_index()

    control = pd.DataFrame(
        [
            {
                "Rut Contraparte": rut(g["rut"]),
                "Monto Línea (CLP)": g["monto_linea"],
                "MTA (CLP)": g["mta"],
                "Exceso sobre línea": g["exceso"],
                "Situación": LLAMADO if g["llamado"] else DENTRO,
                "Monto a llamar": g["monto_llamado"],
            }
            for g in garantias
        ],
        columns=["Rut Contraparte", *COLUMNAS_GARANTIA],
    )
    tabla = tabla.merge(control, on="Rut Contraparte", how="left")
    tabla["Situación"] = tabla["Situación"].fillna("—")  # operaciones sin contraparte
    return tabla[columnas].sort_values("Contraparte").reset_index(drop=True)


# ------------------------------------------------------------------------------ Excel


def detalle_realizado(operaciones: list[dict], perspectiva_contraparte: bool) -> pd.DataFrame:
    """!
    @brief Una fila por operación liquidada, con su P&L realizado desde la perspectiva elegida.
    @param operaciones Operaciones de `GET /cartera/pnl-realizado`.
    @param perspectiva_contraparte Si es verdadero, invierte el signo (P&L del cliente).
    @return DataFrame.
    """
    signo = -1 if perspectiva_contraparte else 1
    filas = [
        {
            "Rut Contraparte": rut(o.get("rut_contraparte")),
            "Contraparte": o.get("contraparte") or "(sin contraparte)",
            "Folio": o["deal_number"],
            "Modalidad": MODALIDADES.get(o["modalidad_liquidacion"], o["modalidad_liquidacion"]),
            "Estado calce": "Calzada" if o.get("grupo_calce") else "Descalzada",
            "Grupo de calce": o.get("grupo_calce") or "",
            "Negociación": pd.Timestamp(o["fecha_negociacion"]),
            "Vencimiento": pd.Timestamp(o["fecha_vencimiento"]),
            "Moneda recibe": "UF" if o["moneda_recibe"] == "CLF" else o["moneda_recibe"],
            "Monto recibe": o["monto_recibe"],
            "Moneda paga": "UF" if o["moneda_paga"] == "CLF" else o["moneda_paga"],
            "Monto paga": o["monto_paga"],
            "Fecha tipo de cambio": pd.Timestamp(o["fecha_tipo_cambio"]),
            "P&L realizado": signo * o["pnl"],
        }
        for o in operaciones
        if o["pnl"] is not None
    ]
    return pd.DataFrame(filas)


def resumen_realizado(detalle_ops: pd.DataFrame) -> pd.DataFrame:
    """!
    @brief Una fila por contraparte con el P&L realizado de calzadas, de descalzadas y total.
    @param detalle_ops Resultado de @ref comun.reporte_pnl.detalle_realizado.
    @return DataFrame ordenado por contraparte.
    """
    columnas = ["Rut Contraparte", "Contraparte", "Operaciones", "Calzadas", "Descalzadas", "Total"]
    if detalle_ops.empty:
        return pd.DataFrame(columns=columnas)
    claves = ["Rut Contraparte", "Contraparte"]
    tabla = detalle_ops.pivot_table(
        index=claves, columns="Estado calce", values="P&L realizado", aggfunc="sum", fill_value=0.0
    ).reindex(columns=["Calzada", "Descalzada"], fill_value=0.0)
    tabla.columns = ["Calzadas", "Descalzadas"]
    tabla["Total"] = tabla["Calzadas"] + tabla["Descalzadas"]
    tabla.insert(0, "Operaciones", detalle_ops.groupby(claves).size())
    return tabla.reset_index()[columnas].sort_values("Contraparte").reset_index(drop=True)


def excel_realizado(tabla: pd.DataFrame, detalle_ops: pd.DataFrame, desde: date, fecha: date, perspectiva: str) -> bytes:
    """!
    @brief Excel del P&L realizado: hoja por contraparte y hoja con el detalle por operación.
    @param tabla Resultado de @ref comun.reporte_pnl.resumen_realizado.
    @param detalle_ops Resultado de @ref comun.reporte_pnl.detalle_realizado.
    @param desde Primer vencimiento incluido.
    @param fecha Último vencimiento incluido.
    @param perspectiva Institución o Cliente.
    @return Contenido del archivo .xlsx.
    """
    salida = io.BytesIO()
    encabezado = dict(
        font=Font(bold=True, color="FFFFFF"),
        fill=PatternFill("solid", fgColor=AZUL),
        alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
    )
    total = pd.DataFrame(
        [{"Rut Contraparte": "", "Contraparte": "Total", "Operaciones": tabla["Operaciones"].sum(),
          "Calzadas": tabla["Calzadas"].sum(), "Descalzadas": tabla["Descalzadas"].sum(), "Total": tabla["Total"].sum()}]
    )  # fmt: skip
    resumen_xl = pd.concat([tabla, total], ignore_index=True).rename(
        columns={"Calzadas": "P&L calzadas", "Descalzadas": "P&L descalzadas", "Total": "P&L realizado total"}
    )
    detalle_xl = detalle_ops.assign(
        **{c: detalle_ops[c].dt.date for c in ("Negociación", "Vencimiento", "Fecha tipo de cambio")}
    )
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        for nombre, datos in (("Resumen", resumen_xl), ("Detalle Liquidadas", detalle_xl)):
            datos.to_excel(escritor, sheet_name=nombre, index=False, startrow=3)
            hoja = escritor.sheets[nombre]
            hoja["A1"] = "P&L realizado"
            hoja["A1"].font = Font(bold=True, size=14)
            hoja["A2"] = f"Vencimientos del {desde:%d-%m-%Y} al {fecha:%d-%m-%Y}, en CLP. Perspectiva: {perspectiva}."
            hoja["A2"].font = Font(italic=True, color="52514E")
            for celda in hoja[4]:
                for atributo, valor in encabezado.items():
                    setattr(celda, atributo, valor)
            for i, columna in enumerate(datos.columns, start=1):
                letra = get_column_letter(i)
                hoja.column_dimensions[letra].width = 26 if columna == "Contraparte" else 17
                formato = None
                if columna.startswith("P&L") or columna.startswith("Monto"):
                    formato = FORMATO_MONTO
                elif columna in ("Negociación", "Vencimiento", "Fecha tipo de cambio"):
                    formato = "dd-mm-yyyy"
                if formato:
                    for f in range(5, len(datos) + 5):
                        hoja[f"{letra}{f}"].number_format = formato
            hoja.freeze_panes = "C5"
        hoja_res = escritor.sheets["Resumen"]
        for celda in hoja_res[len(resumen_xl) + 4]:
            celda.font = Font(bold=True)
    return salida.getvalue()


def excel(
    tabla: pd.DataFrame,
    detalle_ops: pd.DataFrame,
    fecha: date,
    perspectiva: str,
    productos: str,
    liquidado: pd.DataFrame | None = None,
    desde: date | None = None,
) -> bytes:
    """!
    @brief Excel con el formato de la hoja Resumen y una hoja con el detalle por operación.

    El bloque "P&L histórico liquidado" toma el P&L realizado del período; una contraparte que
    sólo tiene operaciones liquidadas aparece con el P&L por liquidar en cero.
    @param tabla Resultado de @ref comun.reporte_pnl.resumen.
    @param detalle_ops Resultado de @ref comun.reporte_pnl.detalle.
    @param fecha Fecha de proceso.
    @param perspectiva Institución o Cliente.
    @param productos Productos incluidos, como texto.
    @param liquidado Resultado de @ref comun.reporte_pnl.resumen_realizado, o nada.
    @param desde Primera fecha del P&L liquidado.
    @return Contenido del archivo .xlsx.
    """
    claves = ["Rut Contraparte", "Contraparte"]
    if liquidado is None:
        liquidado = pd.DataFrame(columns=[*claves, "Calzadas", "Descalzadas", "Total"])
    liq = liquidado[[*claves, "Calzadas", "Descalzadas", "Total"]].rename(
        columns={"Calzadas": "L_Calzadas", "Descalzadas": "L_Descalzadas", "Total": "L_Total"}
    )
    combinada = tabla.merge(liq, on=claves, how="outer").sort_values("Contraparte").reset_index(drop=True)
    montos = ["L_Calzadas", "L_Descalzadas", "L_Total", "Calzadas", "Descalzadas", "Total"]
    combinada[montos] = combinada[montos].astype(float).fillna(0.0)
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as escritor:
        libro = escritor.book
        hoja = libro.create_sheet("Resumen")
        borde = Side(style="thin", color="BFBFBF")
        encabezado = dict(
            font=Font(bold=True, color="FFFFFF"),
            fill=PatternFill("solid", fgColor=AZUL),
            alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
            border=Border(left=borde, right=borde, top=borde, bottom=borde),
        )

        hoja["B2"], hoja["C2"] = "Fecha Proceso:", fecha
        hoja["C2"].number_format = "dd-mm-yyyy"
        periodo = f"Liquidado desde {desde:%d-%m-%Y}" if desde else "Operaciones vigentes"
        hoja["D2"], hoja["E2"] = "Periodo:", periodo
        hoja["B3"] = (
            f"Perspectiva: {perspectiva}. Productos: {productos}. Control de garantías: exposición de todas "
            "las operaciones vigentes de la contraparte, desde la perspectiva de la institución."
        )
        for celda in ("B2", "D2"):
            hoja[celda].font = Font(bold=True)
        hoja["B3"].font = Font(italic=True, color="52514E")

        for rango, titulo in (("B4:B5", "Rut Contraparte"), ("C4:C5", "Contraparte")):
            hoja.merge_cells(rango)
            hoja[rango.split(":")[0]] = titulo
        bloques = [
            ("D4:F4", "P&L histórico liquidado", ["Por oper. Calzadas", "Por oper. Descalzadas", "Total P&L liquidado"]),
            ("G4:I4", "P&L por liquidar (no realizado)", ["Por oper. Calzadas", "Por oper. Descalzadas", "Total P&L por liquidar"]),
            ("J4:L4", "Totales Generales", ["P&L liquidado", "P&L por liquidar", "Performance total"]),
            ("M4:Q4", "Control de garantías", COLUMNAS_GARANTIA),
        ]
        columna = 4
        for rango, titulo, subtitulos in bloques:
            hoja.merge_cells(rango)
            hoja[rango.split(":")[0]] = titulo
            for subtitulo in subtitulos:
                hoja.cell(5, columna, subtitulo)
                columna += 1
        ultima = columna - 1
        for fila in (4, 5):
            for col in range(2, ultima + 1):
                for atributo, valor in encabezado.items():
                    setattr(hoja.cell(fila, col), atributo, valor)
        hoja.row_dimensions[5].height = 32

        fila = 6
        for _, r in combinada.iterrows():
            valores = [
                r["Rut Contraparte"], r["Contraparte"], r["L_Calzadas"], r["L_Descalzadas"], r["L_Total"],
                r["Calzadas"], r["Descalzadas"], r["Total"], r["L_Total"], r["Total"], r["L_Total"] + r["Total"],
                *(None if pd.isna(r[c]) else r[c] for c in COLUMNAS_GARANTIA),
            ]
            for col, valor in enumerate(valores, start=2):
                celda = hoja.cell(fila, col, valor)
                if col > 3 and col != 16:
                    celda.number_format = FORMATO_MONTO
            hoja.cell(fila, 16).alignment = Alignment(horizontal="center")
            if valores[14] == LLAMADO:
                hoja.cell(fila, 16).font = Font(bold=True, color=ROJO)
            fila += 1
        hoja.cell(fila, 2, "Total").font = Font(bold=True)
        for col in (*range(4, 13), 16, 17):  # la línea, el MTA y el exceso no se suman
            letra = get_column_letter(col)
            if fila == 6:
                formula = 0
            elif col == 16:
                formula = f'=COUNTIF({letra}6:{letra}{fila - 1},"{LLAMADO}")'
            else:
                formula = f"=SUM({letra}6:{letra}{fila - 1})"
            celda = hoja.cell(fila, col, formula)
            celda.number_format = "0" if col == 16 else FORMATO_MONTO
            celda.font = Font(bold=True)
            celda.alignment = Alignment(horizontal="center") if col == 16 else Alignment()
        for col in range(2, ultima + 1):
            hoja.cell(fila, col).border = Border(top=Side(style="thin", color="000000"))

        hoja.column_dimensions["A"].width = 2
        hoja.column_dimensions["B"].width = 15
        hoja.column_dimensions["C"].width = 26
        for col in range(4, ultima + 1):
            hoja.column_dimensions[get_column_letter(col)].width = 17
        hoja.freeze_panes = "D6"
        libro.remove(libro["Sheet"]) if "Sheet" in libro.sheetnames else None

        detalle_excel = detalle_ops.assign(Vencimiento=detalle_ops["Vencimiento"].dt.date)
        detalle_excel.to_excel(escritor, sheet_name="Detalle Vigentes", index=False)
        hoja_det = escritor.sheets["Detalle Vigentes"]
        for celda in hoja_det[1]:
            for atributo, valor in encabezado.items():
                setattr(celda, atributo, valor)
        for i, nombre in enumerate(detalle_excel.columns, start=1):
            letra = get_column_letter(i)
            hoja_det.column_dimensions[letra].width = 26 if nombre == "Contraparte" else 16
            formato = {"Vencimiento": "dd-mm-yyyy", "P&L no realizado": FORMATO_MONTO}.get(nombre)
            if formato:
                for f in range(2, len(detalle_excel) + 2):
                    hoja_det[f"{letra}{f}"].number_format = formato
        hoja_det.freeze_panes = "D2"
        if len(detalle_excel):
            hoja_det.auto_filter.ref = f"A1:{get_column_letter(len(detalle_excel.columns))}{len(detalle_excel) + 1}"
    return salida.getvalue()


# -------------------------------------------------------------------------------- PDF


def pdf(tabla: pd.DataFrame, fecha: date, perspectiva: str, productos: str) -> bytes:
    """!
    @brief PDF horizontal con la tabla por contraparte y su control de garantías.
    @param tabla Resultado de @ref comun.reporte_pnl.resumen.
    @param fecha Fecha de proceso.
    @param perspectiva Institución o Cliente.
    @param productos Productos incluidos, como texto.
    @return Contenido del archivo .pdf.
    """
    salida = io.BytesIO()
    pagina = landscape(A4)
    documento = SimpleDocTemplate(
        salida, pagesize=pagina, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title="P&L no realizado por contraparte", author="Valorizador de Derivados",
    )  # fmt: skip
    titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=14, leading=18)
    subtitulo = ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#52514E"))
    blanco = ParagraphStyle("enc", fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white, alignment=1)

    encabezados = [
        "Rut Contraparte", "Contraparte", "Oper.", "P&L calzadas", "P&L descalzadas", "P&L no realizado total",
        "Monto Línea (CLP)", "MTA (CLP)", "Situación", "Monto a llamar",
    ]  # fmt: skip
    monto = lambda v: "" if pd.isna(v) else numero(v)  # noqa: E731
    datos = [[Paragraph(escape(e), blanco) for e in encabezados]]
    for r in tabla.itertuples(index=False):
        datos.append(
            [r[0], r.Contraparte, numero(r.Operaciones), numero(r.Calzadas), numero(r.Descalzadas), numero(r.Total),
             monto(r[6]), monto(r[7]), r[9], monto(r[10])]
        )  # fmt: skip
    llamados = int((tabla["Situación"] == LLAMADO).sum())
    datos.append(
        ["Total", "", numero(tabla["Operaciones"].sum()), numero(tabla["Calzadas"].sum()),
         numero(tabla["Descalzadas"].sum()), numero(tabla["Total"].sum()), "", "", str(llamados),
         numero(tabla["Monto a llamar"].sum())]
    )  # fmt: skip

    estilo = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{AZUL}")),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (8, 1), (8, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F0EFEC")]),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
    )
    # Negativos en rojo, como en el formato del cuadro.
    for f, fila in enumerate(datos[1:], start=1):
        for c in (3, 4, 5):
            if str(fila[c]).startswith("-"):
                estilo.add("TEXTCOLOR", (c, f), (c, f), colors.HexColor("#C00000"))
        if fila[8] == LLAMADO:
            estilo.add("TEXTCOLOR", (8, f), (8, f), colors.HexColor(f"#{ROJO}"))
            estilo.add("FONTNAME", (8, f), (8, f), "Helvetica-Bold")
    ancho = pagina[0] - 24 * mm
    proporciones = [0.09, 0.14, 0.05, 0.1, 0.1, 0.11, 0.1, 0.08, 0.11, 0.12]
    tabla_pdf = LongTable(datos, colWidths=[ancho * p for p in proporciones], repeatRows=1)
    tabla_pdf.setStyle(estilo)

    def pie(lienzo, doc):
        """!
        @brief Pie de página con el nombre del reporte y el número de página.
        @param lienzo Lienzo de reportlab.
        @param doc Documento.
        """
        lienzo.saveState()
        lienzo.setFont("Helvetica", 7)
        lienzo.setFillColor(colors.HexColor("#52514E"))
        lienzo.drawString(12 * mm, 6 * mm, "Valorizador de Derivados · P&L no realizado por contraparte")
        lienzo.drawRightString(pagina[0] - 12 * mm, 6 * mm, f"Página {doc.page}")
        lienzo.restoreState()

    documento.build(
        [
            Paragraph(escape("P&L no realizado por contraparte"), titulo),
            Paragraph(
                escape(
                    f"Operaciones vigentes al {fecha:%d-%m-%Y}, en CLP. Perspectiva: {perspectiva}. "
                    f"Productos: {productos}. Generado el {datetime.now():%d-%m-%Y %H:%M}. "
                    "Garantías: hay llamado cuando la exposición de la contraparte, con todas sus operaciones "
                    "vigentes y desde la perspectiva de la institución, supera su línea, por el exceso o por el MTA, el mayor de los dos."
                ),
                subtitulo,
            ),
            Spacer(1, 4 * mm),
            tabla_pdf,
        ],
        onFirstPage=pie,
        onLaterPages=pie,
    )
    return salida.getvalue()
