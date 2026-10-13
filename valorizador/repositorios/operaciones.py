"""!
@package valorizador.repositorios.operaciones
@brief Lectura y escritura de operaciones, sus patas y su historial.
"""

from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from valorizador.db import modelos
from valorizador.enums import Estado, Producto
from valorizador.errores import DatoInvalido, OperacionDuplicada, OperacionNoEncontrada
from valorizador.schemas.operaciones import (
    OperacionEntrada,
    OperacionModificacion,
    OperacionSalida,
    validar_estructura,
    validar_modalidad,
)

## Columnas de la tabla `pata` que forman parte de los datos de la pata (todas menos las claves).
_COLUMNAS_PATA = [c.key for c in modelos.Pata.__table__.columns if c.key not in ("id", "operacion_id")]


def _valores_planos(datos: dict) -> dict:
    """!
    @brief Reemplaza los valores enum por su texto para guardarlos.
    @param datos Diccionario de un modelo Pydantic.
    @return El mismo diccionario con valores simples.
    """
    return {k: (v.value if isinstance(v, Enum) else v) for k, v in datos.items()}


def _pata_a_modelo(pata) -> modelos.Pata:
    """!
    @brief Convierte una pata del esquema al modelo ORM.
    @param pata Pata validada.
    @return @ref valorizador.db.modelos.Pata sin operación asignada.
    """
    return modelos.Pata(**_valores_planos(pata.model_dump()))


def a_esquema(operacion: modelos.Operacion) -> OperacionSalida:
    """!
    @brief Convierte la operación guardada al modelo que usan la API y el motor.

    Las columnas nulas de cada pata se omiten para que Pydantic elija el tipo de pata correcto.
    @param operacion Modelo ORM con sus patas y su contraparte cargadas.
    @return @ref valorizador.schemas.operaciones.OperacionSalida.
    """
    patas = [
        {c: getattr(p, c) for c in _COLUMNAS_PATA if getattr(p, c) is not None} for p in operacion.patas
    ]
    return OperacionSalida.model_validate(
        {
            "deal_number": operacion.deal_number,
            "producto": operacion.producto,
            "rut_contraparte": operacion.rut_contraparte,
            "contraparte": operacion.contraparte.nombre if operacion.contraparte else None,
            "modalidad_liquidacion": operacion.modalidad_liquidacion,
            "grupo_calce": operacion.grupo_calce,
            "fecha_negociacion": operacion.fecha_negociacion,
            "patas": patas,
            "estado": operacion.estado,
            "version": operacion.version,
            "fecha_vencimiento": max(p.fecha_pago or p.fecha_fin for p in operacion.patas),
            "creado_en": operacion.creado_en,
            "actualizado_en": operacion.actualizado_en,
        }
    )


def _consulta():
    """!
    @brief Consulta base de operaciones, que carga en la misma lectura sus patas y su contraparte.
    @return Sentencia `select` de SQLAlchemy.
    """
    return select(modelos.Operacion).options(
        selectinload(modelos.Operacion.patas), selectinload(modelos.Operacion.contraparte)
    )


def _validar_contraparte(db: Session, rut: str | None) -> None:
    """!
    @brief Verifica que el RUT exista en el maestro.
    @param db Sesión.
    @param rut RUT normalizado, o nada.
    @throws DatoInvalido Si el RUT no está registrado.
    """
    if rut is not None and db.get(modelos.Contraparte, rut) is None:
        raise DatoInvalido(f"No existe la contraparte con RUT {rut}; regístrela antes en /contrapartes")


def obtener(db: Session, deal_number: str) -> modelos.Operacion:
    """!
    @brief Lee una operación por folio.
    @param db Sesión.
    @param deal_number Folio.
    @return Modelo ORM.
    @throws OperacionNoEncontrada Si no existe.
    """
    operacion = db.scalars(_consulta().where(modelos.Operacion.deal_number == deal_number)).first()
    if operacion is None:
        raise OperacionNoEncontrada(f"No existe la operación {deal_number}")
    return operacion


def listar(
    db: Session, producto: Producto | None, estado: Estado | None, limite: int, desde: int
) -> list[modelos.Operacion]:
    """!
    @brief Página de operaciones ordenadas por folio.
    @param db Sesión.
    @param producto Filtro opcional.
    @param estado Filtro opcional.
    @param limite Tamaño de la página.
    @param desde Operaciones a saltar.
    @return Modelos ORM.
    """
    consulta = _consulta().order_by(modelos.Operacion.deal_number).limit(limite).offset(desde)
    if producto:
        consulta = consulta.where(modelos.Operacion.producto == producto.value)
    if estado:
        consulta = consulta.where(modelos.Operacion.estado == estado.value)
    return list(db.scalars(consulta))


def listar_todas(db: Session, producto: Producto | None, estado: Estado | None) -> list[modelos.Operacion]:
    """!
    @brief Todas las operaciones que cumplen los filtros, sin paginar. La usa el cálculo de cartera.
    @param db Sesión.
    @param producto Filtro opcional.
    @param estado Filtro opcional.
    @return Modelos ORM ordenados por folio.
    """
    consulta = _consulta().order_by(modelos.Operacion.deal_number)
    if producto:
        consulta = consulta.where(modelos.Operacion.producto == producto.value)
    if estado:
        consulta = consulta.where(modelos.Operacion.estado == estado.value)
    return list(db.scalars(consulta))


def crear(db: Session, entrada: OperacionEntrada) -> modelos.Operacion:
    """!
    @brief Inserta una operación nueva con sus patas, en versión 1 y estado VIGENTE.
    @param db Sesión.
    @param entrada Operación validada.
    @return Modelo ORM creado.
    @throws OperacionDuplicada Si el folio ya existe.
    @throws DatoInvalido Si la contraparte no está registrada.
    """
    existe = db.scalar(select(modelos.Operacion.id).where(modelos.Operacion.deal_number == entrada.deal_number))
    if existe is not None:
        raise OperacionDuplicada(f"Ya existe la operación {entrada.deal_number}")
    _validar_contraparte(db, entrada.rut_contraparte)
    operacion = modelos.Operacion(
        deal_number=entrada.deal_number,
        producto=entrada.producto.value,
        rut_contraparte=entrada.rut_contraparte,
        modalidad_liquidacion=entrada.modalidad_liquidacion.value,
        grupo_calce=entrada.grupo_calce,
        fecha_negociacion=entrada.fecha_negociacion,
        estado=Estado.VIGENTE.value,
        version=1,
        patas=[_pata_a_modelo(p) for p in entrada.patas],
    )
    db.add(operacion)
    db.flush()
    db.refresh(operacion)
    return operacion


def modificar(db: Session, deal_number: str, cambios: OperacionModificacion) -> modelos.Operacion:
    """!
    @brief Aplica los cambios, guarda la versión anterior en el historial y sube la versión.

    Si se envían patas, se validan contra el producto y reemplazan a las dos anteriores. La
    modalidad se valida contra las patas que quedarán, sean las nuevas o las actuales.
    @param db Sesión.
    @param deal_number Folio.
    @param cambios Campos a cambiar; sólo se consideran los enviados.
    @return Modelo ORM modificado.
    @throws DatoInvalido Si no se envía ningún campo, uno obligatorio viene nulo o las patas no son válidas.
    """
    operacion = obtener(db, deal_number)
    enviados = cambios.model_fields_set
    if not enviados:
        raise DatoInvalido("La modificación no trae ningún campo")

    anterior = a_esquema(operacion)
    if "patas" in enviados:
        if cambios.patas is None:
            raise DatoInvalido("patas no puede ser nulo")
        try:
            validar_estructura(Producto(operacion.producto), cambios.patas)
        except ValueError as error:
            raise DatoInvalido(str(error)) from error
    if "rut_contraparte" in enviados:
        _validar_contraparte(db, cambios.rut_contraparte)
    if "fecha_negociacion" in enviados and cambios.fecha_negociacion is None:
        raise DatoInvalido("fecha_negociacion no puede ser nula")
    if "estado" in enviados and cambios.estado is None:
        raise DatoInvalido("estado no puede ser nulo")
    if "modalidad_liquidacion" in enviados and cambios.modalidad_liquidacion is None:
        raise DatoInvalido("modalidad_liquidacion no puede ser nula")
    try:  # la modalidad se valida contra las patas que quedarán, sean las nuevas o las actuales
        validar_modalidad(
            cambios.modalidad_liquidacion if "modalidad_liquidacion" in enviados else anterior.modalidad_liquidacion,
            cambios.patas if "patas" in enviados else anterior.patas,
        )
    except ValueError as error:
        raise DatoInvalido(str(error)) from error

    db.add(
        modelos.OperacionHistorial(
            operacion_id=operacion.id, version=operacion.version, datos=anterior.model_dump(mode="json")
        )
    )

    if "rut_contraparte" in enviados:
        operacion.rut_contraparte = cambios.rut_contraparte
    if "fecha_negociacion" in enviados:
        operacion.fecha_negociacion = cambios.fecha_negociacion
    if "estado" in enviados:
        operacion.estado = cambios.estado.value
    if "modalidad_liquidacion" in enviados:
        operacion.modalidad_liquidacion = cambios.modalidad_liquidacion.value
    if "grupo_calce" in enviados:
        operacion.grupo_calce = cambios.grupo_calce
    if "patas" in enviados:
        operacion.patas.clear()
        db.flush()  # borra las patas anteriores antes de insertar las nuevas
        operacion.patas.extend(_pata_a_modelo(p) for p in cambios.patas)
    operacion.version += 1

    db.flush()
    db.refresh(operacion)
    return operacion


def historial(db: Session, deal_number: str) -> list[modelos.OperacionHistorial]:
    """!
    @brief Versiones anteriores de una operación.
    @param db Sesión.
    @param deal_number Folio.
    @return Filas de historial ordenadas por versión.
    """
    operacion = obtener(db, deal_number)
    return list(
        db.scalars(
            select(modelos.OperacionHistorial)
            .where(modelos.OperacionHistorial.operacion_id == operacion.id)
            .order_by(modelos.OperacionHistorial.version)
        )
    )
