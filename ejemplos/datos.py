"""!
@package ejemplos.datos
@brief Datos de ejemplo: mercado del 6 de octubre de 2026, dos contrapartes y una operación de cada producto.

Los usan @ref ejemplos.cargar_ejemplo y los tests.
"""

## Fecha del mercado de ejemplo.
FECHA = "2026-10-06"

## Tipos de cambio de la fecha.
FX = {
    "fecha": FECHA,
    "valores": [
        {"par": "USDCLP", "valor": 950.0},
        {"par": "CLFCLP", "valor": 39500.0},  # valor de la UF
    ],
}

## Curvas cero de la fecha.
CURVAS = [
    {
        "fecha": FECHA,
        "codigo": "CLP_CAMARA",
        "fraccion_anio": "ACT365",
        "factor_capitalizacion": "COM",
        "vertices": [
            {"plazo_dias": 1, "tasa": 0.0450},
            {"plazo_dias": 180, "tasa": 0.0460},
            {"plazo_dias": 365, "tasa": 0.0475},
            {"plazo_dias": 730, "tasa": 0.0490},
            {"plazo_dias": 1825, "tasa": 0.0510},
        ],
    },
    {
        "fecha": FECHA,
        "codigo": "CLF_CAMARA",
        "fraccion_anio": "ACT365",
        "factor_capitalizacion": "COM",
        "vertices": [
            {"plazo_dias": 1, "tasa": 0.0150},
            {"plazo_dias": 365, "tasa": 0.0180},
            {"plazo_dias": 730, "tasa": 0.0200},
            {"plazo_dias": 1825, "tasa": 0.0230},
        ],
    },
    {
        "fecha": FECHA,
        "codigo": "USD_SOFR",
        "fraccion_anio": "ACT365",
        "factor_capitalizacion": "COM",
        "vertices": [
            {"plazo_dias": 1, "tasa": 0.0400},
            {"plazo_dias": 180, "tasa": 0.0410},
            {"plazo_dias": 365, "tasa": 0.0420},
            {"plazo_dias": 730, "tasa": 0.0430},
            {"plazo_dias": 1825, "tasa": 0.0440},
        ],
    },
]

## Valores publicados de ICP y SOFRINDX.
INDICES = [
    {
        "indice": "ICP",
        "valores": [
            {"fecha": "2026-07-06", "valor": 24000.00},
            {"fecha": FECHA, "valor": 24270.00},
        ],
    },
    {
        "indice": "SOFRINDX",
        "valores": [
            {"fecha": "2026-08-10", "valor": 1.265000},
            {"fecha": FECHA, "valor": 1.273000},
        ],
    },
]

## Feriados del calendario SCL.
FERIADOS = {
    "calendario": "SCL",
    "fechas": ["2026-10-12", "2026-12-08", "2026-12-25", "2027-01-01", "2027-05-21", "2027-12-08", "2028-05-01"],
}

## Contrapartes ficticias, con RUT ficticio. La línea y el MTA están en CLP.
CONTRAPARTES = [
    {"rut": "77700100-0", "nombre": "Banco Ejemplo", "monto_linea": 50_000_000, "mta": 5_000_000},
    {"rut": "77700200-7", "nombre": "Otro Banco", "monto_linea": 0, "mta": 0},
]

## Compra de USD 1.000.000 a 955 el 6 de enero de 2027.
FX_FORWARD = {
    "deal_number": "FWD-0001",
    "producto": "FX_FORWARD",
    "rut_contraparte": "77700100-0",
    "fecha_negociacion": "2026-09-01",
    "patas": [
        {
            "numero": 1,
            "tipo": "SIMPLE",
            "rec_pay": "RECIBE",
            "moneda": "USD",
            "nocional": 1_000_000.0,
            "curva_descuento": "USD_SOFR",
            "fecha_pago": "2027-01-06",
        },
        {
            "numero": 2,
            "tipo": "SIMPLE",
            "rec_pay": "PAGA",
            "moneda": "CLP",
            "nocional": 955_000_000.0,
            "curva_descuento": "CLP_CAMARA",
            "fecha_pago": "2027-01-06",
        },
    ],
}

## Swap promedio cámara: recibe 5% fijo, paga ICP, CLP 1.000 millones, 2 años, semestral.
IR_SWAP = {
    "deal_number": "IRS-0001",
    "producto": "IR_SWAP",
    "rut_contraparte": "77700100-0",
    "fecha_negociacion": "2026-07-03",
    "patas": [
        {
            "numero": 1,
            "tipo": "FIJA",
            "rec_pay": "RECIBE",
            "moneda": "CLP",
            "nocional": 1_000_000_000.0,
            "curva_descuento": "CLP_CAMARA",
            "fecha_inicio": "2026-07-06",
            "fecha_fin": "2028-07-06",
            "periodicidad": "6M",
            "calendario": "SCL",
            "tasa": 0.05,
            "fraccion_anio": "ACT360",
            "factor_capitalizacion": "LIN",
        },
        {
            "numero": 2,
            "tipo": "INDICE_OVERNIGHT",
            "rec_pay": "PAGA",
            "moneda": "CLP",
            "nocional": 1_000_000_000.0,
            "curva_descuento": "CLP_CAMARA",
            "fecha_inicio": "2026-07-06",
            "fecha_fin": "2028-07-06",
            "periodicidad": "6M",
            "calendario": "SCL",
            "indice": "ICP",
            "curva_proyeccion": "CLP_CAMARA",
            "decimales_tasa": 4,
        },
    ],
}

## Cross currency swap: recibe 2,5% fijo sobre UF 100.000, paga SOFR sobre USD 4.150.000, 3 años, semestral, con intercambio de nocionales al vencimiento.
CC_SWAP = {
    "deal_number": "CCS-0001",
    "producto": "CC_SWAP",
    "rut_contraparte": "77700100-0",
    "fecha_negociacion": "2026-08-06",
    "patas": [
        {
            "numero": 1,
            "tipo": "FIJA",
            "rec_pay": "RECIBE",
            "moneda": "CLF",
            "nocional": 100_000.0,
            "curva_descuento": "CLF_CAMARA",
            "fecha_inicio": "2026-08-10",
            "fecha_fin": "2029-08-10",
            "periodicidad": "6M",
            "calendario": "SCL",
            "intercambia_nocional": True,
            "tasa": 0.025,
            "fraccion_anio": "ACT360",
            "factor_capitalizacion": "LIN",
        },
        {
            "numero": 2,
            "tipo": "INDICE_OVERNIGHT",
            "rec_pay": "PAGA",
            "moneda": "USD",
            "nocional": 4_150_000.0,
            "curva_descuento": "USD_SOFR",
            "fecha_inicio": "2026-08-10",
            "fecha_fin": "2029-08-10",
            "periodicidad": "6M",
            "calendario": "SCL",
            "intercambia_nocional": True,
            "indice": "SOFRINDX",
            "curva_proyeccion": "USD_SOFR",
            "decimales_tasa": 6,
        },
    ],
}

## Las tres operaciones de ejemplo.
OPERACIONES = [FX_FORWARD, IR_SWAP, CC_SWAP]
