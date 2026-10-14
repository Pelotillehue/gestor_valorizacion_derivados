"""!
@package valorizador.schemas.cartera
@brief Esquemas de resultado de los cálculos sobre toda la cartera: MtM, vencimientos y flujos.
"""

from datetime import date

from pydantic import BaseModel, Field


class MtmOperacion(BaseModel):
    """!
    @brief MtM de una operación dentro de `GET /cartera/mtm`.
    """

    ## Folio.
    deal_number: str
    ## Producto.
    producto: str
    ## RUT de la contraparte.
    rut_contraparte: str | None
    ## Nombre de la contraparte.
    contraparte: str | None
    ## Modalidad de liquidación.
    modalidad_liquidacion: str
    ## Grupo de calce; nulo si la operación está descalzada.
    grupo_calce: str | None = Field(default=None, description="Nulo si la operación está descalzada")
    ## Vencimiento contractual.
    fecha_vencimiento: date
    ## MtM en la moneda pedida; nulo si la operación no se pudo valorizar.
    mtm: float | None = Field(description="Nulo si la operación no se pudo valorizar")
    ## Motivo por el que no se valorizó.
    error: str | None = Field(default=None, description="Motivo por el que no se valorizó")


class TotalProducto(BaseModel):
    """!
    @brief Totales de un producto dentro de `GET /cartera/mtm`.
    """

    ## Producto.
    producto: str
    ## Operaciones vigentes del producto.
    operaciones: int
    ## Operaciones con MtM.
    valorizadas: int
    ## Operaciones sin MtM.
    con_error: int
    ## Suma del MtM de las valorizadas.
    mtm: float = Field(description="Suma de las operaciones valorizadas")


class MtmCartera(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/mtm`.
    """

    ## Fecha de valorización.
    fecha_proceso: date
    ## Moneda de los montos.
    moneda_valorizacion: str
    ## Suma del MtM de las operaciones valorizadas.
    mtm_total: float = Field(description="Suma de las operaciones valorizadas")
    ## Totales por producto.
    totales: list[TotalProducto]
    ## MtM de cada operación vigente.
    operaciones: list[MtmOperacion]


class FlujoVencimiento(BaseModel):
    """!
    @brief Monto que se intercambia al vencimiento de una operación (`GET /cartera/vencimientos`).
    """

    ## Folio.
    deal_number: str
    ## Producto.
    producto: str
    ## RUT de la contraparte.
    rut_contraparte: str | None
    ## Nombre de la contraparte.
    contraparte: str | None
    ## Modalidad de liquidación.
    modalidad_liquidacion: str
    ## Vencimiento contractual.
    fecha_vencimiento: date
    ## RECIBE o PAGA en entrega física; NETO en compensación.
    sentido: str = Field(description="RECIBE o PAGA en entrega física; NETO en compensación")
    ## Moneda del monto: la de la pata en entrega física, CLP en compensación.
    moneda: str
    ## Positivo si se recibe, negativo si se paga.
    monto: float = Field(description="Positivo si se recibe, negativo si se paga")


class VencimientosCartera(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/vencimientos`.
    """

    ## Fecha de proceso.
    fecha_proceso: date
    ## Moneda de los montos por compensación (CLP).
    moneda_compensacion: str
    ## Montos al vencimiento.
    flujos: list[FlujoVencimiento]
    ## Operaciones omitidas y su motivo.
    errores: dict[str, str] = Field(default_factory=dict, description="Operaciones omitidas y su motivo")


class FlujoCaja(BaseModel):
    """!
    @brief Un flujo futuro de una pata (`GET /cartera/flujos`): cupón, amortización o monto de un forward.
    """

    ## Folio.
    deal_number: str
    ## Producto.
    producto: str
    ## RUT de la contraparte.
    rut_contraparte: str | None
    ## Nombre de la contraparte.
    contraparte: str | None
    ## Modalidad de liquidación.
    modalidad_liquidacion: str
    ## Grupo de calce.
    grupo_calce: str | None
    ## Número de la pata.
    numero_pata: int
    ## Sentido de la pata.
    rec_pay: str
    ## Moneda de la pata.
    moneda: str
    ## Fecha de pago del flujo.
    fecha_pago: date
    ## Nocional que se intercambia en la fecha, en la moneda de la pata; cero si no hay.
    amortizacion: float = Field(description="Nocional que se intercambia en la fecha, en la moneda de la pata; cero si no hay")
    ## Cupón de la fecha, en la moneda de la pata; cero en un forward.
    interes: float = Field(description="Cupón de la fecha, en la moneda de la pata; cero en un forward")
    ## Amortización más interés, en la moneda de la pata. Positivo si se recibe.
    flujo: float = Field(description="Amortización más interés, en la moneda de la pata. Positivo si se recibe")
    ## Spot de la fecha de proceso para pasar a CLP.
    tipo_cambio: float = Field(description="Spot de la fecha de proceso para pasar a CLP")
    ## Flujo convertido a CLP.
    flujo_clp: float


class FlujosCartera(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/flujos`.
    """

    ## Fecha de proceso.
    fecha_proceso: date
    ## Moneda de los montos convertidos (CLP).
    moneda: str
    ## Flujos ordenados por fecha de pago, folio y pata.
    flujos: list[FlujoCaja]
    ## Operaciones que no se pudieron proyectar y su motivo.
    errores: dict[str, str] = Field(default_factory=dict, description="Operaciones omitidas y su motivo")


class PnlRealizadoOperacion(BaseModel):
    """!
    @brief P&L realizado de una operación vencida (`GET /cartera/pnl-realizado`).
    """

    ## Folio.
    deal_number: str
    ## Producto.
    producto: str
    ## RUT de la contraparte.
    rut_contraparte: str | None
    ## Nombre de la contraparte.
    contraparte: str | None
    ## Modalidad de liquidación.
    modalidad_liquidacion: str
    ## Grupo de calce; nulo si la operación está descalzada.
    grupo_calce: str | None
    ## Fecha de negociación.
    fecha_negociacion: date
    ## Fecha de pago (vencimiento).
    fecha_vencimiento: date
    ## Moneda que se recibe.
    moneda_recibe: str
    ## Monto que se recibe.
    monto_recibe: float
    ## Moneda que se paga.
    moneda_paga: str
    ## Monto que se paga.
    monto_paga: float
    ## Fecha de los tipos de cambio usados: la de pago o, si ese día no hay datos, la anterior.
    fecha_tipo_cambio: date | None = None
    ## P&L realizado en CLP: lo recibido menos lo pagado, al spot de la fecha de pago. Nulo si no se pudo calcular.
    pnl: float | None = Field(description="Lo recibido menos lo pagado, en CLP al spot de la fecha de pago")
    ## Motivo por el que no se calculó.
    error: str | None = None


class PnlRealizadoCartera(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/pnl-realizado`.
    """

    ## Primera fecha de vencimiento incluida.
    desde: date
    ## Fecha de proceso: última fecha de vencimiento incluida.
    fecha_proceso: date
    ## Moneda del P&L (CLP).
    moneda: str
    ## Suma del P&L de las operaciones calculadas.
    pnl_total: float
    ## Una fila por operación vencida en el período.
    operaciones: list[PnlRealizadoOperacion]


class ForwardBasilea(BaseModel):
    """!
    @brief Un FX Forward vigente en el detalle Basilea (`GET /cartera/forwards-basilea`).

    La moneda principal es la moneda extranjera del par (USD, EUR o UF) y la secundaria la otra.
    El movimiento es Compra si la institución recibe la moneda principal y Venta si la entrega.
    El valor razonable activo es el valor presente de lo que se recibe y el pasivo el de lo que se
    paga, ambos en CLP y positivos; el valor razonable es su diferencia.
    """

    ## Folio.
    deal_number: str
    ## RUT de la contraparte.
    rut_contraparte: str | None
    ## Nombre de la contraparte.
    contraparte: str | None
    ## Modalidad de liquidación.
    modalidad_liquidacion: str
    ## Grupo de calce; nulo si la operación está descalzada.
    grupo_calce: str | None = None
    ## Compra o Venta de la moneda principal, desde la institución.
    movimiento: str
    ## Par del forward, por ejemplo `USD/CLP`.
    par: str
    ## Moneda principal (extranjera).
    moneda_principal: str
    ## Monto en la moneda principal.
    monto_principal: float
    ## Moneda secundaria.
    moneda_secundaria: str
    ## Monto en la moneda secundaria.
    monto_secundario: float
    ## Precio pactado: unidades de moneda secundaria por una de la principal.
    tipo_cambio: float
    ## Fecha de negociación.
    fecha_negociacion: date
    ## Días entre la negociación y el vencimiento.
    plazo: int
    ## Fecha de vencimiento.
    fecha_vencimiento: date
    ## Días entre la fecha de proceso y el vencimiento.
    dias_al_vencimiento: int
    ## Tasa de la curva de descuento de la pata que se recibe al plazo residual, en tanto por uno.
    tasa_activo: float | None = None
    ## Valor presente de lo que se recibe, en CLP.
    valor_razonable_activo: float | None = None
    ## Tasa de la curva de descuento de la pata que se paga al plazo residual, en tanto por uno.
    tasa_pasivo: float | None = None
    ## Valor presente de lo que se paga, en CLP, positivo.
    valor_razonable_pasivo: float | None = None
    ## Valor razonable (MtM) en CLP: activo menos pasivo. Nulo si no se pudo valorizar.
    valor_razonable: float | None = None
    ## Motivo por el que no se valorizó.
    error: str | None = None


class ForwardsBasilea(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/forwards-basilea`.
    """

    ## Fecha de proceso.
    fecha_proceso: date
    ## Moneda de los valores razonables (CLP).
    moneda: str
    ## Un FX Forward vigente por fila.
    operaciones: list[ForwardBasilea]
