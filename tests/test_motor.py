"""!
@package tests.test_motor
@brief Tests del motor de valorización. No usan base de datos.

Comparan los resultados de QC Financial con cálculos independientes de @ref tests.calculo.
"""

from dataclasses import replace
from datetime import date

import pytest

from ejemplos import datos
from tests.calculo import factor_descuento
from valorizador.errores import DatoInvalido, DatoMercadoFaltante
from valorizador.schemas.operaciones import OperacionEntrada
from valorizador.valorizacion import motor

## Fecha de proceso de los datos de ejemplo.
FECHA = date(2026, 10, 6)
## Fechas de cupón del IRS de ejemplo.
CUPONES_IRS = [date(2026, 7, 6), date(2027, 1, 6), date(2027, 7, 6), date(2028, 1, 6), date(2028, 7, 6)]


def operacion(datos_operacion: dict) -> OperacionEntrada:
    """!
    @brief Valida un diccionario de ejemplo como operación.
    @param datos_operacion Operación en el formato de la API.
    @return @ref valorizador.schemas.operaciones.OperacionEntrada.
    """
    return OperacionEntrada.model_validate(datos_operacion)


# ------------------------------------------------------------------------- FX Forward


def test_fx_forward_coincide_con_calculo_independiente(escenario):
    """!
    @brief El MtM de un forward es el valor presente de cada pata calculado sin QC Financial, convertido al spot.
    """
    resultado = motor.valorizar(operacion(datos.FX_FORWARD), escenario, "CLP")

    pago = date(2027, 1, 6)
    vp_usd = 1_000_000 * factor_descuento(escenario.curvas["USD_SOFR"], FECHA, pago)
    vp_clp = -955_000_000 * factor_descuento(escenario.curvas["CLP_CAMARA"], FECHA, pago)

    assert resultado.patas[0].valor_presente == pytest.approx(vp_usd, rel=1e-10)
    assert resultado.patas[1].valor_presente == pytest.approx(vp_clp, rel=1e-10)
    assert resultado.mtm == pytest.approx(vp_usd * 950.0 + vp_clp, rel=1e-10)


def test_fx_forward_en_otra_moneda_de_valorizacion(escenario):
    """!
    @brief Valorizar en USD da el MtM en CLP dividido por el spot.
    """
    en_clp = motor.valorizar(operacion(datos.FX_FORWARD), escenario, "CLP").mtm
    en_usd = motor.valorizar(operacion(datos.FX_FORWARD), escenario, "USD").mtm
    assert en_usd == pytest.approx(en_clp / 950.0, rel=1e-10)


def test_flujo_que_se_paga_en_la_fecha_de_proceso_no_se_valoriza(escenario):
    """!
    @brief Un flujo que se paga en la fecha de proceso ya no forma parte del MtM.
    """
    en_vencimiento = replace(escenario, fecha=date(2027, 1, 6))
    assert motor.valorizar(operacion(datos.FX_FORWARD), en_vencimiento, "CLP").mtm == 0.0


# ---------------------------------------------------------------------------- IR Swap


def test_pata_fija_coincide_con_calculo_independiente(escenario):
    """!
    @brief El valor de una pata fija coincide con el descuento manual de sus cupones.
    """
    resultado = motor.valorizar(operacion(datos.IR_SWAP), escenario, "CLP")
    curva = escenario.curvas["CLP_CAMARA"]
    esperado = sum(
        1e9 * 0.05 * (fin - inicio).days / 360 * factor_descuento(curva, FECHA, fin)
        for inicio, fin in zip(CUPONES_IRS, CUPONES_IRS[1:])
    )
    assert resultado.patas[0].valor_presente == pytest.approx(esperado, rel=1e-10)


def test_pata_flotante_coincide_con_calculo_independiente(escenario):
    """!
    @brief El valor de una pata ICP coincide con el cálculo manual: cupón vigente con índice publicado y cupones futuros proyectados.
    """
    resultado = motor.valorizar(operacion(datos.IR_SWAP), escenario, "CLP")
    curva = escenario.curvas["CLP_CAMARA"]

    def indice(fecha: date) -> float:
        """!
        @brief Índice publicado o proyectado en una fecha, calculado a mano.
        @param fecha Fecha del índice.
        @return Valor del índice.
        """
        if fecha <= FECHA:
            return escenario.indices["ICP"][fecha]
        return 24270.0 / factor_descuento(curva, FECHA, fecha)

    esperado = -sum(
        1e9 * (indice(fin) / indice(inicio) - 1.0) * factor_descuento(curva, FECHA, fin)
        for inicio, fin in zip(CUPONES_IRS, CUPONES_IRS[1:])
    )
    assert resultado.patas[1].valor_presente == pytest.approx(esperado, rel=1e-10)


def test_mtm_del_swap_es_la_suma_de_sus_patas(escenario):
    """!
    @brief El MtM de un swap es la suma del valor convertido de sus dos patas.
    """
    resultado = motor.valorizar(operacion(datos.IR_SWAP), escenario, "CLP")
    assert resultado.mtm == pytest.approx(sum(p.valor_presente for p in resultado.patas))
    assert resultado.patas[0].valor_presente > 0 > resultado.patas[1].valor_presente


def test_detalle_de_flujos_suma_el_valor_de_la_pata(escenario):
    """!
    @brief La suma del valor presente de los flujos del detalle es el valor de la pata.
    """
    resultado = motor.valorizar(operacion(datos.IR_SWAP), escenario, "CLP", detalle=True)
    for pata in resultado.patas:
        assert len(pata.flujos) == 4
        assert sum(f["valor_presente"] for f in pata.flujos) == pytest.approx(pata.valor_presente, rel=1e-12)


def test_feriado_desplaza_la_fecha_de_pago(escenario):
    """!
    @brief Un feriado cargado mueve la fecha de pago del cupón al día hábil siguiente.
    """
    con_feriado = replace(escenario, feriados={"SCL": (date(2027, 1, 6),)})
    resultado = motor.valorizar(operacion(datos.IR_SWAP), con_feriado, "CLP", detalle=True)
    assert resultado.patas[0].flujos[0]["fecha_pago"] == "2027-01-07"


def test_falta_el_valor_del_indice_al_inicio_del_cupon_vigente(escenario):
    """!
    @brief Sin el valor del índice al inicio del cupón vigente, la valorización falla con DatoMercadoFaltante.
    """
    sin_valor = replace(escenario, indices={"ICP": {FECHA: 24270.0}})
    with pytest.raises(DatoMercadoFaltante, match="ICP.*2026-07-06"):
        motor.valorizar(operacion(datos.IR_SWAP), sin_valor, "CLP")


def test_falta_una_curva(escenario):
    """!
    @brief Sin una curva que la operación usa, la valorización falla con DatoMercadoFaltante.
    """
    sin_curva = replace(escenario, curvas={})
    with pytest.raises(DatoMercadoFaltante, match="CLP_CAMARA"):
        motor.valorizar(operacion(datos.IR_SWAP), sin_curva, "CLP")


def test_cupon_terminado_y_no_pagado_usa_los_valores_publicados(escenario):
    """!
    @brief Un cupón cuyo devengo terminó pero aún no se paga usa los índices publicados al inicio y al fin.
    """
    con_lag = {**datos.IR_SWAP, "patas": [{**p, "lag_pago": 2} for p in datos.IR_SWAP["patas"]]}
    fecha = date(2027, 1, 7)  # el primer cupón terminó el 6 y se paga el 8
    indices = {"ICP": {date(2026, 7, 6): 24000.0, date(2027, 1, 6): 24540.0, fecha: 24543.0}}
    al_dia_siguiente = replace(escenario, fecha=fecha, indices=indices)

    resultado = motor.valorizar(operacion(con_lag), al_dia_siguiente, "CLP", detalle=True)
    primero = resultado.patas[1].flujos[0]

    assert primero["fecha_pago"] == "2027-01-08"
    assert primero["valor_indice_inicial"] == 24000.0
    assert primero["valor_indice_final"] == 24540.0
    assert primero["monto_descontado"] == pytest.approx(-1e9 * (24540.0 / 24000.0 - 1.0))


def test_despues_del_ultimo_pago_el_mtm_es_cero(escenario):
    """!
    @brief Después del último pago la operación no tiene flujos y su MtM es cero.
    """
    vencida = replace(escenario, fecha=date(2028, 7, 7))
    assert motor.valorizar(operacion(datos.IR_SWAP), vencida, "CLP").mtm == 0.0


# ---------------------------------------------------------------------------- CC Swap


def test_cc_swap_convierte_cada_pata_con_su_tipo_de_cambio(escenario):
    """!
    @brief En un cross currency swap cada pata se convierte con el spot de su moneda.
    """
    resultado = motor.valorizar(operacion(datos.CC_SWAP), escenario, "CLP")
    clf, usd = resultado.patas
    assert (clf.tipo_cambio, usd.tipo_cambio) == (39500.0, 950.0)
    assert resultado.mtm == pytest.approx(clf.valor_presente * 39500.0 + usd.valor_presente * 950.0)


def test_pata_flotante_con_nocional_vale_el_nocional_capitalizado(escenario):
    """!
    @brief Una pata ICP que intercambia nocional y se descuenta con la misma curva vale el nocional capitalizado con el índice publicado.
    """
    resultado = motor.valorizar(operacion(datos.CC_SWAP), escenario, "CLP")
    assert resultado.patas[1].valor_presente == pytest.approx(-4_150_000 * 1.273 / 1.265, rel=1e-10)


def test_cc_swap_triangula_por_clp(escenario):
    """!
    @brief Un par no cargado se obtiene triangulando por CLP.
    """
    en_usd = motor.valorizar(operacion(datos.CC_SWAP), escenario, "USD")
    assert en_usd.patas[0].tipo_cambio == pytest.approx(39500.0 / 950.0)
    assert en_usd.mtm == pytest.approx(motor.valorizar(operacion(datos.CC_SWAP), escenario, "CLP").mtm / 950.0)


def test_falta_un_tipo_de_cambio(escenario):
    """!
    @brief Sin forma de convertir una moneda, la valorización falla con DatoMercadoFaltante.
    """
    sin_uf = replace(escenario, fx={"USDCLP": 950.0})
    with pytest.raises(DatoMercadoFaltante, match="CLF"):
        motor.valorizar(operacion(datos.CC_SWAP), sin_uf, "CLP")


# ---------------------------------------------------------------------- sensibilidades


def test_sensibilidad_fx_del_forward(escenario):
    """!
    @brief La sensibilidad FX de un forward es el valor de la pata en moneda extranjera por el desplazamiento.
    """
    resultado = motor.sensibilidades(operacion(datos.FX_FORWARD), escenario, "CLP")
    por_factor = {s.factor: s.delta_mtm for s in resultado.sensibilidades}
    vp_usd = motor.valorizar(operacion(datos.FX_FORWARD), escenario, "CLP").patas[0].valor_presente
    assert por_factor["FX:USDCLP"] == pytest.approx(vp_usd * 950.0 * 0.01, rel=1e-9)


def test_factores_del_swap_son_los_vertices_de_su_curva(escenario):
    """!
    @brief Los factores de riesgo de un swap en CLP son los vértices de sus curvas, sin factores FX.
    """
    resultado = motor.sensibilidades(operacion(datos.IR_SWAP), escenario, "CLP")
    assert [s.factor for s in resultado.sensibilidades] == [
        "IR:CLP_CAMARA:1",
        "IR:CLP_CAMARA:180",
        "IR:CLP_CAMARA:365",
        "IR:CLP_CAMARA:730",
        "IR:CLP_CAMARA:1825",
    ]


def test_suma_de_sensibilidades_aproxima_el_desplazamiento_paralelo(escenario):
    """!
    @brief La suma de las sensibilidades por vértice aproxima el efecto de mover toda la curva.
    """
    op = operacion(datos.IR_SWAP)
    resultado = motor.sensibilidades(op, escenario, "CLP")

    paralelo = escenario
    for factor in escenario.factores_curva("CLP_CAMARA"):
        paralelo = paralelo.desplazar(factor, motor.PUNTO_BASE)
    delta_paralelo = motor.valorizar(op, paralelo, "CLP").mtm - resultado.mtm

    assert delta_paralelo < 0  # recibe fijo: pierde cuando suben las tasas
    assert sum(s.delta_mtm for s in resultado.sensibilidades) == pytest.approx(delta_paralelo, rel=1e-3)


def test_desplazar_no_modifica_el_escenario_original(escenario):
    """!
    @brief Desplazar un factor devuelve un escenario nuevo y deja intacto el original.
    """
    escenario.desplazar("FX:USDCLP", 0.10)
    escenario.desplazar("IR:CLP_CAMARA:365", 0.01)
    assert escenario.fx["USDCLP"] == 950.0
    assert escenario.curvas["CLP_CAMARA"].tasas[2] == 0.0475


def test_factor_inexistente(escenario):
    """!
    @brief Desplazar un factor que no existe lanza DatoInvalido.
    """
    with pytest.raises(DatoInvalido):
        escenario.desplazar("IR:CLP_CAMARA:999", 0.0001)


# ------------------------------------------------------------------------ vencimiento


def test_fecha_de_ultimo_pago_ajusta_por_calendario():
    # El 6 de julio de 2028 es jueves; si es feriado, el pago pasa al viernes 7.
    """!
    @brief La fecha de último pago considera feriados y ajuste de fecha.
    """
    assert motor.fecha_ultimo_pago(operacion(datos.IR_SWAP), {}) == date(2028, 7, 6)
    assert motor.fecha_ultimo_pago(operacion(datos.IR_SWAP), {"SCL": (date(2028, 7, 6),)}) == date(2028, 7, 7)
    assert motor.fecha_ultimo_pago(operacion(datos.FX_FORWARD), {}) == date(2027, 1, 6)


# ------------------------------------------------------------------------- validación


@pytest.mark.parametrize(
    "cambio, mensaje",
    [
        ({"producto": "IR_SWAP"}, "SIMPLE"),
        ({"patas": [datos.FX_FORWARD["patas"][0]]}, "dos patas"),
        ({"patas": [datos.FX_FORWARD["patas"][0], {**datos.FX_FORWARD["patas"][1], "rec_pay": "RECIBE"}]}, "RECIBE"),
        ({"patas": [datos.FX_FORWARD["patas"][0], {**datos.FX_FORWARD["patas"][1], "moneda": "USD"}]}, "monedas distintas"),
    ],
)
def test_estructura_invalida_del_forward(cambio, mensaje):
    """!
    @brief Un forward con patas mal formadas se rechaza con el motivo esperado.
    @param cambio Modificación que se aplica a las patas.
    @param mensaje Texto que debe aparecer en el error.
    """
    with pytest.raises(ValueError, match=mensaje):
        OperacionEntrada.model_validate({**datos.FX_FORWARD, **cambio})


def test_swap_de_tasas_exige_una_sola_moneda():
    """!
    @brief Un IR_SWAP con patas en monedas distintas se rechaza.
    """
    with pytest.raises(ValueError, match="CC_SWAP"):
        OperacionEntrada.model_validate({**datos.CC_SWAP, "producto": "IR_SWAP"})


def test_valor_de_un_dia_sin_publicacion_usa_el_siguiente_dia_habil(escenario):
    # El ICP de ejemplo está publicado el lunes 2026-07-06; el sábado anterior toma ese valor.
    """!
    @brief Si un día no tiene publicación del índice se usa la siguiente, sin pasar de la fecha de proceso.
    """
    assert escenario.valor_indice("ICP", date(2026, 7, 4)) == escenario.valor_indice("ICP", date(2026, 7, 6))
    with pytest.raises(DatoMercadoFaltante):
        escenario.valor_indice("ICP", date(2026, 6, 20))  # más de una semana sin publicación
    with pytest.raises(DatoMercadoFaltante):
        escenario.valor_indice("ICP", date(2026, 10, 7))  # posterior a la fecha de proceso
