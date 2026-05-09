# AGENTS.md — Smart Demand Signals (Inibsa · InterHack BCN 2026)

## Project Overview

Smart Demand Signals es una solución analítica para Inibsa (fabricante farmacéutico dental) que transforma datos transaccionales de ~6.000-7.000 clínicas dentales en alertas comerciales accionables. El sistema detecta patrones de deterioro de compra y ventanas de oportunidad, prioriza las alertas, y las expone en una UI para que delegados/televenta actúen. Una IA con ML aprende del feedback recibido para ajustar prioridades.

El proyecto se presenta en el InterHack BCN 2026, dentro del marco BCN Clima (criterios de sostenibilidad).

## Tech Stack

| Capa | Tecnología | Detalle |
|------|-----------|---------|
| Base de datos | PostgreSQL (Docker) | Tablas: cliente, producto, ventas, campanas, potencial, alertas |
| Ingesta | Python (pandas, openpyxl, sqlalchemy) | Lee `data/Datasets.xlsx` → PostgreSQL |
| Motor de detección | Python (pandas, numpy, sqlalchemy) | Análisis estadístico por cliente-familia |
| Priorizador / IA | Python (scikit-learn / xgboost) | ML entrenado con feedback diario |
| Frontend | Streamlit | Dashboard de alertas + asignación de feedback |
| Orquestación | Docker Compose | 3 servicios: db, analytics, frontend |

## Architecture (3-layer)

```
┌──────────────────────────────────────────────┐
│  CAPA DE ACTIVACIÓN (Streamlit UI)            │
│  - Muestra alertas con feedback NULL          │
│  - Permite asignar feedback (positivo/negativo)│
│  - Filtros por provincia, tipo, familia       │
├──────────────────────────────────────────────┤
│  CAPA ANALÍTICA (Python)                      │
│  ┌────────────┐ ┌──────────────┐ ┌─────────┐ │
│  │ Commodity  │ │ Technical    │ │Prioritiz│ │
│  │ Engine     │ │ Engine       │ │  -er    │ │
│  │(consumo    │ │(riesgo fuga, │ │(ML 0-200│ │
│  │ esperado,  │ │ caída free,  │ │ score)  │ │
│  │ promiscuidad│ │ volumen,     │ │         │ │
│  │ captura)   │ │ ausencia,    │ │         │ │
│  │            │ │ anomalía)    │ │         │ │
│  └────────────┘ └──────────────┘ └─────────┘ │
│  Pipeline diario: detección → priorización    │
│  Entrenamiento nocturno con feedback recolectado│
├──────────────────────────────────────────────┤
│  CAPA DE DATOS (PostgreSQL)                   │
│  cliente | producto | ventas | potencial      │
│  campanas | alertas (tabla central)           │
└──────────────────────────────────────────────┘
```

## Database Schema (`alertas` table)

La tabla `alertas` es el núcleo del sistema. Su esquema completo está en `example/001_create_alertas.sql`. Columnas clave:

| Bloque | Columnas | Responsable |
|--------|----------|-------------|
| 1 - Datos DB | id_cliente, familia, bloque, provincia, potencial_h | Ingesta |
| 2 - Calculados | dias_desde_ultima_compra, impacto_estimado, urgencia_dias, ratio_promiscuidad | Analytics |
| 3 - Auto | id_alerta (UUID), fecha, created_at, updated_at | Sistema |
| 4 - Detector | tipo_alerta, motivo, probabilidad_deteccion, alerta_frecuencia/volumen/ausencia/anomalia | Engine |
| 5 - Priorizador | prioridad (0-200), score_conversion (0-1) | IA/ML |
| 6 - Feedback | feedback (0=negativo, 1=positivo), fecha_feedback | UI/Delegado |

**ENUMs:** `tipo_alerta_enum` = `ventana_captura`, `reposicion`, `riesgo_fuga`, `cliente_perdido`
           `bloque_enum` = `Commodities`, `Productos Técnicos`

## Key Business Logic

### Detección (4 patrones por cliente-familia)
1. **Caída de frecuencia** — gap entre compras > 1.5× media histórica
2. **Caída de volumen** — último importe < 50% media histórica
3. **Ausencia de compra** — días desde última compra > max(30, 2× frecuencia media)
4. **Actividad anómala** — Z-score > 2 en importe o volumen

### Diferenciación Commodities vs Técnicos
- **Commodities** (anestesia, agujas, desinfección): compra recurrente. Lógica de consumo esperado, ratio de promiscuidad, ventanas de captura frente a competencia.
- **Técnicos**: compra variable según caso clínico/especialidad. Lógica de deterioro de patrón, riesgo de abandono.

### Priorización (score 0-200)
Factores con pesos configurables:
- Beneficio potencial para la empresa (potencial_h, impacto_estimado)
- Tipo de cliente (leal, promiscuo, marginal)
- Tipo de alerta (ventana_captura > reposicion > riesgo_fuga > cliente_perdido)
- Probabilidad de éxito (ML entrenado con feedback histórico)

### Machine Learning
- Entrenamiento diario con datos de `alertas_feedback` (alertas con feedback != NULL)
- Features: tipo_alerta, bloque, provincia, impacto_estimado, urgencia_dias, ratio_promiscuidad, dias_desde_ultima_compra, etc.
- Target: feedback (0 o 1)
- Output: `score_conversion` (probabilidad de éxito) que se integra en la prioridad final
- El modelo ajusta pesos de prioridad según patrones aprendidos

## Getting Started

```bash
# 1. Levantar la base de datos (ingesta automática del Excel)
docker compose up db -d

# 2. Crear tabla alertas (solo primera vez)
docker compose exec db psql -U admin_inibsa -d inibsa_smart_signals \
  -f /docker-entrypoint-initdb.d/001_create_alertas.sql
# (Nota: copiar el SQL a init.sql o montarlo como volumen extra)

# 3. Ejecutar detección
python3 detector_alertas.py

# 4. (WIP) Ejecutar pipeline completo + UI
docker compose up
```

## Conventions

- **Idioma**: código en inglés (variables, funciones, comentarios técnicos), datos y alertas en español (nombres de columna de negocio, motivos, tipos)
- **Python**: type hints donde sea útil, docstrings en funciones públicas
- **SQL**: snake_case, comentarios de columna con `COMMENT ON`
- **Commits**: convencionales (`feat:`, `fix:`, `refactor:`, `docs:`)
- **Variables de entorno**: cargar desde `.env` con `python-dotenv`, nunca hardcodear credenciales
- **Fechas**: la fecha de referencia del hackathon es `2026-05-09` (hardcodeada en `FECHA_HOY`). En producción usar `datetime.now()`.

## Project Structure

```
inibisa/
├── database/          # PostgreSQL + ingesta de datos
│   ├── init.sql       # Schema base (cliente, producto, ventas, campanas)
│   ├── ingest_all.py  # Pipeline de ingesta Excel → PostgreSQL
│   └── Dockerfile     # Imagen Postgres + Python para ingesta
├── analytics/         # Pipeline analítico y priorización
│   ├── main.py        # Orquestador del pipeline diario
│   ├── src/
│   │   ├── engine_commodity.py   # Lógica productos commodity
│   │   ├── engine_technical.py   # Lógica productos técnicos
│   │   └── prioritizer.py        # Scoring y ML
│   ├── models/        # Modelos entrenados (.pkl, .json)
│   └── utils/         # Conectores DB, helpers
├── frontend/          # Streamlit dashboard
│   ├── app.py         # UI principal
│   └── requirements.txt
├── example/           # SQL de referencia
│   └── 001_create_alertas.sql  # Esquema completo alertas
├── docs/              # Documentación del hackathon (PDFs)
├── data/              # Datos raw (Datasets.xlsx)
├── detector_alertas.py # Script standalone de detección (prototipo)
├── docker-compose.yml
└── .env
```

## Current Status

| Componente | Estado |
|-----------|--------|
| DB + ingesta | Funcional |
| Tabla alertas (schema) | Definido en `example/`, no en `init.sql` |
| Motor de detección | Prototipo funcional (`detector_alertas.py`) |
| Engine Commodity | Por implementar |
| Engine Technical | Por implementar |
| Priorizador + ML | Por implementar |
| Frontend Streamlit | Por implementar |
| Pipeline diario | Por implementar |
| Entrenamiento ML nocturno | Por implementar |
