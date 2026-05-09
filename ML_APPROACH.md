# ML Approach — Smart Demand Signals

## Origen y Adaptación

El motor de Machine Learning de este proyecto se basa en el análisis exploratorio y
modelado predictivo realizado en el notebook de Colab del equipo:

> **[Notebook Colab — Análisis Predictivo Inibsa](https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_)**

Dicho notebook validó los siguientes hallazgos clave que hemos incorporado:

1. **XGBoost como algoritmo óptimo** — El notebook entrenó un XGBClassifier con
   `scale_pos_weight` para compensar el desbalanceo de clases, demostrando que
   los árboles de gradiente boosting son el algoritmo más adecuado para predecir
   la conversión/fuga de clientes en el dominio farmacéutico dental.

2. **Feature importance** — El análisis de importancia del modelo Colab confirmó
   que las variables de tendencia (pendiente lineal, Z-score) son los predictores
   más fuertes, seguidas por métricas de volumen y frecuencia. Esta conclusión
   guía la selección de features en nuestro modelo.

3. **Scoring 0-200** — El notebook implementó un sistema de puntuación comercial
   0-200 (`probabilidad × 200`), consistente con nuestro framework de priorización
   de 6 factores ponderados.

4. **Feedback loop** — El notebook propuso un ciclo de `registrar_feedback →
   reentrenar_modelo`, que hemos implementado como el pipeline nocturno de
   reentrenamiento automático.

5. **Segmentación PCA** — El notebook identificó 3 perfiles de cliente
   (generalistas de alto volumen, clínicas especializadas en biomateriales,
   centros operativos de anestesia/bioseguridad), que corresponden a nuestros
   perfiles `leal`, `promiscuo`, `marginal` basados en `ratio_promiscuidad`.

## Diferencias con el Notebook

| Aspecto | Notebook Colab | Nuestra Implementación |
|---------|---------------|----------------------|
| **Granularidad** | Agregados mensuales por cliente | Por alerta (cliente-familia-tipo) |
| **Target** | `Alerta_Caida_Tendencia` (sintético: pendiente < -5%) | `feedback` real del delegado (0/1) |
| **Features** | `Valores_H`, `Z_Score`, `Pendiente_6m`, `Media_6m`, `Pendiente_Relativa` | `tipo_alerta`, `bloque`, `provincia`, `perfil_cliente`, `potencial_h`, `impacto_estimado`, `urgencia_dias`, `ratio_promiscuidad`, `dias_desde_ultima_compra`, `freq_media_dias`, `n_compras_hist` |
| **Fuente de datos** | CSVs locales | PostgreSQL |
| **Scoring** | `probabilidad × 200` | 6 factores ponderados, ML = 20% (máx 40 pts) |
| **Reentrenamiento** | Manual en Colab | Automático nocturno en pipeline |

## Arquitectura del ML Engine

```
┌─────────────────────────────────────────────┐
│  Cold Start (sin feedback)                  │
│  ─────────────────────────────────────────  │
│  Heurística basada en:                      │
│    • tipo_alerta → probabilidad base        │
│    • perfil_cliente → multiplicador         │
│    • impacto_estimado → ajuste de impacto    │
│    • urgencia_dias → ajuste de timing        │
│                                              │
│  Valores derivados del análisis de feature   │
│  importance del notebook Colab               │
├─────────────────────────────────────────────┤
│  ML Model (con feedback suficiente)         │
│  ─────────────────────────────────────────  │
│  XGBClassifier:                             │
│    objective = binary:logistic              │
│    scale_pos_weight = n_neg / n_pos         │
│    n_estimators = 100                       │
│    learning_rate = 0.1                      │
│    max_depth = 4                             │
│                                              │
│  Preprocesado:                               │
│    • OneHotEncoder (tipo_alerta, bloque,    │
│      provincia, perfil_cliente)              │
│    • StandardScaler (potencial_h,           │
│      impacto_estimado, urgencia_dias, ...)   │
│                                              │
│  Target: feedback (0=negativo, 1=positivo)  │
│  Output: score_conversion (0-1)              │
├─────────────────────────────────────────────┤
│  Reentrenamiento Nocturno                   │
│  ─────────────────────────────────────────  │
│  1. Leer alertas_feedback (donde feedback    │
│     IS NOT NULL)                             │
│  2. Si n_samples >= 30: entrenar XGBoost    │
│  3. Guardar model.pkl + preprocessor.pkl     │
│  4. Guardar metadata.json                    │
│  5. El próximo run del pipeline carga el     │
│     modelo actualizado                       │
└─────────────────────────────────────────────┘
```

## Mejora Progresiva

| Feedback registrado | Comportamiento del score_conversion |
|--------------------|-------------------------------------|
| 0 samples | Heurística: combinación de tipo_alerta, perfil, impacto, urgencia |
| 1-29 samples | Heurística (insuficiente para entrenar) |
| 30+ samples | XGBoost con `scale_pos_weight`, mejora con cada reentrenamiento |

Cada noche el pipeline entrena (o salta) un nuevo modelo. Cuantos más
feedbacks acumule el sistema, más preciso será el `score_conversion`,
y mayor será la contribución del 20% ML al score final de prioridad.

## Archivos

| Archivo | Función |
|---------|---------|
| `analytics/src/ml_engine.py` | Inferencia: carga modelo o heurística, predice `score_conversion` |
| `analytics/src/ml_trainer.py` | Entrenamiento: lee feedback, entrena XGBoost, guarda modelo |
| `analytics/models/model.pkl` | Modelo XGBoost entrenado (autogenerado) |
| `analytics/models/preprocessor.pkl` | ColumnTransformer ajustado (autogenerado) |
| `analytics/models/metadata.json` | Métricas y parámetros del último entrenamiento |
| `analytics/utils/config.py` | Pesos de priorización y configuración del ML |