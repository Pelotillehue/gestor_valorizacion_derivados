# Valorizador de Derivados

API en Python para dar de alta, consultar, modificar y valorizar FX Forward, IR Swap y CC Swap.
El cálculo financiero lo hace la librería [QC Financial](https://qcfinancial.cl) y los datos se
guardan en PostgreSQL.

## Requisitos

- Python 3.14 de 64 bits (también sirve 3.11, 3.12 o 3.13)
- PostgreSQL 13 o superior

## Instalación en Windows

En PowerShell, desde la carpeta del proyecto:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Si PowerShell rechaza `Activate.ps1` por la política de ejecución de scripts, usar
`.venv\Scripts\activate.bat` desde el símbolo del sistema.

Editar `.env` con el usuario, la clave y el nombre de la base de datos. Luego crear la base y
sus tablas:

```powershell
psql -U postgres -c "CREATE DATABASE valorizador"
alembic upgrade head
```

Si `psql` no está en el PATH, la base se puede crear desde pgAdmin.

Crear al menos un usuario para iniciar sesión (pide la clave sin mostrarla):

```powershell
python scripts/crear_usuario.py usuario@empresa.cl --nombre "Nombre Apellido"
```

## Usuarios y sesión

La app pide usuario y clave antes de mostrar cualquier página. La API los compara con la tabla
`usuario`, donde la clave se guarda como hash PBKDF2-SHA256 con sal, nunca en texto plano, y
entrega un token de sesión firmado que vale `HORAS_SESION` horas (12 por defecto).

Todos los endpoints salvo `GET /salud` y `POST /auth/login` exigen ese token en el header
`Authorization: Bearer <token>`. En `/docs` se ingresa con el botón *Authorize*, pegando el
token que devuelve `POST /auth/login`.

| Variable de `.env` | Uso |
|---|---|
| `CLAVE_SECRETA` | Clave con que se firman los tokens. Debe ser larga, aleatoria y la misma en todas las instancias de la API. Si falta, la API genera una al iniciar y las sesiones se pierden cada vez que se reinicia |
| `HORAS_SESION` | Horas de validez de una sesión |
| `REQUERIR_AUTENTICACION` | `false` desactiva la exigencia de token, sólo para desarrollo local |

`scripts/crear_usuario.py` crea un usuario, le cambia la clave si ya existe, o lo desactiva con
`--desactivar`. Los scripts que usan la API (`scripts/cargar_indices.py` y
`ejemplos/cargar_ejemplo.py`) piden usuario y clave por consola, o los toman de
`VALORIZADOR_USUARIO` y `VALORIZADOR_CLAVE`.

## Ejecución

```powershell
uvicorn valorizador.main:app --reload
```

La documentación interactiva queda en <http://localhost:8000/docs>. Desde ahí se puede probar
cada endpoint.

## App

Con la API corriendo en una terminal, en otra terminal con el ambiente activado:

```powershell
streamlit run app/inicio.py
```

Se abre en el navegador en <http://localhost:8501>. Tiene estas páginas:

| Página | Qué hace |
|---|---|
| Operaciones FX Forward | Forwards vigentes con filtros por contraparte, modalidad y calce: montos de cada moneda, par y precio pactado. Al seleccionar uno muestra sus patas y su MtM con el detalle de flujos |
| Operaciones Interest Rate Swap y Cross Currency Swap | Swaps vigentes con, para cada lado, moneda, tipo de tasa (Fix o Float), tasa fija o índice y curva de proyección, y spread (cero si no tiene). Mismo detalle y MtM al seleccionar uno |
| MtM de cartera | MtM de todas las operaciones vigentes a una fecha, con totales por producto, por contraparte y los motivos de las que no se pudieron valorizar |
| Vencimientos | Todos los flujos futuros en CLP (montos de forwards, cupones y nocionales de swaps), por día, mes, trimestre o año, apilados por producto; filtros por modalidad y por componente (nocional o intereses) |
| Contrapartes | Maestro de contrapartes: RUT, nombre, monto de línea y MTA, editables; alta de contrapartes nuevas |
| Índices | Historia del ICP y del SOFR índice, con la tasa overnight implícita |
| Tipos de cambio y UF | Historia de cada par cargado; el par CLFCLP se muestra como UF |
| Curvas | Superficie 3D de la historia de una curva cero y comparación de la curva en distintas fechas |
| P&L No Realizado | P&L no realizado de las operaciones vigentes por contraparte, separado en calzadas y descalzadas, con el control de garantías (línea, MTA y situación: "Llamado a Garantía" en rojo o "Dentro de Límite") y descarga en Excel (formato del cuadro de performance) y PDF |
| Carga de operaciones | Sube un Excel o CSV con una fila por pata; trae una plantilla descargable con la descripción de cada columna |
| P&L Realizado | P&L de los FX Forward vencidos en un período (por defecto, desde el 1 de enero), por contraparte, calzados y descalzados, con descarga en Excel |
| Listado de Operaciones Vigentes | Descarga en Excel y PDF el listado de las operaciones vigentes a la fecha de proceso de cada familia, con su MtM si se pide |

La app no se conecta a la base de datos: todo pasa por la API. Si la API corre en otra
dirección, se cambia en la barra lateral o con la variable de entorno `VALORIZADOR_API_URL`.

Para cargar un mercado de ejemplo y una operación de cada producto, con la API corriendo en
otra terminal:

```powershell
python -m ejemplos.cargar_ejemplo
```

Resultado esperado:

```
MtM en CLP al 2026-10-06
  FWD-0001             -3,808,452
  IRS-0001              5,915,567
  CCS-0001             48,720,128
```

## Despliegue en Heroku

El mismo repositorio se despliega en dos apps de Heroku: una con la API y Heroku Postgres, y
otra con la app Streamlit. El `Procfile` llama a `scripts/heroku.sh`, que según la variable
`ROL` de cada app levanta uno u otro servicio. En la app de la API, la fase *release* aplica
`alembic upgrade head` en cada despliegue.

`.python-version` fija Python 3.11 porque `qcfinancial` sólo publica para Linux una versión
compilada para 3.11. Heroku corre sobre Linux, aunque localmente se use otra versión.

Requisitos: Heroku CLI instalado y con sesión iniciada (`heroku login`), el proyecto en un
repositorio git con todo commiteado, y `psql` y `pg_dump` en el PATH si se va a copiar la base
local.

**1. App de la API con su base de datos.** Los nombres de app son únicos en todo Heroku; si
uno está tomado, elegir otro.

```powershell
heroku create valorizador-api
heroku addons:create heroku-postgresql:essential-0 -a valorizador-api
heroku config:set ROL=api CLAVE_SECRETA=<texto largo y aleatorio> -a valorizador-api
```

Heroku define `DATABASE_URL` al agregar Postgres. La API le agrega el driver `psycopg` sola.

**2. Datos.** La forma más simple es copiar la base local completa, con mercado, índices,
operaciones, contrapartes y usuarios. Se hace antes del primer despliegue, porque la base de
Heroku debe estar vacía:

```powershell
heroku pg:push "postgresql://postgres:CLAVE@localhost:5434/Valorizador" DATABASE_URL -a valorizador-api
```

Si falla, por ejemplo porque la versión de PostgreSQL de Heroku es más antigua que la local,
desplegar primero (paso 3, que crea las tablas) y cargar los scripts con
`heroku pg:psql -a valorizador-api`:

```
\i 'datos mercados demo/cargar_datos_mercado.sql'
\i 'datos cartera sintetica/cargar_cartera_sintetica.sql'
```

Luego crear el usuario en Heroku con
`heroku run python scripts/crear_usuario.py usuario@empresa.cl -a valorizador-api`, y cargar
los índices con `python scripts/cargar_indices.py --fecha AAAA-MM-DD --api <URL de la API>`.

**3. Desplegar la API:**

```powershell
heroku git:remote -a valorizador-api -r heroku-api
git push heroku-api master
heroku info -a valorizador-api
```

`heroku info` muestra la *Web URL*. `<URL de la API>/salud` debe responder `{"estado":"ok"}`.

**4. App Streamlit:**

```powershell
heroku create valorizador-app
heroku config:set ROL=streamlit VALORIZADOR_API_URL=<URL de la API sin / final> -a valorizador-app
heroku git:remote -a valorizador-app -r heroku-app
git push heroku-app master
heroku open -a valorizador-app
```

Si la rama local se llama `main`, usar `main` en los `git push`. Para cada nueva versión basta
repetir los dos `git push`. Los errores se ven con `heroku logs --tail -a <app>`.

Heroku corta las solicitudes que tardan más de 30 segundos. Con la cartera sintética, el
cálculo más pesado (`GET /cartera/mtm`) tarda menos de un segundo.

## Endpoints

| Método y ruta | Función |
|---|---|
| `POST /auth/login` | Valida usuario y clave y entrega un token de sesión |
| `GET /auth/yo` | Usuario del token; responde 401 si la sesión venció |
| `POST /contrapartes` | Alta de una contraparte: RUT, nombre, monto de línea y MTA |
| `GET /contrapartes` y `GET /contrapartes/{rut}` | Maestro de contrapartes |
| `PATCH /contrapartes/{rut}` | Modifica nombre, línea o MTA |
| `POST /operaciones` | Alta de una operación |
| `GET /operaciones` | Lista, con filtros por producto y estado |
| `GET /operaciones/{deal}` | Datos de una operación |
| `PATCH /operaciones/{deal}` | Modificación |
| `GET /operaciones/{deal}/historial` | Versiones anteriores a cada modificación |
| `GET /operaciones/{deal}/vencimiento` | Vencimiento contractual y fecha del último pago |
| `GET /operaciones/{deal}/mtm?fecha=` | MtM a una fecha de proceso |
| `GET /operaciones/{deal}/sensibilidades?fecha=` | Cambio del MtM por cada factor de mercado |
| `GET /cartera/mtm?fecha=` | MtM de todas las operaciones vigentes, con totales por producto |
| `GET /cartera/vencimientos?fecha=` | Montos que se intercambian al vencimiento de cada operación vigente |
| `GET /cartera/pnl-realizado?fecha=&desde=` | P&L realizado de los FX Forward vencidos en el período, liquidados al spot de su fecha de pago |
| `GET /cartera/flujos?fecha=` | Todos los flujos futuros de cada pata (nocional e interés), en su moneda y en CLP |
| `GET /cartera/garantias?fecha=` | Exposición de cada contraparte contra su línea y llamado a constituir garantías |
| `GET /mercado/resumen` | Series de mercado guardadas y su rango de fechas |
| `POST /mercado/fx` y `GET /mercado/fx?fecha=` | Tipos de cambio |
| `GET /mercado/fx/{par}?desde=&hasta=` | Historia de un tipo de cambio |
| `POST /mercado/curvas` y `GET /mercado/curvas/{codigo}?fecha=` | Curvas cero |
| `GET /mercado/curvas/{codigo}/historia?desde=&hasta=` | Historia de una curva |
| `POST /mercado/indices` y `GET /mercado/indices/{indice}` | Valores de índices |
| `POST /mercado/feriados` y `GET /mercado/feriados/{calendario}` | Feriados |

Los endpoints de MtM y vencimientos de cartera aceptan `producto` para filtrar. El MtM de cartera lee el
mercado una sola vez y valoriza todas las operaciones; una operación que no se puede
valorizar queda con `mtm` nulo y el motivo en `error`, sin detener a las demás.

El endpoint de MtM acepta además `moneda` (moneda del resultado, por defecto la de `.env`) y
`detalle=true` (flujo por flujo de cada pata).

## Vigencia y P&L realizado

Los cálculos de cartera (MtM, vencimientos, flujos y garantías) sólo consideran las
operaciones vigentes a la fecha de proceso: no anuladas, con fecha de negociación igual o
anterior y vencimiento posterior. Una operación que vence en la fecha de proceso ya se liquidó.

`GET /cartera/pnl-realizado` liquida cada FX Forward vencido entre `desde` y `fecha`: lo
recibido menos lo pagado, ambos en CLP al spot de su fecha de pago (si ese día no tiene
tipos de cambio, el del día anterior con datos). Por ahora no incluye swaps vencidos. El Excel
de P&L No Realizado usa este P&L, desde el 1 de enero, en el bloque "P&L histórico liquidado".

## Contrapartes y garantías

Las contrapartes están en la tabla `contraparte`, con el RUT como clave. Se guarda sin
puntos y con guion (`76123456-K`); la API lo acepta también con puntos y valida el dígito
verificador. Una operación se asocia a su contraparte con `rut_contraparte`, que debe
existir antes en el maestro; la API devuelve además el nombre en `contraparte`.

Cada contraparte tiene un **monto de línea**, la exposición a favor de la institución que se
acepta sin garantías, y un **MTA** (monto mínimo de transferencia), ambos en CLP.
`GET /cartera/garantias` suma el MtM en CLP de todas las operaciones vigentes de cada
contraparte (positivo si la contraparte le debe a la institución) y:

- exceso = máximo entre cero y exposición menos línea;
- hay llamado a constituir garantías si el exceso es positivo, es decir, si la exposición
  supera la línea;
- el monto a llamar es el mayor entre el exceso y el MTA: el MTA es lo mínimo que se
  transfiere, aunque el exceso sea menor.

Una exposición negativa, en que la institución es la deudora, no genera llamado.

## Cómo se describe una operación

Toda operación tiene una modalidad de liquidación, `modalidad_liquidacion`:
`COMPENSACION` (por defecto), en que al vencimiento se paga sólo la diferencia en CLP, o
`ENTREGA_FISICA`, en que se intercambian los montos de cada pata en su moneda. Una
operación con una pata en UF (`CLF`) sólo admite compensación, porque la UF es unidad de
cuenta y no se entrega; la API rechaza la combinación en el alta y en la modificación. Hoy
la modalidad sólo afecta a `GET /cartera/vencimientos`; el MtM es el mismo en ambos casos.

El campo opcional `grupo_calce` marca las operaciones que se cubren entre sí en monto y
vencimiento: todas las de un mismo grupo están calzadas, y una operación sin grupo está
descalzada.

Toda operación tiene dos patas, una que recibe y otra que paga. Hay tres tipos de pata:

| Tipo | Uso | Campos propios |
|---|---|---|
| `SIMPLE` | Un flujo único. Patas de un FX Forward | `fecha_pago` |
| `FIJA` | Cupones a tasa fija | `tasa`, `fraccion_anio`, `factor_capitalizacion` |
| `INDICE_OVERNIGHT` | Cupones sobre un índice overnight capitalizado, como ICP o el índice SOFR | `indice`, `curva_proyeccion`, `spread`, `gearing`, `decimales_tasa` |

Las patas con cupones comparten `fecha_inicio`, `fecha_fin`, `periodicidad` (por ejemplo `6M`),
`stub`, `ajuste_fecha`, `calendario`, `lag_pago`, `tipo_amortizacion` e `intercambia_nocional`. Todas las patas
llevan `moneda`, `nocional` y `curva_descuento`.

Reglas por producto:

- `FX_FORWARD`: dos patas `SIMPLE` en monedas distintas y con la misma fecha de pago.
- `IR_SWAP`: dos patas con cupones en la misma moneda.
- `CC_SWAP`: dos patas con cupones en monedas distintas. Un swap UF contra cámara en pesos
  entra aquí, con la pata en UF expresada en `CLF`.

En `ejemplos/datos.py` hay una operación completa de cada producto.

## Datos de mercado

- **Tipos de cambio.** El par `USDCLP` es pesos por dólar. La UF se carga como `CLFCLP`. Si no
  existe el par directo se usa el inverso, y si tampoco existe se triangula por CLP o por USD.
- **Curvas.** Se cargan como curvas cero: plazo en días y tasa en tanto por uno, junto con la
  convención de esas tasas (por defecto Act/365 compuesta). La interpolación es lineal en
  tasas. El proyecto no construye curvas a partir de instrumentos de mercado.
- **Valores de índices.** Nivel publicado de cada índice por fecha, en la tabla
  `valor_indice`. Una pata flotante necesita el valor de la fecha de proceso y el del
  inicio del cupón vigente. Si el inicio cae en un día sin publicación, se usa el primer
  valor publicado dentro de los siete días siguientes. Las patas en UF que devengan cámara
  usan el mismo índice `ICP` que las en pesos.

  Para cargar el ICP y el índice SOFR que necesita la cartera vigente desde el servicio de
  datos de mercado, con la API corriendo:

  ```powershell
  python scripts/cargar_indices.py --fecha 2026-08-17
  ```
- **Feriados.** Por código de calendario. Sin feriados cargados sólo se consideran sábados y
  domingos.

## Cómo se calcula el MtM

1. Se lee la operación y se arma el escenario de mercado de la fecha de proceso.
2. Cada pata se construye con `LegFactory` de QC Financial, o con un `SimpleCashflow` en el
   forward.
3. En las patas flotantes se fija el índice inicial y final de cada cupón: valor publicado si
   la fecha ya ocurrió, proyección con la curva si es futura.
4. Cada pata se descuenta en su moneda con su curva.
5. Cada valor presente se convierte a la moneda de valorización con el spot de la fecha y se
   suman.

Supuestos que conviene tener presentes:

- Curvas y tipos de cambio deben existir para la fecha de proceso exacta. No se arrastran
  valores de días anteriores; si falta un dato la API responde 422 indicando cuál.
- Un flujo que se paga en la fecha de proceso ya no entra en el MtM.
- `tipo_amortizacion` sólo admite `BULLET`: todo el nocional al vencimiento. `intercambia_nocional` controla si el nocional se paga como flujo
  al vencimiento. El intercambio inicial de nocionales no se modela.
- Una pata que se liquida en una moneda distinta a la de su nocional, como una pata en UF que
  se paga en pesos, se valoriza en la moneda del nocional y se convierte al spot.
- En las patas flotantes QC Financial descuenta el interés sin redondear, mientras que el flujo
  que muestra usa la tasa equivalente redondeada a `decimales_tasa`. El detalle de flujos
  informa ambos montos: `flujo` y `monto_descontado`.
- No hay patas sobre tasas a plazo tipo Ibor o Term SOFR.
- La API no tiene autenticación.

## Estructura

```
valorizador/
├── main.py            Aplicación FastAPI y traducción de errores a HTTP
├── config.py          Configuración desde .env
├── enums.py           Productos, tipos de pata, monedas y convenciones
├── errores.py         Errores del dominio
├── seguridad.py       Hash de claves y tokens de sesión
├── cliente.py         Inicio de sesión para scripts que usan la API
├── api/               Endpoints
├── schemas/           Modelos Pydantic de entrada y salida
├── db/                Modelos SQLAlchemy y sesión
├── repositorios/      Lectura y escritura en PostgreSQL, armado del escenario
└── valorizacion/
    ├── escenario.py   Escenario de mercado inmutable y sus factores
    ├── constructores.py  Traducción a objetos de QC Financial
    └── motor.py       MtM, sensibilidades y fecha de último pago
app/
├── inicio.py          App Streamlit: inicio de sesión, navegación y conexión con la API
├── paginas/           Una página por pantalla; las tres de operaciones usan comun/vista_operaciones.py
└── comun/             Cliente de la API, plantilla de carga, reportes Excel y PDF
migraciones/           Migraciones Alembic
ejemplos/              Datos de ejemplo y script de carga
tests/                 Tests del motor y de la API
docs/                  Doxyfile y página de arquitectura de la documentación Doxygen
Procfile               Arranque en Heroku, con scripts/heroku.sh
```

La base de datos guarda términos contractuales y datos de mercado. Los objetos de QC Financial
se construyen en memoria en cada valorización.

## Base para el VaR

`valorizacion/motor.py` no accede a la base de datos: recibe la operación y un
`EscenarioMercado` y devuelve el resultado. Cada dato que puede moverse es un factor con clave
propia:

- `FX:USDCLP` para un tipo de cambio
- `IR:CLP_CAMARA:365` para el vértice de 365 días de una curva

`escenario.desplazar(factor, delta)` devuelve un escenario nuevo con ese único factor movido.
Con eso, la segunda etapa queda planteada así:

- **VaR histórico:** valorizar la cartera con un escenario por cada día de la ventana.
- **VaR paramétrico:** usar las sensibilidades por factor, que ya entrega
  `motor.sensibilidades`, junto con la matriz de covarianzas.
- **VaR Explain:** mover un factor a la vez, FX por FX y vértice por vértice.

## Tests

```powershell
pytest
```

Los tests del motor no necesitan base de datos y contrastan el MtM con un cálculo
independiente de QC Financial. Los de la API corren contra PostgreSQL y se omiten si no está
definida `DATABASE_URL_TEST` en `.env`. Esa base debe ser exclusiva para pruebas, porque los
tests borran y recrean sus tablas:

```powershell
psql -U postgres -c "CREATE DATABASE valorizador_test"
```

## Cartera sintética

`datos cartera sintetica/` tiene una cartera de prueba de 77 operaciones vigentes al 17-08-2026, con calces, y 22 FX Forward ya vencidos a esa fecha (folios `FXV-`, 8 pares calzados y 6 descalzados) para el P&L realizado. Las vigentes:

| Producto | Operaciones | Calzadas |
|---|---|---|
| FX Forward | 60 | 54 |
| IR Swap | 12 | 10 |
| CC Swap | 5 | 4 |

Cada grupo de calce parte de una operación real de la cartera preliminar y se cubre con
una o dos operaciones en sentido contrario, por el mismo monto y vencimiento y, en los
swaps, con las mismas fechas de cupón. La cobertura tiene un precio algo mejor, así que el
grupo deja un margen. Sólo se usan como base operaciones con tipo de cambio pactado a menos
de 10% del spot. Las 35 contrapartes son ficticias, con RUT ficticio, una línea con distribución
triangular de mínimo 5, moda 25 y máximo 50 millones de pesos, y un MTA triangular de mínimo
500 mil, moda 1 millón y máximo 5 millones, ambos redondeados a miles. `actualizar_lineas_contrapartes.sql` actualiza sólo la línea y el
MTA, sin tocar las operaciones. `calces.csv` indica el grupo y
el rol de cada operación.

`cargar_cartera_sintetica.sql` reemplaza todas las operaciones y todas las contrapartes de la base:

```powershell
psql -U postgres -p 5434 -d Valorizador -f "datos cartera sintetica\cargar_cartera_sintetica.sql"
```

## Flujos de caja

`GET /cartera/flujos` entrega cada flujo con fecha de pago posterior a la fecha de proceso:
el monto de cada pata de un forward y, en los swaps, cada cupón y cada amortización. Los
cupones flotantes se proyectan con la curva de proyección de la pata y los valores de índice
ya publicados. Cada flujo va en su moneda y en CLP, convertido al spot de la fecha de
proceso, con signo: positivo lo que se recibe, negativo lo que se paga. La página
Vencimientos de la app usa este endpoint.

## Montos al vencimiento

`GET /cartera/vencimientos` considera las operaciones vigentes que vencen después de la
fecha de proceso y sólo el nocional que se intercambia al vencimiento:

- **Entrega física:** un monto por pata en su moneda, positivo si se recibe y negativo si
  se paga. Un forward da dos montos; una pata con cupones sólo si `intercambia_nocional`.
- **Compensación:** un único monto neto en CLP, con cada pata convertida al tipo de cambio
  spot de la fecha de proceso, no al forward. Un swap de una moneda no tiene monto.

Los cupones de los swaps no se incluyen.

## Actualizar una base existente

Una base creada antes de la revisión 0008 puede no tener las columnas `modalidad_liquidacion`
(revisión 0003) o `grupo_calce` (0005), tener la tabla de índices con el nombre `fixing`
(0004) o guardar el nombre de la contraparte en la operación en vez de su RUT (0006), o no tener
`tipo_amortizacion` en las patas (0007, que la deja en `BULLET` en las patas con cupones), o
no tener la tabla `usuario` (0008). Se actualiza con:

```powershell
alembic upgrade head
```

Después de la revisión 0008 hay que crear un usuario con `scripts/crear_usuario.py`; sin él no
se puede iniciar sesión.

Las operaciones existentes quedan como `COMPENSACION`. La revisión 0006 crea una contraparte
por cada nombre distinto, con RUT ficticio y línea y MTA en cero; la cartera sintética las
reemplaza por las suyas. La cartera preliminar trae su propia
modalidad: después de la migración, volver a ejecutar
`datos cartera preliminar/cargar_operaciones.sql`.

## Documentación del código

Todo el código está documentado con comentarios Doxygen: cada módulo, clase, método y
función tiene un docstring que empieza con tres comillas dobles seguidas de `!`, con `@brief`, `@param`, `@return` y
`@throws`, y los atributos y constantes llevan un comentario `##`. La configuración está en
`docs/Doxyfile` y la página de arquitectura y conexiones en `docs/arquitectura.md`.

Para generar la documentación HTML, con [Doxygen](https://www.doxygen.nl/download.html)
instalado, desde la carpeta del proyecto:

```powershell
doxygen docs/Doxyfile
```

Se abre en `docs/doxygen/html/index.html`. Esa carpeta no se versiona. Con Graphviz instalado
se puede poner `HAVE_DOT = YES` en `docs/Doxyfile` para agregar diagramas de clases y de
llamadas.

## Cambios al modelo de datos

Después de modificar `valorizador/db/modelos.py`:

```powershell
alembic revision --autogenerate -m "Descripción del cambio"
alembic upgrade head
```
