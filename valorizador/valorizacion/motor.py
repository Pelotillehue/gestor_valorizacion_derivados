"""!
@package valorizador.valorizacion.motor
@brief Motor de valorización.

Las funciones de este módulo son puras: reciben la operación y un escenario de mercado y
devuelven el resultado. No leen ni escriben en la base de datos.

Cada pata se construye con @ref valorizador.valorizacion.constructores.construir_pata, se
descuenta con su curva de descuento mediante `qcf.PresentValue` y se convierte a la moneda de
valorización con el spot del escenario.
"""

from datetime import date

import qcfinancial as qcf

from valorizador.schemas.operaciones import OperacionEntrada, PataIndiceOvernight
from valorizador.schemas.valorizacion import Sensibilidad, Sensibilidades, Valorizacion, ValorizacionPata
from valorizador.valorizacion.constructores import (
    a_date,
    a_qcdate,
    construir_curva,
    construir_pata,
    fijar_indices,
)
from valorizador.valorizacion.escenario import EscenarioMercado

## Desplazamiento por defecto de las tasas en las sensibilidades: 1 punto base.
PUNTO_BASE = 0.0001
## Desplazamiento por defecto de los tipos de cambio en las sensibilidades: 1%.
UNO_POR_CIENTO = 0.01

## Nombres de columna del detalle de flujos que entrega QC Financial para cada tipo de pata.
_COLUMNAS = {
    "SIMPLE": qcf.get_column_names("SimpleCashflow"),
    "FIJA": qcf.get_column_names("FixedRateCashflow"),
    "INDICE_OVERNIGHT": qcf.get_column_names("OvernightIndexCashflow"),
}


def valorizar(
    operacion: OperacionEntrada,
    escenario: EscenarioMercado,
    moneda_valorizacion: str = "CLP",
    detalle: bool = False,
) -> Valorizacion:
    """!
    @brief MtM de la operación en la fecha del escenario.

    Cada pata se descuenta en su propia moneda con su curva de descuento y se convierte a la moneda
    de valorización con el tipo de cambio spot del escenario. Las patas flotantes proyectan el
    índice con su curva de proyección. Los flujos cuya fecha de pago es la fecha de proceso o
    anterior no entran en el valor.
    @param operacion Operación en el esquema de entrada.
    @param escenario Datos de mercado de la fecha.
    @param moneda_valorizacion Moneda del MtM.
    @param detalle Si es verdadero, incluye el detalle de flujos de cada pata.
    @return @ref valorizador.schemas.valorizacion.Valorizacion.
    @throws DatoMercadoFaltante Si falta una curva, un tipo de cambio o un valor de índice.
    """
    fecha = a_qcdate(escenario.fecha)
    curvas: dict[str, qcf.ZeroCouponCurve] = {}

    def curva(codigo: str) -> qcf.ZeroCouponCurve:
        """!
        @brief Construye cada curva una sola vez por valorización.
        @param codigo Código de la curva.
        @return `qcf.ZeroCouponCurve`.
        """
        if codigo not in curvas:
            curvas[codigo] = construir_curva(escenario.curva(codigo))
        return curvas[codigo]

    resultados = []
    for pata in sorted(operacion.patas, key=lambda p: p.numero):
        feriados = escenario.feriados.get(getattr(pata, "calendario", ""), ())
        leg = construir_pata(pata, feriados, escenario.fecha)
        if isinstance(pata, PataIndiceOvernight):
            fijar_indices(leg, pata, escenario, curva(pata.curva_proyeccion))

        descuento = curva(pata.curva_descuento)
        valor_presente = qcf.PresentValue().pv(fecha, leg, descuento)
        tipo_cambio = escenario.tipo_cambio(pata.moneda.value, moneda_valorizacion)

        resultados.append(
            ValorizacionPata(
                numero=pata.numero,
                tipo=pata.tipo,
                rec_pay=pata.rec_pay.value,
                moneda=pata.moneda.value,
                valor_presente=valor_presente,
                tipo_cambio=tipo_cambio,
                valor_presente_convertido=valor_presente * tipo_cambio,
                flujos=_detalle_flujos(leg, pata.tipo, fecha, descuento) if detalle else None,
            )
        )

    return Valorizacion(
        deal_number=operacion.deal_number,
        producto=operacion.producto.value,
        fecha_proceso=escenario.fecha,
        moneda_valorizacion=moneda_valorizacion,
        mtm=sum(r.valor_presente_convertido for r in resultados),
        patas=resultados,
    )


def _detalle_flujos(leg: qcf.Leg, tipo: str, fecha: qcf.QCDate, descuento: qcf.ZeroCouponCurve) -> list[dict]:
    """!
    @brief Detalle de cada flujo de una pata, con su monto y su valor presente.

    En patas flotantes QC Financial muestra el flujo con la tasa equivalente redondeada pero
    descuenta el monto sin redondear; se informan ambos para que el detalle cuadre.
    @param leg Pata de QC Financial.
    @param tipo Tipo de la pata.
    @param fecha Fecha de proceso.
    @param descuento Curva de descuento.
    @return Una fila (diccionario) por flujo.
    """
    columnas = _COLUMNAS[tipo]
    flujos = []
    for i in range(leg.size()):
        flujo = leg.get_cashflow_at(i)
        fila = dict(zip(columnas, qcf.show(flujo)))
        # En patas flotantes qcfinancial muestra el flujo con la tasa equivalente redondeada,
        # pero descuenta el monto sin redondear. Se informan ambos para que el detalle cuadre.
        fila["monto_descontado"] = flujo.amount()
        fila["valor_presente"] = qcf.PresentValue().pv(fecha, flujo, descuento)
        flujos.append(fila)
    return flujos


def factores_de_riesgo(operacion: OperacionEntrada, escenario: EscenarioMercado, moneda_valorizacion: str) -> list[str]:
    """!
    @brief Factores del escenario que intervienen en el MtM de la operación.
    @param operacion Operación.
    @param escenario Escenario.
    @param moneda_valorizacion Moneda del MtM.
    @return Claves de factor: primero los pares FX que se usan para convertir, luego cada vértice de cada curva.
    """
    factores: list[str] = []
    for pata in sorted(operacion.patas, key=lambda p: p.numero):
        for par, _ in escenario.ruta_fx(pata.moneda.value, moneda_valorizacion):
            if f"FX:{par}" not in factores:
                factores.append(f"FX:{par}")
    for codigo in sorted({c for pata in operacion.patas for c in pata.curvas}):
        factores.extend(escenario.factores_curva(codigo))
    return factores


def sensibilidades(
    operacion: OperacionEntrada,
    escenario: EscenarioMercado,
    moneda_valorizacion: str = "CLP",
    desplazamiento_ir: float = PUNTO_BASE,
    desplazamiento_fx: float = UNO_POR_CIENTO,
) -> Sensibilidades:
    """!
    @brief Cambio del MtM al mover cada factor por separado, por revalorización completa.
    @param operacion Operación.
    @param escenario Escenario base.
    @param moneda_valorizacion Moneda del MtM.
    @param desplazamiento_ir Desplazamiento absoluto de las tasas.
    @param desplazamiento_fx Desplazamiento relativo de los tipos de cambio.
    @return @ref valorizador.schemas.valorizacion.Sensibilidades.
    """
    base = valorizar(operacion, escenario, moneda_valorizacion).mtm
    filas = []
    for factor in factores_de_riesgo(operacion, escenario, moneda_valorizacion):
        es_fx = factor.startswith("FX:")
        delta = desplazamiento_fx if es_fx else desplazamiento_ir
        desplazado = valorizar(operacion, escenario.desplazar(factor, delta), moneda_valorizacion).mtm
        filas.append(
            Sensibilidad(
                factor=factor,
                desplazamiento=delta,
                tipo_desplazamiento="RELATIVO" if es_fx else "ABSOLUTO",
                delta_mtm=desplazado - base,
            )
        )
    return Sensibilidades(
        deal_number=operacion.deal_number,
        fecha_proceso=escenario.fecha,
        moneda_valorizacion=moneda_valorizacion,
        mtm=base,
        sensibilidades=filas,
    )


def fecha_ultimo_pago(operacion: OperacionEntrada, feriados: dict[str, tuple[date, ...]]) -> date:
    """!
    @brief Última fecha de pago de la operación según calendario, ajuste y lag de cada pata.
    @param operacion Operación.
    @param feriados Feriados por calendario.
    @return Fecha del último pago.
    """
    ultima = date.min
    for pata in operacion.patas:
        leg = construir_pata(pata, feriados.get(getattr(pata, "calendario", ""), ()), pata.fecha_final)
        for i in range(leg.size()):
            flujo = leg.get_cashflow_at(i)
            pago = flujo.date() if pata.tipo == "SIMPLE" else flujo.get_settlement_date()
            ultima = max(ultima, a_date(pago))
    return ultima
