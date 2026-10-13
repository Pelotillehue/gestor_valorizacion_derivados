-- =============================================================================
-- Valorizador de Derivados: esquema de base de datos para PostgreSQL
--
-- Crea las mismas tablas que "alembic upgrade head" y deja registrada la
-- revisión 0006, de modo que las migraciones futuras de Alembic se apliquen
-- sobre este esquema sin conflicto. Use este script o Alembic, no ambos.
--
-- Uso, sobre una base de datos ya creada y vacía:
--     psql -U postgres -d valorizador -f esquema.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------- contrapartes

-- Maestro de contrapartes. La línea y el MTA se expresan en CLP.
CREATE TABLE contraparte (
    rut                VARCHAR(12) NOT NULL,      -- sin puntos y con guion: 76123456-K
    nombre             VARCHAR(100) NOT NULL,
    monto_linea        FLOAT DEFAULT '0' NOT NULL, -- exposición aceptada sin garantías
    mta                FLOAT DEFAULT '0' NOT NULL, -- monto mínimo de transferencia
    creado_en          TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    actualizado_en     TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT contraparte_pkey PRIMARY KEY (rut),
    CONSTRAINT contraparte_nombre_key UNIQUE (nombre)
);

-- ----------------------------------------------------------------- operaciones

-- Una fila por operación, con los datos comunes a cualquier producto.
CREATE TABLE operacion (
    id                 SERIAL NOT NULL,
    deal_number        VARCHAR(50) NOT NULL,
    producto           VARCHAR(20) NOT NULL,      -- FX_FORWARD, IR_SWAP, CC_SWAP
    rut_contraparte    VARCHAR(12),
    modalidad_liquidacion VARCHAR(20) DEFAULT 'COMPENSACION' NOT NULL,  -- COMPENSACION, ENTREGA_FISICA
    grupo_calce        VARCHAR(30),               -- mismo grupo: se cubren entre sí; nulo: descalzada
    fecha_negociacion  DATE NOT NULL,
    estado             VARCHAR(20) NOT NULL,      -- VIGENTE, ANULADA
    version            INTEGER NOT NULL,          -- sube con cada modificación
    creado_en          TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    actualizado_en     TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT operacion_rut_contraparte_fkey FOREIGN KEY (rut_contraparte)
        REFERENCES contraparte (rut) ON UPDATE CASCADE
);

CREATE UNIQUE INDEX ix_operacion_deal_number ON operacion (deal_number);
CREATE INDEX ix_operacion_grupo_calce ON operacion (grupo_calce);
CREATE INDEX ix_operacion_rut_contraparte ON operacion (rut_contraparte);

-- Dos filas por operación. Las columnas que no aplican al tipo de pata quedan nulas.
CREATE TABLE pata (
    id                     SERIAL NOT NULL,
    operacion_id           INTEGER NOT NULL,
    numero                 INTEGER NOT NULL,
    tipo                   VARCHAR(20) NOT NULL,  -- SIMPLE, FIJA, INDICE_OVERNIGHT
    rec_pay                VARCHAR(10) NOT NULL,  -- RECIBE, PAGA
    moneda                 VARCHAR(3) NOT NULL,
    nocional               DOUBLE PRECISION NOT NULL,
    curva_descuento        VARCHAR(50) NOT NULL,
    -- Pata SIMPLE
    fecha_pago             DATE,
    -- Patas con cupones
    fecha_inicio           DATE,
    fecha_fin              DATE,
    periodicidad           VARCHAR(10),
    stub                   VARCHAR(15),
    ajuste_fecha           VARCHAR(15),
    calendario             VARCHAR(20),
    lag_pago               INTEGER,
    tipo_amortizacion      VARCHAR(15),
    intercambia_nocional   BOOLEAN,
    fraccion_anio          VARCHAR(10),
    factor_capitalizacion  VARCHAR(3),
    -- Pata FIJA
    tasa                   DOUBLE PRECISION,
    -- Pata INDICE_OVERNIGHT
    indice                 VARCHAR(30),
    curva_proyeccion       VARCHAR(50),
    spread                 DOUBLE PRECISION,
    gearing                DOUBLE PRECISION,
    decimales_tasa         INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY (operacion_id) REFERENCES operacion (id) ON DELETE CASCADE,
    UNIQUE (operacion_id, numero)
);

CREATE INDEX ix_pata_operacion_id ON pata (operacion_id);

-- Copia de la operación tal como estaba antes de cada modificación.
CREATE TABLE operacion_historial (
    id              SERIAL NOT NULL,
    operacion_id    INTEGER NOT NULL,
    version         INTEGER NOT NULL,
    datos           JSONB NOT NULL,
    reemplazado_en  TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (operacion_id) REFERENCES operacion (id) ON DELETE CASCADE,
    UNIQUE (operacion_id, version)
);

CREATE INDEX ix_operacion_historial_operacion_id ON operacion_historial (operacion_id);

-- --------------------------------------------------------------------- mercado

-- Tipos de cambio. El par BASECOTIZ vale unidades de COTIZ por una de BASE.
CREATE TABLE fx (
    fecha  DATE NOT NULL,
    par    VARCHAR(6) NOT NULL,
    valor  DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (fecha, par)
);

-- Encabezado de una curva cero en una fecha, con la convención de sus tasas.
CREATE TABLE curva (
    id                     SERIAL NOT NULL,
    fecha                  DATE NOT NULL,
    codigo                 VARCHAR(50) NOT NULL,
    fraccion_anio          VARCHAR(10) NOT NULL,
    factor_capitalizacion  VARCHAR(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (fecha, codigo)
);

CREATE INDEX ix_curva_fecha ON curva (fecha);

-- Vértices de cada curva: plazo en días y tasa en tanto por uno.
-- El código repite el de la curva, para consultar los vértices sin cruzar tablas.
CREATE TABLE curva_vertice (
    curva_id    INTEGER NOT NULL,
    codigo      VARCHAR(50) NOT NULL,
    plazo_dias  INTEGER NOT NULL,
    tasa        DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (curva_id, plazo_dias),
    FOREIGN KEY (curva_id) REFERENCES curva (id) ON DELETE CASCADE
);

-- Valores publicados de índices, por ejemplo ICPCLP o SOFRINDX.
CREATE TABLE valor_indice (
    indice  VARCHAR(30) NOT NULL,
    fecha   DATE NOT NULL,
    valor   DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (indice, fecha)
);

-- Feriados por calendario.
CREATE TABLE feriado (
    calendario  VARCHAR(20) NOT NULL,
    fecha       DATE NOT NULL,
    PRIMARY KEY (calendario, fecha)
);

-- --------------------------------------------------------------------- Alembic

-- Registro de la revisión aplicada, para que Alembic reconozca este esquema.
CREATE TABLE alembic_version (
    version_num  VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('0006');

COMMIT;
