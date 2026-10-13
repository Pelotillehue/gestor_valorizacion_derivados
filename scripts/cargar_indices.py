"""!
@package cargar_indices
@brief Carga en el valorizador los valores del ICP y del índice SOFR que necesita la cartera vigente.

Los toma del servicio de datos de mercado y los envía a `POST /mercado/indices`, con la API
del valorizador corriendo. Se puede ejecutar más de una vez: los valores ya cargados se
actualizan.

Uso, desde la carpeta del proyecto:
@code
python scripts/cargar_indices.py --fecha 2026-08-17
python scripts/cargar_indices.py --fecha 2026-08-17 --api http://localhost:8001
python scripts/cargar_indices.py --desde 2026-08-01 --fecha 2026-08-25
@endcode

Para cada índice se cargan todos los valores publicados desde el 01-01-2025, o desde antes si
alguna pata flotante vigente empieza antes, hasta la fecha de proceso. La fecha inicial se
puede cambiar con `--desde`. El usuario y la clave de la API se piden por consola o se toman
de `VALORIZADOR_USUARIO` y `VALORIZADOR_CLAVE`.
"""

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valorizador.cliente import iniciar_sesion  # noqa: E402

## Dirección del servicio de datos de mercado del que se descargan los índices.
SERVICIO = "https://ab-market-data-4595e01f106a.herokuapp.com"
## Dirección de la API del valorizador; se puede cambiar con `--api` o la variable `VALORIZADOR_API_URL`.
API = os.environ.get("VALORIZADOR_API_URL", "http://localhost:8000")

## Ruta del servicio para cada índice, con las fechas desde y hasta.
RUTAS = {
    "ICP": "/icp/{desde}/{hasta}",
    "SOFRINDX": "/sofr/index/{desde}/{hasta}",
}
## Días que se agregan antes del inicio más antiguo, por si esa fecha se ajusta a un día hábil anterior.
DIAS_HOLGURA = 10
## Primera fecha que se carga si ninguna pata empieza antes.
DESDE = date(2025, 1, 1)
## Operaciones por página al recorrer `GET /operaciones`.
TAMANO_PAGINA = 1000


def operaciones_vigentes(api: httpx.Client) -> list[dict]:
    """!
    @brief Todas las operaciones vigentes del valorizador, recorriendo las páginas.
    @param api Cliente HTTP de la API.
    @return Operaciones.
    @throws httpx.HTTPStatusError Si la API responde con error.
    """
    resultado, desde = [], 0
    while True:
        pagina = api.get("/operaciones", params={"estado": "VIGENTE", "limite": TAMANO_PAGINA, "desde": desde})
        pagina.raise_for_status()
        resultado += pagina.json()
        if len(pagina.json()) < TAMANO_PAGINA:
            return resultado
        desde += TAMANO_PAGINA


def inicio_por_indice(operaciones: list[dict]) -> dict[str, date]:
    """!
    @brief Fecha de inicio más antigua de las patas flotantes de cada índice.
    @param operaciones Operaciones vigentes.
    @return Diccionario índice → fecha.
    """
    inicios: dict[str, date] = {}
    for operacion in operaciones:
        for pata in operacion["patas"]:
            if pata["tipo"] == "INDICE_OVERNIGHT":
                inicio = date.fromisoformat(pata["fecha_inicio"])
                inicios[pata["indice"]] = min(inicio, inicios.get(pata["indice"], inicio))
    return inicios


def descargar(servicio: httpx.Client, indice: str, desde: date, hasta: date) -> dict[date, float]:
    """!
    @brief Descarga los valores de un índice del servicio de datos de mercado.
    @param servicio Cliente HTTP del servicio.
    @param indice `ICP` o `SOFRINDX`.
    @param desde Primera fecha.
    @param hasta Última fecha.
    @return Diccionario fecha → valor.
    @throws httpx.HTTPStatusError Si el servicio responde con error.
    """
    ruta = RUTAS[indice].format(desde=desde.isoformat(), hasta=hasta.isoformat())
    respuesta = servicio.get(ruta)
    respuesta.raise_for_status()
    return {date.fromisoformat(v["date"][:10]): float(v["value"]) for v in respuesta.json()}


def main() -> int:
    """!
    @brief Lee los argumentos, descarga cada índice y lo carga en la API.
    @return Código de salida: 0 si todo se cargó.
    """
    parser = argparse.ArgumentParser(description="Carga en el valorizador los valores del ICP y del índice SOFR.")
    parser.add_argument("--fecha", required=True, type=date.fromisoformat, help="Fecha de proceso, AAAA-MM-DD")
    parser.add_argument("--api", default=API, help=f"Dirección del valorizador (por defecto {API})")
    parser.add_argument("--servicio", default=SERVICIO, help="Dirección del servicio de datos de mercado")
    parser.add_argument(
        "--desde", default=DESDE, type=date.fromisoformat, help=f"Primera fecha a cargar (por defecto {DESDE})"
    )
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=120) as api, httpx.Client(base_url=args.servicio, timeout=120) as servicio:
        iniciar_sesion(api)
        inicios = inicio_por_indice(operaciones_vigentes(api))
        if not inicios:
            print("La cartera vigente no tiene patas flotantes.")
            return 0

        sin_ruta = sorted(set(inicios) - set(RUTAS))
        if sin_ruta:
            print(f"Sin fuente para: {', '.join(sin_ruta)}. Esas patas seguirán sin valorizar.")

        hubo_error = False
        for indice in sorted(set(inicios) & set(RUTAS)):
            # Desde --desde, o antes si una pata vigente lo necesita.
            desde = min(args.desde, inicios[indice] - timedelta(days=DIAS_HOLGURA))
            valores = descargar(servicio, indice, desde, args.fecha)
            if not valores:
                print(f"{indice}: el servicio no devolvió valores entre {desde} y {args.fecha}.")
                hubo_error = True
                continue
            carga = {
                "indice": indice,
                "valores": [{"fecha": f.isoformat(), "valor": v} for f, v in sorted(valores.items())],
            }
            api.post("/mercado/indices", json=carga).raise_for_status()
            print(
                f"{indice}: {len(valores)} valores del {min(valores):%d-%m-%Y} al {max(valores):%d-%m-%Y}; "
                f"último {valores[max(valores)]}"
            )
            if args.fecha not in valores:
                print(f"  Atención: no hay valor publicado para la fecha de proceso {args.fecha:%d-%m-%Y}.")
                hubo_error = True
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main())
