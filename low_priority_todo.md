# Low Priority TODO — Smart Demand Signals

Mejoras detectadas durante el desarrollo que son interesantes pero **NO prioritarias**
para el hackathon. Se abordarán si sobra tiempo o post-evento.

---

## Infraestructura / DevOps

- [ ] Pinear versión de PostgreSQL en `database/Dockerfile` (`postgres:16` en vez de `latest`)
- [ ] Añadir `DB_HOST`, `DB_PORT`, `FECHA_HOY` al `.env` (ahora cubiertos por defaults en utils)
- [ ] Eliminar `DATA_PATH=./data/raw` del `.env` (no se usa, ruta inexistente)
- [ ] Añadir healthcheck al servicio `db` en `docker-compose.yml`:
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
    interval: 10s
    timeout: 5s
    retries: 5
  ```
- [ ] Usar `virtualenv` en `database/Dockerfile` en vez de `--break-system-packages`
- [ ] Añadir servicio `analytics` al `docker-compose.yml`
- [ ] Añadir servicio `frontend` al `docker-compose.yml`
- [ ] Definir red explícita en `docker-compose.yml` en vez de usar la default

## Analytics / Motores

- [ ] Diferentes thresholds de detección por familia de producto (no solo Commodity vs Técnico)
- [ ] Considerar estacionalidad en la detección (ej. menor actividad en agosto)
- [ ] Filtrar ruido en commodities igual que en técnicos (CV analysis)
- [ ] Añadir test suite (pytest) para engines y métricas
- [ ] Logging structured (JSON) para trazabilidad en producción

## Frontend

- [ ] Gráfico de historial de compras en el detalle de alerta (plotly)
- [ ] Exportación de alertas a CSV/Excel para delegados
- [ ] Modo oscuro / tema corporativo Inibsa
- [ ] Métricas agregadas en dashboard (total alertas por tipo, tasa de conversión)

## ML

- [ ] Comparar XGBoost vs scikit-learn (LogisticRegression, RandomForest) para el modelo
- [ ] Feature engineering: añadir features temporales (día de la semana, mes, trimestre)
- [ ] Registrar métricas de entrenamiento (accuracy, precision, recall, F1) en BD
- [ ] Implementar A/B testing de pesos de prioridad

## Datos

- [ ] Validar integridad referencial post-ingesta (clientes sin provincia, productos sin familia)
- [ ] Detectar y loguear outliers en Datasets.xlsx durante la ingesta
