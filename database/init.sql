
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
    valores_h FLOAT, -- Valor económico de la transacción[cite: 2]
    PRIMARY KEY (numero_factura, id_producto) -- Clave compuesta por factura y SKU
);

CREATE TABLE IF NOT EXISTS campanas (
    id_campana SERIAL PRIMARY KEY,
    campana TEXT,
    fecha_inicio DATE,
    fecha_fin DATE
);

-- CREATE TABLE IF NOT EXISTS alertas (
--     id_alerta SERIAL PRIMARY KEY,
--     fecha_generacion DATE DEFAULT CURRENT_DATE,
--     id_cliente INTEGER REFERENCES cliente(id),
--     familia_producto TEXT,
--     motivo_alerta TEXT, -- Ej: "Riesgo abandono" o "Ventana captura"
--     score_prioridad FLOAT, -- Basado en potencial e impacto
--     prioridad_texto TEXT, -- Alta, Media, Baja
--     canal_sugerido TEXT -- Delegado, Televenta o Marketing
-- );