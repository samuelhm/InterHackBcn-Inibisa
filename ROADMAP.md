# ROADMAP — Smart Demand Signals

Solo se listan las tareas pendientes. Lo ya completado (DB + ingesta, detector_alertas.py prototipo, schema alertas en init.sql) no se incluye.

---

## Fase 1: Tabla alertas en init.sql

**Objetivo:** Que la tabla `alertas` se cree automáticamente al levantar la DB.

- [x] Migrar el contenido de `example/001_create_alertas.sql` a `database/init.sql` (ENUMs, tabla, índices, triggers, vistas `alertas_delegado` y `alertas_feedback`)
- [x] Alternativa descartada — migración directa a `init.sql`
- [x] Verificar que la tabla se crea correctamente: `docker compose down -v && docker compose up db -d`

**Dependencias:** Ninguna | **Estado:** COMPLETADA

---

## Fase 2: Utilidades compartidas (analytics/utils/)

**Objetivo:** Módulos reutilizables por todos los engines y el pipeline.

- [ ] `analytics/utils/db.py` — Conexión SQLAlchemy a PostgreSQL (lectura de `.env`)
- [ ] `analytics/utils/config.py` — Pesos configurables de priorización (dict con defaults). Factores:
  - Peso por tipo de alerta (`ventana_captura` > `reposicion` > `riesgo_fuga` > `cliente_perdido`)
  - Peso por tipo de cliente (leal, promiscuo, marginal)
  - Peso por potencial_h
  - Peso por urgencia
  - Peso del score ML (0% mientras no esté implementado)
- [ ] `analytics/utils/metrics.py` — Funciones compartidas de cálculo (frecuencia media, volumen medio, Z-score, días desde última compra, ratio de promiscuidad)

**Dependencias:** Ninguna

---

## Fase 3: Engine Commodity

**Objetivo:** Detectar ventanas de captura y necesidad de reposición en productos commodity.

Archivo: `analytics/src/engine_commodity.py`

- [ ] **Clasificar clientes por familia** en 3 perfiles:
  - **Leal**: concentra >70% de su potencial de compra con Inibsa
  - **Promiscuo**: reparte su demanda con competencia (30%-70%)
  - **Marginal**: compra nula o <30% de su potencial
- [ ] **Estimar consumo esperado** por cliente-familia a partir de su potencial_h y su frecuencia media histórica
- [ ] **Detectar ventana de captura** (clientes promiscuos):
  - Calcular `impacto_estimado = potencial_h - SUM(compras_12m)`
  - Cuando `dias_desde_ultima_compra` se acerca a la frecuencia media esperada → alerta `ventana_captura`
- [ ] **Detectar reposición** (clientes leales):
  - Cuando stock estimado está próximo a agotarse → alerta `reposicion`
- [ ] **Escribir alertas** en tabla `alertas` con bloque `Commodities`, tipo `ventana_captura` o `reposicion`
- [ ] **Calcular columnas del bloque 2**: `impacto_estimado`, `urgencia_dias`, `ratio_promiscuidad`, `dias_desde_ultima_compra`

**Dependencias:** Fase 1 (tabla alertas), Fase 2 (utils)

---

## Fase 4: Engine Technical

**Objetivo:** Detectar deterioro de compra y riesgo de abandono en productos técnicos.

Archivo: `analytics/src/engine_technical.py`

- [ ] **4 procesos de detección** por cliente-familia (misma lógica base que `detector_alertas.py` pero refinada):
  1. **Caída de frecuencia**: gap actual > 1.5× media histórica
  2. **Caída de volumen**: último importe < 50% media histórica
  3. **Ausencia de compra**: días desde última compra > max(30, 2× frecuencia media)
  4. **Actividad anómala**: Z-score > 2 en importe o volumen
- [ ] **Distinguir ruido de señal**:
  - No alertar si el cliente tiene patrón históricamente esporádico (CV > umbral)
  - No alertar si la caída coincide con estacionalidad conocida
  - Considerar el perfil de clínica y especialidad si los datos lo permiten
- [ ] **Clasificar tipo de alerta**:
  - `riesgo_fuga`: deterioro detectado pero cliente aún activo
  - `cliente_perdido`: ausencia > 90 días
- [ ] **Escribir alertas** en tabla `alertas` con bloque `Productos Técnicos`
- [ ] **Calcular columnas del bloque 2**: mismas que commodity

**Dependencias:** Fase 1, Fase 2

---

## Fase 5: Priorizador

**Objetivo:** Asignar una prioridad numérica (0-200) a cada alerta generada.

Archivo: `analytics/src/prioritizer.py`

- [ ] **Leer alertas sin priorizar** (`prioridad IS NULL`) de la tabla `alertas`
- [ ] **Calcular score base** (0-200) combinando con pesos configurables:
  - Peso por tipo de alerta (ej: `ventana_captura` = 1.0, `cliente_perdido` = 0.3)
  - Peso por potencial_h normalizado (0-1)
  - Peso por urgencia (a menor urgencia_dias, mayor peso)
  - Peso por tipo de cliente (leal > promiscuo > marginal)
- [ ] **Integrar score ML**: `prioridad_final = clamp(score_base + score_ml, 0, 200)`
  - El score ML se obtiene llamando a `getMachineLearningPriority(alert_id)` del ml_engine
  - Si no hay modelo entrenado, el score ML es 0
- [ ] **Escribir** `prioridad` y `score_conversion` en la tabla `alertas`
- [ ] **Hacer configurables los pesos** desde `utils/config.py` (diccionario, JSON o YAML)

**Dependencias:** Fase 3, Fase 4, Fase 2

---

## Fase 6: ML Engine (stub + entrenamiento)

**Objetivo:** Motor de ML modular que aprende del feedback para ajustar prioridades.

Archivos: `analytics/src/ml_engine.py` y `analytics/src/ml_trainer.py`

### ml_engine.py (inferencia)

- [ ] Función `getMachineLearningPriority(alert_id: str) -> float`:
  - Recibe el ID de una alerta
  - Consulta sus features desde la BD (tipo_alerta, bloque, provincia, impacto_estimado, urgencia_dias, ratio_promiscuidad, dias_desde_ultima_compra, etc.)
  - Si hay modelo entrenado → retorna score entre -100 y +100
  - Si no hay modelo → retorna 0
  - El score se suma a la prioridad base en el priorizador
- [ ] Carga del modelo desde `analytics/models/` (.pkl o .json)

### ml_trainer.py (entrenamiento nocturno)

- [ ] **Consultar** `alertas_feedback` (vista con alertas que tienen `feedback IS NOT NULL`)
- [ ] **Features**: tipo_alerta, bloque, provincia, impacto_estimado, urgencia_dias, ratio_promiscuidad, dias_desde_ultima_compra, probabilidad_deteccion
- [ ] **Target**: `feedback` (0 = negativo, 1 = positivo)
- [ ] **Entrenar** modelo de clasificación binaria:
  - Tecnología a decidir (scikit-learn o XGBoost)
  - Output: `score_conversion` (probabilidad de clase 1) y `priority_adjustment`
- [ ] **Guardar** modelo entrenado en `analytics/models/`
- [ ] **Lógica de ajuste**: patrones con feedback positivo → suman prioridad; feedback negativo → restan prioridad
- [ ] **Ejecución programada**: script diseñado para cron/daily job

**Dependencias:** Fase 5 (necesita alertas con prioridad para tener datos de entrenamiento)

---

## Fase 7: Pipeline diario (main.py)

**Objetivo:** Orquestar la ejecución diaria completa.

Archivo: `analytics/main.py`

- [ ] **Paso 1 — Detección**: Ejecutar `engine_commodity` y `engine_technical`
  - Para cada cliente activo (compra en último año)
  - Agrupar por familia de producto
  - Generar alertas nuevas en tabla `alertas` (con `prioridad = NULL`)
- [ ] **Paso 2 — Priorización**: Ejecutar `prioritizer`
  - Leer alertas sin priorizar
  - Calcular score 0-200
  - Actualizar `prioridad` y `score_conversion` en BD
- [ ] **Paso 3 — Resumen**: Logging de cuántas alertas generadas, por tipo y bloque
- [ ] **Manejo de duplicados**: No insertar alerta si ya existe una para el mismo cliente-familia-tipo en los últimos N días
- [ ] **FECHA_HOY**: usar variable de entorno o parámetro; default `2026-05-09` para el hackathon

**Dependencias:** Fase 3, 4, 5

---

## Fase 8: Frontend Streamlit

**Objetivo:** Dashboard para delegados/televenta que muestra alertas y permite dar feedback.

Archivo: `frontend/app.py`

- [ ] **Vista principal: tabla de alertas**
  - Solo alertas con `feedback IS NULL` (pendientes de acción)
  - Ordenadas por `prioridad DESC`
  - Columnas: prioridad, cliente, familia, tipo, motivo, provincia, impacto, urgencia, score_conversion
- [ ] **Filtros**:
  - Por provincia (dropdown)
  - Por tipo de alerta (multiselect)
  - Por bloque (Commodities / Productos Técnicos)
  - Por familia de producto
  - Por rango de prioridad
- [ ] **Detalle de alerta**: Al hacer clic, mostrar:
  - Motivo completo
  - Variables que activaron la alerta (trazabilidad)
  - Historial de compras del cliente-familia (gráfico)
- [ ] **Acción de feedback**:
  - Botón "Positivo" (feedback = 1, fecha_feedback = today)
  - Botón "Negativo" (feedback = 0, fecha_feedback = today)
  - Confirmación antes de enviar
  - Actualización en BD
- [ ] **Conexión a PostgreSQL** desde Streamlit (usar `utils/db.py` o directa)
- [ ] `frontend/requirements.txt`: streamlit, pandas, plotly, sqlalchemy, psycopg2-binary, python-dotenv

**Dependencias:** Fase 7 (necesita alertas priorizadas en BD)

---

## Fase 9: Docker Compose (servicios analytics + frontend)

**Objetivo:** Orquestar los 3 servicios con un solo `docker compose up`.

- [ ] **Dockerfile analytics**: Python 3.11, instalar dependencias de `analytics/requirements.txt`, entrypoint `python main.py`
- [ ] **Dockerfile frontend**: Python 3.11-slim, instalar dependencias de `frontend/requirements.txt`, entrypoint `streamlit run app.py`
- [ ] **Servicio analytics** en `docker-compose.yml`:
  - Depende de `db`
  - Variables de entorno desde `.env`
  - Volumen para modelos entrenados (`analytics/models/`)
  - Ejecución diaria (entrypoint con sleep loop o cron simulado)
- [ ] **Servicio frontend** en `docker-compose.yml`:
  - Depende de `db` y `analytics`
  - Puerto 8501 expuesto
  - Variables de entorno desde `.env`
- [ ] **Red interna** para comunicación entre servicios
- [ ] **Script de entrada** para el servicio analytics que ejecute el pipeline diario en bucle (sleep 86400)

**Dependencias:** Fase 7, Fase 8

---

## Fase 10: Entrenamiento ML nocturno automatizado

**Objetivo:** El modelo de ML se reentrena cada día con los nuevos feedbacks.

- [ ] **Script `ml_trainer.py`** completamente funcional con modelo real
- [ ] **Integración en el pipeline**: el servicio analytics ejecuta detección + priorización de día, y entrenamiento de noche
- [ ] **Métricas de rendimiento**: accuracy, precisión, recall del modelo; evolución en el tiempo
- [ ] **Registro de entrenamientos**: log de fecha, nº de muestras, métricas, modelo guardado

**Dependencias:** Fase 6 (stub), Fase 7, Fase 9

---

## Resumen de dependencias

```
Fase 1 (alertas en init.sql)
  └── Fase 2 (utils)
        ├── Fase 3 (engine commodity)
        │     └── Fase 5 (prioritizer)
        │           └── Fase 6 (ml engine stub)
        │                 └── Fase 7 (pipeline main.py)
        │                       ├── Fase 8 (frontend)
        │                       └── Fase 9 (docker compose)
        │                             └── Fase 10 (ml trainer real)
        └── Fase 4 (engine technical)
              └── Fase 5 (prioritizer)
                    └── ...
```

## Notas

- Las fases 1-2 se pueden hacer en paralelo.
- Las fases 3 y 4 se pueden hacer en paralelo (son independientes entre sí).
- La fase 6 (stub) puede empezar en cuanto la fase 5 esté lista.
- La fase 8 (frontend) puede empezar su estructura en cuanto la fase 1 esté lista (puede leer de BD con datos dummy).
- Las fases 9 y 10 son las finales, dependen de todo lo anterior.
