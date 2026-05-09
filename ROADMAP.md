# ROADMAP — Smart Demand Signals

---

## Fase 1: Tabla alertas en init.sql ✅ COMPLETADA

**Objetivo:** Que la tabla `alertas` se cree automáticamente al levantar la DB.

- [x] Migrar el contenido de `example/001_create_alertas.sql` a `database/init.sql` (ENUMs, tabla, índices, triggers, vistas `alertas_delegado` y `alertas_feedback`)
- [x] Alternativa descartada — migración directa a `init.sql`
- [x] Verificar que la tabla se crea correctamente: `docker compose down -v && docker compose up db -d`

---

## Fase 2: Utilidades compartidas (analytics/utils/) ✅ COMPLETADA

**Objetivo:** Módulos reutilizables por todos los engines y el pipeline.

- [x] `analytics/utils/db.py` — Conexión SQLAlchemy a PostgreSQL (lectura de `.env`)
- [x] `analytics/utils/config.py` — Pesos configurables de priorización (dict con defaults). Factores:
  - Peso por tipo de alerta (`ventana_captura` = 1.0, `reposicion` = 0.83, `riesgo_fuga` = 0.67, `cliente_perdido` = 0.50)
  - Peso por tipo de cliente (leal 1.0, promiscuo 0.80, marginal 0.50)
  - Peso por potencial_h (17.5%)
  - Peso por urgencia (10%)
  - Peso por impacto_estimado (12.5%)
  - Peso del score ML (20% — 0% mientras no esté implementado)
  - Thresholds de detección por bloque (Commodity vs Technical)
  - `DEDUP_WINDOW_DAYS = 7`, `MAX_INACTIVE_DAYS = 365`, `FECHA_HOY` configurable vía env
- [x] `analytics/utils/metrics.py` — Funciones compartidas de cálculo (frecuencia media, volumen medio, Z-score, días desde última compra, ratio de promiscuidad, impacto estimado, urgencia, clasificación de perfil)

---

## Fase 3: Engine Commodity ✅ COMPLETADA

**Objetivo:** Detectar ventanas de captura y necesidad de reposición en productos commodity.

Archivo: `analytics/src/engine_commodity.py`

- [x] **Clasificar clientes por familia** en 3 perfiles (`perfil_cliente`: leal/promiscuo/marginal)
- [x] **Estimar consumo esperado** por cliente-familia a partir de su potencial_h y frecuencia media histórica
- [x] **Detectar ventana de captura** (clientes promiscuos/marginales):
  - `impacto_estimado = potencial_h - SUM(compras_12m)`
  - Cuando `dias_desde_ultima_compra > freq_media × 0.7` → alerta `ventana_captura`
- [x] **Detectar reposición** (clientes leales):
  - Cuando `dias_desde_ultima_compra > freq_media × 0.6` → alerta `reposicion`
- [x] **Escribir alertas** en tabla `alertas` con bloque `Commodities`
- [x] **Calcular columnas del bloque 2**: `impacto_estimado`, `urgencia_dias`, `ratio_promiscuidad`, `dias_desde_ultima_compra`
- [x] **Columnas adicionales para trazabilidad y ML**: `perfil_cliente`, `freq_media_dias`, `n_compras_hist`
- [x] **Motivos descriptivos** con valores reales y umbrales (ej: "Sin compra hace 129d, umbral: 30d basado en frecuencia media de 0d")
- [x] **Deduplicación**: `_alert_exists()` evita alertas duplicadas para el mismo cliente-familia si ya hay una pendiente en los últimos 7 días
- [x] **Filtro de inactividad**: no genera alertas para cliente-familias inactivos > 365 días

---

## Fase 4: Engine Technical ✅ COMPLETADA

**Objetivo:** Detectar deterioro de compra y riesgo de abandono en productos técnicos.

Archivo: `analytics/src/engine_technical.py`

- [x] **4 procesos de detección** por cliente-familia:
  1. **Caída de frecuencia**: gap actual > 1.3× media histórica (más sensible que commodity)
  2. **Caída de volumen**: último importe < 60% media histórica (más sensible que commodity)
  3. **Ausencia de compra**: días desde última compra > max(45, 1.5× frecuencia media)
  4. **Actividad anómala**: Z-score > 2 en importe
- [x] **Distinguir ruido de señal**:
  - No alertar si CV > 1.0 y < 2 patrones simultáneos (comprador esporádico)
  - ~~No alertar si coincide con estacionalidad~~ → planificado en `low_priority_todo.md` (requiere cruce con tabla `campanas`)
- [x] **Clasificar tipo de alerta**:
  - `reposicion`: cliente acercándose a su ciclo de compra
  - `riesgo_fuga`: deterioro detectado pero cliente aún activo
  - `cliente_perdido`: ausencia > 180 días
- [x] **Escribir alertas** en tabla `alertas` con bloque `Productos Técnicos`
- [x] **Calcular columnas del bloque 2**: mismas que commodity + `perfil_cliente`, `freq_media_dias`, `n_compras_hist`
- [x] **Deduplicación** y **filtro de inactividad** igual que commodity

---

## Fase 5: Priorizador ✅ COMPLETADA

**Objetivo:** Asignar una prioridad numérica (0-200) a cada alerta generada.

Archivo: `analytics/src/prioritizer.py`

- [x] **Leer alertas sin priorizar** (`prioridad IS NULL`) de la tabla `alertas`
- [x] **Calcular score base** (0-200) combinando con pesos configurables:
  - Peso por tipo de alerta (`ventana_captura` = 1.0, `reposicion` = 0.83, `riesgo_fuga` = 0.67, `cliente_perdido` = 0.50)
  - Peso por potencial_h normalizado (0-1) dentro del batch
  - Peso por impacto_estimado normalizado (0-1) dentro del batch
  - Peso por urgencia (a menor urgencia_dias, mayor peso)
  - Peso por tipo de cliente (leal 1.0, promiscuo 0.80, marginal 0.50)
- [x] **Integrar score ML**: `score_conversion = ml.get_score(alert_id)`. Stub devuelve 0.0; peso 20% (40 pts máx)
- [x] **Escribir** `prioridad` y `score_conversion` en la tabla `alertas`
- [x] **Pesos configurables** desde `utils/config.py` — diccionario Python con valores por defecto

**Resultado promedio:** ventana_captura 95, reposicion 90, riesgo_fuga 72, cliente_perdido 70. Rango total 50–139.

---

## Fase 6: ML Engine ✅ COMPLETADA

**Objetivo:** Motor de ML que predice la probabilidad de conversión de cada alerta.

Archivos: `analytics/src/ml_engine.py`, `analytics/src/ml_trainer.py`

- [x] **Cold-start heuristic** — cuando no hay suficiente feedback, devuelve probabilidades basadas en tipo_alerta, perfil_cliente, impacto y urgencia (derivado del feature importance del notebook Colab)
- [x] **XGBoost** con `scale_pos_weight` para desbalanceo de clases (enfoque validado en el Colab del equipo)
- [x] **Features**: tipo_alerta, bloque, provincia, perfil_cliente (OneHotEncoder) + potencial_h, impacto_estimado, urgencia_dias, ratio_promiscuidad, dias_desde_ultima_compra, freq_media_dias, n_compras_hist (StandardScaler)
- [x] **Target**: `feedback` real del delegado (0=negativo, 1=positivo)
- [x] **Threshold mínimo**: 30 muestras de feedback para entrenar (configurable en `ml_engine.py`)
- [x] **Persistencia**: model.pkl, preprocessor.pkl, metadata.json en `analytics/models/`
- [x] **Integración en priorizador**: `predict_batch()` reemplaza el stub que devolvía 0.0
- [x] **Reentrenamiento nocturno**: integrado en el pipeline (`main.py` Step 3)
- [x] **Metadatos**: fecha, samples, accuracy, recall, scale_pos_weight guardados en metadata.json
- **Documentación**: `analytics/ML_APPROACH.md` describe la conexión con el notebook Colab del equipo

**Dependencias:** Fase 5

---

## Fase 7: Pipeline diario (main.py) ✅ COMPLETADA

**Objetivo:** Orquestar la ejecución diaria completa.

Archivo: `analytics/main.py`

- [x] **Paso 1 — Detección**: Ejecutar `engine_commodity` y `engine_technical`
  - Para cada cliente activo (compra en último año)
  - Agrupar por familia de producto
  - Generar alertas nuevas en tabla `alertas` (con `prioridad = NULL`)
- [x] **Deduplicación**: No insertar alerta si ya existe una pendiente para el mismo cliente-familia en los últimos 7 días
- [x] **Paso 2 — Inserción**: `df.to_sql("alertas", ...)` con `method="multi"` y `chunksize=500`
- [x] **Paso 3 — Logging**: Logging de cuántas alertas generadas y saltadas
- [x] **FECHA_HOY**: configurable vía env (default `2026-02-01` para el hackathon)
- [x] **Scheduler**: ejecución inmediata al levantar + diaria a las 20:00
- [x] **Espera de BD**: `wait_for_db()` con reintentos antes de conectar

**Nota:** Falta **Paso 2 — Priorización** como parte del pipeline (depende de Fase 5).

---

## Fase 8: Frontend Streamlit 🔲 PENDIENTE

**Objetivo:** Dashboard para delegados/televenta que muestra alertas y permite dar feedback.

Archivo: `frontend/app.py`

- [ ] **Agrupación por cliente**: alerta principal = mayor prioridad, resto desplegables (ver `frontend.md`)
- [ ] **Vista principal: tabla de alertas**
  - Solo alertas con `feedback IS NULL` (pendientes de acción)
  - Ordenadas por `prioridad DESC`
  - Columnas: prioridad, cliente, familia, tipo, motivo, provincia, impacto, urgencia, score_conversion, perfil_cliente
- [ ] **Filtros**:
  - Por provincia, tipo de alerta, bloque, familia, rango de prioridad
- [ ] **Detalle de alerta**: motivo descriptivo con valores reales, métricas del cliente-familia
- [ ] **Acción de feedback**: botones "Positivo"/"Negativo" con confirmación
- [ ] **Conexión a PostgreSQL** desde Streamlit
- [ ] `frontend/requirements.txt`: streamlit, pandas, plotly, sqlalchemy, psycopg2-binary, python-dotenv

**Dependencias:** Fase 5 (priorizador) para ordenar por prioridad. Se puede empezar con prioridad NULL.

---

## Fase 9: Docker Compose (servicios analytics + frontend) 🔄 PARCIAL

**Objetivo:** Orquestar los 3 servicios con un solo `docker compose up`.

- [x] **Dockerfile analytics**: Python 3.11-slim + dependencias + `CMD python main.py`
- [x] **Servicio analytics** en `docker-compose.yml`:
  - Depende de `db` con healthcheck
  - Variables de entorno desde `.env`
  - Ejecución diaria (20:00) + inicial al arrancar
- [x] **Healthcheck** para `db` service
- [ ] **Dockerfile frontend**: Python 3.11-slim + Streamlit
- [ ] **Servicio frontend** en `docker-compose.yml`
- [ ] **Red interna** para comunicación entre servicios
- [ ] **Volumen** para modelos entrenados (`analytics/models/`)

---

## Fase 10: Entrenamiento ML nocturno automatizado ✅ COMPLETADO

**Objetivo:** El modelo de ML se reentrena cada día con los nuevos feedbacks.

- [x] **Script `ml_trainer.py`** completamente funcional con XGBoost
- [x] **Integración en el pipeline**: detección → priorización → entrenamiento ML (Step 3 en main.py)
- [x] **Métricas de rendimiento**: accuracy, precision, recall guardados en `metadata.json`
- [x] **Registro de entrenamientos**: log de fecha, nº de muestras, métricas
- [x] **Cold-start heuristic**: sin feedback suficiente, usa reglas basadas en alert_type y perfil
- [x] **Reentrenamiento progresivo**: cada día con más feedback, el modelo mejora

**Dependencias:** Fase 6 ✅

---

## Resumen de dependencias

```
Fase 1 ✅ → Fase 2 ✅ → Fase 3 ✅ ──┐
                                 ├── Fase 5 ✅ → Fase 6 ✅ → Fase 7 ✅ → Fase 8 🔲
                    Fase 4 ✅ ──┘                              Fase 9 🔄 → Fase 10 ✅
```

## Notas

- Las fases 1-2 se pueden hacer en paralelo. ✅ Completadas.
- Las fases 3 y 4 se pueden hacer en paralelo (son independientes entre sí). ✅ Completadas.
- La fase 6 (stub) puede empezar en cuanto la fase 5 esté lista.
- La fase 8 (frontend) puede empezar su estructura en cuanto la fase 1 esté lista. ✅
- Las fases 9 y 10 son las finales, dependen de todo lo anterior.
- Mejoras no críticas se registran en `low_priority_todo.md`.