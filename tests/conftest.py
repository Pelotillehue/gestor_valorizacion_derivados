"""!
@package tests.conftest
@brief Fixtures comunes de pytest.

Los tests del motor no necesitan base de datos. Los de la API usan la base indicada en
`DATABASE_URL_TEST` y borran y recrean sus tablas, por lo que debe ser una base exclusiva para
pruebas. Si la variable no está definida, esos tests se omiten.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ejemplos import datos
from valorizador.config import configuracion
from valorizador.seguridad import hash_clave
from valorizador.valorizacion.escenario import CurvaDatos, EscenarioMercado


## Usuario que se crea en la base de pruebas y con el que inicia sesión el cliente de la API.
USUARIO = "prueba@ejemplo.cl"
## Clave de ese usuario.
CLAVE = "clave-de-prueba"


@pytest.fixture
def escenario() -> EscenarioMercado:
    """!
    @brief El mercado de ejemplo de @ref ejemplos.datos como escenario en memoria.
    @return @ref valorizador.valorizacion.escenario.EscenarioMercado.
    """
    return EscenarioMercado(
        fecha=date.fromisoformat(datos.FECHA),
        fx={v["par"]: v["valor"] for v in datos.FX["valores"]},
        curvas={
            c["codigo"]: CurvaDatos(
                codigo=c["codigo"],
                plazos=tuple(v["plazo_dias"] for v in c["vertices"]),
                tasas=tuple(v["tasa"] for v in c["vertices"]),
            )
            for c in datos.CURVAS
        },
        indices={
            f["indice"]: {date.fromisoformat(v["fecha"]): v["valor"] for v in f["valores"]}
            for f in datos.INDICES
        },
        feriados={datos.FERIADOS["calendario"]: tuple(date.fromisoformat(f) for f in datos.FERIADOS["fechas"])},
    )


@pytest.fixture
def api():
    """!
    @brief Cliente de la API con sesión iniciada, sobre una base de pruebas recién creada, con las contrapartes de ejemplo.

    Reemplaza la dependencia de sesión de la aplicación por una sesión sobre `DATABASE_URL_TEST`.
    @return `TestClient` de FastAPI.
    """
    if not configuracion.database_url_test:
        pytest.skip("Defina DATABASE_URL_TEST para ejecutar los tests de la API")

    from fastapi.testclient import TestClient

    from valorizador.db import modelos  # noqa: F401
    from valorizador.db.base import Base, obtener_sesion
    from valorizador.main import app

    motor = create_engine(configuracion.database_url_test)
    Base.metadata.drop_all(motor)
    Base.metadata.create_all(motor)
    Sesion = sessionmaker(bind=motor, expire_on_commit=False)

    def sesion_de_prueba():
        """!
        @brief Sesión sobre la base de pruebas, con commit o rollback como la de producción.
        @return Generador que entrega la sesión.
        """
        sesion = Sesion()
        try:
            yield sesion
            sesion.commit()
        except Exception:
            sesion.rollback()
            raise
        finally:
            sesion.close()

    app.dependency_overrides[obtener_sesion] = sesion_de_prueba
    with Sesion() as sesion:
        sesion.add(modelos.Usuario(email=USUARIO, nombre="Usuario de prueba", hash_clave=hash_clave(CLAVE)))
        sesion.commit()
    with TestClient(app) as cliente:
        token = cliente.post("/auth/login", json={"usuario": USUARIO, "clave": CLAVE}).json()["token"]
        cliente.headers["Authorization"] = f"Bearer {token}"
        for contraparte in datos.CONTRAPARTES:  # las operaciones de ejemplo las referencian
            assert cliente.post("/contrapartes", json=contraparte).status_code == 201
        yield cliente
    app.dependency_overrides.clear()
    motor.dispose()


@pytest.fixture
def api_con_datos(api):
    """!
    @brief La API con el mercado y las tres operaciones de ejemplo ya cargados.
    @param api Fixture @ref tests.conftest.api.
    @return El mismo cliente.
    """
    assert api.post("/mercado/fx", json=datos.FX).status_code == 201
    assert api.post("/mercado/feriados", json=datos.FERIADOS).status_code == 201
    for curva in datos.CURVAS:
        assert api.post("/mercado/curvas", json=curva).status_code == 201
    for indice in datos.INDICES:
        assert api.post("/mercado/indices", json=indice).status_code == 201
    for operacion in datos.OPERACIONES:
        assert api.post("/operaciones", json=operacion).status_code == 201
    return api
