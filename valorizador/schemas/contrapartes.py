"""!
@package valorizador.schemas.contrapartes
@brief Esquemas del maestro de contrapartes y del control de garantías.
"""

from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from valorizador.rut import normalizar

## Tipo de un RUT de entrada: acepta puntos y guion opcional y lo normaliza con @ref valorizador.rut.normalizar.
Rut = Annotated[
    str,
    Field(examples=["76123456-0"], description="Se acepta con o sin puntos; se guarda como 76123456-0"),
    AfterValidator(normalizar),
]


class ContraparteEntrada(BaseModel):
    """!
    @brief Datos para dar de alta una contraparte (`POST /contrapartes`).
    """

    ## Rechaza campos desconocidos.
    model_config = ConfigDict(extra="forbid")

    ## RUT; se guarda normalizado.
    rut: Rut
    ## Nombre, único en el maestro.
    nombre: str = Field(min_length=1, max_length=100)
    ## Exposición aceptada sin garantías, en CLP.
    monto_linea: float = Field(default=0, ge=0, description="Exposición aceptada sin garantías, en CLP")
    ## Monto mínimo de transferencia, en CLP.
    mta: float = Field(default=0, ge=0, description="Monto mínimo de transferencia, en CLP")


class ContraparteSalida(ContraparteEntrada):
    """!
    @brief Contraparte tal como la devuelve la API.
    """

    ## Permite construir el esquema desde el modelo ORM.
    model_config = ConfigDict(from_attributes=True)

    ## Fecha y hora de alta.
    creado_en: datetime
    ## Fecha y hora de la última modificación.
    actualizado_en: datetime


class ContraparteModificacion(BaseModel):
    """!
    @brief Cambios a una contraparte (`PATCH /contrapartes/{rut}`). El RUT no se modifica.
    """

    ## Rechaza campos desconocidos.
    model_config = ConfigDict(extra="forbid")

    ## Nuevo nombre.
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    ## Nuevo monto de línea.
    monto_linea: float | None = Field(default=None, ge=0)
    ## Nuevo MTA.
    mta: float | None = Field(default=None, ge=0)


class GarantiaContraparte(BaseModel):
    """!
    @brief Control de garantías de una contraparte (`GET /cartera/garantias`).

    Hay llamado si la exposición supera la línea; el monto a llamar es el mayor entre el exceso
    y el MTA. Ver @ref valorizador.api.cartera.control_garantia.
    """

    ## RUT.
    rut: str
    ## Nombre.
    nombre: str
    ## Operaciones vigentes con la contraparte.
    operaciones: int
    ## Operaciones sin MtM, que no entran en la exposición.
    con_error: int = Field(description="Operaciones sin MtM, que no entran en la exposición")
    ## Suma del MtM de sus operaciones vigentes, en CLP. Positivo: a favor de la institución.
    exposicion: float = Field(description="Suma del MtM de sus operaciones vigentes, en CLP. Positivo: a favor de la institución")
    ## Monto de línea.
    monto_linea: float
    ## MTA.
    mta: float
    ## Exposición sobre la línea; cero si no la supera.
    exceso: float = Field(description="Exposición sobre la línea; cero si no la supera")
    ## Verdadero si la exposición supera la línea.
    llamado: bool = Field(description="Hay llamado si la exposición supera la línea")
    ## Garantía a constituir: el mayor entre el exceso y el MTA si hay llamado; si no, cero.
    monto_llamado: float = Field(
        description="Garantía a constituir: el mayor entre el exceso y el MTA si hay llamado; si no, cero"
    )


class GarantiasCartera(BaseModel):
    """!
    @brief Respuesta de `GET /cartera/garantias`.
    """

    ## Fecha de proceso.
    fecha_proceso: date
    ## Moneda de los montos (CLP).
    moneda: str
    ## Una fila por contraparte registrada.
    contrapartes: list[GarantiaContraparte]
    ## Folios de operaciones vigentes sin contraparte asignada.
    sin_contraparte: list[str] = Field(default_factory=list, description="Operaciones vigentes sin contraparte asignada")
