"""!
@package valorizador.cliente
@brief Inicio de sesión en la API para los scripts que la usan como cliente HTTP.

Toma el usuario y la clave de las variables de entorno `VALORIZADOR_USUARIO` y
`VALORIZADOR_CLAVE`; si no están, los pide por consola sin mostrar la clave.
"""

import getpass
import os

import httpx


def iniciar_sesion(api: httpx.Client) -> None:
    """!
    @brief Inicia sesión con `POST /auth/login` y deja el token en los headers del cliente.

    Si la API tiene la autenticación desactivada, no hace nada.
    @param api Cliente HTTP apuntando a la API del valorizador.
    @throws SystemExit Si las credenciales no son válidas.
    """
    if api.get("/auth/yo").status_code != 401:
        return
    usuario = os.environ.get("VALORIZADOR_USUARIO") or input("Usuario: ")
    clave = os.environ.get("VALORIZADOR_CLAVE") or getpass.getpass("Clave: ")
    respuesta = api.post("/auth/login", json={"usuario": usuario, "clave": clave})
    if respuesta.status_code == 401:
        raise SystemExit("Usuario o clave incorrectos")
    respuesta.raise_for_status()
    api.headers["Authorization"] = f"Bearer {respuesta.json()['token']}"
