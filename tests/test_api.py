"""!
@package tests.test_api
@brief Tests de la API completa sobre una base PostgreSQL de pruebas.

Requieren la variable `DATABASE_URL_TEST`; si no está definida, se omiten.
"""

from datetime import date

import pytest

from ejemplos import datos
from valorizador.schemas.operaciones import OperacionEntrada
from valorizador.valorizacion import motor

FECHA = {"fecha": datos.FECHA}


def test_salud(api):
    """!
    @brief `GET /salud` responde.
    """
    assert api.get("/salud").json() == {"estado": "ok"}


# ------------------------------------------------------------------------ operaciones


def test_alta_y_consulta(api):
    """!
    @brief Una operación dada de alta se lee igual, en versión 1 y vigente.
    """
    creada = api.post("/operaciones", json=datos.IR_SWAP)
    assert creada.status_code == 201
    assert creada.json()["estado"] == "VIGENTE"
    assert creada.json()["version"] == 1
    assert creada.json()["fecha_vencimiento"] == "2028-07-06"

    leida = api.get("/operaciones/IRS-0001").json()
    assert leida["producto"] == "IR_SWAP"
    assert [p["tipo"] for p in leida["patas"]] == ["FIJA", "INDICE_OVERNIGHT"]
    assert leida["patas"][0]["tasa"] == 0.05
    assert leida["patas"][1]["indice"] == "ICP"
    # Lo que devuelve la API se puede volver a enviar como alta.
    reenviable = {k: leida[k] for k in datos.IR_SWAP}
    assert OperacionEntrada.model_validate(reenviable) == OperacionEntrada.model_validate(datos.IR_SWAP)


def test_alta_duplicada(api):
    """!
    @brief Un folio repetido se rechaza con 409.
    """
    assert api.post("/operaciones", json=datos.FX_FORWARD).status_code == 201
    repetida = api.post("/operaciones", json=datos.FX_FORWARD)
    assert repetida.status_code == 409
    assert "FWD-0001" in repetida.json()["detail"]


def test_alta_invalida(api):
    """!
    @brief Patas incompletas o campos desconocidos se rechazan con 422.
    """
    sin_pata = {**datos.FX_FORWARD, "patas": datos.FX_FORWARD["patas"][:1]}
    assert api.post("/operaciones", json=sin_pata).status_code == 422
    campo_desconocido = {**datos.FX_FORWARD, "otro": 1}
    assert api.post("/operaciones", json=campo_desconocido).status_code == 422


def test_operacion_inexistente(api):
    """!
    @brief Los endpoints de una operación que no existe responden 404.
    """
    for ruta in ("", "/vencimiento", "/historial"):
        assert api.get(f"/operaciones/NO-EXISTE{ruta}").status_code == 404
    assert api.get("/operaciones/NO-EXISTE/mtm", params=FECHA).status_code == 404
    assert api.patch("/operaciones/NO-EXISTE", json={"grupo_calce": "X"}).status_code == 404


def test_lista_con_filtros(api_con_datos):
    """!
    @brief El listado se ordena por folio y filtra por producto.
    """
    todas = api_con_datos.get("/operaciones").json()
    assert [o["deal_number"] for o in todas] == ["CCS-0001", "FWD-0001", "IRS-0001"]
    swaps = api_con_datos.get("/operaciones", params={"producto": "IR_SWAP"}).json()
    assert [o["deal_number"] for o in swaps] == ["IRS-0001"]


def test_vencimiento(api_con_datos):
    """!
    @brief Vencimiento contractual, último pago y días hasta él.
    """
    respuesta = api_con_datos.get("/operaciones/CCS-0001/vencimiento", params=FECHA).json()
    assert respuesta == {
        "deal_number": "CCS-0001",
        "fecha_vencimiento_contractual": "2029-08-10",
        "fecha_ultimo_pago": "2029-08-10",
        "dias_al_ultimo_pago": (date(2029, 8, 10) - date(2026, 10, 6)).days,
    }
    sin_fecha = api_con_datos.get("/operaciones/FWD-0001/vencimiento").json()
    assert sin_fecha["fecha_ultimo_pago"] == "2027-01-06"
    assert sin_fecha["dias_al_ultimo_pago"] is None


# ----------------------------------------------------------------------- modificación


def test_modificar_datos_generales(api_con_datos):
    """!
    @brief Cambiar la contraparte sube la versión y deja la anterior en el historial.
    """
    respuesta = api_con_datos.patch("/operaciones/FWD-0001", json={"rut_contraparte": "77.700.200-7"})
    assert respuesta.status_code == 200
    assert respuesta.json()["rut_contraparte"] == "77700200-7"
    assert respuesta.json()["contraparte"] == "Otro Banco"
    assert respuesta.json()["version"] == 2
    assert len(respuesta.json()["patas"]) == 2

    historial = api_con_datos.get("/operaciones/FWD-0001/historial").json()
    assert len(historial) == 1
    assert historial[0]["version"] == 1
    assert historial[0]["datos"]["contraparte"] == "Banco Ejemplo"


def test_modificar_patas_cambia_el_mtm(api_con_datos):
    """!
    @brief Cambiar la tasa de una pata cambia el MtM.
    """
    antes = api_con_datos.get("/operaciones/IRS-0001/mtm", params=FECHA).json()["mtm"]

    patas = [dict(p) for p in datos.IR_SWAP["patas"]]
    patas[0]["tasa"] = 0.06
    respuesta = api_con_datos.patch("/operaciones/IRS-0001", json={"patas": patas})
    assert respuesta.status_code == 200
    assert respuesta.json()["patas"][0]["tasa"] == 0.06

    despues = api_con_datos.get("/operaciones/IRS-0001/mtm", params=FECHA).json()["mtm"]
    assert despues > antes  # recibe una tasa fija mayor

    historial = api_con_datos.get("/operaciones/IRS-0001/historial").json()
    assert historial[0]["datos"]["patas"][0]["tasa"] == 0.05


def test_modificacion_invalida(api_con_datos):
    """!
    @brief Una modificación vacía o con patas inválidas se rechaza.
    """
    patas_de_forward = datos.FX_FORWARD["patas"]
    assert api_con_datos.patch("/operaciones/IRS-0001", json={"patas": patas_de_forward}).status_code == 422
    assert api_con_datos.patch("/operaciones/IRS-0001", json={}).status_code == 422
    assert api_con_datos.patch("/operaciones/IRS-0001", json={"deal_number": "X"}).status_code == 422
    # Nada de lo anterior debe haber dejado rastro.
    assert api_con_datos.get("/operaciones/IRS-0001").json()["version"] == 1
    assert api_con_datos.get("/operaciones/IRS-0001/historial").json() == []


def test_operacion_anulada_no_se_valoriza(api_con_datos):
    """!
    @brief Una operación anulada responde 409 al pedir su MtM.
    """
    assert api_con_datos.patch("/operaciones/FWD-0001", json={"estado": "ANULADA"}).status_code == 200
    respuesta = api_con_datos.get("/operaciones/FWD-0001/mtm", params=FECHA)
    assert respuesta.status_code == 409
    assert "ANULADA" in respuesta.json()["detail"]


# ---------------------------------------------------------------------------- mercado


def test_consulta_de_mercado(api_con_datos):
    """!
    @brief Los datos de mercado cargados se pueden consultar.
    """
    assert api_con_datos.get("/mercado/fx", params=FECHA).json() == {"CLFCLP": 39500.0, "USDCLP": 950.0}

    curva = api_con_datos.get("/mercado/curvas/CLP_CAMARA", params=FECHA).json()
    assert curva == datos.CURVAS[0]

    valores = api_con_datos.get("/mercado/indices/ICP", params={"desde": "2026-08-01"}).json()
    assert valores == {"2026-10-06": 24270.0}

    assert api_con_datos.get("/mercado/feriados/SCL").json() == datos.FERIADOS["fechas"]


def test_recargar_mercado_reemplaza(api_con_datos):
    """!
    @brief Cargar de nuevo una curva o un tipo de cambio reemplaza el valor anterior.
    """
    api_con_datos.post("/mercado/fx", json={"fecha": datos.FECHA, "valores": [{"par": "USDCLP", "valor": 960.0}]})
    assert api_con_datos.get("/mercado/fx", params=FECHA).json() == {"CLFCLP": 39500.0, "USDCLP": 960.0}

    nueva = {**datos.CURVAS[0], "vertices": [{"plazo_dias": 30, "tasa": 0.04}, {"plazo_dias": 3650, "tasa": 0.05}]}
    assert api_con_datos.post("/mercado/curvas", json=nueva).json() == {"registros": 2}
    assert len(api_con_datos.get("/mercado/curvas/CLP_CAMARA", params=FECHA).json()["vertices"]) == 2

    assert api_con_datos.post("/mercado/feriados", json=datos.FERIADOS).status_code == 201
    assert api_con_datos.get("/mercado/feriados/SCL").json() == datos.FERIADOS["fechas"]


def test_vertices_guardan_el_codigo_de_su_curva(api_con_datos):
    """!
    @brief Cada vértice guarda el código de su curva.
    """
    from sqlalchemy import create_engine, text

    from valorizador.config import configuracion

    motor_bd = create_engine(configuracion.database_url_test)
    with motor_bd.connect() as conexion:
        filas = conexion.execute(
            text(
                "SELECT v.codigo, c.codigo, count(*) FROM curva_vertice v "
                "JOIN curva c ON c.id = v.curva_id GROUP BY v.codigo, c.codigo ORDER BY v.codigo"
            )
        ).all()
    motor_bd.dispose()
    assert [tuple(f) for f in filas] == [
        ("CLF_CAMARA", "CLF_CAMARA", 4),
        ("CLP_CAMARA", "CLP_CAMARA", 5),
        ("USD_SOFR", "USD_SOFR", 5),
    ]


def test_mercado_invalido(api):
    """!
    @brief Datos de mercado mal formados se rechazan con 422.
    """
    un_vertice = {**datos.CURVAS[0], "vertices": [{"plazo_dias": 30, "tasa": 0.04}]}
    assert api.post("/mercado/curvas", json=un_vertice).status_code == 422
    assert api.post("/mercado/fx", json={"fecha": datos.FECHA, "valores": [{"par": "usdclp", "valor": 1}]}).status_code == 422
    assert api.get("/mercado/curvas/NO_EXISTE", params=FECHA).status_code == 422


# ------------------------------------------------------------------------ valorización


@pytest.mark.parametrize("datos_operacion", datos.OPERACIONES, ids=lambda d: d["deal_number"])
def test_mtm_de_la_api_coincide_con_el_motor(api_con_datos, escenario, datos_operacion):
    """!
    @brief El MtM de la API es el mismo que entrega el motor con el escenario en memoria.
    @param api_con_datos API con el mercado y las operaciones de ejemplo.
    @param escenario El mismo mercado como escenario en memoria.
    @param datos_operacion Cada operación de ejemplo.
    """
    deal = datos_operacion["deal_number"]
    esperado = motor.valorizar(OperacionEntrada.model_validate(datos_operacion), escenario, "CLP")

    respuesta = api_con_datos.get(f"/operaciones/{deal}/mtm", params=FECHA)
    assert respuesta.status_code == 200
    assert respuesta.json()["mtm"] == pytest.approx(esperado.mtm, rel=1e-12)
    assert respuesta.json()["moneda_valorizacion"] == "CLP"
    assert respuesta.json()["patas"][0]["flujos"] is None


def test_mtm_con_detalle_y_en_otra_moneda(api_con_datos):
    """!
    @brief El MtM se puede pedir con detalle de flujos y en otra moneda.
    """
    en_clp = api_con_datos.get("/operaciones/CCS-0001/mtm", params=FECHA).json()["mtm"]
    respuesta = api_con_datos.get(
        "/operaciones/CCS-0001/mtm", params={**FECHA, "moneda": "USD", "detalle": "true"}
    ).json()
    assert respuesta["mtm"] == pytest.approx(en_clp / 950.0)
    assert len(respuesta["patas"][0]["flujos"]) == 6
    assert respuesta["patas"][1]["flujos"][-1]["fecha_pago"] == "2029-08-10"


def test_mtm_sin_mercado_para_la_fecha(api_con_datos):
    """!
    @brief Sin mercado para la fecha, el MtM responde 422.
    """
    respuesta = api_con_datos.get("/operaciones/IRS-0001/mtm", params={"fecha": "2026-10-07"})
    assert respuesta.status_code == 422
    assert "CLP_CAMARA" in respuesta.json()["detail"]
    assert "2026-10-07" in respuesta.json()["detail"]


def test_mtm_exige_fecha(api_con_datos):
    """!
    @brief El MtM sin fecha responde 422.
    """
    assert api_con_datos.get("/operaciones/IRS-0001/mtm").status_code == 422


def test_sensibilidades(api_con_datos):
    """!
    @brief Las sensibilidades incluyen cada factor de la operación.
    """
    respuesta = api_con_datos.get("/operaciones/CCS-0001/sensibilidades", params=FECHA).json()
    factores = [s["factor"] for s in respuesta["sensibilidades"]]
    assert factores[:2] == ["FX:CLFCLP", "FX:USDCLP"]
    assert "IR:CLF_CAMARA:365" in factores and "IR:USD_SOFR:1825" in factores
    assert len(factores) == 2 + 4 + 5
    por_factor = {s["factor"]: s["delta_mtm"] for s in respuesta["sensibilidades"]}
    assert por_factor["FX:CLFCLP"] > 0 > por_factor["FX:USDCLP"]  # recibe UF, paga USD


# ----------------------------------------------------------------------------- cartera


def test_mtm_de_cartera_coincide_con_cada_operacion(api_con_datos):
    """!
    @brief El MtM de cartera de cada operación coincide con su MtM individual, y los totales suman.
    """
    respuesta = api_con_datos.get("/cartera/mtm", params=FECHA)
    assert respuesta.status_code == 200
    cartera = respuesta.json()
    por_deal = {o["deal_number"]: o for o in cartera["operaciones"]}
    assert sorted(por_deal) == ["CCS-0001", "FWD-0001", "IRS-0001"]
    for deal, fila in por_deal.items():
        individual = api_con_datos.get(f"/operaciones/{deal}/mtm", params=FECHA).json()["mtm"]
        assert fila["mtm"] == pytest.approx(individual, rel=1e-12)
        assert fila["error"] is None
    assert [t["producto"] for t in cartera["totales"]] == ["FX_FORWARD", "IR_SWAP", "CC_SWAP"]
    assert cartera["mtm_total"] == pytest.approx(sum(o["mtm"] for o in cartera["operaciones"]))


def test_mtm_de_cartera_informa_errores_sin_detenerse(api_con_datos):
    """!
    @brief Una operación que no se puede valorizar queda con error y no detiene a las demás.
    """
    respuesta = api_con_datos.get("/cartera/mtm", params={"fecha": "2026-10-07"}).json()
    assert all(o["mtm"] is None and o["error"] for o in respuesta["operaciones"])
    assert respuesta["mtm_total"] == 0
    assert all(t["con_error"] == t["operaciones"] == 1 for t in respuesta["totales"])


def test_mtm_de_cartera_excluye_anuladas_y_filtra_producto(api_con_datos):
    """!
    @brief El MtM de cartera excluye las anuladas y respeta el filtro de producto.
    """
    api_con_datos.patch("/operaciones/FWD-0001", json={"estado": "ANULADA"})
    deals = [o["deal_number"] for o in api_con_datos.get("/cartera/mtm", params=FECHA).json()["operaciones"]]
    assert deals == ["CCS-0001", "IRS-0001"]
    solo_swaps = api_con_datos.get("/cartera/mtm", params={**FECHA, "producto": "IR_SWAP"}).json()
    assert [o["deal_number"] for o in solo_swaps["operaciones"]] == ["IRS-0001"]


def test_modalidad_de_liquidacion(api_con_datos):
    """!
    @brief La modalidad se guarda y por defecto es compensación.
    """
    assert api_con_datos.get("/operaciones/FWD-0001").json()["modalidad_liquidacion"] == "COMPENSACION"
    respuesta = api_con_datos.patch("/operaciones/FWD-0001", json={"modalidad_liquidacion": "ENTREGA_FISICA"})
    assert respuesta.json()["modalidad_liquidacion"] == "ENTREGA_FISICA"
    assert api_con_datos.patch("/operaciones/FWD-0001", json={"modalidad_liquidacion": "OTRA"}).status_code == 422


def test_operacion_en_uf_no_admite_entrega_fisica(api_con_datos):
    """!
    @brief Una operación con una pata en UF no puede ser de entrega física, ni en el alta ni al modificarla.
    """
    con_uf = {**datos.CC_SWAP, "deal_number": "CCS-FISICA", "modalidad_liquidacion": "ENTREGA_FISICA"}
    respuesta = api_con_datos.post("/operaciones", json=con_uf)
    assert respuesta.status_code == 422
    assert "CLF" in str(respuesta.json()["detail"])

    # Tampoco se puede llegar a esa combinación modificando la modalidad o las patas.
    assert api_con_datos.patch("/operaciones/CCS-0001", json={"modalidad_liquidacion": "ENTREGA_FISICA"}).status_code == 422
    api_con_datos.patch("/operaciones/FWD-0001", json={"modalidad_liquidacion": "ENTREGA_FISICA"})
    patas_en_uf = [dict(p) for p in datos.FX_FORWARD["patas"]]
    patas_en_uf[1] = {**patas_en_uf[1], "moneda": "CLF", "nocional": 25_000.0, "curva_descuento": "CLF_CAMARA"}
    assert api_con_datos.patch("/operaciones/FWD-0001", json={"patas": patas_en_uf}).status_code == 422
    assert api_con_datos.get("/operaciones/CCS-0001").json()["modalidad_liquidacion"] == "COMPENSACION"


def test_vencimientos_por_modalidad(api_con_datos):
    """!
    @brief Entrega física da un flujo por pata en su moneda; compensación, uno neto en CLP.
    """
    compensacion = api_con_datos.get("/cartera/vencimientos", params=FECHA).json()["flujos"]
    por_deal = {f["deal_number"]: f for f in compensacion}
    # Forward por compensación: USD 1.000.000 al spot de 950 contra CLP 955.000.000.
    assert por_deal["FWD-0001"]["sentido"] == "NETO"
    assert por_deal["FWD-0001"]["monto"] == pytest.approx(950_000_000 - 955_000_000)
    # CCS por compensación: UF 100.000 a 39.500 contra USD 4.150.000 a 950.
    assert por_deal["CCS-0001"]["monto"] == pytest.approx(100_000 * 39_500 - 4_150_000 * 950)
    # IR swap de una moneda sin intercambio de nocional: no hay flujo al vencimiento.
    assert "IRS-0001" not in por_deal

    api_con_datos.patch("/operaciones/FWD-0001", json={"modalidad_liquidacion": "ENTREGA_FISICA"})
    fisica = [
        (f["sentido"], f["moneda"], f["monto"])
        for f in api_con_datos.get("/cartera/vencimientos", params=FECHA).json()["flujos"]
        if f["deal_number"] == "FWD-0001"
    ]
    assert fisica == [("RECIBE", "USD", 1_000_000.0), ("PAGA", "CLP", -955_000_000.0)]


# ---------------------------------------------------------------- historia de mercado


def test_resumen_de_mercado(api_con_datos):
    """!
    @brief El resumen de mercado lista cada serie con su rango de fechas.
    """
    resumen = api_con_datos.get("/mercado/resumen").json()
    assert [s["nombre"] for s in resumen["fx"]] == ["CLFCLP", "USDCLP"]
    assert {s["nombre"] for s in resumen["curvas"]} == {"CLF_CAMARA", "CLP_CAMARA", "USD_SOFR"}
    icp = next(s for s in resumen["indices"] if s["nombre"] == "ICP")
    assert icp == {"nombre": "ICP", "desde": "2026-07-06", "hasta": datos.FECHA, "fechas": 2}


def test_historia_de_fx_y_curvas(api_con_datos):
    """!
    @brief La historia de un par y de una curva respeta el rango pedido.
    """
    otra = {"fecha": "2026-10-05", "valores": [{"par": "USDCLP", "valor": 945.0}]}
    api_con_datos.post("/mercado/fx", json=otra)
    assert api_con_datos.get("/mercado/fx/USDCLP").json() == {"2026-10-05": 945.0, datos.FECHA: 950.0}
    assert api_con_datos.get("/mercado/fx/USDCLP", params={"desde": datos.FECHA}).json() == {datos.FECHA: 950.0}

    api_con_datos.post("/mercado/curvas", json={**datos.CURVAS[0], "fecha": "2026-10-05"})
    historia = api_con_datos.get("/mercado/curvas/CLP_CAMARA/historia").json()
    assert [c["fecha"] for c in historia] == ["2026-10-05", datos.FECHA]
    assert historia[1] == datos.CURVAS[0]
    assert api_con_datos.get("/mercado/curvas/NO_EXISTE/historia").json() == []


def test_grupo_de_calce(api_con_datos):
    """!
    @brief El grupo de calce se guarda, se modifica y aparece en el MtM de cartera.
    """
    assert api_con_datos.get("/operaciones/FWD-0001").json()["grupo_calce"] is None
    espejo = {**datos.FX_FORWARD, "deal_number": "FWD-0002", "grupo_calce": "G1"}
    espejo["patas"] = [{**p, "rec_pay": "PAGA" if p["rec_pay"] == "RECIBE" else "RECIBE"} for p in espejo["patas"]]
    assert api_con_datos.post("/operaciones", json=espejo).status_code == 201
    assert api_con_datos.patch("/operaciones/FWD-0001", json={"grupo_calce": "G1"}).json()["grupo_calce"] == "G1"
    cartera = {o["deal_number"]: o for o in api_con_datos.get("/cartera/mtm", params=FECHA).json()["operaciones"]}
    assert cartera["FWD-0001"]["grupo_calce"] == cartera["FWD-0002"]["grupo_calce"] == "G1"
    assert cartera["FWD-0001"]["mtm"] == pytest.approx(-cartera["FWD-0002"]["mtm"])
    assert cartera["IRS-0001"]["grupo_calce"] is None


# ------------------------------------------------------------------------ contrapartes


def test_rut():
    """!
    @brief Normalización, formato y validación del dígito verificador del RUT.
    """
    from valorizador.rut import formatear, normalizar

    assert normalizar("77.700.100-0") == "77700100-0"
    assert normalizar("14569485k") == "14569485-K"
    assert formatear("77700100-0") == "77.700.100-0"
    for invalido in ("77700100-1", "abc", "1234567890-1"):
        with pytest.raises(ValueError):
            normalizar(invalido)


def test_alta_y_modificacion_de_contraparte(api):
    """!
    @brief Alta, duplicados, validaciones y modificación de contrapartes.
    """
    nueva = {"rut": "14.569.485-K", "nombre": "Contraparte Nueva", "monto_linea": 1e8, "mta": 1e7}
    respuesta = api.post("/contrapartes", json=nueva)
    assert respuesta.status_code == 201
    assert respuesta.json()["rut"] == "14569485-K"

    assert api.post("/contrapartes", json=nueva).status_code == 409
    assert api.post("/contrapartes", json={**nueva, "rut": "77700300-3"}).status_code == 409  # nombre repetido
    assert api.post("/contrapartes", json={**nueva, "rut": "14569485-1"}).status_code == 422
    assert api.post("/contrapartes", json={**nueva, "rut": "77700300-3", "nombre": "X", "mta": -1}).status_code == 422

    cambio = api.patch("/contrapartes/14.569.485-k", json={"monto_linea": 2e8})
    assert cambio.status_code == 200
    assert cambio.json()["monto_linea"] == 2e8
    assert api.get("/contrapartes/14569485-K").json()["nombre"] == "Contraparte Nueva"
    assert api.get("/contrapartes/77700300-3").status_code == 404
    assert [c["nombre"] for c in api.get("/contrapartes").json()] == ["Banco Ejemplo", "Contraparte Nueva", "Otro Banco"]


def test_operacion_exige_contraparte_registrada(api):
    """!
    @brief Una operación con un RUT no registrado se rechaza con 422.
    """
    sin_registro = {**datos.FX_FORWARD, "rut_contraparte": "77700300-3"}
    respuesta = api.post("/operaciones", json=sin_registro)
    assert respuesta.status_code == 422
    assert "77700300-3" in respuesta.json()["detail"]
    creada = api.post("/operaciones", json=datos.FX_FORWARD).json()
    assert (creada["rut_contraparte"], creada["contraparte"]) == ("77700100-0", "Banco Ejemplo")


def test_control_de_garantia():
    """!
    @brief Regla de llamado: bajo la línea, exceso menor que el MTA, exceso mayor y exposición negativa.
    """
    from valorizador.api.cartera import control_garantia

    assert control_garantia(80, 100, 5) == (0, False, 0)  # bajo la línea
    assert control_garantia(103, 100, 5) == (3, True, 5)  # exceso menor que el MTA: se llama por el MTA
    assert control_garantia(130, 100, 5) == (30, True, 30)
    assert control_garantia(-500, 100, 5) == (0, False, 0)  # la institución es la deudora


def test_garantias_de_cartera(api_con_datos):
    """!
    @brief La exposición por contraparte suma el MtM de sus operaciones y aplica la regla de llamado.
    """
    mtm = api_con_datos.get("/cartera/mtm", params=FECHA).json()
    exposicion = sum(o["mtm"] for o in mtm["operaciones"] if o["rut_contraparte"] == "77700100-0")

    respuesta = api_con_datos.get("/cartera/garantias", params=FECHA).json()
    filas = {c["rut"]: c for c in respuesta["contrapartes"]}
    banco = filas["77700100-0"]
    assert banco["operaciones"] == 3
    assert banco["exposicion"] == pytest.approx(exposicion)
    exceso = max(exposicion - 50_000_000, 0)
    assert banco["exceso"] == pytest.approx(exceso)
    assert banco["llamado"] == (exceso > 0)
    assert banco["monto_llamado"] == pytest.approx(max(exceso, 5_000_000) if exceso > 0 else 0)
    assert filas["77700200-7"]["operaciones"] == 0
    assert respuesta["sin_contraparte"] == []


def test_flujos_de_cartera(api_con_datos):
    """!
    @brief Los flujos futuros cuadran (flujo = nocional + interés), tienen el signo de su pata e incluyen los cupones de los swaps.
    """
    respuesta = api_con_datos.get("/cartera/flujos", params=FECHA).json()
    assert respuesta["errores"] == {}
    flujos = respuesta["flujos"]
    assert {f["deal_number"] for f in flujos} == {"FWD-0001", "IRS-0001", "CCS-0001"}
    assert all(f["fecha_pago"] > FECHA["fecha"] for f in flujos)
    for f in flujos:
        assert f["flujo"] == pytest.approx(f["amortizacion"] + f["interes"])
        assert f["flujo_clp"] == pytest.approx(f["flujo"] * f["tipo_cambio"])
        assert (f["flujo"] > 0) == (f["rec_pay"] == "RECIBE")
    # El IRS tiene cupones en varias fechas, no sólo al vencimiento.
    assert len({f["fecha_pago"] for f in flujos if f["deal_number"] == "IRS-0001"}) > 1
    forward = [f for f in flujos if f["deal_number"] == "FWD-0001"]
    assert len(forward) == 2 and all(f["interes"] == 0 for f in forward)


def test_vigencia_por_fecha_de_proceso(api_con_datos):
    """!
    @brief Una operación sólo está vigente entre su negociación y su vencimiento.
    """
    antes = api_con_datos.get("/cartera/mtm", params={"fecha": "2026-08-01"}).json()
    assert "FWD-0001" not in {o["deal_number"] for o in antes["operaciones"]}  # negociada el 01-09-2026
    despues = api_con_datos.get("/cartera/mtm", params={"fecha": "2027-01-06"}).json()
    assert "FWD-0001" not in {o["deal_number"] for o in despues["operaciones"]}  # vence el 06-01-2027
    assert "IRS-0001" in {o["deal_number"] for o in despues["operaciones"]}


def test_pnl_realizado(api_con_datos):
    """!
    @brief El P&L realizado de un forward vencido es lo recibido menos lo pagado al último spot disponible.
    """
    respuesta = api_con_datos.get("/cartera/pnl-realizado", params={"fecha": "2027-01-10"}).json()
    assert respuesta["desde"] == "2027-01-01"
    [fila] = respuesta["operaciones"]
    assert fila["deal_number"] == "FWD-0001"
    assert fila["fecha_tipo_cambio"] == datos.FECHA  # no hay datos después: se usa el último
    usdclp = next(v["valor"] for v in datos.FX["valores"] if v["par"] == "USDCLP")
    assert fila["pnl"] == pytest.approx(1_000_000 * usdclp - 955_000_000)
    assert respuesta["pnl_total"] == pytest.approx(fila["pnl"])
    vacio = api_con_datos.get("/cartera/pnl-realizado", params={"fecha": "2026-12-31"}).json()
    assert vacio["operaciones"] == []


def test_forwards_basilea(api_con_datos):
    """!
    @brief El detalle Basilea separa el valor presente de cada pata y su diferencia es el MtM.
    """
    respuesta = api_con_datos.get("/cartera/forwards-basilea", params={"fecha": datos.FECHA}).json()
    [fila] = respuesta["operaciones"]
    assert fila["deal_number"] == "FWD-0001"
    assert fila["par"] == "USD/CLP"
    assert fila["movimiento"] == "Compra"  # recibe USD
    assert fila["tipo_cambio"] == pytest.approx(955)
    assert fila["valor_razonable_activo"] > 0 and fila["valor_razonable_pasivo"] > 0
    assert fila["valor_razonable"] == pytest.approx(fila["valor_razonable_activo"] - fila["valor_razonable_pasivo"])
    mtm = api_con_datos.get("/operaciones/FWD-0001/mtm", params={"fecha": datos.FECHA}).json()["mtm"]
    assert fila["valor_razonable"] == pytest.approx(mtm)
    assert 0 < fila["tasa_activo"] < 0.2 and 0 < fila["tasa_pasivo"] < 0.2


# ------------------------------------------------------------------ autenticación


def test_login_entrega_token_y_yo_lo_reconoce(api):
    """!
    @brief Con la clave correcta se obtiene un token; `GET /auth/yo` devuelve su usuario.
    """
    from tests.conftest import CLAVE, USUARIO

    r = api.post("/auth/login", json={"usuario": USUARIO.upper(), "clave": CLAVE}, headers={"Authorization": ""})
    assert r.status_code == 200
    token = r.json()["token"]
    yo = api.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert yo.json()["usuario"] == USUARIO


def test_login_con_clave_incorrecta_responde_401(api):
    """!
    @brief Una clave errada o un usuario inexistente responden 401 con el mismo mensaje.
    """
    from tests.conftest import USUARIO

    malo = api.post("/auth/login", json={"usuario": USUARIO, "clave": "otra"})
    inexistente = api.post("/auth/login", json={"usuario": "nadie@ejemplo.cl", "clave": "otra"})
    assert malo.status_code == inexistente.status_code == 401
    assert malo.json() == inexistente.json()


def test_endpoints_exigen_token(api):
    """!
    @brief Sin token o con un token alterado los datos responden 401; `/salud` sigue abierto.
    """
    assert api.get("/contrapartes", headers={"Authorization": ""}).status_code == 401
    token = api.headers["Authorization"].removeprefix("Bearer ")
    alterado = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    assert api.get("/contrapartes", headers={"Authorization": f"Bearer {alterado}"}).status_code == 401
    assert api.get("/salud", headers={"Authorization": ""}).status_code == 200


def test_token_vencido_no_vale():
    """!
    @brief Un token con vencimiento pasado no se acepta.
    """
    from valorizador import seguridad

    token, _ = seguridad.crear_token("prueba@ejemplo.cl", -1)
    assert seguridad.leer_token(token) is None
    vigente, _ = seguridad.crear_token("prueba@ejemplo.cl", 1)
    assert seguridad.leer_token(vigente) == "prueba@ejemplo.cl"
