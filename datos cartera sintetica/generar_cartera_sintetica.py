"""!
@package generar_cartera_sintetica
@brief Genera una cartera sintética con operaciones calzadas y descalzadas.

Uso, desde esta carpeta:
@code
python generar_cartera_sintetica.py
@endcode

Deja `cargar_cartera_sintetica.sql`, que reemplaza todas las operaciones y contrapartes de la
base por esta cartera; `actualizar_lineas_contrapartes.sql`, que sólo actualiza la línea y el
MTA; y `calces.csv`, que indica a qué grupo de calce pertenece cada operación. El grupo
también queda en la columna `operacion.grupo_calce`; las descalzadas lo tienen nulo.

Composición:

| Producto   | Operaciones | Calzadas | Descalzadas |
|------------|-------------|----------|-------------|
| FX_FORWARD | 60          | 54       | 6           |
| IR_SWAP    | 12          | 10       | 2           |
| CC_SWAP    | 5           | 4        | 1           |

Además, 22 FX Forward que vencieron antes de la fecha de proceso (8 pares calzados y 6
descalzados, folios `FXV-`), para el P&L realizado: cada uno parte de un forward real, con un
plazo de 30 a 180 días, fechas con tipos de cambio en el mercado demo y un precio forward
calculado sobre el spot de su fecha de negociación.

Cómo se arma:
- Cada grupo de calce parte de una operación real de la cartera preliminar (`fwds.csv` y
  `swaps.csv`, con los mismos filtros y supuestos de @ref generar_carga_operaciones), que hace
  de operación con el cliente. Así los nocionales, plazos y tasas siguen la distribución de la
  cartera original.
- Su cobertura es la misma operación en sentido contrario, con otra contraparte: igual monto y
  vencimiento y, en los swaps, las mismas fechas de cupón y periodicidad. En los grupos de
  tres, la cobertura se reparte en dos operaciones que suman el monto original.
- La cobertura tiene un precio algo mejor para la institución, de modo que el grupo deja
  margen: en forwards el monto de la otra moneda se mueve entre 0,05% y 0,30%; en swaps la tasa
  fija, o el spread si no hay pata fija, se mueve entre 2 y 10 puntos base.
- En un forward el monto que se calza es el de la moneda base del par: CLF en CLFCLP y CLFUSD,
  USD en USDCLP.
- Las descalzadas son operaciones reales sin cobertura.
- Sólo se usan como base operaciones cuyo tipo de cambio pactado está a menos de 10% del spot
  de la fecha de proceso, para evitar precios fuera de mercado.
- Contrapartes: 35 ficticias, con RUT ficticio, monto de línea con distribución triangular de
  mínimo 5, moda 25 y máximo 50 millones de pesos, y MTA con distribución triangular de mínimo
  500 mil, moda 1 millón y máximo 5 millones; ambos redondeados a miles y asignados al azar con
  semilla fija.
- Modalidad de liquidación: la misma en todo un grupo. Compensación para los IR_SWAP y para
  toda operación con una pata en UF; entrega física para a lo más el 10% de la cartera.
"""

import csv
import importlib.util
import random
from collections import Counter, defaultdict
from copy import deepcopy
import re
from datetime import date, timedelta
from pathlib import Path

## Carpeta del script, donde se escriben los resultados.
CARPETA = Path(__file__).resolve().parent
## Generador de la cartera preliminar, del que se reutilizan la lectura y conversión de los CSV.
ORIGEN = CARPETA.parent / "datos cartera preliminar" / "generar_carga_operaciones.py"

## Semilla fija de la generación.
SEMILLA = 20261012
## Contrapartes ficticias.
CONTRAPARTES = [f"Contraparte Dummy {i:02d}" for i in range(1, 36)]
## Fracción máxima de la cartera con entrega física.
MAXIMO_ENTREGA_FISICA = 0.10
## Monto de línea: distribución triangular en CLP (mínimo, moda, máximo).
LINEA_TRIANGULAR = (5e6, 25e6, 50e6)
## MTA: distribución triangular en CLP (mínimo, moda, máximo).
MTA_TRIANGULAR = (500e3, 1e6, 5e6)
## Paso de redondeo de línea y MTA (miles).
REDONDEO = 1_000

## Forwards ya vencidos a la fecha de proceso, para el P&L realizado: (pares de calce, descalzadas).
VENCIDOS = (8, 6)
## Prefijo del folio y del grupo de calce de los forwards vencidos.
PREFIJO_VENCIDOS = "FXV"
## Mercado demo, del que se leen los tipos de cambio para fechar y poner precio a los forwards vencidos.
MERCADO_DEMO = CARPETA.parent / "datos mercados demo" / "cargar_datos_mercado.sql"
## Tasa anual aproximada de cada moneda para los puntos forward de los forwards vencidos.
TASA_FORWARD = {"CLP": 0.0475, "USD": 0.04, "CLF": 0.015}
## Producto: (prefijo del folio, pares de calce, tríos de calce, descalzadas).
COMPOSICION = {
    "FX_FORWARD": ("FX", 18, 6, 6),
    "IR_SWAP": ("IRS", 2, 2, 2),
    "CC_SWAP": ("CCS", 2, 0, 1),
}
## Ajustes manuales posteriores: folio y factor que multiplica los nocionales de ambas patas, de modo que la operación conserva su tipo de cambio implícito.
AJUSTES_NOCIONAL: dict[str, float] = {}
## Prioridad de monedas para elegir la moneda que se calza en un forward.
ORDEN_BASE = ["CLF", "USD", "CLP"]
## Pesos por unidad al 17-08-2026. Se usan para descartar como base operaciones cuyo tipo de cambio pactado está lejos del mercado.
SPOT_CLP = {"CLP": 1.0, "USD": 914.15, "CLF": 40855.33}
## Desvío máximo del tipo de cambio implícito respecto del spot.
DESVIO_MAXIMO = 0.10  # moneda que se calza en un forward: la primera presente
## Paso de redondeo por moneda al repartir una cobertura en dos operaciones.
PASO_REDONDEO = {"USD": 100_000, "CLF": 1_000, "CLP": 1_000_000}


def _cargar_origen():
    """!
    @brief Importa el generador de la cartera preliminar desde su archivo.
    @return Módulo.
    """
    spec = importlib.util.spec_from_file_location("origen", ORIGEN)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


## Módulo del generador de la cartera preliminar.
origen = _cargar_origen()


# ------------------------------------------------------------------ cartera de origen


def _cerca_del_mercado(op: dict) -> bool:
    """!
    @brief Indica si el tipo de cambio implícito de una operación difiere a lo más @ref DESVIO_MAXIMO del spot.
    @param op Operación.
    @return Verdadero si está cerca del mercado o si es de una sola moneda.
    """
    a, b = op["patas"]
    if a["moneda"] == b["moneda"]:
        return True
    implicito = (a["nocional"] / b["nocional"]) / (SPOT_CLP[b["moneda"]] / SPOT_CLP[a["moneda"]])
    return abs(implicito - 1) <= DESVIO_MAXIMO


def cartera_origen() -> dict[str, list[dict]]:
    """!
    @brief Operaciones de la cartera preliminar que pueden servir de base, por producto.
    @return Diccionario producto → operaciones.
    """
    pool = defaultdict(list)
    for deal, patas in origen.leer("fwds.csv").items():
        if {p["currency"] for p in patas} <= origen.MONEDAS_CARTERA:
            op = origen.convertir_forward(deal, patas)
            if _cerca_del_mercado(op):
                pool["FX_FORWARD"].append(op)
    for deal, patas in origen.leer("swaps.csv").items():
        if not {p["currency"] for p in patas} <= origen.MONEDAS_CARTERA:
            continue
        if any(p["amort"] != "BULLET" for p in patas) or {p["type_rate"] for p in patas} - {"FIX", "FLOATCAM"}:
            continue
        op = origen.convertir_swap(deal, patas)
        tipos = sorted(p["tipo"] for p in op["patas"])
        # IR swap de calce: fija contra flotante, con ambas patas en las mismas fechas.
        if op["producto"] == "IR_SWAP" and tipos != ["FIJA", "INDICE_OVERNIGHT"]:
            continue
        if len({(p["fecha_inicio"], p["fecha_fin"], p["periodicidad"]) for p in op["patas"]}) != 1:
            continue
        if _cerca_del_mercado(op):
            pool[op["producto"]].append(op)
    return pool


# ------------------------------------------------------------------------- coberturas


def _invertir(rec_pay: str) -> str:
    """!
    @brief Sentido contrario.
    @param rec_pay RECIBE o PAGA.
    @return El otro.
    """
    return "PAGA" if rec_pay == "RECIBE" else "RECIBE"


def _mejor_precio(valor: float, rec_pay_base: str, margen: float) -> float:
    """!
    @brief Precio de la cobertura: si la base recibe, la cobertura paga menos; si paga, recibe más.
    @param valor Tasa o spread de la base.
    @param rec_pay_base Sentido de la pata en la base.
    @param margen Margen a favor de la institución.
    @return Valor de la cobertura.
    """
    return valor - margen if rec_pay_base == "RECIBE" else valor + margen


def _partes(monto: float, moneda: str, azar: random.Random) -> list[float] | None:
    """!
    @brief Divide un monto en dos partes redondeadas.
    @param monto Monto a dividir.
    @param moneda Moneda, para el paso de redondeo.
    @param azar Generador aleatorio.
    @return Las dos partes, o nada si no se puede dividir.
    """
    paso = PASO_REDONDEO.get(moneda, 1)
    primera = round(monto * azar.uniform(0.35, 0.65) / paso) * paso
    if primera <= 0 or primera >= monto:
        return None
    return [float(primera), float(monto - primera)]


def cobertura_forward(base: dict, fraccion: float, azar: random.Random) -> dict:
    """!
    @brief Forward de cobertura: sentido contrario, una fracción del monto y un precio algo mejor.
    @param base Operación base.
    @param fraccion Fracción del monto que cubre.
    @param azar Generador aleatorio.
    @return Operación de cobertura.
    """
    op = deepcopy(base)
    moneda_calce = next(m for m in ORDEN_BASE if m in {p["moneda"] for p in op["patas"]})
    margen = azar.uniform(0.0005, 0.0030)
    for pata, pata_base in zip(op["patas"], base["patas"]):
        pata["rec_pay"] = _invertir(pata_base["rec_pay"])
        if pata["moneda"] == moneda_calce:
            pata["nocional"] = pata_base["nocional"] * fraccion
        else:
            factor = 1 - margen if pata_base["rec_pay"] == "RECIBE" else 1 + margen
            pata["nocional"] = round(pata_base["nocional"] * fraccion * factor, 2)
    return op


def cobertura_swap(base: dict, fraccion: float, azar: random.Random) -> dict:
    """!
    @brief Swap de cobertura: sentido contrario, una fracción del nocional, mismas fechas y una tasa o spread algo mejor.
    @param base Operación base.
    @param fraccion Fracción del nocional que cubre.
    @param azar Generador aleatorio.
    @return Operación de cobertura.
    """
    op = deepcopy(base)
    margen = azar.uniform(0.0002, 0.0010)
    fija = next((p for p in op["patas"] if p["tipo"] == "FIJA"), None)
    ajustada = fija if fija is not None else op["patas"][0]
    for pata, pata_base in zip(op["patas"], base["patas"]):
        pata["rec_pay"] = _invertir(pata_base["rec_pay"])
        pata["nocional"] = round(pata_base["nocional"] * fraccion, 2)
        if pata is ajustada:
            campo = "tasa" if pata["tipo"] == "FIJA" else "spread"
            pata[campo] = round(_mejor_precio(pata_base[campo], pata_base["rec_pay"], margen), 6)
    return op


def moneda_y_monto_calzado(op: dict) -> tuple[str, float]:
    """!
    @brief Moneda y monto que se calzan en una operación.
    @param op Operación.
    @return Tupla (moneda, monto).
    """
    if op["producto"] == "FX_FORWARD":
        moneda = next(m for m in ORDEN_BASE if m in {p["moneda"] for p in op["patas"]})
        return moneda, next(p["nocional"] for p in op["patas"] if p["moneda"] == moneda)
    pata = op["patas"][0]
    return pata["moneda"], pata["nocional"]


# --------------------------------------------------------------------------- cartera


def _plazo(op: dict) -> int:
    """!
    @brief Días entre la fecha de proceso y el vencimiento.
    @param op Operación.
    @return Plazo en días.
    """
    return (max(p.get("fecha_pago") or p["fecha_fin"] for p in op["patas"]) - origen.FECHA_PROCESO).days


def _muestra_estratificada(pool: list[dict], n: int, azar: random.Random) -> list[dict]:
    """!
    @brief Operaciones de base repartidas por plazo como en la cartera original.

    Ordena por plazo, divide en n tramos de igual tamaño y toma una al azar de cada tramo. Devuelve además el resto en orden aleatorio, como reserva si un tramo no sirve.
    @param pool Operaciones candidatas.
    @param n Cantidad de operaciones de base.
    @param azar Generador aleatorio.
    @return Operaciones elegidas seguidas de la reserva.
    """
    ordenado = sorted(pool, key=_plazo)
    tramo = len(ordenado) / n
    elegidas = [ordenado[int(i * tramo) + azar.randrange(max(1, int(tramo)))] for i in range(n)]
    azar.shuffle(elegidas)
    ids = {id(o) for o in elegidas}
    reserva = [o for o in ordenado if id(o) not in ids]
    azar.shuffle(reserva)
    return reserva + elegidas  # se consumen desde el final con pop()


def generar() -> tuple[list[dict], list[dict]]:
    """!
    @brief Arma la cartera: grupos de calce, descalzadas, folios, contrapartes y modalidad.
    @return Tupla (operaciones, grupos de calce).
    """
    azar = random.Random(SEMILLA)
    pool = cartera_origen()
    operaciones, grupos = [], []

    for producto, (prefijo, pares, trios, descalzadas) in COMPOSICION.items():
        tamanos = [2] * pares + [3] * trios + [1] * descalzadas
        disponibles = _muestra_estratificada(pool[producto], len(tamanos), azar)
        cobertura = cobertura_forward if producto == "FX_FORWARD" else cobertura_swap
        del_producto = []

        for tamano in tamanos:
            while True:
                base = deepcopy(disponibles.pop())
                if tamano < 3:
                    fracciones = [1.0] * (tamano - 1)
                    break
                moneda, monto = moneda_y_monto_calzado(base)
                partes = _partes(monto, moneda, azar)
                if partes:
                    fracciones = [parte / monto for parte in partes]
                    break
            grupo = [base] + [cobertura(base, f, azar) for f in fracciones]
            if producto == "FX_FORWARD" and tamano == 3:  # montos exactos en la moneda calzada
                moneda, monto = moneda_y_monto_calzado(base)
                for op, parte in zip(grupo[1:], partes):
                    next(p for p in op["patas"] if p["moneda"] == moneda)["nocional"] = parte
            contrapartes = azar.sample(CONTRAPARTES, tamano)
            for i, (op, contraparte) in enumerate(zip(grupo, contrapartes)):
                op["contraparte"] = contraparte
                op["rol"] = "DESCALZADA" if tamano == 1 else ("BASE" if i == 0 else "COBERTURA")
            grupos.append(grupo)
            del_producto.extend(grupo)

        # Deal numbers correlativos en orden aleatorio, para que los grupos no queden juntos.
        azar.shuffle(del_producto)
        for n, op in enumerate(del_producto, start=1):
            op["deal_number"] = f"{prefijo}-{n:03d}"
        operaciones.extend(del_producto)

    for op in operaciones:
        if op["deal_number"] in AJUSTES_NOCIONAL:
            for pata in op["patas"]:
                pata["nocional"] = round(pata["nocional"] * AJUSTES_NOCIONAL[op["deal_number"]], 2)

    # Modalidad por grupo, con tope de entrega física.
    maximo_fisica = int(MAXIMO_ENTREGA_FISICA * len(operaciones))
    fisicas = 0
    for grupo in azar.sample(grupos, len(grupos)):
        posible = grupo[0]["producto"] != "IR_SWAP" and not any(
            p["moneda"] == "CLF" for p in grupo[0]["patas"]
        )
        fisica = posible and fisicas + len(grupo) <= maximo_fisica and azar.random() < 0.15
        fisicas += len(grupo) if fisica else 0
        for op in grupo:
            op["modalidad_liquidacion"] = "ENTREGA_FISICA" if fisica else "COMPENSACION"

    for op in operaciones:
        origen.validar(op)

    # Nombre de cada grupo de calce, que se guarda en la operación; las descalzadas quedan sin grupo.
    numeros = Counter()
    for grupo in sorted(grupos, key=lambda g: (list(COMPOSICION).index(g[0]["producto"]), g[0]["deal_number"])):
        producto = grupo[0]["producto"]
        nombre = None
        if len(grupo) > 1:
            numeros[producto] += 1
            nombre = f"{COMPOSICION[producto][0]}-G{numeros[producto]:02d}"
        for op in grupo:
            op["grupo_calce"] = nombre
    assert len({o["deal_number"] for o in operaciones}) == len(operaciones)
    return operaciones, grupos


# ------------------------------------------------------------------------------ salida


def _triangular(azar: random.Random, parametros: tuple[float, float, float]) -> float:
    """!
    @brief Monto con distribución triangular, redondeado a @ref REDONDEO.
    @param azar Generador aleatorio.
    @param parametros (mínimo, moda, máximo).
    @return Monto.
    """
    minimo, moda, maximo = parametros
    return float(round(azar.triangular(minimo, maximo, moda) / REDONDEO) * REDONDEO)


def maestro_contrapartes() -> list[dict]:
    """!
    @brief RUT, nombre, línea y MTA de cada contraparte. Usa su propia semilla para no alterar la cartera.
    @return Lista de contrapartes.
    """
    azar = random.Random(SEMILLA + 4)
    return [
        {"rut": origen.rut_dummy(nombre), "nombre": nombre,
         "monto_linea": _triangular(azar, LINEA_TRIANGULAR), "mta": _triangular(azar, MTA_TRIANGULAR)}
        for nombre in CONTRAPARTES
    ]


def escribir_sql(operaciones: list[dict]) -> None:
    """!
    @brief Escribe `cargar_cartera_sintetica.sql`, que reemplaza todas las operaciones y contrapartes.
    @param operaciones Operaciones generadas.
    """
    conteo = Counter(o["producto"] for o in operaciones)
    resumen = ", ".join(f"{conteo[p]} {p}" for p in COMPOSICION)
    lineas = f"""-- =============================================================================
-- Valorizador de Derivados: carga de la cartera sintética con calces
--
-- Generado por generar_cartera_sintetica.py, con fecha de proceso {origen.FECHA_PROCESO}.
-- Contenido: {len(operaciones)} operaciones ({resumen}) y {2 * len(operaciones)} patas.
-- El detalle de qué operaciones se calzan entre sí está en calces.csv.
--
-- REEMPLAZA TODAS LAS OPERACIONES DE LA BASE, con sus patas e historial, Y TODAS LAS
-- CONTRAPARTES. No toca los datos de mercado. Requiere el esquema en revisión 0006 o
-- posterior (alembic upgrade head).
--
-- Uso:
--     psql -U postgres -p 5434 -d Valorizador -f cargar_cartera_sintetica.sql
-- =============================================================================

BEGIN;

CREATE TEMP TABLE tmp_operacion (
    deal_number           VARCHAR(50) PRIMARY KEY,
    producto              VARCHAR(20) NOT NULL,
    rut_contraparte       VARCHAR(12),
    modalidad_liquidacion VARCHAR(20) NOT NULL,
    grupo_calce           VARCHAR(30),
    fecha_negociacion     DATE NOT NULL
) ON COMMIT DROP;

CREATE TEMP TABLE tmp_pata (LIKE pata INCLUDING DEFAULTS) ON COMMIT DROP;
ALTER TABLE tmp_pata DROP COLUMN id, DROP COLUMN operacion_id, ADD COLUMN deal_number VARCHAR(50) NOT NULL;

""".split("\n")
    lineas += origen.inserts(
        "tmp_operacion",
        ["deal_number", "producto", "rut_contraparte", "modalidad_liquidacion", "grupo_calce", "fecha_negociacion"],
        [
            [
                o["deal_number"], o["producto"], origen.rut_dummy(o["contraparte"]), o["modalidad_liquidacion"], o["grupo_calce"],
                o["fecha_negociacion"].isoformat(),
            ]
            for o in operaciones
        ],
    )
    columnas = origen.COLUMNAS_PATA
    lineas += origen.inserts(
        "tmp_pata",
        ["deal_number"] + columnas,
        [
            [o["deal_number"]] + [v.isoformat() if isinstance(v := p.get(c), date) else v for c in columnas]
            for o in operaciones
            for p in o["patas"]
        ],
    )
    lineas += ["DELETE FROM operacion;", "DELETE FROM contraparte;", ""]
    lineas += origen.inserts(
        "contraparte",
        ["rut", "nombre", "monto_linea", "mta"],
        [[c["rut"], c["nombre"], c["monto_linea"], c["mta"]] for c in maestro_contrapartes()],
    )
    lineas += f"""INSERT INTO operacion (deal_number, producto, rut_contraparte, modalidad_liquidacion, grupo_calce, fecha_negociacion, estado, version)
SELECT deal_number, producto, rut_contraparte, modalidad_liquidacion, grupo_calce, fecha_negociacion, 'VIGENTE', 1
FROM tmp_operacion
ORDER BY deal_number;

INSERT INTO pata (operacion_id, {', '.join(columnas)})
SELECT o.id, {', '.join('t.' + c for c in columnas)}
FROM tmp_pata t
JOIN operacion o ON o.deal_number = t.deal_number
ORDER BY o.id, t.numero;

COMMIT;
""".split("\n")
    (CARPETA / "cargar_cartera_sintetica.sql").write_text("\n".join(lineas), encoding="utf-8", newline="\n")


def escribir_calces(grupos: list[list[dict]]) -> None:
    """!
    @brief Escribe `calces.csv` con el grupo, el rol y el monto calzado de cada operación.
    @param grupos Grupos de calce y descalzadas.
    """
    with open(CARPETA / "calces.csv", "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(
            ["grupo", "producto", "deal_number", "rol", "contraparte", "vencimiento", "moneda_calzada", "monto_calzado", "sentido"]
        )
        for grupo in sorted(grupos, key=lambda g: (list(COMPOSICION).index(g[0]["producto"]), g[0]["deal_number"])):
            producto = grupo[0]["producto"]
            nombre = grupo[0]["grupo_calce"] or ""
            for op in grupo:
                moneda, monto = moneda_y_monto_calzado(op)
                pata = next(p for p in op["patas"] if p["moneda"] == moneda)
                vencimiento = max(p.get("fecha_pago") or p["fecha_fin"] for p in op["patas"])
                escritor.writerow(
                    [nombre, producto, op["deal_number"], op["rol"], op["contraparte"], vencimiento.isoformat(), moneda, monto, pata["rec_pay"]]
                )


def escribir_actualizacion_lineas() -> None:
    """!
    @brief Escribe `actualizar_lineas_contrapartes.sql`, que sólo actualiza la línea y el MTA de las contrapartes, sin tocar operaciones.
    """
    filas = maestro_contrapartes()
    lineas = [
        "-- Monto de línea y MTA sintéticos (CLP) de las contrapartes de la cartera sintética.",
        "-- Generado por generar_cartera_sintetica.py. Sólo actualiza la tabla contraparte; no toca",
        "-- operaciones. Requiere la revisión 0006.",
        "-- Uso en psql: \\i 'D:/Valorizador Derivados/datos cartera sintetica/actualizar_lineas_contrapartes.sql'",
        "",
        "BEGIN;",
        "",
        "UPDATE contraparte c SET monto_linea = v.monto_linea, mta = v.mta, actualizado_en = now()",
        "FROM (VALUES",
    ]
    lineas += [
        f"    ('{c['rut']}', {c['monto_linea']:.0f}, {c['mta']:.0f})" + ("," if i < len(filas) - 1 else "")
        for i, c in enumerate(filas)
    ]
    lineas += [") AS v (rut, monto_linea, mta)", "WHERE c.rut = v.rut;", "",
               "SELECT count(*) AS con_linea FROM contraparte WHERE monto_linea > 0;", "", "COMMIT;", ""]  # fmt: skip
    (CARPETA / "actualizar_lineas_contrapartes.sql").write_text("\n".join(lineas), encoding="utf-8", newline="\n")


def leer_spot() -> dict[str, dict[date, float]]:
    """!
    @brief Tipos de cambio USDCLP y CLFCLP del mercado demo.
    @return Diccionario par → (fecha → valor).
    """
    spot: dict[str, dict[date, float]] = defaultdict(dict)
    texto = MERCADO_DEMO.read_text(encoding="utf-8")
    for fecha, par, valor in re.findall(r"\('(\d{4}-\d{2}-\d{2})', '(USDCLP|CLFCLP)', ([\d.]+)\)", texto):
        spot[par][date.fromisoformat(fecha)] = float(valor)
    return spot


def _en_clp(spot: dict[str, dict[date, float]], moneda: str, fecha: date) -> float:
    """!
    @brief Pesos por una unidad de la moneda en una fecha del mercado demo.
    @param spot Resultado de @ref leer_spot.
    @param moneda CLP, USD o CLF.
    @param fecha Fecha con datos.
    @return Valor en pesos.
    """
    return 1.0 if moneda == "CLP" else spot[f"{moneda}CLP"][fecha]


def forward_vencido(base: dict, spot: dict[str, dict[date, float]], azar: random.Random) -> dict:
    """!
    @brief Forward que venció antes de la fecha de proceso, a partir de una operación real.

    Conserva las monedas, el sentido y el monto de la moneda base del par. Elige un plazo de
    30 a 180 días y una fecha de pago con tipos de cambio en el mercado demo, anterior a la
    fecha de proceso. El monto de la otra moneda es el precio forward a la fecha de negociación:
    el spot de ese día ajustado por el diferencial de tasas de @ref TASA_FORWARD durante el plazo.
    @param base Operación FX_FORWARD de la cartera preliminar.
    @param spot Resultado de @ref leer_spot.
    @param azar Generador aleatorio.
    @return Operación con fechas y montos nuevos.
    """
    op = deepcopy(base)
    fechas = sorted(f for f in spot["USDCLP"] if f in spot["CLFCLP"] and f < origen.FECHA_PROCESO)
    plazo = azar.randint(30, 180)
    pago = azar.choice([f for f in fechas if f - timedelta(days=plazo) >= fechas[0]])
    negociacion = max(f for f in fechas if f <= pago - timedelta(days=plazo))
    t = (pago - negociacion).days / 365
    base_par = next(m for m in ORDEN_BASE if m in {p["moneda"] for p in op["patas"]})
    cotizada = next(p["moneda"] for p in op["patas"] if p["moneda"] != base_par)
    precio = _en_clp(spot, base_par, negociacion) / _en_clp(spot, cotizada, negociacion)
    precio *= (1 + TASA_FORWARD[cotizada] * t) / (1 + TASA_FORWARD[base_par] * t) * (1 + azar.uniform(-0.002, 0.002))
    monto_base = next(p["nocional"] for p in op["patas"] if p["moneda"] == base_par)
    op["fecha_negociacion"] = negociacion
    for pata in op["patas"]:
        pata["fecha_pago"] = pago
        if pata["moneda"] == cotizada:
            pata["nocional"] = round(monto_base * precio, 2)
    return op


def generar_vencidos() -> tuple[list[dict], list[dict]]:
    """!
    @brief Forwards vencidos antes de la fecha de proceso: @ref VENCIDOS pares calzados y descalzados.

    Usa su propia semilla, para no alterar la cartera vigente.
    @return Tupla (operaciones, grupos de calce).
    """
    azar = random.Random(SEMILLA + 5)
    spot = leer_spot()
    pares, descalzadas = VENCIDOS
    bases = azar.sample(cartera_origen()["FX_FORWARD"], pares + descalzadas)
    grupos = []
    for i, base in enumerate(bases):
        vencido = forward_vencido(base, spot, azar)
        grupo = [vencido, cobertura_forward(vencido, 1.0, azar)] if i < pares else [vencido]
        for j, (op, contraparte) in enumerate(zip(grupo, azar.sample(CONTRAPARTES, len(grupo)))):
            op["contraparte"] = contraparte
            op["rol"] = "DESCALZADA" if len(grupo) == 1 else ("BASE" if j == 0 else "COBERTURA")
            op["grupo_calce"] = f"{PREFIJO_VENCIDOS}-G{i + 1:02d}" if len(grupo) > 1 else None
            op["modalidad_liquidacion"] = "COMPENSACION"
        if not any(p["moneda"] == "CLF" for p in grupo[0]["patas"]) and azar.random() < 0.15:
            for op in grupo:
                op["modalidad_liquidacion"] = "ENTREGA_FISICA"
        grupos.append(grupo)
    operaciones = [op for grupo in grupos for op in grupo]
    azar.shuffle(operaciones)
    for n, op in enumerate(operaciones, start=1):
        op["deal_number"] = f"{PREFIJO_VENCIDOS}-{n:03d}"
        origen.validar(op)
    return operaciones, grupos


def main() -> None:
    """!
    @brief Genera la cartera, escribe los archivos y muestra un resumen.
    """
    operaciones, grupos = generar()
    vencidos, grupos_vencidos = generar_vencidos()
    operaciones, grupos = operaciones + vencidos, grupos + grupos_vencidos
    escribir_sql(operaciones)
    escribir_actualizacion_lineas()
    escribir_calces(grupos)

    print("Operaciones:", dict(Counter(o["producto"] for o in operaciones)), "total", len(operaciones))
    print("Vencidos antes de la fecha de proceso:", len(vencidos))
    for producto in COMPOSICION:
        del_producto = [o for o in operaciones if o["producto"] == producto and o not in vencidos]
        calzadas = sum(1 for o in del_producto if o["rol"] != "DESCALZADA")
        print(f"  {producto:<11} calzadas {calzadas} de {len(del_producto)} ({calzadas / len(del_producto):.0%})")
    print("Contrapartes usadas:", len({o["contraparte"] for o in operaciones}))
    print("Modalidad:", dict(Counter(o["modalidad_liquidacion"] for o in operaciones)))
    print("Monedas:", dict(Counter(tuple(sorted(p["moneda"] for p in o["patas"])) for o in operaciones)))


if __name__ == "__main__":
    main()
