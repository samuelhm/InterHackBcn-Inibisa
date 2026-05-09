<div align="center">
  <img src="resource/logo_center-ubopVpzx.svg" alt="InterHack BCN 2026" width="380" />

  # Smart Demand Signals

  **Prediccion de compra y deteccion temprana de riesgo de abandono en clinicas dentales**

  [![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
  [![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://postgresql.org)
  [![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?logo=streamlit)](https://streamlit.io)
  [![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://docker.com)
  [![XGBoost](https://img.shields.io/badge/XGBoost-ML-AA4A44)](https://xgboost.readthedocs.io)
  [![BCN Clima](https://img.shields.io/badge/BCN_Clima-Sostenibilidad-2ecc71)](https://www.barcelona.cat/bcnclima)

</div>

---

## El reto

Inibsa opera con ~6.000 clinicas dentales y 5+ anos de historico de ventas. El problema: **los delegados comerciales no saben a que clinica llamar, para que producto, ni por que**. Existen dos dinamicas radicalmente distintas:

- **Commodities** (anestesia, agujas, desinfeccion): compra recurrente donde la competencia captura hasta el 80% del potencial de algunas clinicas sin que Inibsa lo detecte.
- **Productos tecnicos** (implantes, biomateriales): compra variable donde un deterioro silencioso precede al abandono definitivo del cliente.

**Smart Demand Signals** transforma datos transaccionales en alertas comerciales accionables que dicen al delegado: _"llama a esta clinica, por este producto, ahora, y por esta razon"_.

---

## Que hace

```
┌─────────────────────────────────────────────────────┐
│  CAPA DE ACTIVACION (Streamlit)                      │
│  Dashboard · KPIs · Filtros · Feedback               │
├─────────────────────────────────────────────────────┤
│  CAPA ANALITICA (Python)                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐         │
│  │Commodity │  │Technical │  │Prioritazer│         │
│  │ Engine   │  │ Engine   │  │ + ML      │         │
│  │captura   │  │riesgo    │  │score 0-200│         │
│  │reposicion│  │fuga      │  │6 factores │         │
│  └──────────┘  └──────────┘  └───────────┘         │
│  Pipeline diario · Reentrenamiento ML nocturno       │
├─────────────────────────────────────────────────────┤
│  CAPA DE DATOS (PostgreSQL)                          │
│  clientes · productos · ventas · potencial · alertas │
└─────────────────────────────────────────────────────┘
```

### 1. Deteccion dual con 4 patrones por bloque

| Patron | Commodity | Technical |
|--------|-----------|-----------|
| Caida de frecuencia | gap > 1.5x media | gap > 1.3x media |
| Caida de volumen | importe < 50% media | importe < 60% media |
| Ausencia de compra | > max(30d, 2x freq) | > max(45d, 1.5x freq) |
| Anomalia (Z-score) | Z > 2.0 | Z > 2.0 |

**Filtro anti-ruido**: en productos tecnicos, si el CV del cliente > 1.0 (comprador erratico), se requieren **2+ patrones simultaneos** para evitar falsos positivos.

### 2. Priorizacion inteligente (0-200)

Cada alerta recibe una prioridad combinando **6 factores ponderados**:

| Factor | Peso | Max pts |
|--------|------|---------|
| Tipo de alerta | 30% | 60 |
| Potencial del cliente | 17.5% | 35 |
| Impacto estimado (en EUR) | 12.5% | 25 |
| Urgencia temporal | 10% | 20 |
| Perfil del cliente | 10% | 20 |
| **ML score (XGBoost)** | **20%** | **40** |

### 3. Machine Learning que mejora cada dia

- **Cold-start inteligente**: sin feedback suficiente, usa una heuristica que ya diferencia (ventana_captura = 0.65, cliente_perdido = 0.20). No empieza en 0.
- **XGBoost con scale_pos_weight** para compensar el desbalanceo natural de clases.
- **Reentrenamiento nocturno** con `alertas_feedback`: cada feedback del delegado afina el modelo.
- **Mejora demostrable**: con solo 500 feedbacks, el XGBoost ya discrimina mejor que la heuristica (ventana_captura+marginal = 0.90, riesgo_fuga+promiscuo = 0.29).

### 4. Trazabilidad total — no caja negra

Cada alerta incluye:
- **Motivo descriptivo**: "Sin compra hace 129d (umbral: 60d basado en frecuencia media de 30d)"
- **4 flags booleanos** que indican que patron se activo
- **Metricas de contexto**: `perfil_cliente`, `freq_media_dias`, `n_compras_hist`, `ratio_promiscuidad`
- **Score de prioridad y conversion** transparentes y auditables

---

## Demo

```
$ docker compose up

✔ Network inibisa_network   Created
✔ Container inibsa_db        Healthy
✔ Container inibsa_frontend  Started
✔ Container inibsa_analytics Started
```

- **5.282 alertas** generadas sobre datos reales de 6.000 clinicas
- Dashboard con KPIs, filtros, y flujo de feedback
- Pipeline diario automatizado: deteccion → priorizacion → ML

<div align="center">
  <em>(screenshots del dashboard aqui)</em>
</div>

---

## Tecnologia

| Capa | Stack | Proposito |
|------|-------|-----------|
| Datos | PostgreSQL 16 | Schema relacional con ENUMs, indices, triggers y vistas |
| Ingesta | Python (pandas, SQLAlchemy) | Carga `Datasets.xlsx` → PostgreSQL |
| Deteccion | Python (pandas, numpy) | 2 engines independientes (commodity + technical) |
| Priorizacion | Python (pandas) | Score 0-200 con 6 factores ponderados |
| ML | XGBoost + scikit-learn | Clasificacion binaria con `scale_pos_weight` |
| Frontend | Streamlit | Dashboard, KPIs, filtros, feedback |
| Orquestacion | Docker Compose | 3 servicios: db, analytics, frontend |

---

## Estructura del proyecto

```
inibisa/
├── analytics/              # Pipeline analitico y ML
│   ├── src/
│   │   ├── engine_commodity.py   # Deteccion commodities
│   │   ├── engine_technical.py   # Deteccion tecnicos
│   │   ├── ml_engine.py          # Inferencia ML (XGBoost + cold-start)
│   │   ├── ml_trainer.py         # Entrenamiento nocturno XGBoost
│   │   └── prioritizer.py        # Scoring 0-200 con 6 factores
│   ├── models/             # Modelos entrenados (autogenerados)
│   ├── utils/              # DB connector, config, metrics
│   ├── main.py             # Orquestador del pipeline diario
│   └── Dockerfile
├── database/               # PostgreSQL + schema
│   ├── init.sql            # Tablas, ENUMs, indices, triggers, vistas
│   ├── ingest_all.py       # Pipeline de ingesta Excel → DB
│   └── Dockerfile
├── frontend/               # Dashboard Streamlit
│   ├── app.py              # UI principal con KPIs, filtros, feedback
│   └── Dockerfile
├── resource/               # Assets (logos)
├── docker-compose.yml      # Orquestacion 3 servicios
├── presentacion.md         # Guion de presentacion
├── ML_APPROACH.md          # Documentacion del enfoque ML
└── ROADMAP.md              # Plan de fases
```

---

## Metricas de exito

| Metrica | Definicion | Medible desde |
|---------|-----------|---------------|
| Tasa de conversion | alertas con feedback=1 / total feedback | Dia 1 |
| Tasa de recuperacion | cliente_perdido recuperado / total perdidos | Dia 1 |
| Precision del ML | accuracy XGBoost en test set | Tras 30+ feedbacks |
| Reduccion de ruido | alertas con 2+ patrones / total tecnicos | Dia 1 |
| Mejora progresiva | recall y accuracy registrados en `metadata.json` | Cada reentrenamiento |

---

## Sostenibilidad — BCN Clima

- Optimizacion de rutas comerciales: menos kilometros = menos emisiones
- Eficiencia operativa: detectar + priorizar = maximizar impacto con minimo esfuerzo
- Infraestructura ligera: PostgreSQL + Python + Streamlit, sin clusters de GPU

---

## Equipo

|  |  |
|----------|------|
| **Samuel Hurtado** | Desarrollo backend + ML Engine |
| **Carlos Murillo** | Analisis exploratorio + deteccion |
| **Agustin Paternoster** | Arquitectura + infraestructura |
| **Federico Carranza** | Frontend + UX |

---

## Instalacion

```bash
# 1. Clonar
git clone https://github.com/usuario/inibisa-smart-demand.git
cd inibisa-smart-demand

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con credenciales de DB

# 3. Levantar todo
docker compose up -d

# 4. Acceder al dashboard
open http://localhost:8501
```

---

<div align="center">
  <sub>InterHack BCN 2026 · Barcelona Innovation Coast · Smart Demand Signals</sub>
</div>