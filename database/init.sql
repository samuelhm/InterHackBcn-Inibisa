
CREATE TABLE IF NOT EXISTS cliente (
    id SERIAL PRIMARY KEY,
    codigo_postal INTEGER,
    provincia TEXT
);


CREATE TABLE IF NOT EXISTS producto (
    id SERIAL PRIMARY KEY,
    bloque_analitico TEXT,
    categoria_h TEXT,
    familia TEXT
);

CREATE TABLE IF NOT EXISTS ventas (
    numero_factura BIGINT,
    fecha DATE NOT NULL,
    id_cliente INTEGER REFERENCES cliente(id),
    id_producto INTEGER REFERENCES producto(id),
    unidades INTEGER,
    valores_h FLOAT,
    PRIMARY KEY (numero_factura, id_producto)
);

CREATE TABLE IF NOT EXISTS campanas (
    id_campana SERIAL PRIMARY KEY,
    campana TEXT,
    fecha_inicio DATE,
    fecha_fin DATE
);

-- ─── ENUM types ──────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE tipo_alerta_enum AS ENUM (
        'ventana_captura',
        'reposicion',
        'riesgo_fuga',
        'cliente_perdido'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE bloque_enum AS ENUM (
        'Commodities',
        'Productos Técnicos'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ─── Tabla alertas ──────────────────────────────────────

CREATE TABLE IF NOT EXISTS alertas (

    id_cliente              TEXT        NOT NULL,
    familia                 TEXT        NOT NULL,
    bloque                  bloque_enum NOT NULL,
    provincia               TEXT        NOT NULL,
    potencial_h             REAL        NOT NULL CHECK (potencial_h >= 0),

    dias_desde_ultima_compra INTEGER    DEFAULT NULL CHECK (dias_desde_ultima_compra IS NULL OR dias_desde_ultima_compra >= 0),
    impacto_estimado        REAL        DEFAULT NULL CHECK (impacto_estimado IS NULL OR impacto_estimado >= 0),
    urgencia_dias           SMALLINT    DEFAULT NULL CHECK (urgencia_dias IS NULL OR urgencia_dias BETWEEN 1 AND 90),
    ratio_promiscuidad      REAL        DEFAULT NULL CHECK (ratio_promiscuidad IS NULL OR ratio_promiscuidad BETWEEN 0 AND 1),

    id_alerta               UUID        NOT NULL DEFAULT gen_random_uuid(),
    fecha                   DATE        NOT NULL DEFAULT CURRENT_DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    tipo_alerta             tipo_alerta_enum NOT NULL,
    motivo                  TEXT        NOT NULL,
    probabilidad_deteccion  REAL        DEFAULT NULL CHECK (probabilidad_deteccion BETWEEN 0 AND 1),

    alerta_frecuencia       BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_volumen          BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_ausencia         BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_anomalia         BOOLEAN     NOT NULL DEFAULT FALSE,

    prioridad               SMALLINT    DEFAULT NULL CHECK (prioridad BETWEEN 0 AND 200),
    score_conversion        REAL        DEFAULT NULL CHECK (score_conversion BETWEEN 0 AND 1),

    feedback                SMALLINT    DEFAULT NULL CHECK (feedback IN (0, 1)),
    fecha_feedback          DATE        DEFAULT NULL,

    CONSTRAINT pk_alertas PRIMARY KEY (id_alerta),
    CONSTRAINT chk_feedback_fecha CHECK (
        (feedback IS NULL AND fecha_feedback IS NULL) OR
        (feedback IS NOT NULL AND fecha_feedback IS NOT NULL)
    )
);

-- ─── Índices ─────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_alertas_pendientes
    ON alertas (fecha, prioridad)
    WHERE feedback IS NULL AND prioridad IS NULL;

CREATE INDEX IF NOT EXISTS idx_alertas_feedback
    ON alertas (fecha_feedback, feedback)
    WHERE feedback IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_alertas_dashboard
    ON alertas (provincia, tipo_alerta, bloque, prioridad DESC);

CREATE INDEX IF NOT EXISTS idx_alertas_cliente
    ON alertas (id_cliente, fecha);

-- ─── Comentarios ─────────────────────────────────────────

COMMENT ON TABLE alertas IS 'Alertas comerciales generadas por el sistema Smart Demand Signals de Inibsa. Las escribe el motor de detección, las prioriza el motor de IA y las consume el delegado.';

COMMENT ON COLUMN alertas.id_cliente             IS 'ID de la clínica dental';
COMMENT ON COLUMN alertas.familia                IS 'Familia de producto';
COMMENT ON COLUMN alertas.bloque                 IS 'Commodities o Productos Técnicos';
COMMENT ON COLUMN alertas.provincia              IS 'Provincia (53 valores, España)';
COMMENT ON COLUMN alertas.potencial_h            IS 'Potencial de compra anual en € (enmascarado)';

COMMENT ON COLUMN alertas.dias_desde_ultima_compra IS 'CURRENT_DATE - MAX(ventas.fecha) para este cliente-familia';
COMMENT ON COLUMN alertas.impacto_estimado       IS 'potencial_h - SUM(ventas últimos 12m). € no capturados, en manos de la competencia.';
COMMENT ON COLUMN alertas.urgencia_dias          IS 'media_ciclo_compras - dias_desde_ultima_compra. Días de margen para contactar antes de perder la ventana.';
COMMENT ON COLUMN alertas.ratio_promiscuidad     IS '1 - (compras_12m / potencial_h). 0 = leal, 1 = casi todo a competencia.';

COMMENT ON COLUMN alertas.id_alerta              IS 'UUID generado por PostgreSQL';
COMMENT ON COLUMN alertas.fecha                  IS 'Fecha en que se inserta la alerta';
COMMENT ON COLUMN alertas.created_at             IS 'Timestamp de inserción';
COMMENT ON COLUMN alertas.updated_at             IS 'Timestamp de última modificación (trigger)';

COMMENT ON COLUMN alertas.tipo_alerta            IS 'ventana_captura | reposicion | riesgo_fuga | cliente_perdido';
COMMENT ON COLUMN alertas.motivo                 IS 'Texto explicativo: qué reglas/variables activaron la alerta';
COMMENT ON COLUMN alertas.probabilidad_deteccion  IS '0-1. Confianza del modelo detector al generar esta alerta';

COMMENT ON COLUMN alertas.prioridad              IS '0-200. A mayor valor, más urgente contactar. Sale del modelo de IA.';
COMMENT ON COLUMN alertas.score_conversion       IS '0-1. Probabilidad estimada de que la alerta convierta en venta.';

COMMENT ON COLUMN alertas.feedback               IS 'Resultado: 1 = venta, 0 = no venta, NULL = pendiente';
COMMENT ON COLUMN alertas.fecha_feedback         IS 'Fecha en que se contactó al cliente';

-- ─── Trigger: updated_at automático ─────────────────────

CREATE OR REPLACE FUNCTION trg_alertas_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    CREATE TRIGGER alertas_updated_at
        BEFORE UPDATE ON alertas
        FOR EACH ROW
        EXECUTE FUNCTION trg_alertas_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ─── Vista: alertas listas para el delegado ──────────────

CREATE OR REPLACE VIEW alertas_delegado AS
SELECT
    id_alerta,
    fecha,
    id_cliente,
    familia,
    tipo_alerta,
    motivo,
    provincia,
    impacto_estimado,
    urgencia_dias,
    prioridad,
    score_conversion,
    feedback
FROM alertas
WHERE prioridad IS NOT NULL
ORDER BY prioridad DESC;

COMMENT ON VIEW alertas_delegado IS 'Vista que consume el delegado/dashboard: solo alertas ya priorizadas, ordenadas por prioridad descendente.';

-- ─── Vista: feedback para reentreno ──────────────────────

CREATE OR REPLACE VIEW alertas_feedback AS
SELECT
    id_alerta,
    fecha,
    tipo_alerta,
    bloque,
    familia,
    provincia,
    impacto_estimado,
    urgencia_dias,
    dias_desde_ultima_compra,
    ratio_promiscuidad,
    probabilidad_deteccion,
    prioridad,
    score_conversion,
    feedback,
    fecha_feedback
FROM alertas
WHERE feedback IS NOT NULL
ORDER BY fecha_feedback DESC;

COMMENT ON VIEW alertas_feedback IS 'Vista que consume el priorizador cada noche: datos de entrenamiento con feedback real.';
