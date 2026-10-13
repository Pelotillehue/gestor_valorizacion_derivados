"""!
@package valorizador.schemas.mercado
@brief Esquemas de carga y consulta de datos de mercado: tipos de cambio, curvas, índices y feriados.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from valorizador.enums import FactorCapitalizacion, FraccionAnio


class FxValor(BaseModel):
    """!
    @brief Valor de un par de monedas.
    """

    model_config = ConfigDict(extra="forbid")

    ## Par BASECOTIZ: unidades de COTIZ por una de BASE, por ejemplo `USDCLP`.
    par: str = Field(pattern=r"^[A-Z]{6}$", examples=["USDCLP"], description="BASECOTIZ: unidades de COTIZ por una de BASE")
    ## Valor del par, positivo.
    valor: float = Field(gt=0)

    @model_validator(mode="after")
    def _monedas_distintas(self):
        """!
        @brief Valida que el par tenga dos monedas distintas.
        @throws ValueError Si son iguales.
        """
        if self.par[:3] == self.par[3:]:
            raise ValueError("el par debe tener dos monedas distintas")
        return self


class FxCarga(BaseModel):
    """!
    @brief Tipos de cambio de una fecha (`POST /mercado/fx`). Reemplaza los pares que ya existían ese día.
    """

    model_config = ConfigDict(extra="forbid")

    ## Fecha de los valores.
    fecha: date
    ## Uno o más pares con su valor.
    valores: list[FxValor] = Field(min_length=1)


class Vertice(BaseModel):
    """!
    @brief Un punto de una curva cero.
    """

    model_config = ConfigDict(extra="forbid")

    ## Plazo en días desde la fecha de la curva.
    plazo_dias: int = Field(gt=0)
    ## Tasa cero en tanto por uno.
    tasa: float = Field(description="Tasa cero en tanto por uno")


class CurvaCarga(BaseModel):
    """!
    @brief Curva cero completa de una fecha (`POST /mercado/curvas`). Cargarla de nuevo reemplaza la anterior.
    """

    model_config = ConfigDict(extra="forbid")

    ## Fecha de la curva.
    fecha: date
    ## Código con que las patas referencian la curva.
    codigo: str = Field(min_length=1, max_length=50, examples=["CLP_CAMARA"])
    ## Convención de conteo de días de las tasas.
    fraccion_anio: FraccionAnio = FraccionAnio.ACT365
    ## Forma de capitalización de las tasas.
    factor_capitalizacion: FactorCapitalizacion = FactorCapitalizacion.COMPUESTO
    ## Al menos dos vértices, sin plazos repetidos.
    vertices: list[Vertice] = Field(min_length=2)

    @model_validator(mode="after")
    def _plazos_unicos(self):
        """!
        @brief Valida que no haya plazos repetidos y ordena los vértices por plazo.
        @throws ValueError Si hay plazos repetidos.
        """
        plazos = [v.plazo_dias for v in self.vertices]
        if len(set(plazos)) != len(plazos):
            raise ValueError("hay plazos repetidos en la curva")
        self.vertices.sort(key=lambda v: v.plazo_dias)
        return self


class IndiceValor(BaseModel):
    """!
    @brief Valor de un índice en una fecha.
    """

    model_config = ConfigDict(extra="forbid")

    ## Fecha de publicación.
    fecha: date
    ## Valor del índice capitalizado.
    valor: float = Field(gt=0)


class IndiceCarga(BaseModel):
    """!
    @brief Valores de un índice (`POST /mercado/indices`). Reemplaza los de las mismas fechas.
    """

    model_config = ConfigDict(extra="forbid")

    ## Nombre del índice, por ejemplo `ICP` o `SOFRINDX`.
    indice: str = Field(min_length=1, max_length=30, examples=["ICP"])
    ## Uno o más valores por fecha.
    valores: list[IndiceValor] = Field(min_length=1)


class FeriadoCarga(BaseModel):
    """!
    @brief Feriados de un calendario (`POST /mercado/feriados`).
    """

    model_config = ConfigDict(extra="forbid")

    ## Código del calendario, por ejemplo `SCL`.
    calendario: str = Field(min_length=1, max_length=20, examples=["SCL"])
    ## Fechas feriadas.
    fechas: list[date] = Field(min_length=1)


class ResultadoCarga(BaseModel):
    """!
    @brief Respuesta de las cargas de mercado.
    """

    ## Cantidad de registros guardados.
    registros: int


class SerieDisponible(BaseModel):
    """!
    @brief Una serie de mercado guardada: su nombre, el rango de fechas y cuántas fechas tiene.
    """

    ## Par, código de curva o nombre de índice.
    nombre: str
    ## Primera fecha con datos.
    desde: date
    ## Última fecha con datos.
    hasta: date
    ## Cantidad de fechas distintas con datos.
    fechas: int


class ResumenMercado(BaseModel):
    """!
    @brief Respuesta de `GET /mercado/resumen`: qué series hay guardadas.
    """

    ## Pares de tipo de cambio.
    fx: list[SerieDisponible] = Field(description="Pares de tipo de cambio")
    ## Curvas cero, por código.
    curvas: list[SerieDisponible] = Field(description="Curvas cero, por código")
    ## Índices como ICP o SOFRINDX.
    indices: list[SerieDisponible] = Field(description="Índices como ICP o SOFRINDX")
