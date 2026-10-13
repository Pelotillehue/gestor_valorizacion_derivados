"""!
@package valorizador.enums
@brief Enumeraciones del dominio.

Heredan de `str`, de modo que se guardan en la base de datos y viajan en JSON como texto.
"""

from enum import Enum


class Producto(str, Enum):
    """!
    @brief Familia de producto derivado que maneja el valorizador.
    """

    ## Forward de monedas: dos flujos simples en la misma fecha de pago.
    FX_FORWARD = "FX_FORWARD"
    ## Swap de tasa de interés: dos patas con cupones en la misma moneda.
    IR_SWAP = "IR_SWAP"
    ## Swap de monedas: dos patas con cupones en monedas distintas.
    CC_SWAP = "CC_SWAP"


class Estado(str, Enum):
    """!
    @brief Estado de una operación. Sólo las vigentes se valorizan.
    """

    ## Operación activa, incluida en los cálculos de cartera.
    VIGENTE = "VIGENTE"
    ## Operación dada de baja; se conserva con su historial.
    ANULADA = "ANULADA"


class ModalidadLiquidacion(str, Enum):
    """!
    @brief Forma en que se liquidan los flujos al vencimiento.
    """

    ## Se paga sólo la diferencia neta, en CLP.
    COMPENSACION = "COMPENSACION"
    ## Se intercambia el monto completo de cada pata en su moneda.
    ENTREGA_FISICA = "ENTREGA_FISICA"


class TipoPata(str, Enum):
    """!
    @brief Tipo de pata; define qué campos son obligatorios y cómo se valoriza.
    """

    ## Un único flujo en una fecha. Patas de un FX Forward.
    SIMPLE = "SIMPLE"
    ## Cupones a tasa fija.
    FIJA = "FIJA"
    ## Cupones flotantes sobre un índice overnight capitalizado (ICP, SOFR).
    INDICE_OVERNIGHT = "INDICE_OVERNIGHT"


class RecPay(str, Enum):
    """!
    @brief Sentido de una pata desde el punto de vista de la institución.
    """

    ## La institución recibe los flujos de la pata.
    RECIBE = "RECIBE"
    ## La institución paga los flujos de la pata.
    PAGA = "PAGA"


class Moneda(str, Enum):
    """!
    @brief Monedas admitidas, con código ISO 4217.

    La UF se representa como `CLF`; en la app se muestra como UF.
    """

    CLP = "CLP"
    CLF = "CLF"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CHF = "CHF"
    CAD = "CAD"
    AUD = "AUD"
    BRL = "BRL"
    MXN = "MXN"
    COP = "COP"
    PEN = "PEN"
    CNY = "CNY"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"
    HKD = "HKD"


class FraccionAnio(str, Enum):
    """!
    @brief Convención de conteo de días para calcular la fracción de año de un cupón o de una tasa de curva.

    Los nombres que empiezan con número llevan el prefijo `T` porque un identificador Python no
    puede empezar con un dígito; su valor es el texto que espera QC Financial.
    """

    ACT360 = "ACT360"
    ACT365 = "ACT365"
    ACTACT = "ACTACT"
    T30360 = "30360"
    ACT30 = "ACT30"
    T3030 = "3030"


class FactorCapitalizacion(str, Enum):
    """!
    @brief Forma de capitalizar una tasa: lineal, compuesta o continua.
    """

    LINEAL = "LIN"
    COMPUESTO = "COM"
    CONTINUO = "CON"


class AjusteFecha(str, Enum):
    """!
    @brief Ajuste de una fecha que cae en día no hábil (convenciones ISDA).
    """

    NO = "NO"
    FOLLOW = "FOLLOW"
    MODFOLLOW = "MODFOLLOW"
    PREVIOUS = "PREVIOUS"
    MODPREVIOUS = "MODPREVIOUS"


class TipoAmortizacion(str, Enum):
    """!
    @brief Forma en que se amortiza el nocional de una pata con cupones.

    Por ahora sólo bullet: todo el nocional al vencimiento.
    """

    BULLET = "BULLET"


class Stub(str, Enum):
    """!
    @brief Tratamiento del período irregular cuando el plazo no es múltiplo de la periodicidad.
    """

    NO = "NO"
    SHORTFRONT = "SHORTFRONT"
    SHORTBACK = "SHORTBACK"
    LONGFRONT = "LONGFRONT"
    LONGBACK = "LONGBACK"
