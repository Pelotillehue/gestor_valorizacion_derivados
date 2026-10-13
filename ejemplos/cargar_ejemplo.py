"""!
@package ejemplos.cargar_ejemplo
@brief Carga los datos de ejemplo en una API en ejecución y muestra el MtM de cada operación.

Uso, con la API corriendo en otra terminal:
@code
python -m ejemplos.cargar_ejemplo
python -m ejemplos.cargar_ejemplo http://localhost:8000
@endcode
"""

import sys

import httpx

from ejemplos import datos


def main(url_base: str) -> None:
    """!
    @brief Carga mercado, contrapartes y operaciones, y muestra el MtM de cada una.
    @param url_base Dirección de la API.
    """
    with httpx.Client(base_url=url_base, timeout=30) as api:
        api.post("/mercado/fx", json=datos.FX).raise_for_status()
        api.post("/mercado/feriados", json=datos.FERIADOS).raise_for_status()
        for curva in datos.CURVAS:
            api.post("/mercado/curvas", json=curva).raise_for_status()
        for indice in datos.INDICES:
            api.post("/mercado/indices", json=indice).raise_for_status()

        for contraparte in datos.CONTRAPARTES:
            respuesta = api.post("/contrapartes", json=contraparte)
            if respuesta.status_code not in (201, 409):  # 409: ya estaba registrada
                respuesta.raise_for_status()

        for operacion in datos.OPERACIONES:
            respuesta = api.post("/operaciones", json=operacion)
            if respuesta.status_code not in (201, 409):  # 409: ya estaba cargada
                respuesta.raise_for_status()

        print(f"MtM en CLP al {datos.FECHA}")
        for operacion in datos.OPERACIONES:
            deal = operacion["deal_number"]
            mtm = api.get(f"/operaciones/{deal}/mtm", params={"fecha": datos.FECHA}).raise_for_status().json()
            print(f"  {deal:<10} {mtm['mtm']:>20,.0f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
