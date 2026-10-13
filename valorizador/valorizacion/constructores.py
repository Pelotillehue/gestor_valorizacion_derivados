"""!
@package valorizador.valorizacion.constructores
@brief Traducción de los datos guardados a objetos de QC Financial.

Todo lo que toca la librería está en este módulo y en @ref valorizador.valorizacion.motor.
"""

from datetime import date

import qcfinancial as qcf

from valorizador.enums import AjusteFecha, FactorCapitalizacion, FraccionAnio, RecPay, Stub
from valorizador.errores import DatoInvalido
from valorizador.schemas.operaciones import PataCupones, PataFija, PataIndiceOvernight, PataSimple
from valorizador.valorizacion.escenario import CurvaDatos, EscenarioMercado

## Clase de moneda de QC Financial para cada código ISO.
_MONEDAS = {
    "CLP": qcf.QCCLP, "CLF": qcf.QCCLF, "USD": qcf.QCUSD, "EUR": qcf.QCEUR, "GBP": qcf.QCGBP,
    "JPY": qcf.QCJPY, "CHF": qcf.QCCHF, "CAD": qcf.QCCAD, "AUD": qcf.QCAUD, "BRL": qcf.QCBRL,
    "MXN": qcf.QCMXN, "COP": qcf.QCCOP, "PEN": qcf.QCPEN, "CNY": qcf.QCCNY, "SEK": qcf.QCSEK,
    "NOK": qcf.QCNOK, "DKK": qcf.QCDKK, "HKD": qcf.QCHKD,
}  # fmt: skip

## Clase de fracción de año de QC Financial para cada convención.
_FRACCIONES = {
    FraccionAnio.ACT360: qcf.QCAct360,
    FraccionAnio.ACT365: qcf.QCAct365,
    FraccionAnio.ACTACT: qcf.QCActAct,
    FraccionAnio.T30360: qcf.QC30360,
    FraccionAnio.ACT30: qcf.QCAct30,
    FraccionAnio.T3030: qcf.QC3030,
}

## Clase de factor de capitalización de QC Financial para cada forma de capitalizar.
_FACTORES = {
    FactorCapitalizacion.LINEAL: qcf.QCLinearWf,
    FactorCapitalizacion.COMPUESTO: qcf.QCCompoundWf,
    FactorCapitalizacion.CONTINUO: qcf.QCContinousWf,
}

## Regla de ajuste de fechas de QC Financial.
_AJUSTES = {
    AjusteFecha.NO: qcf.BusyAdjRules.NO,
    AjusteFecha.FOLLOW: qcf.BusyAdjRules.FOLLOW,
    AjusteFecha.MODFOLLOW: qcf.BusyAdjRules.MODFOLLOW,
    AjusteFecha.PREVIOUS: qcf.BusyAdjRules.PREVIOUS,
    AjusteFecha.MODPREVIOUS: qcf.BusyAdjRules.MODPREVIOUS,
}

## Tratamiento de período irregular de QC Financial.
_STUBS = {
    Stub.NO: qcf.StubPeriod.NO,
    Stub.SHORTFRONT: qcf.StubPeriod.SHORTFRONT,
    Stub.SHORTBACK: qcf.StubPeriod.SHORTBACK,
    Stub.LONGFRONT: qcf.StubPeriod.LONGFRONT,
    Stub.LONGBACK: qcf.StubPeriod.LONGBACK,
}

## Sentido de la pata en QC Financial.
_REC_PAY = {RecPay.RECIBE: qcf.RecPay.RECEIVE, RecPay.PAGA: qcf.RecPay.PAY}


def a_qcdate(fecha: date) -> qcf.QCDate:
    """!
    @brief Convierte una fecha de Python a `QCDate`.
    @param fecha Fecha.
    @return `qcf.QCDate`.
    """
    return qcf.QCDate(fecha.day, fecha.month, fecha.year)


def a_date(fecha: qcf.QCDate) -> date:
    """!
    @brief Convierte un `QCDate` a fecha de Python.
    @param fecha `qcf.QCDate`.
    @return Fecha.
    """
    return date(fecha.year(), fecha.month(), fecha.day())


def moneda_qcf(codigo: str) -> qcf.QCCurrency:
    """!
    @brief Moneda de QC Financial.
    @param codigo Código ISO.
    @return Instancia de `qcf.QCCurrency`.
    """
    return _MONEDAS[codigo]()


def tasa_qcf(valor: float, fraccion: FraccionAnio, factor: FactorCapitalizacion) -> qcf.QCInterestRate:
    """!
    @brief Tasa de interés de QC Financial.
    @param valor Tasa en tanto por uno.
    @param fraccion Convención de conteo de días.
    @param factor Forma de capitalización.
    @return `qcf.QCInterestRate`.
    """
    return qcf.QCInterestRate(valor, _FRACCIONES[fraccion](), _FACTORES[factor]())


def construir_calendario(feriados: tuple[date, ...], desde: date, hasta: date) -> qcf.BusinessCalendar:
    """!
    @brief Calendario hábil con sábados, domingos y los feriados cargados.
    @param feriados Feriados del calendario.
    @param desde Primera fecha que debe cubrir.
    @param hasta Última fecha que debe cubrir.
    @return `qcf.BusinessCalendar`.
    """
    anio_inicial = desde.year - 1
    calendario = qcf.BusinessCalendar(qcf.QCDate(1, 1, anio_inicial), hasta.year - anio_inicial + 2)
    for feriado in feriados:
        calendario.add_holiday(a_qcdate(feriado))
    return calendario


def construir_curva(datos: CurvaDatos) -> qcf.ZeroCouponCurve:
    """!
    @brief Curva cero de QC Financial con interpolación lineal en tasas.
    @param datos Plazos, tasas y convención.
    @return `qcf.ZeroCouponCurve`.
    """
    plazos, tasas = qcf.long_vec(), qcf.double_vec()
    for plazo, tasa in zip(datos.plazos, datos.tasas):
        plazos.append(plazo)
        tasas.append(tasa)
    return qcf.ZeroCouponCurve(
        qcf.QCLinearInterpolator(qcf.QCCurve(plazos, tasas)),
        tasa_qcf(0.0, datos.fraccion_anio, datos.factor_capitalizacion),
    )


def construir_pata(pata, feriados: tuple[date, ...], fecha_referencia: date) -> qcf.Leg:
    """!
    @brief Pata de QC Financial con su calendario de flujos. No usa datos de mercado.

    Las patas flotantes quedan con los valores de índice sin fijar: los asigna @ref valorizador.valorizacion.constructores.fijar_indices.
    @param pata Pata del esquema (SIMPLE, FIJA o INDICE_OVERNIGHT).
    @param feriados Feriados de su calendario.
    @param fecha_referencia Fecha que el calendario debe cubrir además de las de la pata.
    @return `qcf.Leg`.
    @throws DatoInvalido Si QC Financial no puede construirla o el tipo no está soportado.
    """
    try:
        if isinstance(pata, PataSimple):
            return _pata_simple(pata)
        calendario = construir_calendario(
            feriados, min(pata.fecha_inicio, fecha_referencia), max(pata.fecha_fin, fecha_referencia)
        )
        if isinstance(pata, PataFija):
            return _pata_fija(pata, calendario)
        if isinstance(pata, PataIndiceOvernight):
            return _pata_indice_overnight(pata, calendario)
    except (RuntimeError, ValueError) as error:
        raise DatoInvalido(f"No se pudo construir la pata {pata.numero}: {error}") from error
    raise DatoInvalido(f"Tipo de pata no soportado: {pata.tipo}")


def _pata_simple(pata: PataSimple) -> qcf.Leg:
    """!
    @brief Pata de un único flujo, con signo según el sentido.
    @param pata Pata SIMPLE.
    @return `qcf.Leg` con un `SimpleCashflow`.
    """
    signo = 1.0 if pata.rec_pay == RecPay.RECIBE else -1.0
    leg = qcf.Leg()
    leg.append_cashflow(
        qcf.SimpleCashflow(a_qcdate(pata.fecha_pago), signo * pata.nocional, moneda_qcf(pata.moneda))
    )
    return leg


def _argumentos_comunes(pata: PataCupones, calendario: qcf.BusinessCalendar) -> dict:
    """!
    @brief Argumentos de `LegFactory` comunes a las patas con cupones.
    @param pata Pata con cupones.
    @param calendario Calendario hábil.
    @return Diccionario de argumentos con nombre.
    """
    return dict(
        rec_pay=_REC_PAY[pata.rec_pay],
        start_date=a_qcdate(pata.fecha_inicio),
        end_date=a_qcdate(pata.fecha_fin),
        bus_adj_rule=_AJUSTES[pata.ajuste_fecha],
        settlement_periodicity=qcf.Tenor(pata.periodicidad),
        settlement_stub_period=_STUBS[pata.stub],
        settlement_calendar=calendario,
        settlement_lag=pata.lag_pago,
        initial_notional=pata.nocional,
        amort_is_cashflow=pata.intercambia_nocional,
        interest_rate=tasa_qcf(
            pata.tasa if isinstance(pata, PataFija) else 0.0, pata.fraccion_anio, pata.factor_capitalizacion
        ),
        notional_currency=moneda_qcf(pata.moneda),
    )


def _pata_fija(pata: PataFija, calendario: qcf.BusinessCalendar) -> qcf.Leg:
    """!
    @brief Pata bullet a tasa fija.
    @param pata Pata FIJA.
    @param calendario Calendario hábil.
    @return `qcf.Leg`.
    """
    return qcf.LegFactory.build_bullet_fixed_rate_leg(**_argumentos_comunes(pata, calendario), is_bond=False)


def _pata_indice_overnight(pata: PataIndiceOvernight, calendario: qcf.BusinessCalendar) -> qcf.Leg:
    """!
    @brief Pata bullet sobre un índice overnight; la tasa equivalente se calcula sobre las fechas de devengo.
    @param pata Pata INDICE_OVERNIGHT.
    @param calendario Calendario hábil, también usado para las fechas de fijación.
    @return `qcf.Leg`.
    """
    return qcf.LegFactory.build_bullet_overnight_index_leg(
        **_argumentos_comunes(pata, calendario),
        fix_adj_rule=_AJUSTES[pata.ajuste_fecha],
        fixing_calendar=calendario,
        spread=pata.spread,
        gearing=pata.gearing,
        index_name=pata.indice,
        eq_rate_decimal_places=pata.decimales_tasa,
        dates_for_eq_rate=qcf.DatesForEquivalentRate.ACCRUAL,
    )


def fijar_indices(
    leg: qcf.Leg, pata: PataIndiceOvernight, escenario: EscenarioMercado, curva_proyeccion: qcf.ZeroCouponCurve
) -> None:
    """!
    @brief Asigna el índice inicial y final de cada cupón que aún no se ha pagado.

    Si la fecha del índice ya pasó o es la fecha de proceso, se usa el valor publicado. Si es
    futura, se proyecta: índice de hoy dividido por el factor de descuento de la curva de
    proyección entre la fecha de proceso y esa fecha.
    @param leg Pata de QC Financial construida con @ref valorizador.valorizacion.constructores.construir_pata.
    @param pata Pata del esquema, con el nombre del índice.
    @param escenario Escenario con los valores publicados.
    @param curva_proyeccion Curva con que se proyectan los valores futuros.
    @throws DatoMercadoFaltante Si falta un valor publicado necesario.
    """
    fecha = escenario.fecha
    indice_hoy: float | None = None

    def valor_indice(fecha_indice: date) -> float:
        """!
        @brief Valor del índice en una fecha, publicado o proyectado.
        @param fecha_indice Fecha.
        @return Valor del índice.
        """
        nonlocal indice_hoy
        if fecha_indice <= fecha:
            return escenario.valor_indice(pata.indice, fecha_indice)
        if indice_hoy is None:
            indice_hoy = escenario.valor_indice(pata.indice, fecha)
        dias = (fecha_indice - fecha).days
        return indice_hoy / curva_proyeccion.get_discount_factor_at(dias)

    for i in range(leg.size()):
        flujo = leg.get_cashflow_at(i)
        if a_date(flujo.get_settlement_date()) <= fecha:
            continue
        flujo.set_start_date_index(valor_indice(a_date(flujo.get_index_start_date())))
        flujo.set_end_date_index(valor_indice(a_date(flujo.get_index_end_date())))

