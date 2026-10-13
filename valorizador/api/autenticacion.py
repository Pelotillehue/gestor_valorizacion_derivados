"""!
@package valorizador.api.autenticacion
@brief Inicio de sesión y dependencia que protege los demás endpoints.

`POST /auth/login` recibe correo y clave, los compara con la tabla `usuario` y entrega un
token de sesión. Los demás endpoints, salvo `/salud`, exigen ese token en el header
`Authorization: Bearer <token>` mediante @ref valorizador.api.autenticacion.usuario_actual,
a menos que @ref valorizador.config.Configuracion.requerir_autenticacion sea falso.
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from valorizador import seguridad
from valorizador.config import configuracion
from valorizador.db import modelos
from valorizador.db.base import obtener_sesion

## Router montado en `/auth`.
router = APIRouter(prefix="/auth", tags=["Autenticación"])

## Sesión de base de datos, inyectada por FastAPI con @ref valorizador.db.base.obtener_sesion.
Sesion = Annotated[Session, Depends(obtener_sesion)]
## Lee el header `Authorization: Bearer`. No falla solo, para responder siempre 401 en español.
_portador = HTTPBearer(auto_error=False, description="Token entregado por POST /auth/login")


class Credenciales(BaseModel):
    """!
    @brief Correo y clave para iniciar sesión (`POST /auth/login`).
    """

    ## Correo del usuario; no distingue mayúsculas.
    usuario: str = Field(min_length=1, max_length=100, examples=["usuario@empresa.cl"])
    ## Clave en texto plano; viaja sólo en esta solicitud.
    clave: str = Field(min_length=1, max_length=200)


class SesionUsuario(BaseModel):
    """!
    @brief Respuesta de `POST /auth/login` y `GET /auth/yo`.
    """

    ## Correo del usuario.
    usuario: str
    ## Nombre para mostrar.
    nombre: str | None = None
    ## Token para el header `Authorization: Bearer`. Vacío en `GET /auth/yo`.
    token: str = ""
    ## Vencimiento del token.
    vence: datetime | None = None


def _no_autorizado(mensaje: str) -> HTTPException:
    """!
    @brief Error 401 con el header que indica el esquema Bearer.
    @param mensaje Detalle.
    @return Excepción para lanzar.
    """
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=mensaje, headers={"WWW-Authenticate": "Bearer"})


def usuario_actual(
    db: Sesion, credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_portador)]
) -> modelos.Usuario | None:
    """!
    @brief Dependencia que exige un token válido de un usuario activo.
    @param db Sesión de base de datos.
    @param credenciales Header `Authorization`, si viene.
    @return El usuario, o nada si la autenticación está desactivada.
    @throws HTTPException 401 si falta el token, es inválido, venció o el usuario está inactivo.
    """
    if not configuracion.requerir_autenticacion:
        return None
    if credenciales is None:
        raise _no_autorizado("Debe iniciar sesión")
    email = seguridad.leer_token(credenciales.credentials)
    usuario = db.get(modelos.Usuario, email) if email else None
    if usuario is None or not usuario.activo:
        raise _no_autorizado("La sesión no es válida o venció; inicie sesión nuevamente")
    return usuario


@router.post("/login", response_model=SesionUsuario, summary="Inicia sesión y entrega un token")
def login(credenciales: Credenciales, db: Sesion):
    """!
    @brief Valida correo y clave contra la tabla `usuario` y entrega un token de sesión.
    @param credenciales Correo y clave.
    @param db Sesión de base de datos.
    @return Usuario, nombre, token y vencimiento.
    @throws HTTPException 401 si el correo no existe, la clave no corresponde o el usuario está inactivo.
    """
    usuario = db.get(modelos.Usuario, credenciales.usuario.strip().lower())
    if usuario is None or not usuario.activo or not seguridad.verificar_clave(credenciales.clave, usuario.hash_clave):
        raise _no_autorizado("Usuario o clave incorrectos")
    usuario.ultimo_ingreso = datetime.now(timezone.utc)
    token, vence = seguridad.crear_token(usuario.email, configuracion.horas_sesion)
    return SesionUsuario(
        usuario=usuario.email, nombre=usuario.nombre, token=token, vence=datetime.fromtimestamp(vence, timezone.utc)
    )


@router.get("/yo", response_model=SesionUsuario, summary="Usuario de la sesión actual")
def yo(usuario: Annotated[modelos.Usuario | None, Depends(usuario_actual)]):
    """!
    @brief Verifica el token y devuelve su usuario. La app lo usa para saber si la sesión sigue vigente.
    @param usuario Usuario del token.
    @return Usuario y nombre; si la autenticación está desactivada, un usuario anónimo.
    """
    if usuario is None:
        return SesionUsuario(usuario="anonimo")
    return SesionUsuario(usuario=usuario.email, nombre=usuario.nombre)
