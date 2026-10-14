# CLAUDE.md

Guía para Claude al trabajar en este repositorio. Complementa el README, que es la
documentación para personas.

## Proyecto

Valorizador de Derivados: API FastAPI que valoriza FX Forward, IR Swap y CC Swap con QC
Financial, sobre PostgreSQL, más una app Streamlit que consume la API. Es la base de una
segunda etapa de VaR histórico y paramétrico con VaR Explain incremental por factor (FX por
par; IR por vértice de cada curva), así que las sensibilidades y el escenario de mercado deben
seguir siendo descomponibles por factor.

## Comandos

```powershell
.venv\Scripts\Activate.ps1                     # Windows; Python 3.14 local
uvicorn valorizador.main:app --reload          # API en http://localhost:8000/docs
streamlit run app/inicio.py                    # app en http://localhost:8501
alembic upgrade head                           # migraciones (head actual: 0008)
python scripts/crear_usuario.py correo@x.cl --nombre "Nombre"   # usuario de login
pytest -q                                      # requiere DATABASE_URL_TEST, base exclusiva
doxygen docs/Doxyfile                          # desde la raíz; salida en docs/doxygen/
```

Base local: PostgreSQL 18, puerto 5434, base `Valorizador`. La configuración se lee de `.env`
(ver `valorizador/config.py`).

## Estructura

- `valorizador/`: API. `api/` endpoints, `schemas/` Pydantic, `db/` modelos SQLAlchemy,
  `repositorios/` acceso a datos, `valorizacion/` escenario, constructores QC Financial y motor.
  `seguridad.py` hash de claves y tokens; `cliente.py` login para scripts.
- `app/`: Streamlit. `inicio.py` login y navegación; `paginas/` una por pantalla;
  `comun/` cliente HTTP (`api.py`), formato, reportes Excel/PDF (`reporte_pnl.py`,
  `reporte_basilea.py`), vista de operaciones.
- `migraciones/versions/`: Alembic, numeradas 0001 a 0008.
- `datos cartera sintetica/`: generador y SQL de la cartera sintética (la que usa la app).
- `datos mercados demo/`: SQL de datos de mercado de demostración.
- `scripts/`: `crear_usuario.py`, `cargar_indices.py`, `heroku.sh`.

La app Streamlit nunca accede a la base: todo pasa por la API.

## Convenciones

- Todo en español: código, mensajes, documentación y archivos generados (Excel, Word, etc.),
  con tildes, diéresis y eñes correctas.
- Documentación Doxygen: docstrings que empiezan con `"""!` y usan `@package`, `@brief`,
  `@param`, `@return`, `@throws` y `@ref` con rutas completas (`valorizador.api.cartera.x`).
  Atributos y constantes se documentan con comentarios `##` en la línea anterior.
  `valorizador/main.py` limpia la sintaxis Doxygen para `/docs`.
- En archivos Markdown no escribir dentro de backticks la secuencia de tres comillas seguida
  de `!`: rompe Doxygen.
- Cada cambio de esquema va en una migración nueva y también en `esquema.sql`. Si afecta a las
  patas, actualizar `COLUMNAS_PATA` (app/comun/formato.py y el generador preliminar) y
  regenerar `cargar_cartera_sintetica.sql`.
- Tests en `tests/`; el fixture `api` crea un usuario y deja el cliente con sesión iniciada.
- Archivos Excel generados: sin letras cursivas.
- Commits con la línea `Co-Authored-By: Claude <noreply@anthropic.com>`.

## Reglas de negocio

- Operación vigente a una fecha: no anulada y `fecha_negociacion <= fecha < fecha_vencimiento`.
  MtM de cartera, vencimientos, garantías, P&L No Realizado y el listado usan sólo vigentes.
- P&L Realizado: sólo FX Forward; recibido menos pagado en CLP al tipo de cambio de la fecha
  de pago, o del último día anterior con dato.
- Garantías por contraparte: hay llamado si la exposición supera la línea; el monto llamado
  es el mayor entre el exceso y el MTA. Línea y MTA en CLP.
- Calce: "Calzada" o "Descalzada" según `grupo_calce` (desde la institución). En reportes con
  perspectiva Cliente, calzada sólo si otra operación del grupo es con la misma contraparte.
- FX Forward en reportes Basilea: Compra si la institución recibe la moneda extranjera o UF,
  Venta si la entrega.
- Cada pata tiene curva de descuento y, si es flotante, curva de proyección, ambas en base.
- Amortización: por ahora sólo `BULLET`. Gearing siempre 1 en la práctica chilena.
- Presentación: CLF se muestra como UF; el código de operación se llama "Folio"; nocionales,
  MtM y P&L sin decimales con separadores en español; fechas como DD-MM-AAAA.

## Datos y seguridad

- Usar sólo la cartera sintética y contrapartes "Contraparte Dummy NN" con RUT ficticio.
  `datos cartera preliminar/` contiene operaciones reales: no se sube a Git (está en
  `.gitignore`) y no se copian nombres ni RUT reales de clientes a ningún archivo. Lo mismo
  para `informes moldes/`: planillas modelo con datos reales, que sólo se usan como formato.
- Nunca commitear `.env`, claves ni `CLAVE_SECRETA`. Las claves de usuario se guardan como
  hash PBKDF2; los usuarios se crean con el script, no en migraciones.
- Todos los endpoints salvo `/salud` y `/auth/login` exigen token Bearer
  (`REQUERIR_AUTENTICACION=false` lo desactiva sólo en local).

## Despliegue

Heroku, dos apps desde este repositorio (ver README, "Despliegue en Heroku"):
`valorizador-api` (ROL=api, con Heroku Postgres; release aplica `alembic upgrade head`) y
`valorizador-app` (ROL=streamlit, `VALORIZADOR_API_URL` apunta a la API). Remotos Git
`heroku-api` y `heroku-app`; se despliega desde `master`. `.python-version` fija 3.11 porque
`qcfinancial` sólo publica para Linux la versión 3.11. La base de Heroku es independiente de
la local: los usuarios se crean en cada una.

## Cómo responder al usuario

Respuestas directas en español, sin preámbulos ni resúmenes de lo dicho, sin ofrecer pasos
siguientes salvo que los pida. Si algo es interpretación y no dato, decirlo al inicio. Cuando
pregunta si algo se puede hacer, responder eso, sin implementarlo.
