# Arquitectura y conexiones {#arquitectura}

El Valorizador de Derivados tiene tres piezas que se ejecutan por separado y se comunican
sólo por HTTP o SQL:

```
 ┌─────────────────────┐   HTTP (httpx)   ┌──────────────────────────────────────────┐
 │  App Streamlit      │ ───────────────▶ │  API FastAPI  (valorizador.main)         │
 │  app/inicio.py      │                  │                                          │
 │  app/paginas/*      │                  │  valorizador.api.*        endpoints      │
 │  app/comun/api.py   │                  │      │                                   │
 └─────────────────────┘                  │      ├─▶ valorizador.repositorios.*  ───┐ │
                                          │      │        (SQLAlchemy)              │ │
 ┌─────────────────────┐   HTTP (httpx)   │      │                                  │ │
 │  scripts/           │ ───────────────▶ │      └─▶ valorizador.valorizacion.*     │ │
 │  cargar_indices.py  │                  │               (QC Financial)            │ │
 └─────────┬───────────┘                  └─────────────────────────────────────────┼─┘
           │ HTTP                                                                   │ SQL (psycopg 3)
           ▼                                                                        ▼
 ┌─────────────────────┐                                              ┌──────────────────────┐
 │ Servicio de datos   │                                              │  PostgreSQL          │
 │ de mercado (ICP,    │                                              │  base "Valorizador"  │
 │ SOFR)               │                                              │  migraciones Alembic │
 └─────────────────────┘                                              └──────────────────────┘
```

## Conexiones

| Desde | Hacia | Cómo | Dónde se configura |
|---|---|---|---|
| API | PostgreSQL | SQLAlchemy 2 con el driver psycopg 3; un pool de conexiones y una sesión por solicitud | `DATABASE_URL` en `.env` (@ref valorizador.config.Configuracion, @ref valorizador.db.base) |
| Tests | PostgreSQL de pruebas | Misma conexión, sobre una base que se borra y recrea | `DATABASE_URL_TEST` en `.env` |
| Alembic | PostgreSQL | Usa la misma `DATABASE_URL` y los modelos ORM | `migraciones/env.py` |
| App | API | `httpx`, con caché de Streamlit de 5 minutos | Barra lateral o `VALORIZADOR_API_URL` (@ref comun.api) |
| `cargar_indices.py` | Servicio de mercado y API | `httpx`: descarga del servicio y carga con `POST /mercado/indices` | Argumentos `--servicio` y `--api` |
| Motor | QC Financial | Llamadas en memoria; ningún objeto de la librería se guarda en la base | @ref valorizador.valorizacion.constructores |

## Capas de la API

1. **Endpoints** (@ref valorizador.api): reciben y validan la solicitud con los esquemas de
   @ref valorizador.schemas y devuelven la respuesta. No ejecutan SQL.
2. **Repositorios** (@ref valorizador.repositorios): única capa que lee y escribe en la base.
   Convierten entre los modelos ORM de @ref valorizador.db.modelos y los esquemas.
3. **Motor** (@ref valorizador.valorizacion): funciones puras. Reciben la operación y un
   @ref valorizador.valorizacion.escenario.EscenarioMercado y devuelven el resultado.
4. **Errores** (@ref valorizador.errores): las capas inferiores lanzan errores del dominio y
   @ref valorizador.main los traduce a códigos HTTP.

## Flujo de una valorización

1. `GET /operaciones/{deal_number}/mtm?fecha=` llega a @ref valorizador.api.operaciones.mtm.
2. El repositorio lee la operación y la convierte a
   @ref valorizador.schemas.operaciones.OperacionEntrada.
3. @ref valorizador.repositorios.mercado.cargar_escenario_cartera lee las curvas de descuento y
   proyección de las patas, los tipos de cambio, los índices y los feriados de la fecha.
4. @ref valorizador.valorizacion.motor.valorizar construye cada pata en QC Financial, fija o
   proyecta los índices de las patas flotantes, descuenta con la curva de descuento y convierte
   a la moneda de valorización.

## Generar esta documentación

Requiere [Doxygen](https://www.doxygen.nl) 1.9 o posterior. Desde la carpeta del proyecto:

```
doxygen docs/Doxyfile
```

El resultado queda en `docs/doxygen/html/index.html`. Si además está instalado Graphviz, se
puede poner `HAVE_DOT = YES` en `docs/Doxyfile` para obtener diagramas de clases y de llamadas.

Convenciones de los comentarios en el código:

- Cada módulo, clase, método y función tiene un docstring que empieza con tres comillas dobles seguidas de `!`, la marca con
  que Doxygen interpreta los comandos dentro de un docstring de Python.
- Comandos usados: `@package`, `@brief`, `@param`, `@return`, `@throws`, `@ref`, `@code`.
- Los atributos y constantes se documentan con un comentario `##` en la línea anterior.
- FastAPI usa los docstrings de los endpoints y de los esquemas como descripción en `/docs`;
  @ref valorizador.main.texto_openapi quita los comandos Doxygen antes de mostrarlos.
