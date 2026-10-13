"""!
@package valorizador.repositorios.mercado
@brief Lectura y escritura de datos de mercado, y armado del escenario de una fecha.

Las funciones `guardar_*` usan `INSERT ... ON CONFLICT` de PostgreSQL para que una carga
repetida reemplace los valores en vez de duplicarlos.
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from valorizador.db import modelos
from valorizador.enums import FactorCapitalizacion, FraccionAnio
from valorizador.errores import DatoMercadoFaltante
from valorizador.schemas.mercado import CurvaCarga, FeriadoCarga, FxCarga, IndiceCarga
from valorizador.schemas.operaciones import OperacionEntrada
from valorizador.valorizacion.escenario import CurvaDatos, EscenarioMercado

## Días antes del inicio de una pata flotante desde los que se leen valores del índice, para alcanzar el valor inicial del primer cupón cuando su fecha se ajusta.
DIAS_HOLGURA_INDICE = 10


# ------------------------------------------------------------------------------ carga


def guardar_fx(db: Session, carga: FxCarga) -> int:
    """!
    @brief Guarda los tipos de cambio de una fecha; un par existente se actualiza.
    @param db Sesión.
    @param carga Fecha y pares.
    @return Cantidad de pares.
    """
    filas = [{"fecha": carga.fecha, "par": v.par, "valor": v.valor} for v in carga.valores]
    sentencia = insert(modelos.TipoCambio).values(filas)
    db.execute(
        sentencia.on_conflict_do_update(index_elements=["fecha", "par"], set_={"valor": sentencia.excluded.valor})
    )
    return len(filas)


def guardar_curva(db: Session, carga: CurvaCarga) -> int:
    """!
    @brief Reemplaza la curva completa de esa fecha y código, con sus vértices.
    @param db Sesión.
    @param carga Curva validada.
    @return Cantidad de vértices.
    """
    anterior = db.scalars(
        select(modelos.Curva).where(modelos.Curva.fecha == carga.fecha, modelos.Curva.codigo == carga.codigo)
    ).first()
    if anterior is not None:
        db.delete(anterior)
        db.flush()
    db.add(
        modelos.Curva(
            fecha=carga.fecha,
            codigo=carga.codigo,
            fraccion_anio=carga.fraccion_anio.value,
            factor_capitalizacion=carga.factor_capitalizacion.value,
            vertices=[
                modelos.CurvaVertice(codigo=carga.codigo, plazo_dias=v.plazo_dias, tasa=v.tasa)
                for v in carga.vertices
            ],
        )
    )
    db.flush()
    return len(carga.vertices)


def guardar_valores_indice(db: Session, carga: IndiceCarga) -> int:
    """!
    @brief Guarda valores de un índice; una fecha existente se actualiza.
    @param db Sesión.
    @param carga Índice y valores.
    @return Cantidad de valores.
    """
    filas = [{"indice": carga.indice, "fecha": v.fecha, "valor": v.valor} for v in carga.valores]
    sentencia = insert(modelos.ValorIndice).values(filas)
    db.execute(
        sentencia.on_conflict_do_update(index_elements=["indice", "fecha"], set_={"valor": sentencia.excluded.valor})
    )
    return len(filas)


def guardar_feriados(db: Session, carga: FeriadoCarga) -> int:
    """!
    @brief Agrega feriados a un calendario; los que ya existían se ignoran.
    @param db Sesión.
    @param carga Calendario y fechas.
    @return Cantidad de fechas distintas recibidas.
    """
    filas = [{"calendario": carga.calendario, "fecha": f} for f in sorted(set(carga.fechas))]
    db.execute(insert(modelos.Feriado).values(filas).on_conflict_do_nothing())
    return len(filas)


# --------------------------------------------------------------------------- consulta


def leer_fx(db: Session, fecha: date) -> dict[str, float]:
    """!
    @brief Todos los pares de una fecha.
    @param db Sesión.
    @param fecha Fecha.
    @return Diccionario par → valor.
    """
    filas = db.execute(
        select(modelos.TipoCambio.par, modelos.TipoCambio.valor)
        .where(modelos.TipoCambio.fecha == fecha)
        .order_by(modelos.TipoCambio.par)
    )
    return {par: valor for par, valor in filas}


def leer_fx_hasta(db: Session, fecha: date) -> tuple[date | None, dict[str, float]]:
    """!
    @brief Tipos de cambio del último día con datos, en la fecha o antes.

    Lo usa el P&L realizado, que liquida cada operación con el spot de su fecha de pago: si ese
    día no tiene publicación (fin de semana o feriado) se usa la anterior.
    @param db Sesión.
    @param fecha Fecha buscada.
    @return Tupla (fecha de los datos, diccionario par → valor); (nada, vacío) si no hay datos.
    """
    dia = db.scalar(select(func.max(modelos.TipoCambio.fecha)).where(modelos.TipoCambio.fecha <= fecha))
    return (dia, leer_fx(db, dia)) if dia else (None, {})


def leer_serie_fx(db: Session, par: str, desde: date | None, hasta: date | None) -> dict[date, float]:
    """!
    @brief Historia de un par.
    @param db Sesión.
    @param par Par.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor ordenado por fecha.
    """
    consulta = select(modelos.TipoCambio.fecha, modelos.TipoCambio.valor).where(modelos.TipoCambio.par == par)
    if desde:
        consulta = consulta.where(modelos.TipoCambio.fecha >= desde)
    if hasta:
        consulta = consulta.where(modelos.TipoCambio.fecha <= hasta)
    return {fecha: valor for fecha, valor in db.execute(consulta.order_by(modelos.TipoCambio.fecha))}


def leer_historia_curva(db: Session, codigo: str, desde: date | None, hasta: date | None) -> list[modelos.Curva]:
    """!
    @brief Todas las fechas de una curva en el rango, cada una con sus vértices.
    @param db Sesión.
    @param codigo Código de la curva.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Curvas ORM ordenadas por fecha.
    """
    consulta = (
        select(modelos.Curva)
        .options(selectinload(modelos.Curva.vertices))
        .where(modelos.Curva.codigo == codigo)
        .order_by(modelos.Curva.fecha)
    )
    if desde:
        consulta = consulta.where(modelos.Curva.fecha >= desde)
    if hasta:
        consulta = consulta.where(modelos.Curva.fecha <= hasta)
    return list(db.scalars(consulta))


def resumen_mercado(db: Session) -> dict[str, list[dict]]:
    """!
    @brief Series guardadas de cada tipo, con su rango de fechas y cantidad de fechas.
    @param db Sesión.
    @return Diccionario con las listas `fx`, `curvas` e `indices`.
    """

    def series(nombre, fecha) -> list[dict]:
        """!
        @brief Agrupa una tabla por nombre de serie.
        @param nombre Columna con el nombre de la serie.
        @param fecha Columna de fecha.
        @return Lista de diccionarios nombre, desde, hasta y fechas.
        """
        filas = db.execute(
            select(nombre, func.min(fecha), func.max(fecha), func.count(func.distinct(fecha))).group_by(nombre).order_by(nombre)
        )
        return [{"nombre": n, "desde": d, "hasta": h, "fechas": c} for n, d, h, c in filas]

    return {
        "fx": series(modelos.TipoCambio.par, modelos.TipoCambio.fecha),
        "curvas": series(modelos.Curva.codigo, modelos.Curva.fecha),
        "indices": series(modelos.ValorIndice.indice, modelos.ValorIndice.fecha),
    }


def leer_curva(db: Session, fecha: date, codigo: str) -> modelos.Curva:
    """!
    @brief Una curva en una fecha, con sus vértices.
    @param db Sesión.
    @param fecha Fecha.
    @param codigo Código de la curva.
    @return Curva ORM.
    @throws DatoMercadoFaltante Si no existe esa curva en esa fecha.
    """
    curva = db.scalars(
        select(modelos.Curva)
        .options(selectinload(modelos.Curva.vertices))
        .where(modelos.Curva.fecha == fecha, modelos.Curva.codigo == codigo)
    ).first()
    if curva is None:
        raise DatoMercadoFaltante(f"No hay curva {codigo} para la fecha {fecha.isoformat()}")
    return curva


def leer_valores_indice(db: Session, indice: str, desde: date | None, hasta: date | None) -> dict[date, float]:
    """!
    @brief Valores de un índice en un rango.
    @param db Sesión.
    @param indice Nombre del índice.
    @param desde Primera fecha, opcional.
    @param hasta Última fecha, opcional.
    @return Diccionario fecha → valor ordenado por fecha.
    """
    consulta = select(modelos.ValorIndice.fecha, modelos.ValorIndice.valor).where(modelos.ValorIndice.indice == indice)
    if desde:
        consulta = consulta.where(modelos.ValorIndice.fecha >= desde)
    if hasta:
        consulta = consulta.where(modelos.ValorIndice.fecha <= hasta)
    return {fecha: valor for fecha, valor in db.execute(consulta.order_by(modelos.ValorIndice.fecha))}


def leer_feriados(db: Session, calendarios: set[str]) -> dict[str, tuple[date, ...]]:
    """!
    @brief Feriados de varios calendarios.
    @param db Sesión.
    @param calendarios Códigos de calendario.
    @return Diccionario calendario → tupla de fechas; un calendario sin feriados queda vacío.
    """
    feriados: dict[str, list[date]] = {c: [] for c in calendarios}
    if calendarios:
        filas = db.execute(
            select(modelos.Feriado.calendario, modelos.Feriado.fecha)
            .where(modelos.Feriado.calendario.in_(calendarios))
            .order_by(modelos.Feriado.fecha)
        )
        for calendario, fecha in filas:
            feriados[calendario].append(fecha)
    return {c: tuple(f) for c, f in feriados.items()}


def calendarios_de(operacion: OperacionEntrada) -> set[str]:
    """!
    @brief Calendarios que usan las patas con cupones de una operación.
    @param operacion Operación.
    @return Conjunto de códigos de calendario.
    """
    return {p.calendario for p in operacion.patas if hasattr(p, "calendario")}


# -------------------------------------------------------------------------- escenario


def cargar_escenario(db: Session, fecha: date, operacion: OperacionEntrada) -> EscenarioMercado:
    """!
    @brief Escenario con los datos de la fecha de proceso que necesita una operación.

    Curvas y tipos de cambio deben existir exactamente para esa fecha: no se arrastran valores de
    días anteriores.
    @param db Sesión.
    @param fecha Fecha de proceso.
    @param operacion Operación a valorizar.
    @return @ref valorizador.valorizacion.escenario.EscenarioMercado.
    """
    return cargar_escenario_cartera(db, fecha, [operacion])


def cargar_escenario_cartera(db: Session, fecha: date, operaciones: list[OperacionEntrada]) -> EscenarioMercado:
    """!
    @brief Un solo escenario con todo lo que necesitan varias operaciones, leído una vez.

    Lee las curvas que usan las patas (de descuento y de proyección), todos los tipos de cambio de
    la fecha, los valores de cada índice desde el inicio de la pata más antigua y los feriados de
    los calendarios usados. Una curva que no existe en la fecha queda fuera del escenario: el error
    aparece al valorizar cada operación que la usa, sin impedir valorizar las demás.
    @param db Sesión.
    @param fecha Fecha de proceso.
    @param operaciones Operaciones a valorizar.
    @return @ref valorizador.valorizacion.escenario.EscenarioMercado.
    """
    curvas = {}
    for codigo in sorted({c for operacion in operaciones for pata in operacion.patas for c in pata.curvas}):
        try:
            curva = leer_curva(db, fecha, codigo)
        except DatoMercadoFaltante:
            continue
        curvas[codigo] = CurvaDatos(
            codigo=codigo,
            plazos=tuple(v.plazo_dias for v in curva.vertices),
            tasas=tuple(v.tasa for v in curva.vertices),
            fraccion_anio=FraccionAnio(curva.fraccion_anio),
            factor_capitalizacion=FactorCapitalizacion(curva.factor_capitalizacion),
        )

    desde_por_indice: dict[str, date] = {}
    for operacion in operaciones:
        for pata in operacion.patas:
            if pata.tipo == "INDICE_OVERNIGHT":
                desde = pata.fecha_inicio - timedelta(days=DIAS_HOLGURA_INDICE)
                desde_por_indice[pata.indice] = min(desde, desde_por_indice.get(pata.indice, desde))
    indices = {indice: leer_valores_indice(db, indice, desde, fecha) for indice, desde in desde_por_indice.items()}

    calendarios = set().union(*(calendarios_de(o) for o in operaciones)) if operaciones else set()
    return EscenarioMercado(
        fecha=fecha,
        fx=leer_fx(db, fecha),
        curvas=curvas,
        indices=indices,
        feriados=leer_feriados(db, calendarios),
    )
