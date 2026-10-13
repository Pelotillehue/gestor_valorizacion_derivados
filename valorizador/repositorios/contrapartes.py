"""!
@package valorizador.repositorios.contrapartes
@brief Lectura y escritura del maestro de contrapartes (tabla `contraparte`).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from valorizador.db import modelos
from valorizador.errores import ContraparteDuplicada, ContraparteNoEncontrada, DatoInvalido
from valorizador.schemas.contrapartes import ContraparteEntrada, ContraparteModificacion


def obtener(db: Session, rut: str) -> modelos.Contraparte:
    """!
    @brief Lee una contraparte por RUT.
    @param db Sesión.
    @param rut RUT normalizado.
    @return El modelo ORM.
    @throws ContraparteNoEncontrada Si no existe.
    """
    contraparte = db.get(modelos.Contraparte, rut)
    if contraparte is None:
        raise ContraparteNoEncontrada(f"No existe la contraparte con RUT {rut}")
    return contraparte


def listar(db: Session) -> list[modelos.Contraparte]:
    """!
    @brief Todas las contrapartes, ordenadas por nombre.
    @param db Sesión.
    @return Lista de modelos ORM.
    """
    return list(db.scalars(select(modelos.Contraparte).order_by(modelos.Contraparte.nombre)))


def _nombre_libre(db: Session, nombre: str, rut: str) -> None:
    """!
    @brief Verifica que el nombre no esté asignado a otro RUT.
    @param db Sesión.
    @param nombre Nombre propuesto.
    @param rut RUT de la contraparte que lo usará.
    @throws ContraparteDuplicada Si otro RUT ya tiene ese nombre.
    """
    otro = db.scalar(select(modelos.Contraparte.rut).where(modelos.Contraparte.nombre == nombre))
    if otro is not None and otro != rut:
        raise ContraparteDuplicada(f"El nombre {nombre} ya está asignado al RUT {otro}")


def crear(db: Session, entrada: ContraparteEntrada) -> modelos.Contraparte:
    """!
    @brief Inserta una contraparte nueva.
    @param db Sesión.
    @param entrada Datos validados.
    @return El modelo ORM creado.
    @throws ContraparteDuplicada Si el RUT o el nombre ya existen.
    """
    if db.get(modelos.Contraparte, entrada.rut) is not None:
        raise ContraparteDuplicada(f"Ya existe la contraparte con RUT {entrada.rut}")
    _nombre_libre(db, entrada.nombre, entrada.rut)
    contraparte = modelos.Contraparte(**entrada.model_dump())
    db.add(contraparte)
    db.flush()
    db.refresh(contraparte)
    return contraparte


def modificar(db: Session, rut: str, cambios: ContraparteModificacion) -> modelos.Contraparte:
    """!
    @brief Aplica los cambios enviados a una contraparte.
    @param db Sesión.
    @param rut RUT normalizado.
    @param cambios Campos a cambiar; sólo se consideran los enviados.
    @return El modelo ORM modificado.
    @throws DatoInvalido Si no se envía ningún campo o uno viene nulo.
    """
    contraparte = obtener(db, rut)
    enviados = cambios.model_fields_set
    if not enviados:
        raise DatoInvalido("La modificación no trae ningún campo")
    for campo in enviados:
        valor = getattr(cambios, campo)
        if valor is None:
            raise DatoInvalido(f"{campo} no puede ser nulo")
        if campo == "nombre":
            _nombre_libre(db, valor, rut)
        setattr(contraparte, campo, valor)
    db.flush()
    db.refresh(contraparte)
    return contraparte
