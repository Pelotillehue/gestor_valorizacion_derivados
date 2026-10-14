"""!
@package cargar_tipos_cambio
@brief Carga en el valorizador tipos de cambio históricos del servicio de datos de mercado: EURCLP, USDCLP y UF.

Descarga cada serie del servicio y la guarda con `POST /mercado/fx`, una solicitud por fecha con
todos los pares de ese día. Se puede ejecutar más de una vez: los valores ya cargados se
actualizan y los demás pares de cada fecha no se tocan.

| Par    | Serie del servicio      |
|--------|-------------------------|
| EURCLP | pesos por euro          |
| USDCLP | pesos por dólar         |
| CLFCLP | valor de la UF en pesos |

Cada par se busca en el servicio entre varias rutas posibles (por ejemplo `/dolar` o `/usd`);
`--listar` muestra las rutas que ofrece el servicio, por si ninguna coincide.

Uso, desde la carpeta del proyecto, con la API corriendo:
@code
python scripts/cargar_tipos_cambio.py
python scripts/cargar_tipos_cambio.py --pares USDCLP CLFCLP --desde 2025-01-01 --hasta 2026-10-14
python scripts/cargar_tipos_cambio.py --api https://valorizador-api-xxxx.herokuapp.com
python scripts/cargar_tipos_cambio.py --listar
@endcode

El usuario y la clave de la API se piden por consola o se toman de `VALORIZADOR_USUARIO` y
`VALORIZADOR_CLAVE`.
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valorizador.cliente import iniciar_sesion  # noqa: E402

## Dirección del servicio de datos de mercado.
SERVICIO = "https://ab-market-data-4595e01f106a.herokuapp.com"
## Dirección de la API del valorizador; se puede cambiar con `--api` o la variable `VALORIZADOR_API_URL`.
API = os.environ.get("VALORIZADOR_API_URL", "http://localhost:8000")
## Primera fecha que se carga por defecto.
DESDE = date(2025, 1, 1)
## Rutas candidatas del servicio para cada par, en orden de preferencia; a cada una se le agrega `/{desde}/{hasta}`.
RUTAS = {
    "EURCLP": ["/euro", "/eur"],
    "USDCLP": ["/dolar", "/dollar", "/usd", "/dolar-observado", "/dolar_observado"],
    "CLFCLP": ["/uf", "/clf"],
}


def _campo(registro: dict, *nombres: str):
    """!
    @brief Primer campo presente de un registro del servicio.
    @param registro Registro JSON.
    @param nombres Nombres posibles del campo.
    @return Su valor.
    @throws KeyError Si no está ninguno.
    """
    for nombre in nombres:
        if nombre in registro:
            return registro[nombre]
    raise KeyError(f"El registro no trae ninguno de {nombres}: {registro}")


def descargar(servicio: httpx.Client, par: str, desde: date, hasta: date) -> tuple[str | None, dict[date, float]]:
    """!
    @brief Descarga la serie de un par probando sus rutas candidatas.
    @param servicio Cliente HTTP del servicio.
    @param par Par de @ref RUTAS.
    @param desde Primera fecha.
    @param hasta Última fecha.
    @return Tupla (ruta que respondió, diccionario fecha → valor); ruta nula si ninguna respondió.
    """
    for ruta in RUTAS[par]:
        respuesta = servicio.get(f"{ruta}/{desde.isoformat()}/{hasta.isoformat()}")
        if respuesta.status_code == 404:
            continue
        respuesta.raise_for_status()
        datos = respuesta.json()
        if isinstance(datos, dict):  # algunos servicios envuelven la lista
            datos = next((v for v in datos.values() if isinstance(v, list)), [])
        valores = {
            date.fromisoformat(str(_campo(r, "date", "fecha"))[:10]): float(_campo(r, "value", "valor"))
            for r in datos
        }
        return ruta, valores
    return None, {}


def main() -> int:
    """!
    @brief Lee los argumentos, descarga cada par y los carga fecha por fecha en la API.
    @return Código de salida: 0 si todo se cargó.
    """
    parser = argparse.ArgumentParser(description="Carga en el valorizador tipos de cambio históricos: EURCLP, USDCLP y UF.")
    parser.add_argument("--pares", nargs="+", default=list(RUTAS), choices=list(RUTAS), help="Pares a cargar (por defecto todos)")
    parser.add_argument("--desde", default=DESDE, type=date.fromisoformat, help=f"Primera fecha, AAAA-MM-DD (por defecto {DESDE})")
    parser.add_argument("--hasta", default=date.today(), type=date.fromisoformat, help="Última fecha, AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--api", default=API, help=f"Dirección del valorizador (por defecto {API})")
    parser.add_argument("--servicio", default=SERVICIO, help="Dirección del servicio de datos de mercado")
    parser.add_argument("--listar", action="store_true", help="Sólo muestra las rutas que ofrece el servicio")
    args = parser.parse_args()

    por_fecha: dict[date, list[dict]] = defaultdict(list)
    faltantes = []
    with httpx.Client(base_url=args.servicio, timeout=120) as servicio:
        if args.listar:
            for ruta in sorted(servicio.get("/openapi.json").raise_for_status().json()["paths"]):
                print(ruta)
            return 0
        for par in args.pares:
            ruta, valores = descargar(servicio, par, args.desde, args.hasta)
            if not valores:
                faltantes.append(par)
                print(f"{par}: sin datos (rutas probadas: {', '.join(RUTAS[par])}). Use --listar para ver las del servicio.")
                continue
            print(f"{par}: {len(valores)} valores de {ruta}, del {min(valores):%d-%m-%Y} al {max(valores):%d-%m-%Y}; último {valores[max(valores)]}")
            for fecha, valor in valores.items():
                por_fecha[fecha].append({"par": par, "valor": valor})

    errores = 0
    if por_fecha:
        with httpx.Client(base_url=args.api, timeout=60) as api:
            iniciar_sesion(api)
            for fecha in sorted(por_fecha):
                respuesta = api.post("/mercado/fx", json={"fecha": fecha.isoformat(), "valores": por_fecha[fecha]})
                if respuesta.status_code >= 400:
                    errores += 1
                    print(f"{fecha}: {respuesta.status_code} {respuesta.text[:200]}")
        print(f"Cargadas {len(por_fecha) - errores} de {len(por_fecha)} fechas.")
    return 1 if errores or faltantes else 0


if __name__ == "__main__":
    sys.exit(main())
