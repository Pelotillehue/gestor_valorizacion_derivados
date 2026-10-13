"""!
@package valorizador.db.modelos
@brief Modelos ORM: una clase por tabla de PostgreSQL.

Se guardan términos contractuales y datos de mercado, nunca objetos de QC Financial: esos se
construyen en memoria en cada valorización. El esquema se crea y actualiza con las
migraciones Alembic de la carpeta `migraciones/`.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from valorizador.db.base import Base


class Contraparte(Base):
    """!
    @brief Tabla `contraparte`: maestro de contrapartes con su línea de crédito y MTA, en CLP.
    """

    __tablename__ = "contraparte"

    ## RUT normalizado (`76123456-K`). Clave primaria.
    rut: Mapped[str] = mapped_column(String(12), primary_key=True)
    ## Nombre de la contraparte. Único.
    nombre: Mapped[str] = mapped_column(String(100), unique=True)
    ## Exposición a favor de la institución que se acepta sin garantías, en CLP.
    monto_linea: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    ## Monto mínimo de transferencia: un llamado a garantías nunca es por menos que esto.
    mta: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    ## Fecha y hora de alta.
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ## Fecha y hora de la última modificación.
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ## Operaciones asociadas a la contraparte.
    operaciones: Mapped[list["Operacion"]] = relationship(back_populates="contraparte")


class Operacion(Base):
    """!
    @brief Tabla `operacion`: una fila por operación, con los datos comunes a cualquier producto.
    """

    __tablename__ = "operacion"

    ## Identificador interno.
    id: Mapped[int] = mapped_column(primary_key=True)
    ## Folio de la operación. Único.
    deal_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    ## Valor de @ref valorizador.enums.Producto.
    producto: Mapped[str] = mapped_column(String(20))
    ## RUT de la contraparte; clave foránea a `contraparte.rut`.
    rut_contraparte: Mapped[str | None] = mapped_column(
        ForeignKey("contraparte.rut", onupdate="CASCADE"), index=True
    )
    ## Valor de @ref valorizador.enums.ModalidadLiquidacion.
    modalidad_liquidacion: Mapped[str] = mapped_column(
        String(20), default="COMPENSACION", server_default="COMPENSACION"
    )
    ## Operaciones con el mismo grupo se cubren entre sí; nulo si la operación está descalzada.
    grupo_calce: Mapped[str | None] = mapped_column(String(30), index=True)
    ## Fecha de cierre de la operación.
    fecha_negociacion: Mapped[date] = mapped_column(Date)
    ## Valor de @ref valorizador.enums.Estado.
    estado: Mapped[str] = mapped_column(String(20), default="VIGENTE")
    ## Sube en uno con cada modificación. Las versiones anteriores quedan en `operacion_historial`.
    version: Mapped[int] = mapped_column(Integer, default=1)
    ## Fecha y hora de alta.
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ## Fecha y hora de la última modificación.
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    ## Contraparte de la operación.
    contraparte: Mapped[Contraparte | None] = relationship(back_populates="operaciones")
    ## Las dos patas, ordenadas por número. Se borran con la operación.
    patas: Mapped[list["Pata"]] = relationship(
        back_populates="operacion", cascade="all, delete-orphan", order_by="Pata.numero"
    )
    ## Versiones anteriores, ordenadas por número de versión.
    historial: Mapped[list["OperacionHistorial"]] = relationship(
        back_populates="operacion", cascade="all, delete-orphan", order_by="OperacionHistorial.version"
    )


class Pata(Base):
    """!
    @brief Tabla `pata`: una fila por pata de una operación.

    Las columnas que no aplican al tipo de pata quedan nulas: una pata SIMPLE sólo usa
    `fecha_pago`; una FIJA, las de cupones y `tasa`; una INDICE_OVERNIGHT, las de cupones y las
    del índice.
    """

    __tablename__ = "pata"
    __table_args__ = (UniqueConstraint("operacion_id", "numero"),)

    ## Identificador interno.
    id: Mapped[int] = mapped_column(primary_key=True)
    ## Operación a la que pertenece.
    operacion_id: Mapped[int] = mapped_column(ForeignKey("operacion.id", ondelete="CASCADE"), index=True)
    ## Número de la pata dentro de la operación (1 o 2).
    numero: Mapped[int] = mapped_column(Integer)
    ## Valor de @ref valorizador.enums.TipoPata.
    tipo: Mapped[str] = mapped_column(String(20))
    ## Valor de @ref valorizador.enums.RecPay.
    rec_pay: Mapped[str] = mapped_column(String(10))
    ## Moneda de la pata (ISO 4217; la UF es `CLF`).
    moneda: Mapped[str] = mapped_column(String(3))
    ## Nocional o monto de la pata, en su moneda.
    nocional: Mapped[float] = mapped_column(Float)
    ## Código de la curva con que se descuentan los flujos.
    curva_descuento: Mapped[str] = mapped_column(String(50))

    ## Pata SIMPLE: fecha de pago del flujo.
    fecha_pago: Mapped[date | None] = mapped_column(Date)

    ## Patas con cupones: inicio del devengo.
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    ## Patas con cupones: vencimiento.
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    ## Patas con cupones: frecuencia de pago, por ejemplo `6M`.
    periodicidad: Mapped[str | None] = mapped_column(String(10))
    ## Patas con cupones: valor de @ref valorizador.enums.Stub.
    stub: Mapped[str | None] = mapped_column(String(15))
    ## Patas con cupones: valor de @ref valorizador.enums.AjusteFecha.
    ajuste_fecha: Mapped[str | None] = mapped_column(String(15))
    ## Patas con cupones: calendario de feriados, por ejemplo `SCL`.
    calendario: Mapped[str | None] = mapped_column(String(20))
    ## Patas con cupones: días hábiles entre el fin del cupón y su pago.
    lag_pago: Mapped[int | None] = mapped_column(Integer)
    ## Patas con cupones: valor de @ref valorizador.enums.TipoAmortizacion.
    tipo_amortizacion: Mapped[str | None] = mapped_column(String(15))
    ## Patas con cupones: si el nocional se paga al vencimiento como un flujo más.
    intercambia_nocional: Mapped[bool | None] = mapped_column(Boolean)
    ## Patas con cupones: valor de @ref valorizador.enums.FraccionAnio.
    fraccion_anio: Mapped[str | None] = mapped_column(String(10))
    ## Patas con cupones: valor de @ref valorizador.enums.FactorCapitalizacion.
    factor_capitalizacion: Mapped[str | None] = mapped_column(String(3))

    ## Pata FIJA: tasa en tanto por uno (0,05 es 5%).
    tasa: Mapped[float | None] = mapped_column(Float)

    ## Pata INDICE_OVERNIGHT: nombre del índice, por ejemplo `ICP` o `SOFRINDX`.
    indice: Mapped[str | None] = mapped_column(String(30))
    ## Pata INDICE_OVERNIGHT: código de la curva con que se proyecta el índice.
    curva_proyeccion: Mapped[str | None] = mapped_column(String(50))
    ## Pata INDICE_OVERNIGHT: spread sobre la tasa del índice, en tanto por uno.
    spread: Mapped[float | None] = mapped_column(Float)
    ## Pata INDICE_OVERNIGHT: multiplicador de la tasa del índice.
    gearing: Mapped[float | None] = mapped_column(Float)
    ## Pata INDICE_OVERNIGHT: decimales con que se redondea la tasa equivalente del cupón.
    decimales_tasa: Mapped[int | None] = mapped_column(Integer)

    ## Operación a la que pertenece la pata.
    operacion: Mapped[Operacion] = relationship(back_populates="patas")


class OperacionHistorial(Base):
    """!
    @brief Tabla `operacion_historial`: copia de la operación tal como estaba antes de cada modificación.
    """

    __tablename__ = "operacion_historial"
    __table_args__ = (UniqueConstraint("operacion_id", "version"),)

    ## Identificador interno.
    id: Mapped[int] = mapped_column(primary_key=True)
    ## Operación modificada.
    operacion_id: Mapped[int] = mapped_column(ForeignKey("operacion.id", ondelete="CASCADE"), index=True)
    ## Versión que fue reemplazada.
    version: Mapped[int] = mapped_column(Integer)
    ## La operación completa en JSON, en el formato de la API.
    datos: Mapped[dict] = mapped_column(JSONB)
    ## Fecha y hora de la modificación.
    reemplazado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ## Operación a la que pertenece la versión.
    operacion: Mapped[Operacion] = relationship(back_populates="historial")


class TipoCambio(Base):
    """!
    @brief Tabla `fx`: valor de un par en una fecha. El par BASECOTIZ vale unidades de COTIZ por una de BASE.
    """

    __tablename__ = "fx"

    ## Fecha del valor.
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    ## Par de seis letras, por ejemplo `USDCLP` (pesos por dólar) o `CLFCLP` (pesos por UF).
    par: Mapped[str] = mapped_column(String(6), primary_key=True)
    ## Unidades de la moneda cotizada por una de la base.
    valor: Mapped[float] = mapped_column(Float)


class Curva(Base):
    """!
    @brief Tabla `curva`: curva cero de una fecha, con la convención en que están expresadas sus tasas.
    """

    __tablename__ = "curva"
    __table_args__ = (UniqueConstraint("fecha", "codigo"),)

    ## Identificador interno.
    id: Mapped[int] = mapped_column(primary_key=True)
    ## Fecha de la curva.
    fecha: Mapped[date] = mapped_column(Date, index=True)
    ## Código con que las patas la referencian, por ejemplo `Curva CLP`.
    codigo: Mapped[str] = mapped_column(String(50))
    ## Convención de conteo de días de las tasas.
    fraccion_anio: Mapped[str] = mapped_column(String(10))
    ## Forma de capitalización de las tasas.
    factor_capitalizacion: Mapped[str] = mapped_column(String(3))

    ## Vértices de la curva, ordenados por plazo.
    vertices: Mapped[list["CurvaVertice"]] = relationship(
        back_populates="curva", cascade="all, delete-orphan", order_by="CurvaVertice.plazo_dias"
    )


class CurvaVertice(Base):
    """!
    @brief Tabla `curva_vertice`: un punto (plazo en días, tasa) de una curva.
    """

    __tablename__ = "curva_vertice"

    ## Curva a la que pertenece.
    curva_id: Mapped[int] = mapped_column(ForeignKey("curva.id", ondelete="CASCADE"), primary_key=True)
    ## Código de la curva, repetido para consultas por vértice (revisión 0002).
    codigo: Mapped[str] = mapped_column(String(50))  # repite el de la curva (revisión 0002)
    ## Plazo del vértice en días desde la fecha de la curva.
    plazo_dias: Mapped[int] = mapped_column(Integer, primary_key=True)
    ## Tasa cero en tanto por uno.
    tasa: Mapped[float] = mapped_column(Float)

    ## Curva a la que pertenece el vértice.
    curva: Mapped[Curva] = relationship(back_populates="vertices")


class ValorIndice(Base):
    """!
    @brief Tabla `valor_indice`: valor publicado de un índice en una fecha, por ejemplo ICP o SOFRINDX.
    """

    __tablename__ = "valor_indice"

    ## Nombre del índice.
    indice: Mapped[str] = mapped_column(String(30), primary_key=True)
    ## Fecha de publicación.
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    ## Valor del índice capitalizado.
    valor: Mapped[float] = mapped_column(Float)


class Feriado(Base):
    """!
    @brief Tabla `feriado`: días no hábiles de cada calendario.
    """

    __tablename__ = "feriado"

    ## Código del calendario, por ejemplo `SCL`.
    calendario: Mapped[str] = mapped_column(String(20), primary_key=True)
    ## Fecha feriada.
    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
