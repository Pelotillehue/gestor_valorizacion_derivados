"""!
@package comun.sesion
@brief Recuerda la sesión en una cookie del navegador, para no pedir las credenciales al actualizar la página o abrir otra pestaña.

La sesión de Streamlit (`st.session_state`) vive mientras dura la conexión de una pestaña: al
actualizar o abrir otra pestaña se crea una nueva y el token se pierde. Por eso, al iniciar
sesión, la app guarda también el token en la cookie @ref comun.sesion.NOMBRE_COOKIE, con el
mismo vencimiento que el token. Cuando una pestaña nueva se conecta, el navegador envía la
cookie, @ref comun.sesion.token_guardado la lee y la app la valida contra la API antes de usarla.

La cookie se escribe y se borra con JavaScript en el navegador (`st.html` con
`unsafe_allow_javascript`), porque Streamlit permite leer cookies pero no escribirlas. Por la
misma razón no puede ser HttpOnly. "Cerrar sesión" la borra; cerrar el navegador no, y la
sesión sigue disponible en ese equipo hasta que vence el token.
"""

import json
from datetime import datetime, timezone
from urllib.parse import unquote

import streamlit as st

## Nombre de la cookie con el token de sesión.
NOMBRE_COOKIE = "valorizador_sesion"


def token_guardado() -> str | None:
    """!
    @brief Token que el navegador envió en la cookie al conectarse esta pestaña.
    @return El token, o nada si no hay cookie. No dice si sigue vigente: eso lo valida la API.
    """
    valor = st.context.cookies.get(NOMBRE_COOKIE)
    return unquote(valor) if valor else None


def _escribir_cookie(valor: str, segundos: int | None) -> None:
    """!
    @brief Escribe la cookie desde el navegador. Con `Secure` cuando la app se sirve por HTTPS.
    @param valor Contenido de la cookie.
    @param segundos Duración; 0 la borra y nada la deja hasta que se cierre el navegador.
    """
    duracion = "" if segundos is None else f"; Max-Age={segundos}"
    st.html(
        f"""<script>
        document.cookie = {json.dumps(NOMBRE_COOKIE)} + "=" + encodeURIComponent({json.dumps(valor)})
            + "{duracion}; Path=/; SameSite=Strict"
            + (window.location.protocol === "https:" ? "; Secure" : "");
        </script>""",
        unsafe_allow_javascript=True,
    )


def guardar(token: str, vence: str | None) -> None:
    """!
    @brief Guarda el token en la cookie hasta su vencimiento.
    @param token Token entregado por `POST /auth/login`.
    @param vence Vencimiento del token en formato ISO, tal como lo entrega la API. Si falta, la
        cookie dura hasta que se cierre el navegador.
    """
    segundos = None
    if vence:
        segundos = int((datetime.fromisoformat(vence) - datetime.now(timezone.utc)).total_seconds())
        if segundos <= 0:
            return
    _escribir_cookie(token, segundos)


def borrar() -> None:
    """!
    @brief Borra la cookie del navegador.
    """
    _escribir_cookie("", 0)
