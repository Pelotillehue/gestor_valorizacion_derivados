"""!
@package valorizador.seguridad
@brief Claves de usuario y tokens de sesión, sólo con la biblioteca estándar.

Las claves se guardan como hash PBKDF2-SHA256 con sal aleatoria, nunca en texto plano. Los
tokens de sesión son el correo del usuario y su vencimiento, firmados con HMAC-SHA256 usando
@ref valorizador.config.Configuracion.clave_secreta.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from valorizador.config import configuracion

## Algoritmo con que se guarda el hash, como prefijo del texto almacenado.
_ALGORITMO = "pbkdf2_sha256"
## Iteraciones de PBKDF2. Hacen lento probar claves por fuerza bruta.
_ITERACIONES = 600_000
## Clave de firma de los tokens. Si no se configura, se genera una al iniciar la API, y los
## tokens dejan de valer cada vez que la API se reinicia.
_CLAVE_FIRMA = (configuracion.clave_secreta or secrets.token_hex(32)).encode()


def hash_clave(clave: str) -> str:
    """!
    @brief Calcula el hash de una clave para guardarlo.
    @param clave Clave en texto plano.
    @return Texto `pbkdf2_sha256$iteraciones$sal$hash`, con sal y hash en hexadecimal.
    """
    sal = secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal, _ITERACIONES)
    return f"{_ALGORITMO}${_ITERACIONES}${sal.hex()}${derivada.hex()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    """!
    @brief Compara una clave con su hash guardado, en tiempo constante.
    @param clave Clave en texto plano.
    @param guardado Resultado de @ref valorizador.seguridad.hash_clave.
    @return Verdadero si la clave corresponde.
    """
    try:
        algoritmo, iteraciones, sal, derivada = guardado.split("$")
    except ValueError:
        return False
    if algoritmo != _ALGORITMO:
        return False
    calculada = hashlib.pbkdf2_hmac("sha256", clave.encode(), bytes.fromhex(sal), int(iteraciones))
    return hmac.compare_digest(calculada.hex(), derivada)


def _b64(datos: bytes) -> str:
    """!
    @brief Base64 para URL, sin relleno.
    @param datos Bytes.
    @return Texto.
    """
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _firma(cuerpo: str) -> str:
    """!
    @brief Firma HMAC-SHA256 de un texto.
    @param cuerpo Texto a firmar.
    @return Firma en base64.
    """
    return _b64(hmac.new(_CLAVE_FIRMA, cuerpo.encode(), hashlib.sha256).digest())


def crear_token(usuario: str, duracion_horas: float) -> tuple[str, int]:
    """!
    @brief Emite un token de sesión.
    @param usuario Correo del usuario.
    @param duracion_horas Horas de validez.
    @return Tupla (token, vencimiento en segundos desde 1970).
    """
    vence = int(time.time() + duracion_horas * 3600)
    cuerpo = _b64(json.dumps({"u": usuario, "v": vence}, separators=(",", ":")).encode())
    return f"{cuerpo}.{_firma(cuerpo)}", vence


def leer_token(token: str) -> str | None:
    """!
    @brief Valida la firma y el vencimiento de un token.
    @param token Token emitido por @ref valorizador.seguridad.crear_token.
    @return El correo del usuario, o nada si el token no es válido o venció.
    """
    try:
        cuerpo, firma = token.split(".")
        if not hmac.compare_digest(firma, _firma(cuerpo)):
            return None
        datos = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
    except (ValueError, TypeError):
        return None
    if datos.get("v", 0) < time.time():
        return None
    return datos.get("u")
