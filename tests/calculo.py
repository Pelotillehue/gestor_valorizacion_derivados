"""!
@package tests.calculo
@brief Cálculos independientes de QC Financial, para contrastar los resultados del motor.
"""

from datetime import date


def tasa_interpolada(plazos, tasas, dias: int) -> float:
    """!
    @brief Interpolación lineal de una tasa cero, plana fuera del rango.
    @param plazos Plazos de los vértices en días.
    @param tasas Tasas de los vértices.
    @param dias Plazo a interpolar.
    @return Tasa interpolada.
    """
    if dias <= plazos[0]:
        return tasas[0]
    if dias >= plazos[-1]:
        return tasas[-1]
    for i in range(1, len(plazos)):
        if dias <= plazos[i]:
            peso = (dias - plazos[i - 1]) / (plazos[i] - plazos[i - 1])
            return tasas[i - 1] + peso * (tasas[i] - tasas[i - 1])
    raise AssertionError


def factor_descuento(curva, desde: date, hasta: date) -> float:
    """!
    @brief Factor de descuento entre dos fechas con la convención de la curva.
    @param curva @ref valorizador.valorizacion.escenario.CurvaDatos.
    @param desde Fecha de proceso.
    @param hasta Fecha del flujo.
    @return Factor de descuento.
    """
    dias = (hasta - desde).days
    return (1.0 + tasa_interpolada(curva.plazos, curva.tasas, dias)) ** (-dias / 365.0)
