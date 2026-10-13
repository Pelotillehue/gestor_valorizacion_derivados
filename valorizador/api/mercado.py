"""!
@package valorizador.api.mercado
@brief Endpoints de datos de mercado: tipos de cambio, curvas, valores de índices y feriados.

Las cargas reemplazan los datos que ya existían para la misma fecha y serie, de modo que se
pueden repetir sin duplicar registros.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from valorizador.db.base import obtener_sesion
from valorizador.repositorios import mercado as repo
from valorizador.schemas.mercado import (
    CurvaCarga,
    FeriadoCarga,
    FxCarga,
    IndiceCarga,
    ResultadoCarga,
    ResumenMercado,
    Vertice,
)

## Router montado en `/mercado`.
router = APIRouter(prefix="/mercado", tags=["Mercado"])

## Sesión de base de datos, inyectada por FastAPI con @ref valorizador.db.base.obtener_sesion.
Sesion = Annotated[Session, Depends(obtener_sesion)]


@router.get("/resumen", response_model=ResumenMercado, summary="Series de mercado guardadas y sus rangos de fechas")
def resumen(db: Sesion):
    """!
    @brief `GET /mercado/resumen`: series guardadas de cada tipo, con su rango de fechas.
    @param db Sesión de base de datos.
    @return @ref valorizador.schemas.mercado.ResumenMercado.
    """
    return repo.resumen_mercado(db)


@router.post("/fx", response_model=ResultadoCarga, status_code=status.HTTP_201_CREATED, summary="Carga tipos de cambio")
def cargar_fx(carga: FxCarga, db: Sesion):
    """!
    @brief `POST /mercado/fx`: guarda los tipos de cambio de una fecha.
    @param carga Fecha y pares.
    @param db Sesión de base de datos.
    @return Cantidad de pares guardados.
    """
    return ResultadoCarga(registros=repo.guardar_fx(db, carga))


@router.get("/fx", response_model=dict[str, float], summary="Tipos de cambio de una fecha")
def consultar_fx(fecha: date, db: Sesion):
    """!
    @brief `GET /mercado/fx?fecha=`: todos los pares de una fecha.
    @param fecha Fecha consultada.
    @param db Sesión de base de datos.
    @return Diccionario par → valor.
    """
    return repo.leer_fx(db, fecha)


@router.get("/fx/{par}", response_model=dict[date, float], summary="Historia de un tipo de cambio")
def consultar_serie_fx(
    par: str,
    db: Sesion,
    desde: Annotated[date | None, Query()] = None,
    hasta: Annotated[date | None, Query()] = None,
):
    """!
    @brief `GET /mercado/fx/{par}`: historia de un par.
    @param par Par, por ejemplo `USDCLP`.
    @param db Sesión de base de datos.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor.
    """
    return repo.leer_serie_fx(db, par, desde, hasta)


@router.post("/curvas", response_model=ResultadoCarga, status_code=status.HTTP_201_CREATED, summary="Carga una curva cero")
def cargar_curva(carga: CurvaCarga, db: Sesion):
    """!
    @brief `POST /mercado/curvas`: guarda una curva cero completa, reemplazando la de la misma fecha y código.
    @param carga Curva con sus vértices.
    @param db Sesión de base de datos.
    @return Cantidad de vértices guardados.
    """
    return ResultadoCarga(registros=repo.guardar_curva(db, carga))


@router.get("/curvas/{codigo}", response_model=CurvaCarga, summary="Curva de una fecha")
def consultar_curva(codigo: str, fecha: date, db: Sesion):
    """!
    @brief `GET /mercado/curvas/{codigo}?fecha=`: una curva en una fecha.
    @param codigo Código de la curva.
    @param fecha Fecha consultada.
    @param db Sesión de base de datos.
    @return La curva con sus vértices.
    @throws DatoMercadoFaltante Si no existe (HTTP 422).
    """
    curva = repo.leer_curva(db, fecha, codigo)
    return CurvaCarga(
        fecha=curva.fecha,
        codigo=curva.codigo,
        fraccion_anio=curva.fraccion_anio,
        factor_capitalizacion=curva.factor_capitalizacion,
        vertices=[Vertice(plazo_dias=v.plazo_dias, tasa=v.tasa) for v in curva.vertices],
    )


@router.get("/curvas/{codigo}/historia", response_model=list[CurvaCarga], summary="Historia de una curva")
def consultar_historia_curva(
    codigo: str,
    db: Sesion,
    desde: Annotated[date | None, Query()] = None,
    hasta: Annotated[date | None, Query()] = None,
):
    """!
    @brief `GET /mercado/curvas/{codigo}/historia`: la curva en cada fecha del rango, con sus vértices.

    Los plazos pueden variar entre fechas.
    @param codigo Código de la curva.
    @param db Sesión de base de datos.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Lista de curvas ordenadas por fecha.
    """
    return [
        CurvaCarga(
            fecha=c.fecha,
            codigo=c.codigo,
            fraccion_anio=c.fraccion_anio,
            factor_capitalizacion=c.factor_capitalizacion,
            vertices=[Vertice(plazo_dias=v.plazo_dias, tasa=v.tasa) for v in c.vertices],
        )
        for c in repo.leer_historia_curva(db, codigo, desde, hasta)
    ]


@router.post("/indices", response_model=ResultadoCarga, status_code=status.HTTP_201_CREATED, summary="Carga valores de un índice")
def cargar_valores_indice(carga: IndiceCarga, db: Sesion):
    """!
    @brief `POST /mercado/indices`: guarda valores de un índice, reemplazando los de las mismas fechas.
    @param carga Índice y valores.
    @param db Sesión de base de datos.
    @return Cantidad de valores guardados.
    """
    return ResultadoCarga(registros=repo.guardar_valores_indice(db, carga))


@router.get("/indices/{indice}", response_model=dict[date, float], summary="Valores de un índice")
def consultar_valores_indice(
    indice: str,
    db: Sesion,
    desde: Annotated[date | None, Query()] = None,
    hasta: Annotated[date | None, Query()] = None,
):
    """!
    @brief `GET /mercado/indices/{indice}`: historia de un índice.
    @param indice Nombre del índice, por ejemplo `ICP`.
    @param db Sesión de base de datos.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor.
    """
    return repo.leer_valores_indice(db, indice, desde, hasta)


@router.post("/feriados", response_model=ResultadoCarga, status_code=status.HTTP_201_CREATED, summary="Carga feriados")
def cargar_feriados(carga: FeriadoCarga, db: Sesion):
    """!
    @brief `POST /mercado/feriados`: agrega feriados a un calendario; los repetidos se ignoran.
    @param carga Calendario y fechas.
    @param db Sesión de base de datos.
    @return Cantidad de fechas recibidas.
    """
    return ResultadoCarga(registros=repo.guardar_feriados(db, carga))


@router.get("/feriados/{calendario}", response_model=list[date], summary="Feriados de un calendario")
def consultar_feriados(calendario: str, db: Sesion):
    """!
    @brief `GET /mercado/feriados/{calendario}`: feriados de un calendario.
    @param calendario Código del calendario.
    @param db Sesión de base de datos.
    @return Fechas ordenadas.
    """
    return list(repo.leer_feriados(db, {calendario})[calendario])
