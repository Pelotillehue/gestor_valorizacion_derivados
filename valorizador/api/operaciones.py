"""!
@package valorizador.api.operaciones
@brief Endpoints de operaciones: alta, consulta, modificación, historial, vencimiento, MtM y sensibilidades.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from valorizador.config import configuracion
from valorizador.db.base import obtener_sesion
from valorizador.enums import Estado, Moneda, Producto
from valorizador.errores import OperacionNoValorizable
from valorizador.repositorios import mercado as repo_mercado
from valorizador.repositorios import operaciones as repo
from valorizador.schemas.operaciones import (
    OperacionEntrada,
    OperacionModificacion,
    OperacionSalida,
    Vencimiento,
    VersionHistorica,
)
from valorizador.schemas.valorizacion import Sensibilidades, Valorizacion
from valorizador.valorizacion import motor

## Router montado en `/operaciones`.
router = APIRouter(prefix="/operaciones", tags=["Operaciones"])

## Sesión de base de datos, inyectada por FastAPI con @ref valorizador.db.base.obtener_sesion.
Sesion = Annotated[Session, Depends(obtener_sesion)]
## Fecha de proceso recibida como parámetro de consulta `fecha` (AAAA-MM-DD).
FechaProceso = Annotated[date, Query(description="Fecha de proceso")]
## Moneda del resultado, parámetro de consulta `moneda`. Si se omite, la configurada por defecto.
MonedaValorizacion = Annotated[
    Moneda | None, Query(description="Moneda del resultado. Si se omite, la configurada por defecto")
]


def _moneda(moneda: Moneda | None) -> str:
    """!
    @brief Moneda de valorización efectiva.
    @param moneda Moneda pedida, o nada.
    @return El código de la moneda pedida o el de la configuración.
    """
    return moneda.value if moneda else configuracion.moneda_valorizacion


def _valorizable(db: Session, deal_number: str) -> OperacionSalida:
    """!
    @brief Lee una operación y verifica que se pueda valorizar.
    @param db Sesión de base de datos.
    @param deal_number Folio.
    @return La operación en el esquema del motor.
    @throws OperacionNoEncontrada Si no existe.
    @throws OperacionNoValorizable Si no está vigente.
    """
    operacion = repo.a_esquema(repo.obtener(db, deal_number))
    if operacion.estado != Estado.VIGENTE:
        raise OperacionNoValorizable(f"La operación {deal_number} está {operacion.estado.value}")
    return operacion


@router.post("", response_model=OperacionSalida, status_code=status.HTTP_201_CREATED, summary="Alta de operación")
def crear(entrada: OperacionEntrada, db: Sesion):
    """!
    @brief `POST /operaciones`: alta de una operación.
    @param entrada Datos de la operación y sus dos patas.
    @param db Sesión de base de datos.
    @return La operación creada, en versión 1.
    @throws OperacionDuplicada Si el folio ya existe (HTTP 409).
    @throws DatoInvalido Si la contraparte no está registrada (HTTP 422).
    """
    return repo.a_esquema(repo.crear(db, entrada))


@router.get("", response_model=list[OperacionSalida], summary="Lista de operaciones")
def listar(
    db: Sesion,
    producto: Producto | None = None,
    estado: Estado | None = None,
    limite: Annotated[int, Query(ge=1, le=1000)] = 100,
    desde: Annotated[int, Query(ge=0)] = 0,
):
    """!
    @brief `GET /operaciones`: lista paginada de operaciones.
    @param db Sesión de base de datos.
    @param producto Filtro opcional por producto.
    @param estado Filtro opcional por estado.
    @param limite Máximo de operaciones por página (1 a 1000).
    @param desde Cantidad de operaciones a saltar.
    @return Operaciones ordenadas por folio.
    """
    return [repo.a_esquema(o) for o in repo.listar(db, producto, estado, limite, desde)]


@router.get("/{deal_number}", response_model=OperacionSalida, summary="Datos de una operación")
def obtener(deal_number: str, db: Sesion):
    """!
    @brief `GET /operaciones/{deal_number}`: datos de una operación.
    @param deal_number Folio.
    @param db Sesión de base de datos.
    @return La operación.
    @throws OperacionNoEncontrada Si no existe (HTTP 404).
    """
    return repo.a_esquema(repo.obtener(db, deal_number))


@router.patch("/{deal_number}", response_model=OperacionSalida, summary="Modificación de una operación")
def modificar(deal_number: str, cambios: OperacionModificacion, db: Sesion):
    """!
    @brief `PATCH /operaciones/{deal_number}`: modifica una operación.

    Guarda la versión anterior en el historial y sube la versión.
    @param deal_number Folio.
    @param cambios Campos a cambiar.
    @param db Sesión de base de datos.
    @return La operación modificada.
    """
    return repo.a_esquema(repo.modificar(db, deal_number, cambios))


@router.get("/{deal_number}/historial", response_model=list[VersionHistorica], summary="Versiones anteriores")
def historial(deal_number: str, db: Sesion):
    """!
    @brief `GET /operaciones/{deal_number}/historial`: versiones anteriores a cada modificación.
    @param deal_number Folio.
    @param db Sesión de base de datos.
    @return Versiones ordenadas.
    """
    return [
        VersionHistorica(version=h.version, reemplazado_en=h.reemplazado_en, datos=h.datos)
        for h in repo.historial(db, deal_number)
    ]


@router.get("/{deal_number}/vencimiento", response_model=Vencimiento, summary="Vencimiento de una operación")
def vencimiento(
    deal_number: str,
    db: Sesion,
    fecha: Annotated[date | None, Query(description="Si se envía, se informan los días hasta el último pago")] = None,
):
    """!
    @brief `GET /operaciones/{deal_number}/vencimiento`: vencimiento contractual y fecha del último pago.

    La fecha del último pago considera calendario, ajuste de fecha y lag de cada pata.
    @param deal_number Folio.
    @param db Sesión de base de datos.
    @param fecha Si se envía, se informan los días corridos hasta el último pago.
    @return @ref valorizador.schemas.operaciones.Vencimiento.
    """
    operacion = repo.a_esquema(repo.obtener(db, deal_number))
    feriados = repo_mercado.leer_feriados(db, repo_mercado.calendarios_de(operacion))
    ultimo_pago = motor.fecha_ultimo_pago(operacion, feriados)
    return Vencimiento(
        deal_number=deal_number,
        fecha_vencimiento_contractual=operacion.fecha_vencimiento,
        fecha_ultimo_pago=ultimo_pago,
        dias_al_ultimo_pago=(ultimo_pago - fecha).days if fecha else None,
    )


@router.get("/{deal_number}/mtm", response_model=Valorizacion, summary="MtM a una fecha de proceso")
def mtm(
    deal_number: str,
    db: Sesion,
    fecha: FechaProceso,
    moneda: MonedaValorizacion = None,
    detalle: Annotated[bool, Query(description="Incluir el detalle de flujos de cada pata")] = False,
):
    """!
    @brief `GET /operaciones/{deal_number}/mtm`: MtM de una operación a una fecha de proceso.
    @param deal_number Folio.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param moneda Moneda del resultado.
    @param detalle Si es verdadero, incluye el detalle de flujos de cada pata.
    @return @ref valorizador.schemas.valorizacion.Valorizacion.
    @throws DatoMercadoFaltante Si falta un dato de mercado de la fecha (HTTP 422).
    """
    operacion = _valorizable(db, deal_number)
    escenario = repo_mercado.cargar_escenario(db, fecha, operacion)
    return motor.valorizar(operacion, escenario, _moneda(moneda), detalle)


@router.get(
    "/{deal_number}/sensibilidades",
    response_model=Sensibilidades,
    summary="Sensibilidad del MtM a cada factor de mercado",
)
def sensibilidades(
    deal_number: str,
    db: Sesion,
    fecha: FechaProceso,
    moneda: MonedaValorizacion = None,
    desplazamiento_ir: Annotated[float, Query(description="Absoluto, en tanto por uno")] = motor.PUNTO_BASE,
    desplazamiento_fx: Annotated[float, Query(description="Relativo, en tanto por uno")] = motor.UNO_POR_CIENTO,
):
    """!
    @brief `GET /operaciones/{deal_number}/sensibilidades`: cambio del MtM al mover cada factor de mercado.

    Mueve por separado cada tipo de cambio (desplazamiento relativo) y cada vértice de cada curva
    (desplazamiento absoluto) y revaloriza. Es la base del VaR por factor.
    @param deal_number Folio.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param moneda Moneda del resultado.
    @param desplazamiento_ir Desplazamiento absoluto de las tasas, en tanto por uno (por defecto 1 pb).
    @param desplazamiento_fx Desplazamiento relativo de los tipos de cambio (por defecto 1%).
    @return @ref valorizador.schemas.valorizacion.Sensibilidades.
    """
    operacion = _valorizable(db, deal_number)
    escenario = repo_mercado.cargar_escenario(db, fecha, operacion)
    return motor.sensibilidades(operacion, escenario, _moneda(moneda), desplazamiento_ir, desplazamiento_fx)
