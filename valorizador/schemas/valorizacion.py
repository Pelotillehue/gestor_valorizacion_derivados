"""!
@package valorizador.schemas.valorizacion
@brief Esquemas de resultado de la valorización de una operación y de sus sensibilidades.
"""

from datetime import date

from pydantic import BaseModel, Field


class ValorizacionPata(BaseModel):
    """!
    @brief Valor presente de una pata.
    """

    ## Número de la pata.
    numero: int
    ## Tipo de la pata.
    tipo: str
    ## Sentido de la pata.
    rec_pay: str
    ## Moneda de la pata.
    moneda: str
    ## Valor presente en la moneda de la pata, con signo (negativo si se paga).
    valor_presente: float = Field(description="En la moneda de la pata, con signo")
    ## Unidades de moneda de valorización por una de la pata, al spot de la fecha de proceso.
    tipo_cambio: float = Field(description="Unidades de moneda de valorización por una de la pata")
    ## Valor presente en la moneda de valorización.
    valor_presente_convertido: float = Field(description="En la moneda de valorización")
    ## Detalle flujo por flujo tal como lo entrega QC Financial; sólo si se pidió detalle.
    flujos: list[dict] | None = None


class Valorizacion(BaseModel):
    """!
    @brief MtM de una operación (`GET /operaciones/{deal_number}/mtm`).
    """

    ## Folio de la operación.
    deal_number: str
    ## Producto.
    producto: str
    ## Fecha de valorización.
    fecha_proceso: date
    ## Moneda del MtM.
    moneda_valorizacion: str
    ## Suma del valor presente convertido de las dos patas.
    mtm: float
    ## Valor de cada pata.
    patas: list[ValorizacionPata]


class Sensibilidad(BaseModel):
    """!
    @brief Cambio del MtM ante el desplazamiento de un factor de mercado.
    """

    ## Factor desplazado: `FX:PAR` o `IR:CURVA:PLAZO`.
    factor: str = Field(description="FX:PAR o IR:CURVA:PLAZO")
    ## Tamaño del desplazamiento aplicado.
    desplazamiento: float
    ## ABSOLUTO para tasas, RELATIVO para tipos de cambio.
    tipo_desplazamiento: str = Field(description="ABSOLUTO para tasas, RELATIVO para tipos de cambio")
    ## MtM desplazado menos MtM base, en moneda de valorización.
    delta_mtm: float = Field(description="MtM desplazado menos MtM base, en moneda de valorización")


class Sensibilidades(BaseModel):
    """!
    @brief Respuesta de `GET /operaciones/{deal_number}/sensibilidades`. Base del VaR por factor.
    """

    ## Folio de la operación.
    deal_number: str
    ## Fecha de valorización.
    fecha_proceso: date
    ## Moneda del MtM y de las deltas.
    moneda_valorizacion: str
    ## MtM base.
    mtm: float
    ## Una entrada por factor de riesgo de la operación.
    sensibilidades: list[Sensibilidad]
