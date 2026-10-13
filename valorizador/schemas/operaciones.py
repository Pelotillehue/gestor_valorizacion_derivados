"""!
@package valorizador.schemas.operaciones
@brief Esquemas de entrada y salida de operaciones y de sus patas.

Estos mismos modelos son los que recibe el motor de valorización
(@ref valorizador.valorizacion.motor), de modo que el motor no depende de la base de datos.
Las reglas de cada producto se validan en @ref valorizador.schemas.operaciones.validar_estructura y
@ref valorizador.schemas.operaciones.validar_modalidad.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from valorizador.enums import (
    AjusteFecha,
    Estado,
    FactorCapitalizacion,
    FraccionAnio,
    ModalidadLiquidacion,
    Moneda,
    Producto,
    RecPay,
    Stub,
    TipoAmortizacion,
)
from valorizador.schemas.contrapartes import Rut

## Periodicidad válida: uno o más grupos número + unidad (Y, M o D), por ejemplo `6M` o `1Y`.
PATRON_PERIODICIDAD = r"^(\d+[YMD])+$"


class PataBase(BaseModel):
    """!
    @brief Campos comunes a todos los tipos de pata.
    """

    ## Rechaza campos desconocidos.
    model_config = ConfigDict(extra="forbid")

    ## Número de la pata dentro de la operación (1 o 2).
    numero: int = Field(ge=1, description="Número de la pata dentro de la operación")
    ## Sentido de la pata para la institución.
    rec_pay: RecPay
    ## Moneda de la pata.
    moneda: Moneda
    ## Monto en la moneda de la pata, siempre positivo; el signo lo da `rec_pay`.
    nocional: float = Field(gt=0, description="Monto en la moneda de la pata, siempre positivo")
    ## Código de la curva con que se descuentan los flujos de la pata.
    curva_descuento: str = Field(min_length=1, max_length=50)


class PataSimple(PataBase):
    """!
    @brief Un único flujo en una fecha. Es la pata de un FX Forward.
    """

    ## Discriminador: siempre `SIMPLE`.
    tipo: Literal["SIMPLE"]
    ## Fecha de pago del flujo.
    fecha_pago: date

    @property
    def fecha_final(self) -> date:
        """!
        @brief Última fecha de la pata.
        @return La fecha de pago.
        """
        return self.fecha_pago

    @property
    def curvas(self) -> set[str]:
        """!
        @brief Curvas de mercado que necesita la pata.
        @return Sólo la curva de descuento.
        """
        return {self.curva_descuento}


class PataCupones(PataBase):
    """!
    @brief Campos comunes a las patas con calendario de cupones.

    La amortización la indica `tipo_amortizacion`; por ahora sólo bullet: todo el nocional al
    final, y sólo se paga como flujo si `intercambia_nocional` es verdadero. El calendario de cupones lo arma QC Financial a partir
    de estas fechas y convenciones.
    """

    ## Inicio del devengo del primer cupón.
    fecha_inicio: date
    ## Fin del devengo del último cupón (vencimiento de la pata).
    fecha_fin: date
    ## Frecuencia de los cupones, por ejemplo `3M`, `6M` o `1Y`.
    periodicidad: str = Field(pattern=PATRON_PERIODICIDAD, examples=["6M"], description="Por ejemplo 3M, 6M o 1Y")
    ## Tratamiento del período irregular.
    stub: Stub = Stub.NO
    ## Ajuste de las fechas que caen en día no hábil.
    ajuste_fecha: AjusteFecha = AjusteFecha.MODFOLLOW
    ## Calendario de feriados con que se ajustan las fechas.
    calendario: str = Field(default="SCL", min_length=1, max_length=20)
    ## Días hábiles entre el fin de cada cupón y su pago.
    lag_pago: int = Field(default=0, ge=0, description="Días hábiles entre el fin del cupón y su pago")
    ## Forma de amortizar el nocional. Por ahora sólo BULLET.
    tipo_amortizacion: TipoAmortizacion = Field(
        default=TipoAmortizacion.BULLET, description="Por ahora sólo BULLET: todo el nocional al vencimiento"
    )
    ## Si es verdadero, el nocional se paga al vencimiento como un flujo más.
    intercambia_nocional: bool = Field(
        default=False, description="Si es verdadero, la amortización final se paga como flujo"
    )
    ## Convención de conteo de días de los cupones.
    fraccion_anio: FraccionAnio = FraccionAnio.ACT360
    ## Forma de capitalización de la tasa de los cupones.
    factor_capitalizacion: FactorCapitalizacion = FactorCapitalizacion.LINEAL

    @model_validator(mode="after")
    def _fechas_ordenadas(self):
        """!
        @brief Valida que el fin sea posterior al inicio.
        @throws ValueError Si no lo es.
        """
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("fecha_fin debe ser posterior a fecha_inicio")
        return self

    @property
    def fecha_final(self) -> date:
        """!
        @brief Última fecha de la pata.
        @return La fecha de fin, sin ajustar por calendario.
        """
        return self.fecha_fin


class PataFija(PataCupones):
    """!
    @brief Pata de cupones a tasa fija.
    """

    ## Discriminador: siempre `FIJA`.
    tipo: Literal["FIJA"]
    ## Tasa fija en tanto por uno: 0,05 es 5%.
    tasa: float = Field(description="Tasa fija en tanto por uno: 0.05 es 5%")

    @property
    def curvas(self) -> set[str]:
        """!
        @brief Curvas de mercado que necesita la pata.
        @return Sólo la curva de descuento.
        """
        return {self.curva_descuento}


class PataIndiceOvernight(PataCupones):
    """!
    @brief Pata flotante sobre un índice overnight capitalizado, como ICP o el índice SOFR.

    Cada cupón devenga la tasa equivalente entre el valor del índice al inicio y al fin del
    período: publicados si ya ocurrieron, proyectados con `curva_proyeccion` si son futuros.
    """

    ## Discriminador: siempre `INDICE_OVERNIGHT`.
    tipo: Literal["INDICE_OVERNIGHT"]
    ## Nombre del índice tal como está en la tabla `valor_indice`.
    indice: str = Field(min_length=1, max_length=30, examples=["ICP"])
    ## Código de la curva con que se proyectan los valores futuros del índice.
    curva_proyeccion: str = Field(min_length=1, max_length=50)
    ## Spread que se suma a la tasa del índice, en tanto por uno.
    spread: float = 0.0
    ## Multiplicador de la tasa del índice.
    gearing: float = 1.0
    ## Decimales con que se redondea la tasa equivalente de cada cupón.
    decimales_tasa: int = Field(default=4, ge=0, le=12, description="Decimales de la tasa equivalente")

    @property
    def curvas(self) -> set[str]:
        """!
        @brief Curvas de mercado que necesita la pata.
        @return La curva de descuento y la de proyección.
        """
        return {self.curva_descuento, self.curva_proyeccion}


## Unión discriminada por `tipo` de los tres tipos de pata: Pydantic elige la clase según ese campo.
Pata = Annotated[PataSimple | PataFija | PataIndiceOvernight, Field(discriminator="tipo")]


def validar_estructura(producto: Producto, patas: list) -> None:
    """!
    @brief Valida las reglas que cada producto impone sobre sus patas.

    - Siempre dos patas, numeradas 1 y 2, una que recibe y otra que paga.
    - FX_FORWARD: dos patas SIMPLE en monedas distintas con la misma fecha de pago.
    - IR_SWAP: patas con cupones en la misma moneda.
    - CC_SWAP: patas con cupones en monedas distintas.

    @param producto Producto de la operación.
    @param patas Patas ya validadas individualmente.
    @throws ValueError Con el motivo, si alguna regla no se cumple.
    """
    if len(patas) != 2:
        raise ValueError("la operación debe tener exactamente dos patas")
    if sorted(p.numero for p in patas) != [1, 2]:
        raise ValueError("las patas deben numerarse 1 y 2")
    if {p.rec_pay for p in patas} != {RecPay.RECIBE, RecPay.PAGA}:
        raise ValueError("una pata debe ser RECIBE y la otra PAGA")

    tipos = [p.tipo for p in patas]
    misma_moneda = patas[0].moneda == patas[1].moneda

    if producto == Producto.FX_FORWARD:
        if tipos != ["SIMPLE", "SIMPLE"]:
            raise ValueError("un FX_FORWARD lleva dos patas de tipo SIMPLE")
        if misma_moneda:
            raise ValueError("las patas de un FX_FORWARD deben estar en monedas distintas")
        if patas[0].fecha_pago != patas[1].fecha_pago:
            raise ValueError("las dos patas de un FX_FORWARD deben tener la misma fecha_pago")
    else:
        if "SIMPLE" in tipos:
            raise ValueError("un swap no admite patas de tipo SIMPLE")
        if producto == Producto.IR_SWAP and not misma_moneda:
            raise ValueError("las patas de un IR_SWAP deben estar en la misma moneda; si no, es un CC_SWAP")
        if producto == Producto.CC_SWAP and misma_moneda:
            raise ValueError("las patas de un CC_SWAP deben estar en monedas distintas; si no, es un IR_SWAP")


## Monedas que son unidades de cuenta: no se entregan, por lo que sólo admiten compensación.
UNIDADES_DE_CUENTA = {Moneda.CLF}


def validar_modalidad(modalidad: ModalidadLiquidacion, patas: list) -> None:
    """!
    @brief Impide la entrega física en operaciones con una pata en unidad de cuenta, como la UF.
    @param modalidad Modalidad de liquidación pedida.
    @param patas Patas de la operación.
    @throws ValueError Si la modalidad es entrega física y alguna pata está en una unidad de cuenta.
    """
    if modalidad == ModalidadLiquidacion.ENTREGA_FISICA:
        en_unidad = sorted({p.moneda.value for p in patas if p.moneda in UNIDADES_DE_CUENTA})
        if en_unidad:
            raise ValueError(
                f"una operación con patas en {', '.join(en_unidad)} sólo puede liquidarse por compensación: "
                "es una unidad de cuenta, no una moneda que se entregue"
            )


class OperacionEntrada(BaseModel):
    """!
    @brief Datos para dar de alta una operación (`POST /operaciones`).
    """

    ## Rechaza campos desconocidos.
    model_config = ConfigDict(extra="forbid")

    ## Folio de la operación: letras, números, guion, punto o guion bajo.
    deal_number: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.\-]+$")
    ## Producto de la operación.
    producto: Producto
    ## RUT de una contraparte ya registrada en `/contrapartes`.
    rut_contraparte: Rut | None = Field(default=None, description="RUT de una contraparte ya registrada")
    ## Compensación (por defecto) o entrega física.
    modalidad_liquidacion: ModalidadLiquidacion = Field(
        default=ModalidadLiquidacion.COMPENSACION,
        description="COMPENSACION: se liquida la diferencia en CLP. ENTREGA_FISICA: se intercambian los montos de cada pata",
    )
    ## Operaciones con el mismo grupo se cubren entre sí en monto y vencimiento. Nulo: descalzada.
    grupo_calce: str | None = Field(
        default=None,
        max_length=30,
        description="Operaciones con el mismo grupo se cubren entre sí en monto y vencimiento. Nulo: descalzada",
    )
    ## Fecha de cierre de la operación.
    fecha_negociacion: date
    ## Las dos patas.
    patas: list[Pata]

    @model_validator(mode="after")
    def _estructura(self):
        """!
        @brief Valida la operación completa con @ref valorizador.schemas.operaciones.validar_estructura y @ref valorizador.schemas.operaciones.validar_modalidad.
        @throws ValueError Si alguna regla no se cumple; FastAPI lo devuelve como error 422.
        """
        validar_estructura(self.producto, self.patas)
        validar_modalidad(self.modalidad_liquidacion, self.patas)
        return self

    def vencimiento_contractual(self) -> date:
        """!
        @brief Vencimiento contractual.
        @return La mayor fecha final entre las patas, sin ajustar por calendario.
        """
        return max(p.fecha_final for p in self.patas)


class OperacionSalida(OperacionEntrada):
    """!
    @brief Operación tal como la devuelve la API, con los datos que agrega el sistema.
    """

    ## Nombre de la contraparte, leído del maestro.
    contraparte: str | None = Field(default=None, description="Nombre de la contraparte")
    ## Estado de la operación.
    estado: Estado
    ## Versión actual; sube con cada modificación.
    version: int
    ## Mayor fecha final entre las patas, sin ajustar.
    fecha_vencimiento: date = Field(description="Mayor fecha final entre las patas, sin ajustar")
    ## Fecha y hora de alta.
    creado_en: datetime
    ## Fecha y hora de la última modificación.
    actualizado_en: datetime


class OperacionModificacion(BaseModel):
    """!
    @brief Cambios a una operación (`PATCH /operaciones/{deal_number}`).

    Sólo se envían los campos que cambian. Si se envía `patas`, reemplaza a las dos.
    """

    ## Rechaza campos desconocidos.
    model_config = ConfigDict(extra="forbid")

    ## Nuevo RUT de contraparte; nulo deja la operación sin contraparte.
    rut_contraparte: Rut | None = Field(default=None, description="Nulo deja la operación sin contraparte")
    ## Nueva modalidad de liquidación.
    modalidad_liquidacion: ModalidadLiquidacion | None = None
    ## Nuevo grupo de calce; nulo deja la operación descalzada.
    grupo_calce: str | None = Field(default=None, max_length=30, description="Nulo deja la operación descalzada")
    ## Nueva fecha de negociación.
    fecha_negociacion: date | None = None
    ## Nuevo estado, por ejemplo ANULADA.
    estado: Estado | None = None
    ## Las dos patas nuevas.
    patas: list[Pata] | None = None


class Vencimiento(BaseModel):
    """!
    @brief Respuesta de `GET /operaciones/{deal_number}/vencimiento`.
    """

    ## Folio de la operación.
    deal_number: str
    ## Mayor fecha final entre las patas, sin ajustar.
    fecha_vencimiento_contractual: date = Field(description="Mayor fecha final entre las patas, sin ajustar")
    ## Último pago según calendario, ajuste y lag de cada pata.
    fecha_ultimo_pago: date = Field(description="Último pago según calendario, ajuste y lag de cada pata")
    ## Días corridos desde la fecha consultada; nulo si no se indicó fecha.
    dias_al_ultimo_pago: int | None = Field(default=None, description="Días corridos desde la fecha consultada")


class VersionHistorica(BaseModel):
    """!
    @brief Una versión anterior de la operación (`GET /operaciones/{deal_number}/historial`).
    """

    ## Número de la versión reemplazada.
    version: int
    ## Fecha y hora en que se reemplazó.
    reemplazado_en: datetime
    ## La operación completa tal como estaba.
    datos: dict
