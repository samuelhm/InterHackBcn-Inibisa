# Presentacion — Smart Demand Signals (InterHack BCN 2026)

Puntos a cubrir durante la presentacion del proyecto ante el jurado.

---

## 1. Problema y contexto

- [ ] Inibsa fabrica y distribuye productos farmaceuticos dentales a ~6.000–7.000 clinicas en Espana.
- [ ] Los delegados comerciales y el equipo de televenta necesitan saber **a que clinica llamar, para que producto, y por que**.
- [ ] Sin un sistema inteligente, se actua a ciegas: se llama a clinicas que no necesitan nada o se ignoran oportunidades de capturar negocio de la competencia.
- [ ] El briefing distingue dos dinamicas fundamentalmente distintas: commodities (compra recurrente) y tecnicos (compra variable). Una logica universal no sirve.

## 2. Solucion: Smart Demand Signals

- [ ] Sistema modular de 3 capas: **datos (PostgreSQL) → analitica (Python) → activacion (Streamlit)**.
- [ ] Orquestado con Docker Compose para despliegue en un solo comando.
- [ ] Cada alerta recibe una **prioridad numerica 0–200** que ordena al delegado que hacer primero.
- [ ] Pipeline diario automatizado: deteccion → insercion → priorizacion → entrenamiento ML, todo en un contenedor que se ejecuta cada noche.

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
- [ ] **Cold-start inteligente**: antes de haber suficiente feedback, el sistema no devuelve 0 — usa una heuristica basada en tipo de alerta, perfil de cliente, impacto y urgencia que ya aporta valor desde el dia 1.
- [ ] **Mejora progresiva demostrable**: con solo 500 feedbacks sinteticos, el XGBoost ya genera scores diferenciadores (ventana_captura+marginal = 0.90, riesgo_fuga+promiscuo = 0.29). Cada dia con feedback real, el modelo se afina mas.

## 6. Trazabilidad completa

- [ ] Cada alerta incluye un **motivo descriptivo** legible por el comercial: "Sin compra hace 129d (umbral: 60d basado en frecuencia media de 30d)" en vez de solo "Ausencia".
- [ ] Columnas de trazabilidad: `perfil_cliente` (leal/promiscuo/marginal), `freq_media_dias` (ciclo medio de compra), `n_compras_hist` (total compras historicas).
- [ ] Los 4 flags booleanos (`alerta_frecuencia`, `alerta_volumen`, `alerta_ausencia`, `alerta_anomalia`) permiten filtrar en el dashboard.
- [ ] El campo `motivo` combina texto con numeros reales: umbrales, porcentajes de caida, Z-scores.
- [ ] **Cumplimos directamente el requisito del briefing**: "cada alerta debera ofrecer capacidad de reconstruir por que se genero y que variables o reglas intervinieron en su activacion."

## 7. Eliminacion de ruido

- [ ] **Filtro estadístico**: clientes con coeficiente de variación alto requieren señales múltiples para generar alerta (evitamos falsos positivos en compradores erráticos).
- [ ] **Filtro de inactividad**: no generamos alertas para cliente-familias cuya última compra es de hace más de 1 año — ya no son nuestros clientes para ese producto.
- [ ] **Deduplicacion**: si ya existe una alerta pendiente para el mismo cliente-familia en los ultimos 7 dias, no se genera otra. Evitamos inundar al delegado.
- [ ] **Deteccion de campañas**: actualmente no disponemos de una forma fiable de detectar si un pico de ventas corresponde a una campaña promocional. Planificado en el roadmap post-hackathon.

## 8. Alineacion con los criterios de evaluacion del briefing

### Capacidad de traducir un problema de negocio en solucion analitica
- [ ] El sistema cubre exactamente los 2 casos de uso del briefing: **commodities** (captura + reposicion) y **tecnicos** (riesgo de fuga + deterioro).
- [ ] Cada alerta responde a las preguntas del briefing: **quien, que producto, por que, y cuando contactar**.

### Diferenciacion inteligente entre productos commodity y tecnicos
- [ ] Dos engines independientes con logica y umbrales distintos.
- [ ] Commodities: logica de consumo esperado, promiscuidad y ventanas de captura.
- [ ] Tecnicos: logica de deterioro de patron, con filtro anti-ruido (CV>1.0 requiere 2+ patrones).

### Calidad de la logica predictiva
- [ ] 4 patrones de deteccion por bloque (frecuencia, volumen, ausencia, anomalia Z-score).
- [ ] Priorizacion ponderada con 6 factores incluyendo ML.
- [ ]El XGBoost con `scale_pos_weight` compensa el desbalanceo natural de clases (muchas alertas negativas vs pocas positivas).

### Interpretabilidad y trazabilidad de las alertas
- [ ] Campo `motivo` con texto legible y valores reales.
- [ ] 4 flags booleanos que indican que patrones se activaron.
- [   ] Columna `perfil_cliente`, `freq_media_dias`, `n_compras_hist` para contexto.
- [ ] Score de prioridad 0-200 y `score_conversion` 0-1 transparentes.

### Capacidad de priorizacion y encaje en el proceso comercial
- [ ] La prioridad no es solo "alto/medio/bajo" — es un numero 0-200 que combina impacto economico, urgencia temporal, perfil del cliente y probabilidad ML.
- [ ] El delegado ve las alertas ordenadas: las de mas prioridad arriba, con el motivo y el impacto estimado en euros.
- [ ] El feedback del delegado (positivo/negativo) cierra el ciclo: mejora el modelo y desregistra la alerta.

### Aplicabilidad real en entorno comercial
- [ ] **No es un demo de laboratorio**: el pipeline corre en Docker, se levanta con un comando, y genera 5.000+ alertas sobre datos reales de 6.000 clinicas.
- [ ] La unidad de decision es **cliente-familia de producto-motivo-momento**, exactamente lo que pide el briefing.
- [ ] El sistema contempla "que ocurre despues de la alerta": feedback del delegado → reentrenamiento ML → mejora progresiva.

### Escalabilidad y viabilidad de evolucion futura
- [ ] Arquitectura 3-capas desacoplada (datos, analitica, activacion).
- [ ] Pipeline diario con scheduler integrado.
- [ ] Agnostico de CRM: las alertas viven en PostgreSQL, exportables a cualquier plataforma.
- [ ] GraphID preparado: integracion con HubSpot/CRM como siguiente fase.

## 9. Sostenibilidad (BCN Clima)

- [ ] Al optimizar las llamadas comerciales, reducimos desplazamientos innecesarios de delegados.
- [ ] Al detectar ventanas de captura, evitamos que el negocio se vaya a competidores que pueden tener practicas menos sostenibles.
- [ ] Infraestructura ligera: PostgreSQL + Python + Streamlit, sin necesidad de grandes clusters de computo.
- [ ] Menos kilometros recorridos por delegados = menos emisiones. Mas eficiencia comercial con menos recursos.

## 10. Metricas de exito (lo que pide el briefing)

- [ ] **Tasa de conversion de alertas**: feedback positivo / total de alertas con feedback (medible desde el dia 1).
- [ ] **Tasa de recuperacion de clientes inactivos**: cliente_perdido con feedback positivo / total de cliente_perdido.
- [ ] **Reduccion de falsos positivos**: el filtro anti-ruido (CV + 2 patrones) ya los elimina a nivel de deteccion; el ML los penaliza en priorizacion.
- [ ] **Mejora progresiva del modelo**: accuracy y recall del XGBoost se registran en metadata.json tras cada reentrenamiento.

## 11. Demo en vivo

- [ ] Levantar el sistema con `docker compose up`.
- [ ] Mostrar 5.282 alertas generadas sobre datos reales de 6.000 clinicas.
- [ ] Mostrar KPIs: impacto economico total, alertas criticas, clinicas a intervenir.
- [ ] Filtrar por tipo de alerta, provincia, bloque.
- [ ] Asignar feedback a una alerta y ver como desaparece de la vista principal.
- [ ] **Demo de ML**: ejecutar el entrenamiento XGBoost en vivo y mostrar como cambian los scores de prioridad tras reentrenar.
- [ ] Mostrar el Cold-start vs ML: la heuristica ya funciona desde el dia 1, el modelo mejora con el tiempo.

## 12. Cierre: por que este proyecto gana

- [ ] **Cubre todos los requisitos del briefing**: productos commodity y tecnicos con logica diferenciada, alertas interpretables, priorizacion, feedback loop, metricas de exito, arquitectura standalone + CRM-ready.
- [ ] **No es un prototype**: es un sistema funcional que procesa 5.000+ alertas sobre datos reales, con pipeline automatizado y ML entrenandose cada noche.
- [ ] **El ML no es decorativo**: el score_conversion cambia el ranking real de prioridades. Demonstramos que con solo 500 feedbacks, el XGBoost ya discrimina mejor que la heuristica.
- [ ] **Trazabilidad total**: cada alerta se puede explicar al comercial con datos concretos, no es una caja negra.
- [ ] **Escalable y mantenible**: pesos configurables sin tocar codigo, engines independientes, Docker Compose un comando.
- [ ] **Sostenibilidad real**: menos desplazamientos, menos recursos, mas eficiencia comercial.