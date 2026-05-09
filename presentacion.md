# Presentacion — Smart Demand Signals (InterHack BCN 2026)

Puntos a cubrir durante la presentacion del proyecto ante el jurado.

---

## 1. Problema y contexto

- [ ] Inibsa fabrica y distribuye productos farmaceuticos dentales a ~6.000–7.000 clinicas en Espana.
- [ ] Los delegados comerciales y el equipo de televenta necesitan saber **a que clinica llamar, para que producto, y por que**.
- [ ] Sin un sistema inteligente, se actua a ciegas: se llama a clinicas que no necesitan nada o se ignoran oportunidades de capturar negocio de la competencia.

## 2. Solucion: Smart Demand Signals

- [ ] Sistema modular de 3 capas: **datos (PostgreSQL) → analitica (Python) → activacion (Streamlit)**.
- [ ] Orquestado con Docker Compose para despliegue en un solo comando.
- [ ] Cada alerta recibe una **prioridad numerica 0–200** que ordena al delegado que hacer primero.

## 3. Diferenciacion por tipo de producto

- [ ] **Commodities** (anestesia, agujas, desinfeccion): compra recurrente y predecible.
  - Calculamos **ratio de promiscuidad**: cuanto del potencial de compra de una clinica se va a la competencia.
  - Detectamos **ventanas de captura**: cuando una clinica promiscua esta proxima a su ciclo de compra, hay oportunidad de ganar negocio nuevo.
  - Detectamos **reposicion**: clinicas leales que necesitan reaprovisionarse.
- [ ] **Productos tecnicos** (implantes, instrumental rotatorio): compra variable segun caso clinico y especialidad.
  - Detectamos **deterioro de patron de compra**: caidas de frecuencia, volumen, ausencias y anomalias estadisticas (Z-score).
  - Umbrales **mas sensibles** que en commodities porque un cliente que abandona un producto tecnico raramente vuelve.
  - **Filtro de ruido**: si el coeficiente de variacion del cliente es muy alto (comprador esporadico), exigimos que se activen al menos 2 patrones simultaneos antes de generar alerta.

## 4. Priorizacion inteligente

- [ ] **Todos los pesos y umbrales son configurables** desde un unico archivo de configuracion (`analytics/utils/config.py`).
- [ ] Esto permite que, tras un analisis real de datos historicos y en colaboracion con los departamentos de **marketing, ventas y direccion comercial**, se ajusten los pesos de cada factor:
  - Peso del tipo de alerta (ventana_captura > reposicion > riesgo_fuga > cliente_perdido).
  - Peso del potencial economico de la clinica.
  - Peso del impacto estimado (dinero en manos de la competencia).
  - Peso de la urgencia temporal.
  - Peso del perfil de cliente (leal, promiscuo, marginal).
  - Peso del modelo de ML (20% del total cuando este entrenado).
- [ ] La configuracion no requiere tocar codigo: es un diccionario Python legible por cualquier perfil tecnico.

## 5. Machine Learning con feedback real

- [ ] El sistema aprende del feedback que dan los delegados (venta conseguida / sin interes).
- [ ] Entrenamiento diario con los datos recolectados.
- [ ] El modelo predice `score_conversion`: probabilidad de que una alerta convierta en venta.
- [ ] Este score se integra en la prioridad final, ajustando el ranking segun patrones aprendidos.

## 6. Trazabilidad completa

- [ ] Cada alerta incluye un **motivo descriptivo** legible por el comercial: "Sin compra hace 129d (umbral: 60d basado en frecuencia media de 30d)" en vez de solo "Ausencia".
- [ ] Columnas de trazabilidad: `perfil_cliente` (leal/promiscuo/marginal), `freq_media_dias` (ciclo medio de compra), `n_compras_hist` (total compras historicas).
- [ ] Los 4 flags booleanos (`alerta_frecuencia`, `alerta_volumen`, `alerta_ausencia`, `alerta_anomalia`) permiten filtrar en el dashboard.
- [ ] El campo `motivo` combina texto con numeros reales: umbrales, porcentajes de caida, Z-scores.

## 7. Eliminación de ruido

- [ ] **Filtro estadístico**: clientes con coeficiente de variación alto requieren señales múltiples para generar alerta (evitamos falsos positivos en compradores erráticos).
- [ ] **Filtro de inactividad**: no generamos alertas para cliente-familias cuya última compra es de hace más de 1 año — ya no son nuestros clientes para ese producto.
- [ ] **Detección de campañas**: actualmente no disponemos de una forma fiable de detectar si un pico de ventas corresponde a una campaña promocional. Planificado en el roadmap post-hackathon.

## 8. Sostenibilidad (BCN Clima)

- [ ] Al optimizar las llamadas comerciales, reducimos desplazamientos innecesarios de delegados.
- [ ] Al detectar ventanas de captura, evitamos que el negocio se vaya a competidores que pueden tener prácticas menos sostenibles.
- [ ] Infraestructura ligera: PostgreSQL + Python + Streamlit, sin necesidad de grandes clusters de cómputo.

## 9. Roadmap y escalabilidad

- [ ] Fase actual: deteccion y priorizacion completas, frontend en desarrollo.
- [ ] Proximos pasos: integracion con CRM de Inibsa, exportacion de alertas a Excel para delegados sin acceso a la plataforma, modelo ML con XGBoost entrenado sobre datos reales.
- [ ] Arquitectura preparada para escalar: los engines son modulos independientes, se pueden paralelizar y ejecutar en horarios diferentes (deteccion de dia, entrenamiento ML de noche).

## 10. Demo en vivo

- [ ] Levantar el sistema con `docker compose up`.
- [ ] Mostrar el dashboard con alertas priorizadas.
- [ ] Asignar feedback a una alerta y ver como desaparece.
- [ ] Ejecutar el pipeline de deteccion y ver nuevas alertas generadas.
