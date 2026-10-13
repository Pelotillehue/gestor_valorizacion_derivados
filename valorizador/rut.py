"""!
@package valorizador.rut
@brief RUT chileno: dígito verificador, normalización y formato.

En la base de datos el RUT se guarda normalizado, sin puntos y con guion: `76123456-K`.
"""

import re

## Expresión regular de un RUT limpio: hasta 8 dígitos, guion opcional y dígito verificador.
_PATRON = re.compile(r"^(\d{1,8})-?([\dK])$")


def digito_verificador(cuerpo: int) -> str:
    """!
    @brief Calcula el dígito verificador por módulo 11.
    @param cuerpo Parte numérica del RUT, sin dígito verificador.
    @return El dígito verificador: `0` a `9` o `K`.
    """
    suma, factor = 0, 2
    for digito in reversed(str(cuerpo)):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - suma % 11
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar(rut: str) -> str:
    """!
    @brief Valida un RUT y lo deja en la forma en que se guarda.

    Acepta puntos, espacios, guion opcional y `k` minúscula.
    @param rut RUT tal como lo ingresa el usuario, por ejemplo `76.123.456-k`.
    @return El RUT normalizado, por ejemplo `76123456-K`.
    @throws ValueError Si el formato no es válido o el dígito verificador no corresponde.
    """
    limpio = rut.strip().upper().replace(".", "").replace(" ", "")
    coincide = _PATRON.match(limpio)
    if not coincide:
        raise ValueError(f"RUT con formato inválido: {rut}")
    cuerpo, dv = int(coincide.group(1)), coincide.group(2)
    if digito_verificador(cuerpo) != dv:
        raise ValueError(f"RUT con dígito verificador inválido: {rut}")
    return f"{cuerpo}-{dv}"


def formatear(rut: str) -> str:
    """!
    @brief Formatea un RUT normalizado con puntos de miles para mostrarlo.
    @param rut RUT normalizado, por ejemplo `76123456-K`.
    @return El RUT con puntos, por ejemplo `76.123.456-K`.
    """
    cuerpo, dv = rut.split("-")
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
