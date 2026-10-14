"""!
@package valorizador.api.cartera
@brief Endpoints de cálculos sobre toda la cartera vigente: MtM, vencimientos, flujos y garantías.

Todos leen el mercado de la fecha una sola vez (@ref valorizador.repositorios.mercado.cargar_escenario_cartera)
y valorizan operación por operación; una operación con error no detiene a las demás.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from valorizador.config import configuracion
from valorizador.db.base import obtener_sesion
from valorizador.enums import Estado, ModalidadLiquidacion, Moneda, Producto, RecPay
from valorizador.errores import ErrorValorizador
from valorizador.repositorios import contrapartes as repo_contrapartes
from valorizador.repositorios import mercado as repo_mercado
from valorizador.repositorios import operaciones as repo
from valorizador.schemas.cartera import (
    ForwardBasilea,
    ForwardsBasilea,
    PnlRealizadoCartera,
    PnlRealizadoOperacion,
    FlujoCaja,
    FlujosCartera,
    FlujoVencimiento,
    MtmCartera,
    MtmOperacion,
    TotalProducto,
    VencimientosCartera,
)
from valorizador.schemas.contrapartes import GarantiaContraparte, GarantiasCartera
from valorizador.schemas.operaciones import OperacionSalida
from valorizador.valorizacion import motor
from valorizador.valorizacion.constructores import construir_curva
from valorizador.valorizacion.escenario import EscenarioMercado

## Router montado en `/cartera`.
router = APIRouter(prefix="/cartera", tags=["Cartera"])

## Sesión de base de datos, inyectada por FastAPI con @ref valorizador.db.base.obtener_sesion.
Sesion = Annotated[Session, Depends(obtener_sesion)]
## Fecha de proceso recibida como parámetro de consulta `fecha` (AAAA-MM-DD).
FechaProceso = Annotated[date, Query(description="Fecha de proceso")]


def _vigentes(db: Session, producto: Producto | None, fecha: date) -> list[OperacionSalida]:
    """!
    @brief Operaciones vigentes a la fecha de proceso, convertidas al esquema que usa el motor.

    Una operación está vigente si no está anulada, ya se negoció (`fecha_negociacion` ≤ fecha)
    y aún no vence (`fecha_vencimiento` > fecha). La que vence en la fecha de proceso ya se
    liquidó y entra en el P&L realizado.
    @param db Sesión de base de datos.
    @param producto Si se indica, sólo las de ese producto.
    @param fecha Fecha de proceso.
    @return Lista de @ref valorizador.schemas.operaciones.OperacionSalida.
    """
    operaciones = [repo.a_esquema(o) for o in repo.listar_todas(db, producto, Estado.VIGENTE)]
    return [o for o in operaciones if o.fecha_negociacion <= fecha < o.fecha_vencimiento]


def _valorizar_vigentes(
    db: Session, fecha: date, producto: Producto | None, moneda_valorizacion: str
) -> list[MtmOperacion]:
    """!
    @brief MtM de cada operación vigente con un único escenario de mercado.

    Una operación que no se puede valorizar queda con MtM nulo y el motivo en `error`.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param producto Si se indica, sólo las de ese producto.
    @param moneda_valorizacion Moneda del MtM.
    @return Una @ref valorizador.schemas.cartera.MtmOperacion por operación vigente.
    """
    operaciones = _vigentes(db, producto, fecha)
    escenario = repo_mercado.cargar_escenario_cartera(db, fecha, operaciones)

    resultados = []
    for operacion in operaciones:
        mtm, error = None, None
        try:
            mtm = motor.valorizar(operacion, escenario, moneda_valorizacion).mtm
        except ErrorValorizador as e:
            error = str(e)
        except (RuntimeError, ValueError) as e:  # errores de qcfinancial
            error = f"Error de cálculo: {e}"
        resultados.append(
            MtmOperacion(
                deal_number=operacion.deal_number,
                producto=operacion.producto.value,
                rut_contraparte=operacion.rut_contraparte,
                contraparte=operacion.contraparte,
                modalidad_liquidacion=operacion.modalidad_liquidacion.value,
                grupo_calce=operacion.grupo_calce,
                fecha_vencimiento=operacion.fecha_vencimiento,
                mtm=mtm,
                error=error,
            )
        )
    return resultados


@router.get("/mtm", response_model=MtmCartera, summary="MtM de todas las operaciones vigentes")
def mtm_cartera(
    db: Sesion,
    fecha: FechaProceso,
    producto: Annotated[Producto | None, Query(description="Si se omite, todos los productos")] = None,
    moneda: Annotated[Moneda | None, Query(description="Moneda del resultado")] = None,
):
    """!
    @brief `GET /cartera/mtm`: MtM de todas las operaciones vigentes, con totales por producto.

    Una operación que no se puede valorizar, por ejemplo por falta del valor de un índice, queda con
    MtM nulo y el motivo en `error`; no detiene el cálculo de las demás.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param producto Filtro opcional por producto.
    @param moneda Moneda del resultado; por defecto la de la configuración.
    @return @ref valorizador.schemas.cartera.MtmCartera.
    """
    moneda_valorizacion = moneda.value if moneda else configuracion.moneda_valorizacion
    resultados = _valorizar_vigentes(db, fecha, producto, moneda_valorizacion)

    totales = []
    for prod in Producto:
        del_producto = [r for r in resultados if r.producto == prod.value]
        if not del_producto:
            continue
        valorizadas = [r.mtm for r in del_producto if r.mtm is not None]
        totales.append(
            TotalProducto(
                producto=prod.value,
                operaciones=len(del_producto),
                valorizadas=len(valorizadas),
                con_error=len(del_producto) - len(valorizadas),
                mtm=sum(valorizadas),
            )
        )

    return MtmCartera(
        fecha_proceso=fecha,
        moneda_valorizacion=moneda_valorizacion,
        mtm_total=sum(t.mtm for t in totales),
        totales=totales,
        operaciones=resultados,
    )


def _monto_al_vencimiento(pata) -> float:
    """!
    @brief Nocional que la pata intercambia al vencimiento, con signo.

    Una pata con cupones sólo intercambia nocional si `intercambia_nocional` es verdadero; los
    cupones no se incluyen.
    @param pata Pata de la operación.
    @return Nocional positivo si se recibe, negativo si se paga, o cero.
    """
    if pata.tipo != "SIMPLE" and not pata.intercambia_nocional:
        return 0.0
    return pata.nocional if pata.rec_pay == RecPay.RECIBE else -pata.nocional


@router.get(
    "/vencimientos",
    response_model=VencimientosCartera,
    summary="Montos que se intercambian al vencimiento de cada operación vigente",
)
def vencimientos_cartera(
    db: Sesion,
    fecha: FechaProceso,
    producto: Annotated[Producto | None, Query(description="Si se omite, todos los productos")] = None,
):
    """!
    @brief `GET /cartera/vencimientos`: nocionales que se intercambian al vencimiento de cada operación.

    Considera las operaciones vigentes que vencen después de la fecha.
    - Entrega física: un flujo por pata en su propia moneda, positivo si se recibe y negativo si se paga.
    - Compensación: un único flujo neto en CLP, convirtiendo cada pata al spot de la fecha de proceso.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param producto Filtro opcional por producto.
    @return @ref valorizador.schemas.cartera.VencimientosCartera.
    """
    escenario = repo_mercado.cargar_escenario_cartera(db, fecha, [])
    flujos, errores = [], {}
    for operacion in _vigentes(db, producto, fecha):
        if operacion.fecha_vencimiento <= fecha:
            continue
        comunes = dict(
            deal_number=operacion.deal_number,
            producto=operacion.producto.value,
            rut_contraparte=operacion.rut_contraparte,
            contraparte=operacion.contraparte,
            modalidad_liquidacion=operacion.modalidad_liquidacion.value,
            fecha_vencimiento=operacion.fecha_vencimiento,
        )
        patas = sorted(operacion.patas, key=lambda p: p.numero)
        if operacion.modalidad_liquidacion == ModalidadLiquidacion.ENTREGA_FISICA:
            for pata in patas:
                monto = _monto_al_vencimiento(pata)
                if monto:
                    flujos.append(
                        FlujoVencimiento(**comunes, sentido=pata.rec_pay.value, moneda=pata.moneda.value, monto=monto)
                    )
            continue
        try:
            neto = sum(_monto_al_vencimiento(p) * escenario.tipo_cambio(p.moneda.value, "CLP") for p in patas)
        except ErrorValorizador as e:
            errores[operacion.deal_number] = str(e)
            continue
        if abs(neto) > 1e-6:  # un swap de una moneda sin intercambio de nocional no tiene flujo
            flujos.append(FlujoVencimiento(**comunes, sentido="NETO", moneda="CLP", monto=neto))

    return VencimientosCartera(fecha_proceso=fecha, moneda_compensacion="CLP", flujos=flujos, errores=errores)


def _flujos_de_pata(pata) -> list[tuple[date, float, float, float]]:
    """!
    @brief Extrae los flujos del detalle que entrega QC Financial para una pata.

    En las patas con cupones el interés se calcula como monto descontado menos amortización, para
    no arrastrar el redondeo de la tasa equivalente que muestra QC Financial.
    @param pata @ref valorizador.schemas.valorizacion.ValorizacionPata con su detalle de flujos.
    @return Tuplas (fecha de pago, amortización, interés, flujo) en la moneda de la pata.
    """
    resultado = []
    for f in pata.flujos or []:
        fecha_pago = date.fromisoformat(str(f["fecha_pago"])[:10])
        if pata.tipo == "SIMPLE":
            resultado.append((fecha_pago, f["monto"], 0.0, f["monto"]))
            continue
        amortizacion = f["amortizacion"] if f.get("amort_es_flujo") else 0.0
        interes = f["monto_descontado"] - amortizacion  # sin el redondeo de la tasa equivalente
        resultado.append((fecha_pago, amortizacion, interes, f["monto_descontado"]))
    return resultado


@router.get(
    "/flujos",
    response_model=FlujosCartera,
    summary="Flujos de caja futuros de todas las operaciones vigentes, en CLP",
)
def flujos_cartera(
    db: Sesion,
    fecha: FechaProceso,
    producto: Annotated[Producto | None, Query(description="Si se omite, todos los productos")] = None,
):
    """!
    @brief `GET /cartera/flujos`: todos los flujos futuros de las operaciones vigentes, en su moneda y en CLP.

    Incluye cada flujo con fecha de pago posterior a la fecha de proceso: el monto de cada pata de
    un forward y, en los swaps, cada cupón y cada amortización. Los cupones flotantes se proyectan
    con la curva de proyección de la pata y los índices ya publicados. Cada flujo se convierte a
    CLP al spot de la fecha de proceso. Positivo lo que se recibe, negativo lo que se paga.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @param producto Filtro opcional por producto.
    @return @ref valorizador.schemas.cartera.FlujosCartera.
    """
    operaciones = _vigentes(db, producto, fecha)
    escenario = repo_mercado.cargar_escenario_cartera(db, fecha, operaciones)
    flujos, errores = [], {}
    for operacion in operaciones:
        try:
            resultado = motor.valorizar(operacion, escenario, "CLP", detalle=True)
        except ErrorValorizador as e:
            errores[operacion.deal_number] = str(e)
            continue
        except (RuntimeError, ValueError) as e:
            errores[operacion.deal_number] = f"Error de cálculo: {e}"
            continue
        for pata in resultado.patas:
            for fecha_pago, amortizacion, interes, flujo in _flujos_de_pata(pata):
                if fecha_pago <= fecha or abs(flujo) < 1e-9:
                    continue
                flujos.append(
                    FlujoCaja(
                        deal_number=operacion.deal_number,
                        producto=operacion.producto.value,
                        rut_contraparte=operacion.rut_contraparte,
                        contraparte=operacion.contraparte,
                        modalidad_liquidacion=operacion.modalidad_liquidacion.value,
                        grupo_calce=operacion.grupo_calce,
                        numero_pata=pata.numero,
                        rec_pay=pata.rec_pay,
                        moneda=pata.moneda,
                        fecha_pago=fecha_pago,
                        amortizacion=amortizacion,
                        interes=interes,
                        flujo=flujo,
                        tipo_cambio=pata.tipo_cambio,
                        flujo_clp=flujo * pata.tipo_cambio,
                    )
                )
    flujos.sort(key=lambda f: (f.fecha_pago, f.deal_number, f.numero_pata))
    return FlujosCartera(fecha_proceso=fecha, moneda="CLP", flujos=flujos, errores=errores)


def control_garantia(exposicion: float, monto_linea: float, mta: float) -> tuple[float, bool, float]:
    """!
    @brief Aplica la regla de llamado a garantías de una contraparte.

    Hay llamado siempre que la exposición a favor de la institución supera la línea. Se llama por
    el exceso, pero nunca por menos que el MTA, el monto mínimo a transferir.
    @param exposicion Suma del MtM en CLP de las operaciones con la contraparte.
    @param monto_linea Exposición aceptada sin garantías.
    @param mta Monto mínimo de transferencia.
    @return Tupla (exceso sobre la línea, hay llamado, monto a llamar).
    """
    exceso = max(exposicion - monto_linea, 0.0)
    llamado = exceso > 0
    return exceso, llamado, max(exceso, mta) if llamado else 0.0


@router.get(
    "/garantias",
    response_model=GarantiasCartera,
    summary="Exposición por contraparte contra su línea y llamado a constituir garantías",
)
def garantias_cartera(db: Sesion, fecha: FechaProceso):
    """!
    @brief `GET /cartera/garantias`: exposición de cada contraparte contra su línea y llamado a garantías.

    Para cada contraparte registrada suma el MtM en CLP de sus operaciones vigentes, positivo
    cuando la contraparte le debe a la institución, y aplica @ref valorizador.api.cartera.control_garantia. Las operaciones
    que no se pudieron valorizar no suman y se informan en `con_error`.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @return @ref valorizador.schemas.contrapartes.GarantiasCartera.
    """
    resultados = _valorizar_vigentes(db, fecha, None, "CLP")
    por_rut: dict[str, list[MtmOperacion]] = {}
    sin_contraparte = []
    for r in resultados:
        if r.rut_contraparte is None:
            sin_contraparte.append(r.deal_number)
        else:
            por_rut.setdefault(r.rut_contraparte, []).append(r)

    filas = []
    for contraparte in repo_contrapartes.listar(db):
        suyas = por_rut.get(contraparte.rut, [])
        exposicion = sum(r.mtm for r in suyas if r.mtm is not None)
        exceso, llamado, monto = control_garantia(exposicion, contraparte.monto_linea, contraparte.mta)
        filas.append(
            GarantiaContraparte(
                rut=contraparte.rut,
                nombre=contraparte.nombre,
                operaciones=len(suyas),
                con_error=sum(r.mtm is None for r in suyas),
                exposicion=exposicion,
                monto_linea=contraparte.monto_linea,
                mta=contraparte.mta,
                exceso=exceso,
                llamado=llamado,
                monto_llamado=monto,
            )
        )
    return GarantiasCartera(fecha_proceso=fecha, moneda="CLP", contrapartes=filas, sin_contraparte=sin_contraparte)


@router.get(
    "/pnl-realizado",
    response_model=PnlRealizadoCartera,
    summary="P&L realizado de los FX Forward que vencieron en un período",
)
def pnl_realizado(
    db: Sesion,
    fecha: FechaProceso,
    desde: Annotated[date | None, Query(description="Primer vencimiento incluido; por defecto, el 1 de enero del año de la fecha")] = None,
):
    """!
    @brief `GET /cartera/pnl-realizado`: P&L realizado de los FX Forward no anulados que vencieron entre `desde` y `fecha`.

    Cada forward se liquida en su fecha de pago: el P&L realizado es lo recibido menos lo
    pagado, ambos convertidos a CLP con el spot de esa fecha (si no hay datos ese día, el del
    día anterior con datos). Es el mismo resultado en compensación y en entrega física.
    Por ahora sólo considera FX Forward; los swaps vencidos no se incluyen.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso: último vencimiento incluido.
    @param desde Primer vencimiento incluido.
    @return @ref valorizador.schemas.cartera.PnlRealizadoCartera.
    """
    desde = desde or date(fecha.year, 1, 1)
    vencidas = [
        o for o in (repo.a_esquema(x) for x in repo.listar_todas(db, Producto.FX_FORWARD, Estado.VIGENTE))
        if desde <= o.fecha_vencimiento <= fecha
    ]
    mercado: dict[date, tuple[date | None, dict[str, float]]] = {}
    filas = []
    for operacion in sorted(vencidas, key=lambda o: (o.fecha_vencimiento, o.deal_number)):
        recibe = next(p for p in operacion.patas if p.rec_pay == RecPay.RECIBE)
        paga = next(p for p in operacion.patas if p.rec_pay == RecPay.PAGA)
        pago = operacion.fecha_vencimiento
        if pago not in mercado:
            mercado[pago] = repo_mercado.leer_fx_hasta(db, pago)
        dia, fx = mercado[pago]
        pnl, error = None, None
        try:
            if dia is None:
                raise ErrorValorizador(f"No hay tipos de cambio hasta el {pago.isoformat()}")
            escenario = EscenarioMercado(fecha=dia, fx=fx)
            pnl = recibe.nocional * escenario.tipo_cambio(recibe.moneda.value, "CLP") - paga.nocional * escenario.tipo_cambio(
                paga.moneda.value, "CLP"
            )
        except ErrorValorizador as e:
            error = str(e)
        filas.append(
            PnlRealizadoOperacion(
                deal_number=operacion.deal_number,
                producto=operacion.producto.value,
                rut_contraparte=operacion.rut_contraparte,
                contraparte=operacion.contraparte,
                modalidad_liquidacion=operacion.modalidad_liquidacion.value,
                grupo_calce=operacion.grupo_calce,
                fecha_negociacion=operacion.fecha_negociacion,
                fecha_vencimiento=pago,
                moneda_recibe=recibe.moneda.value,
                monto_recibe=recibe.nocional,
                moneda_paga=paga.moneda.value,
                monto_paga=paga.nocional,
                fecha_tipo_cambio=dia,
                pnl=pnl,
                error=error,
            )
        )
    return PnlRealizadoCartera(
        desde=desde,
        fecha_proceso=fecha,
        moneda="CLP",
        pnl_total=sum(f.pnl for f in filas if f.pnl is not None),
        operaciones=filas,
    )


## Orden en que se elige la moneda principal de un forward: la primera presente.
_ORDEN_PRINCIPAL = ["CLF", "EUR", "USD", "CLP"]


@router.get(
    "/forwards-basilea",
    response_model=ForwardsBasilea,
    summary="Detalle de FX Forward vigentes con valor razonable activo y pasivo",
)
def forwards_basilea(db: Sesion, fecha: FechaProceso):
    """!
    @brief `GET /cartera/forwards-basilea`: detalle de los FX Forward vigentes para el reporte Basilea.

    Por operación entrega el par, el movimiento (Compra o Venta de la moneda principal), los
    montos, el plazo, y el valor presente en CLP de lo que se recibe (activo) y de lo que se paga
    (pasivo), con la tasa de la curva de descuento de cada pata al plazo residual.
    @param db Sesión de base de datos.
    @param fecha Fecha de proceso.
    @return @ref valorizador.schemas.cartera.ForwardsBasilea.
    """
    operaciones = _vigentes(db, Producto.FX_FORWARD, fecha)
    escenario = repo_mercado.cargar_escenario_cartera(db, fecha, operaciones)
    filas = []
    for operacion in operaciones:
        por_moneda = {p.moneda.value: p for p in operacion.patas}
        principal, secundaria = sorted(por_moneda, key=lambda m: _ORDEN_PRINCIPAL.index(m) if m in _ORDEN_PRINCIPAL else 99)
        pata_principal = por_moneda[principal]
        recibe = next(p for p in operacion.patas if p.rec_pay == RecPay.RECIBE)
        dias = (operacion.fecha_vencimiento - fecha).days
        fila = dict(
            deal_number=operacion.deal_number,
            rut_contraparte=operacion.rut_contraparte,
            contraparte=operacion.contraparte,
            modalidad_liquidacion=operacion.modalidad_liquidacion.value,
            grupo_calce=operacion.grupo_calce,
            movimiento="Compra" if pata_principal.rec_pay == RecPay.RECIBE else "Venta",
            par=f"{principal}/{secundaria}",
            moneda_principal=principal,
            monto_principal=pata_principal.nocional,
            moneda_secundaria=secundaria,
            monto_secundario=por_moneda[secundaria].nocional,
            tipo_cambio=por_moneda[secundaria].nocional / pata_principal.nocional,
            fecha_negociacion=operacion.fecha_negociacion,
            plazo=(operacion.fecha_vencimiento - operacion.fecha_negociacion).days,
            fecha_vencimiento=operacion.fecha_vencimiento,
            dias_al_vencimiento=dias,
        )
        try:
            valor = motor.valorizar(operacion, escenario, "CLP")
            for pata_valor, pata in zip(valor.patas, sorted(operacion.patas, key=lambda p: p.numero)):
                tasa = construir_curva(escenario.curva(pata.curva_descuento)).get_rate_at(dias)
                if pata.rec_pay == recibe.rec_pay:
                    fila.update(tasa_activo=tasa, valor_razonable_activo=pata_valor.valor_presente_convertido)
                else:
                    fila.update(tasa_pasivo=tasa, valor_razonable_pasivo=-pata_valor.valor_presente_convertido)
            fila["valor_razonable"] = valor.mtm
        except ErrorValorizador as e:
            fila["error"] = str(e)
        except (RuntimeError, ValueError) as e:  # errores de qcfinancial
            fila["error"] = f"Error de cálculo: {e}"
        filas.append(ForwardBasilea(**fila))
    return ForwardsBasilea(fecha_proceso=fecha, moneda="CLP", operaciones=filas)
