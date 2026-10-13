"""!
@package generar_carga_operaciones
@brief Genera `cargar_operaciones.sql` (cartera preliminar) a partir de `fwds.csv` y `swaps.csv`.

Uso, desde esta carpeta:
@code
python generar_carga_operaciones.py
@endcode

Filtros:
- Sólo operaciones cuyas dos patas están en CLF, CLP o USD.
- En `swaps.csv`, sólo operaciones con amortización BULLET en ambas patas.
- Se excluyen además las patas que el modelo no representa (tasa FLOAT o VARIABLE).

Supuestos (los archivos no traen fechas, convenciones ni índices):
- `start_time` y `expiry_time` son fracciones de año desde la fecha de proceso. La fecha es la
  fecha de proceso más la fracción por 365 días, redondeada al día.
- Las curvas se asignan por moneda con los códigos de `cargar_datos_mercado.sql`.
- La contraparte es ficticia: una de diez, asignada al azar con semilla fija, con un RUT
  también ficticio. Si la contraparte no existe en la tabla `contraparte`, se crea con línea y
  MTA en cero; si existe, no se modifica.
- Modalidad de liquidación: los IR_SWAP y toda operación con una pata en UF (CLF), por
  compensación, porque la UF es unidad de cuenta y no se entrega. Los demás FX_FORWARD y
  CC_SWAP, compensación o entrega física al azar con semilla fija, con a lo más un 10% de la
  cartera por entrega física. El archivo no la informa.
- Pata fija: ACT360 lineal. Pata flotante: ICP en CLP y en UF, SOFRINDX en USD.

Deja además `operaciones_descartadas.csv` con el motivo de cada descarte.
"""

import csv
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

## Carpeta del script, donde están los CSV de entrada y se escriben los resultados.
CARPETA = Path(__file__).resolve().parent
## Fecha de proceso a la que se refieren las fracciones de año de los archivos.
FECHA_PROCESO = date(2026, 8, 17)
## Días por año para convertir fracciones de año en fechas.
DIAS_ANIO = 365
## Monedas que se leen y a las que se asignan contraparte y modalidad. Se mantiene EUR para que el sorteo de las demás operaciones no cambie respecto de cargas anteriores.
MONEDAS = {"CLF", "CLP", "EUR", "USD"}
## Monedas de la cartera que finalmente se carga.
MONEDAS_CARTERA = {"CLF", "CLP", "USD"}
## Código de curva de descuento de cada moneda.
CURVA = {m: f"Curva {m}" for m in MONEDAS}
## Índice overnight de cada moneda: nombre, decimales de la tasa equivalente y moneda de la curva con que se proyecta. Una pata flotante en UF devenga el ICP nominal sobre su nocional en UF, así que usa el mismo índice que la pata en pesos y se proyecta con la curva en pesos.
INDICE = {
    "CLP": ("ICP", 4, "CLP"),
    "CLF": ("ICP", 4, "CLP"),
    "USD": ("SOFRINDX", 6, "USD"),
}
## Feriados fijos de Chile (mes, día), para mover fechas a un día hábil.
FERIADOS_FIJOS = {(1, 1), (5, 1), (5, 21), (7, 16), (8, 15), (9, 18), (9, 19), (11, 1), (12, 8), (12, 25)}
## Filas por sentencia INSERT en el SQL generado.
FILAS_POR_INSERT = 1000
## Contrapartes ficticias que se asignan al azar.
CONTRAPARTES = [f"Contraparte Dummy {i:02d}" for i in range(1, 11)]
## Fracción máxima de la cartera con entrega física.
MAXIMO_ENTREGA_FISICA = 0.10  # fracción máxima de la cartera con entrega física
## Semilla fija, para que la asignación al azar sea la misma en cada ejecución.
SEMILLA = 20260817  # fija, para que la asignación al azar sea la misma en cada ejecución


def digito_verificador(cuerpo: int) -> str:
    """!
    @brief Dígito verificador de un RUT por módulo 11.
    @param cuerpo Parte numérica.
    @return Dígito verificador.
    """
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def rut_dummy(nombre: str) -> str:
    """!
    @brief RUT ficticio de "Contraparte Dummy NN"; el mismo que asigna la migración 0006.
    @param nombre Nombre de la contraparte.
    @return RUT normalizado.
    """
    cuerpo = 76_000_000 + int(nombre.rsplit(" ", 1)[1]) * 104_729
    return f"{cuerpo}-{digito_verificador(cuerpo)}"


def leer(nombre: str) -> dict[str, list[dict]]:
    """!
    @brief Filas de un CSV agrupadas por deal_number, con los nombres de columna sin prefijo.
    @param nombre Nombre del archivo en @ref CARPETA.
    @return Diccionario folio → filas (una por pata).
    """
    operaciones = defaultdict(list)
    with open(CARPETA / nombre, encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            fila = {k.split(".")[-1]: v.strip() for k, v in fila.items()}
            operaciones[fila["deal_number"]].append(fila)
    return operaciones


# ------------------------------------------------------------------------ fechas


def es_habil(fecha: date) -> bool:
    """!
    @brief Indica si una fecha es día hábil (lunes a viernes y no feriado fijo).
    @param fecha Fecha.
    @return Verdadero si es hábil.
    """
    return fecha.weekday() < 5 and (fecha.month, fecha.day) not in FERIADOS_FIJOS


def a_fecha(fraccion: str) -> date:
    """!
    @brief Fecha de proceso más una fracción de año, medida en año calendario de 365 días.
    @param fraccion Fracción de año como texto.
    @return Fecha.
    """
    return FECHA_PROCESO + timedelta(days=round(float(fraccion) * DIAS_ANIO))


# ------------------------------------------------------------------- conversión

## Sentido de la pata según la columna buy_sell del archivo.
REC_PAY = {"b": "RECIBE", "s": "PAGA"}
## Período irregular según el archivo.
STUB = {"CortoAlInicio": "SHORTFRONT"}
## Factor de capitalización según el archivo.
FACTOR = {"Lin": "LIN"}


def motivo_monedas(patas: list[dict]) -> str | None:
    """!
    @brief Motivo de descarte por moneda.
    @param patas Filas de la operación.
    @return Texto del motivo, o nada si todas las monedas están en alcance.
    """
    otras = sorted({p["currency"] for p in patas} - MONEDAS)
    return f"moneda fuera de alcance: {', '.join(otras)}" if otras else None


def convertir_forward(deal: str, patas: list[dict]) -> dict:
    """!
    @brief Convierte las filas de `fwds.csv` de un folio en una operación FX_FORWARD.
    @param deal Folio.
    @param patas Filas de la operación.
    @return Operación en el formato de la API.
    """
    pago = a_fecha(patas[0]["expiry_time"])
    return {
        "deal_number": deal,
        "producto": "FX_FORWARD",
        "fecha_negociacion": a_fecha(patas[0]["start_time"]),
        "patas": [
            {
                "numero": n,
                "tipo": "SIMPLE",
                "rec_pay": REC_PAY[p["buy_sell"]],
                "moneda": p["currency"],
                "nocional": float(p["amount"]),
                "curva_descuento": CURVA[p["currency"]],
                "fecha_pago": pago,
            }
            for n, p in enumerate(patas, start=1)
        ],
    }


def convertir_swap(deal: str, patas: list[dict]) -> dict:
    """!
    @brief Convierte las filas de `swaps.csv` de un folio en un IR_SWAP o CC_SWAP, con patas fijas o ICP/SOFR.
    @param deal Folio.
    @param patas Filas de la operación.
    @return Operación en el formato de la API.
    """
    salida = []
    for n, p in enumerate(patas, start=1):
        inicio = a_fecha(p["start_time"])
        fin = a_fecha(p["expiry_time"])
        pata = {
            "numero": n,
            "rec_pay": REC_PAY[p["buy_sell"]],
            "moneda": p["currency"],
            "nocional": float(p["amount"]),
            "curva_descuento": CURVA[p["currency"]],
            "fecha_inicio": inicio,
            "fecha_fin": fin,
            "periodicidad": p["periodicity"],
            "stub": STUB[p["stub_period"]],
            "ajuste_fecha": "MODFOLLOW",
            "calendario": "SCL",
            "lag_pago": 0,
            "tipo_amortizacion": p["amort"],
            "intercambia_nocional": p["include_amort"] == "Si",
            "fraccion_anio": "ACT360",
            "factor_capitalizacion": FACTOR[p["forma_tasa"]],
        }
        if p["type_rate"] == "FIX":
            pata |= {"tipo": "FIJA", "tasa": float(p["value_rate"])}
        else:  # FLOATCAM
            indice, decimales, moneda_proyeccion = INDICE[p["currency"]]
            pata |= {
                "tipo": "INDICE_OVERNIGHT",
                "indice": indice,
                "curva_proyeccion": CURVA[moneda_proyeccion],
                "spread": float(p["spread"]),
                "gearing": 1.0,
                "decimales_tasa": decimales,
            }
        salida.append(pata)
    misma_moneda = salida[0]["moneda"] == salida[1]["moneda"]
    return {
        "deal_number": deal,
        "producto": "IR_SWAP" if misma_moneda else "CC_SWAP",
        "fecha_negociacion": min(FECHA_PROCESO, *(p["fecha_inicio"] for p in salida)),
        "patas": salida,
    }


def validar(op: dict) -> None:
    """!
    @brief Aplica las mismas reglas de estructura que la API en el alta.
    @param op Operación.
    @throws AssertionError Si alguna regla no se cumple.
    """
    patas = op["patas"]
    assert len(patas) == 2 and {p["rec_pay"] for p in patas} == {"RECIBE", "PAGA"}, op["deal_number"]
    assert all(p["nocional"] > 0 for p in patas), op["deal_number"]
    misma = patas[0]["moneda"] == patas[1]["moneda"]
    if op["producto"] == "FX_FORWARD":
        assert not misma and patas[0]["fecha_pago"] == patas[1]["fecha_pago"], op["deal_number"]
    else:
        assert all(p["fecha_fin"] > p["fecha_inicio"] for p in patas), op["deal_number"]
        assert misma == (op["producto"] == "IR_SWAP"), op["deal_number"]


# -------------------------------------------------------------------------- SQL

## Columnas de la tabla `pata` que se cargan, en orden.
COLUMNAS_PATA = [
    "numero", "tipo", "rec_pay", "moneda", "nocional", "curva_descuento", "fecha_pago", "fecha_inicio",
    "fecha_fin", "periodicidad", "stub", "ajuste_fecha", "calendario", "lag_pago", "tipo_amortizacion", "intercambia_nocional",
    "fraccion_anio", "factor_capitalizacion", "tasa", "indice", "curva_proyeccion", "spread", "gearing",
    "decimales_tasa",
]  # fmt: skip


def literal(valor) -> str:
    """!
    @brief Valor de Python como literal SQL.
    @param valor Texto, número, lógico o nada.
    @return Literal SQL, con comillas escapadas.
    """
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, (int, float)):
        return repr(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def inserts(tabla: str, columnas: list[str], filas: list[list]) -> list[str]:
    """!
    @brief Sentencias INSERT por bloques de @ref FILAS_POR_INSERT filas.
    @param tabla Tabla destino.
    @param columnas Columnas.
    @param filas Valores de cada fila.
    @return Líneas de SQL.
    """
    lineas = []
    for i in range(0, len(filas), FILAS_POR_INSERT):
        lineas.append(f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES")
        bloque = filas[i : i + FILAS_POR_INSERT]
        lineas += ["(" + ", ".join(literal(v) for v in f) + ")" + ("," if j < len(bloque) - 1 else ";")
                   for j, f in enumerate(bloque)]  # fmt: skip
        lineas.append("")
    return lineas


def escribir_sql(operaciones: list[dict], descartadas: list[str]) -> None:
    """!
    @brief Escribe `cargar_operaciones.sql`, que crea las contrapartes y reemplaza las operaciones de los archivos y las descartadas.
    @param operaciones Operaciones que se cargan.
    @param descartadas Folios descartados, que se borran por si se cargaron antes.
    """
    conteo = Counter(o["producto"] for o in operaciones)
    resumen = ", ".join(f"{conteo[p]} {p}" for p in ("FX_FORWARD", "IR_SWAP", "CC_SWAP"))
    lineas = f"""-- =============================================================================
-- Valorizador de Derivados: carga de la cartera preliminar
--
-- Generado por generar_carga_operaciones.py desde fwds.csv y swaps.csv,
-- con fecha de proceso {FECHA_PROCESO}.
-- Contenido: {len(operaciones)} operaciones ({resumen}) y {2 * len(operaciones)} patas.
--
-- Requiere el esquema en revisión 0006 o posterior (tabla contraparte): alembic upgrade head.
-- Se puede ejecutar más de una vez: las operaciones con los mismos deal_number se
-- borran, junto con sus patas e historial, y se vuelven a insertar en versión 1.
-- También borra las {len(descartadas)} operaciones de los archivos que quedan fuera de la cartera
-- (operaciones_descartadas.csv), por si se cargaron con una versión anterior.
-- No toca otras operaciones.
--
-- Uso:
--     psql -U postgres -p 5434 -d Valorizador -f cargar_operaciones.sql
-- =============================================================================

BEGIN;

CREATE TEMP TABLE tmp_operacion (
    deal_number        VARCHAR(50) PRIMARY KEY,
    producto           VARCHAR(20) NOT NULL,
    rut_contraparte    VARCHAR(12),
    modalidad_liquidacion VARCHAR(20) NOT NULL,
    fecha_negociacion  DATE NOT NULL
) ON COMMIT DROP;

CREATE TEMP TABLE tmp_pata (
    deal_number            VARCHAR(50) NOT NULL,
    numero                 INTEGER NOT NULL,
    tipo                   VARCHAR(20) NOT NULL,
    rec_pay                VARCHAR(10) NOT NULL,
    moneda                 VARCHAR(3) NOT NULL,
    nocional               DOUBLE PRECISION NOT NULL,
    curva_descuento        VARCHAR(50) NOT NULL,
    fecha_pago             DATE,
    fecha_inicio           DATE,
    fecha_fin              DATE,
    periodicidad           VARCHAR(10),
    stub                   VARCHAR(15),
    ajuste_fecha           VARCHAR(15),
    calendario             VARCHAR(20),
    lag_pago               INTEGER,
    tipo_amortizacion      VARCHAR(15),
    intercambia_nocional   BOOLEAN,
    fraccion_anio          VARCHAR(10),
    factor_capitalizacion  VARCHAR(3),
    tasa                   DOUBLE PRECISION,
    indice                 VARCHAR(30),
    curva_proyeccion       VARCHAR(50),
    spread                 DOUBLE PRECISION,
    gearing                DOUBLE PRECISION,
    decimales_tasa         INTEGER
) ON COMMIT DROP;

-- ----------------------------------------------------------------- contrapartes
""".split("\n")
    lineas += [
        "INSERT INTO contraparte (rut, nombre) VALUES",
        ",\n".join(f"    ('{rut_dummy(c)}', '{c}')" for c in sorted({o["contraparte"] for o in operaciones})),
        "ON CONFLICT (rut) DO NOTHING;",
        "",
        "-- ------------------------------------------------------------------ operaciones",
        "",
    ]
    lineas += inserts(
        "tmp_operacion",
        ["deal_number", "producto", "rut_contraparte", "modalidad_liquidacion", "fecha_negociacion"],
        [
            [o["deal_number"], o["producto"], rut_dummy(o["contraparte"]), o["modalidad_liquidacion"], o["fecha_negociacion"].isoformat()]
            for o in operaciones
        ],
    )
    lineas += ["-- ------------------------------------------------------------------------ patas", ""]
    lineas += inserts(
        "tmp_pata",
        ["deal_number"] + COLUMNAS_PATA,
        [
            [o["deal_number"]] + [v.isoformat() if isinstance(v := p.get(c), date) else v for c in COLUMNAS_PATA]
            for o in operaciones
            for p in o["patas"]
        ],
    )
    columnas = ", ".join(COLUMNAS_PATA)
    lineas += ["-- ----------------------------------------------------------------- descartadas", ""]
    lineas += ["CREATE TEMP TABLE tmp_descartada (deal_number VARCHAR(50) PRIMARY KEY) ON COMMIT DROP;", ""]
    lineas += inserts("tmp_descartada", ["deal_number"], [[d] for d in sorted(set(descartadas))])
    lineas += f"""-- ------------------------------------------------------------- tablas finales

DELETE FROM operacion WHERE deal_number IN (SELECT deal_number FROM tmp_operacion);
DELETE FROM operacion WHERE deal_number IN (SELECT deal_number FROM tmp_descartada);

INSERT INTO operacion (deal_number, producto, rut_contraparte, modalidad_liquidacion, fecha_negociacion, estado, version)
SELECT deal_number, producto, rut_contraparte, modalidad_liquidacion, fecha_negociacion, 'VIGENTE', 1
FROM tmp_operacion
ORDER BY deal_number;

INSERT INTO pata (operacion_id, {columnas})
SELECT o.id, {', '.join('t.' + c for c in COLUMNAS_PATA)}
FROM tmp_pata t
JOIN operacion o ON o.deal_number = t.deal_number
ORDER BY o.id, t.numero;

COMMIT;
""".split("\n")
    (CARPETA / "cargar_operaciones.sql").write_text("\n".join(lineas), encoding="utf-8", newline="\n")


# ------------------------------------------------------------------------- main


def _acotar_entrega_fisica(operaciones: list[dict], azar: random.Random) -> None:
    """!
    @brief Deja a lo más @ref MAXIMO_ENTREGA_FISICA de las operaciones por entrega física; el resto pasa a compensación.
    @param operaciones Operaciones.
    @param azar Generador aleatorio con semilla.
    """
    fisicas = [op for op in operaciones if op["modalidad_liquidacion"] == "ENTREGA_FISICA"]
    maximo = int(MAXIMO_ENTREGA_FISICA * len(operaciones))
    if len(fisicas) > maximo:
        conservar = {op["deal_number"] for op in azar.sample(fisicas, maximo)}
        for op in fisicas:
            if op["deal_number"] not in conservar:
                op["modalidad_liquidacion"] = "COMPENSACION"


def main() -> None:
    """!
    @brief Lee los archivos, filtra, convierte, asigna contraparte y modalidad, valida y escribe el SQL y el CSV de descartes.
    """
    operaciones, descartes = [], []

    for deal, patas in leer("fwds.csv").items():
        motivo = motivo_monedas(patas)
        if motivo:
            descartes.append((deal, "fwds.csv", motivo))
        else:
            operaciones.append(convertir_forward(deal, patas))

    for deal, patas in leer("swaps.csv").items():
        no_soportadas = sorted({p["type_rate"] for p in patas} - {"FIX", "FLOATCAM"})
        motivo = motivo_monedas(patas)
        if not motivo and any(p["amort"] != "BULLET" for p in patas):
            motivo = "amortización distinta de BULLET"
        if not motivo and no_soportadas:
            motivo = f"tipo de tasa no soportado por el modelo: {', '.join(no_soportadas)}"
        if motivo:
            descartes.append((deal, "swaps.csv", motivo))
        else:
            operaciones.append(convertir_swap(deal, patas))

    azar = random.Random(SEMILLA)
    azar_modalidad = random.Random(SEMILLA + 1)  # separado, para no alterar el reparto de contrapartes
    for op in operaciones:
        op["contraparte"] = azar.choice(CONTRAPARTES)
        sorteo = azar_modalidad.choice(["COMPENSACION", "ENTREGA_FISICA"])
        con_uf = any(p["moneda"] == "CLF" for p in op["patas"])
        op["modalidad_liquidacion"] = "COMPENSACION" if op["producto"] == "IR_SWAP" or con_uf else sorteo
    # Entrega física acotada a MAXIMO_ENTREGA_FISICA de la cartera; el resto pasa a compensación.
    _acotar_entrega_fisica(operaciones, random.Random(SEMILLA + 2))

    # Se dejan fuera las operaciones con monedas que no son de la cartera, y se vuelve a acotar
    # la entrega física sobre la cartera resultante.
    en_cartera = []
    for op in operaciones:
        fuera = sorted({p["moneda"] for p in op["patas"]} - MONEDAS_CARTERA)
        if fuera:
            archivo = "fwds.csv" if op["producto"] == "FX_FORWARD" else "swaps.csv"
            descartes.append((op["deal_number"], archivo, f"moneda fuera de alcance: {', '.join(fuera)}"))
        else:
            en_cartera.append(op)
    operaciones = en_cartera
    _acotar_entrega_fisica(operaciones, random.Random(SEMILLA + 3))

    for op in operaciones:
        validar(op)
    assert len({o["deal_number"] for o in operaciones}) == len(operaciones), "deal_number repetido"

    escribir_sql(operaciones, [d for d, _, _ in descartes])
    with open(CARPETA / "operaciones_descartadas.csv", "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["deal_number", "archivo", "motivo"])
        escritor.writerows(descartes)

    print("Cargadas:", dict(Counter(o["producto"] for o in operaciones)), "total", len(operaciones))
    print("Descartadas:", len(descartes))
    for (archivo, motivo), n in sorted(Counter((a, m.split(":")[0]) for _, a, m in descartes).items()):
        print(f"  {archivo:<10} {n:>5}  {motivo}")
    flotantes = Counter(p["indice"] for o in operaciones for p in o["patas"] if p["tipo"] == "INDICE_OVERNIGHT")
    print("Contrapartes:", dict(sorted(Counter(o["contraparte"] for o in operaciones).items())))
    print("Modalidad:", dict(Counter((o["producto"], o["modalidad_liquidacion"]) for o in operaciones)))
    print("Índices:", dict(flotantes))
    print("Patas por tipo:", dict(Counter((o["producto"], p["tipo"]) for o in operaciones for p in o["patas"])))
    print("Periodicidades:", dict(Counter(p["periodicidad"] for o in operaciones for p in o["patas"] if "periodicidad" in p)))
    inicios = [p["fecha_inicio"] for o in operaciones for p in o["patas"] if "fecha_inicio" in p]
    print("Swaps con inicio posterior a la fecha de proceso:",
          sum(1 for o in operaciones if any(p.get("fecha_inicio", FECHA_PROCESO) > FECHA_PROCESO for p in o["patas"])))
    print("Pagos en día no hábil:", sum(1 for o in operaciones for p in o["patas"] if not es_habil(p.get("fecha_pago") or p["fecha_fin"])))


if __name__ == "__main__":
    main()
