"""!
@package cargar_euro
@brief Carga en el valorizador el tipo de cambio EURCLP histórico del servicio de datos de mercado.

Descarga los valores del euro en pesos (`/euro/{desde}/{hasta}`) y los guarda como el par
`EURCLP` con `POST /mercado/fx`, una fecha por solicitud. Se puede ejecutar más de una vez: los
valores ya cargados se actualizan y los demás pares de cada fecha no se tocan.

Uso, desde la carpeta del proyecto, con la API corriendo:
@code
python scripts/cargar_euro.py
python scripts/cargar_euro.py --desde 2025-01-01 --hasta 2026-10-14
python scripts/cargar_euro.py --api https://valorizador-api-xxxx.herokuapp.com
@endcode

El usuario y la clave de la API se piden por consola o se toman de `VALORIZADOR_USUARIO` y
`VALORIZADOR_CLAVE`.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from valorizador.cliente import iniciar_sesion  # noqa: E402

## Dirección del servicio de datos de mercado.
SERVICIO = "https://ab-market-data-4595e01f106a.herokuapp.com"
## Dirección de la API del valorizador; se puede cambiar con `--api` o la variable `VALORIZADOR_API_URL`.
API = os.environ.get("VALORIZADOR_API_URL", "http://localhost:8000")
## Par con que se guarda el valor del euro: pesos por euro.
PAR = "EURCLP"
## Primera fecha que se carga por defecto.
DESDE = date(2025, 1, 1)


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


def descargar(servicio: httpx.Client, desde: date, hasta: date) -> dict[date, float]:
    """!
    @brief Descarga el valor del euro en pesos entre dos fechas.
    @param servicio Cliente HTTP del servicio.
    @param desde Primera fecha.
    @param hasta Última fecha.
    @return Diccionario fecha → pesos por euro.
    @throws httpx.HTTPStatusError Si el servicio responde con error.
    """
    respuesta = servicio.get(f"/euro/{desde.isoformat()}/{hasta.isoformat()}")
    respuesta.raise_for_status()
    datos = respuesta.json()
    if isinstance(datos, dict):  # algunos servicios envuelven la lista
        datos = next((v for v in datos.values() if isinstance(v, list)), [])
    return {
        date.fromisoformat(str(_campo(r, "date", "fecha"))[:10]): float(_campo(r, "value", "valor"))
        for r in datos
    }


def main() -> int:
    """!
    @brief Lee los argumentos, descarga el EURCLP y lo carga fecha por fecha en la API.
    @return Código de salida: 0 si todo se cargó.
    """
    parser = argparse.ArgumentParser(description="Carga en el valorizador el tipo de cambio EURCLP histórico.")
    parser.add_argument("--desde", default=DESDE, type=date.fromisoformat, help=f"Primera fecha, AAAA-MM-DD (por defecto {DESDE})")
    parser.add_argument("--hasta", default=date.today(), type=date.fromisoformat, help="Última fecha, AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--api", default=API, help=f"Dirección del valorizador (por defecto {API})")
    parser.add_argument("--servicio", default=SERVICIO, help="Dirección del servicio de datos de mercado")
    args = parser.parse_args()

    with httpx.Client(base_url=args.servicio, timeout=120) as servicio:
        valores = descargar(servicio, args.desde, args.hasta)
    if not valores:
        print(f"El servicio no devolvió valores del euro entre {args.desde} y {args.hasta}.")
        return 1

    errores = 0
    with httpx.Client(base_url=args.api, timeout=60) as api:
        iniciar_sesion(api)
        for fecha, valor in sorted(valores.items()):
            respuesta = api.post("/mercado/fx", json={"fecha": fecha.isoformat(), "valores": [{"par": PAR, "valor": valor}]})
            if respuesta.status_code >= 400:
                errores += 1
                print(f"{fecha}: {respuesta.status_code} {respuesta.text[:200]}")
    print(
        f"{PAR}: {len(valores) - errores} de {len(valores)} valores cargados, del {min(valores):%d-%m-%Y} "
        f"al {max(valores):%d-%m-%Y}; último {valores[max(valores)]}"
    )
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
