-- Migración: creación de la tabla de alertas
-- Sistema Smart Demand Signals (Inibsa · Interhack BCN 2026)
-- Versión: 1.0.0

BEGIN;

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

-- ─── Tabla principal ────────────────────────────────────

CREATE TABLE IF NOT EXISTS alertas (

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 1 — Datos que YA existen en la base de datos         ║
    -- ║  Origen: ventas, clientes, productos, potencial              ║
    -- ║  Responsable: tu compañero (INSERT directo)                  ║
    -- ╚══════════════════════════════════════════════════════════════╝

    id_cliente              TEXT        NOT NULL,
    familia                 TEXT        NOT NULL,
    bloque                  bloque_enum NOT NULL,
    provincia               TEXT        NOT NULL,
    potencial_h             REAL        NOT NULL CHECK (potencial_h >= 0),

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 2 — Columnas CALCULADAS (no existen en la BD)        ║
    -- ╚══════════════════════════════════════════════════════════════╝

    -- Calcular: CURRENT_DATE - MAX(ventas.fecha) para este cliente-familia
    dias_desde_ultima_compra INTEGER    DEFAULT NULL CHECK (dias_desde_ultima_compra IS NULL OR dias_desde_ultima_compra >= 0),

    -- Calcular: potencial_h - SUM(ventas.valores_h últimos 12 meses)
    -- Si valores_h es 0, usar SUM(ventas.unidades * precio_medio) en su lugar
    impacto_estimado        REAL        DEFAULT NULL CHECK (impacto_estimado IS NULL OR impacto_estimado >= 0),

    -- Calcular: media_dias_entre_compras - dias_desde_ultima_compra, clip(1, 30)
    urgencia_dias           SMALLINT    DEFAULT NULL CHECK (urgencia_dias IS NULL OR urgencia_dias BETWEEN 1 AND 90),

    -- Calcular: 1 - (compras_12m / potencial_h). Cuanto más se desvía de su
    -- potencial → más promiscuo. 0 = leal, 1 = compra casi todo a competencia.
    ratio_promiscuidad      REAL        DEFAULT NULL CHECK (ratio_promiscuidad IS NULL OR ratio_promiscuidad BETWEEN 0 AND 1),

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 3 — Generados por el sistema (automáticos)           ║
    -- ╚══════════════════════════════════════════════════════════════╝

    id_alerta               UUID        NOT NULL DEFAULT gen_random_uuid(),
    fecha                   DATE        NOT NULL DEFAULT CURRENT_DATE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 4 — Generados por el modelo detector (Fede)          ║
    -- ╚══════════════════════════════════════════════════════════════╝

    tipo_alerta             tipo_alerta_enum NOT NULL,
    motivo                  TEXT        NOT NULL,
    probabilidad_deteccion  REAL        DEFAULT NULL CHECK (probabilidad_deteccion BETWEEN 0 AND 1),
    
    -- Indicadores de los 4 puntos de detección solicitados
    alerta_frecuencia       BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_volumen          BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_ausencia         BOOLEAN     NOT NULL DEFAULT FALSE,
    alerta_anomalia         BOOLEAN     NOT NULL DEFAULT FALSE,
  

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 5 — Escritos por el priorizador (Yo, cada mañana)    ║
    -- ╚══════════════════════════════════════════════════════════════╝

    prioridad               SMALLINT    DEFAULT NULL CHECK (prioridad BETWEEN 0 AND 200),
    score_conversion        REAL        DEFAULT NULL CHECK (score_conversion BETWEEN 0 AND 1),

    -- ╔══════════════════════════════════════════════════════════════╗
    -- ║  BLOQUE 6 — Escritos por el delegado (cuando actúa)          ║
    -- ╚══════════════════════════════════════════════════════════════╝

    feedback                SMALLINT    DEFAULT NULL CHECK (feedback IN (0, 1)),
    fecha_feedback          DATE        DEFAULT NULL,

    -- ─── Constraints ─────────────────────────────────────────────
    CONSTRAINT pk_alertas PRIMARY KEY (id_alerta),
    CONSTRAINT chk_feedback_fecha CHECK (
        (feedback IS NULL AND fecha_feedback IS NULL) OR
        (feedback IS NOT NULL AND fecha_feedback IS NOT NULL)
    )
);

-- ─── Índices ─────────────────────────────────────────────

-- Búsqueda principal: alertas nuevas sin priorizar (el priorizador las lee cada mañana)
CREATE INDEX IF NOT EXISTS idx_alertas_pendientes
    ON alertas (fecha, prioridad)
    WHERE feedback IS NULL AND prioridad IS NULL;

-- Feedback acumulado para reentreno (el priorizador las lee cada noche)
CREATE INDEX IF NOT EXISTS idx_alertas_feedback
    ON alertas (fecha_feedback, feedback)
    WHERE feedback IS NOT NULL;

-- Consultas del dashboard: filtrar por provincia, tipo, urgencia
CREATE INDEX IF NOT EXISTS idx_alertas_dashboard
    ON alertas (provincia, tipo_alerta, bloque, prioridad DESC);

-- Búsqueda por cliente
CREATE INDEX IF NOT EXISTS idx_alertas_cliente
    ON alertas (id_cliente, fecha);

-- ─── Comentarios de columna ──────────────────────────────

COMMENT ON TABLE alertas IS 'Alertas comerciales generadas por el sistema Smart Demand Signals de Inibsa. Las escribe el motor de detección, las prioriza el motor de IA y las consume el delegado.';

-- Bloque 1: datos que vienen de la BD
COMMENT ON COLUMN alertas.id_cliente             IS '[DB → ventas / clientes] ID de la clínica dental';
COMMENT ON COLUMN alertas.familia                IS '[DB → productos.familia_h] Familia de producto';
COMMENT ON COLUMN alertas.bloque                 IS '[DB → productos.bloque_analitico] Commodities o Productos Técnicos';
COMMENT ON COLUMN alertas.provincia              IS '[DB → clientes.provincia] Provincia (53 valores, España)';
COMMENT ON COLUMN alertas.potencial_h            IS '[DB → potencial.potencial_h] Potencial de compra anual en € (enmascarado)';

-- Bloque 2: calculados por el priorizador
COMMENT ON COLUMN alertas.dias_desde_ultima_compra IS '[CALCULADO] CURRENT_DATE - MAX(ventas.fecha) para este cliente-familia';
COMMENT ON COLUMN alertas.impacto_estimado       IS '[CALCULADO] potencial_h - SUM(ventas últimos 12m). € no capturados, en manos de la competencia.';
COMMENT ON COLUMN alertas.urgencia_dias          IS '[CALCULADO] media_ciclo_compras - dias_desde_ultima_compra. Días de margen para contactar antes de perder la ventana.';
COMMENT ON COLUMN alertas.ratio_promiscuidad     IS '[CALCULADO] 1 - (compras_12m / potencial_h). 0 = leal, 1 = casi todo a competencia.';

-- Bloque 3: automáticos
COMMENT ON COLUMN alertas.id_alerta              IS '[AUTO] UUID generado por PostgreSQL';
COMMENT ON COLUMN alertas.fecha                  IS '[AUTO] Fecha en que se inserta la alerta';
COMMENT ON COLUMN alertas.created_at             IS '[AUTO] Timestamp de inserción';
COMMENT ON COLUMN alertas.updated_at             IS '[AUTO] Timestamp de última modificación (trigger)';

-- Bloque 4: modelo detector (compañero)
COMMENT ON COLUMN alertas.tipo_alerta            IS '[COMPAÑERO] ventana_captura | reposicion | riesgo_fuga | cliente_perdido';
COMMENT ON COLUMN alertas.motivo                 IS '[COMPAÑERO] Texto explicativo: qué reglas/variables activaron la alerta';
COMMENT ON COLUMN alertas.probabilidad_deteccion  IS '[COMPAÑERO] 0-1. Confianza del modelo detector al generar esta alerta';

-- Bloque 5: priorizador (tú)
COMMENT ON COLUMN alertas.prioridad              IS '[PRIORIZADOR] 0-200. A mayor valor, más urgente contactar. Sale del modelo de IA.';
COMMENT ON COLUMN alertas.score_conversion       IS '[PRIORIZADOR] 0-1. Probabilidad estimada de que la alerta convierta en venta.';

-- Bloque 6: delegado
COMMENT ON COLUMN alertas.feedback               IS '[DELEGADO] Resultado: 1 = venta, 0 = no venta, NULL = pendiente';
COMMENT ON COLUMN alertas.fecha_feedback         IS '[DELEGADO] Fecha en que se contactó al cliente';

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

-- ─── Vista: alertas listas para el delegado (ya priorizadas) ──

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

COMMENT ON VIEW alertas_feedback IS ' Vista que consume el priorizador cada noche: datos de entrenamiento con feedback real.';

COMMIT;
