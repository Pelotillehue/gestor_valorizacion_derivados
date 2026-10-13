"""!
@package valorizador.api.contrapartes
@brief Endpoints del maestro de contrapartes: RUT, nombre, línea y MTA.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from valorizador.db.base import obtener_sesion
from valorizador.errores import DatoInvalido
from valorizador.repositorios import contrapartes as repo
from valorizador.rut import normalizar
from valorizador.schemas.contrapartes import ContraparteEntrada, ContraparteModificacion, ContraparteSalida

## Router montado en `/contrapartes`.
router = APIRouter(prefix="/contrapartes", tags=["Contrapartes"])

## Sesión de base de datos, inyectada por FastAPI con @ref valorizador.db.base.obtener_sesion.
Sesion = Annotated[Session, Depends(obtener_sesion)]
## RUT recibido en la ruta, con o sin puntos.
RutRuta = Annotated[str, Path(description="RUT con o sin puntos, por ejemplo 76123456-0")]


def _rut(rut: str) -> str:
    """!
    @brief Normaliza un RUT recibido en la ruta.
    @param rut RUT con o sin puntos.
    @return RUT normalizado.
    @throws DatoInvalido Si el RUT no es válido (HTTP 422).
    """
    try:
        return normalizar(rut)
    except ValueError as error:
        raise DatoInvalido(str(error)) from error


@router.post("", response_model=ContraparteSalida, status_code=status.HTTP_201_CREATED, summary="Alta de contraparte")
def crear(entrada: ContraparteEntrada, db: Sesion):
    """!
    @brief `POST /contrapartes`: alta de una contraparte.
    @param entrada Datos de la contraparte.
    @param db Sesión de base de datos.
    @return La contraparte creada.
    @throws ContraparteDuplicada Si ya existe el RUT o el nombre (HTTP 409).
    """
    return repo.crear(db, entrada)


@router.get("", response_model=list[ContraparteSalida], summary="Lista de contrapartes")
def listar(db: Sesion):
    """!
    @brief `GET /contrapartes`: todas las contrapartes, ordenadas por nombre.
    @param db Sesión de base de datos.
    @return Lista de contrapartes.
    """
    return repo.listar(db)


@router.get("/{rut}", response_model=ContraparteSalida, summary="Datos de una contraparte")
def obtener(rut: RutRuta, db: Sesion):
    """!
    @brief `GET /contrapartes/{rut}`: datos de una contraparte.
    @param rut RUT con o sin puntos.
    @param db Sesión de base de datos.
    @return La contraparte.
    @throws ContraparteNoEncontrada Si no existe (HTTP 404).
    """
    return repo.obtener(db, _rut(rut))


@router.patch("/{rut}", response_model=ContraparteSalida, summary="Modifica nombre, línea o MTA")
def modificar(rut: RutRuta, cambios: ContraparteModificacion, db: Sesion):
    """!
    @brief `PATCH /contrapartes/{rut}`: modifica nombre, línea o MTA.
    @param rut RUT con o sin puntos.
    @param cambios Campos a cambiar.
    @param db Sesión de base de datos.
    @return La contraparte modificada.
    """
    return repo.modificar(db, _rut(rut), cambios)
