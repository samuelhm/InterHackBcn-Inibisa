# Frontend — Smart Demand Signals (Streamlit UI)

Funcionalidades planificadas para el dashboard de delegados/televenta.

---

## Vista principal: tabla de alertas

- [ ] **Agrupación por cliente**: cada fila principal muestra la alerta de mayor prioridad con `feedback IS NULL` de ese cliente. El resto de alertas del mismo cliente se muestran como filas hijas desplegables (expand/collapse). Así el comercial puede resolver varias alertas del mismo cliente en una sola llamada.
- [ ] **Ordenación**: por `prioridad DESC` (las más urgentes arriba).
- [ ] **Columnas visibles**: prioridad, id_cliente, familia, tipo_alerta, motivo, provincia, impacto_estimado, urgencia_dias, score_conversion.
- [ ] **Badge de color** por tipo_alerta: verde (ventana_captura), azul (reposicion), naranja (riesgo_fuga), rojo (cliente_perdido).

## Filtros

- [ ] Provincia (dropdown con valores únicos de la BD).
- [ ] Tipo de alerta (multiselect: ventana_captura, reposicion, riesgo_fuga, cliente_perdido).
- [ ] Bloque (Commodities / Productos Técnicos).
- [ ] Familia de producto (dropdown dependiente del bloque).
- [ ] Rango de prioridad (slider 0–200).
- [ ] Búsqueda por id_cliente (text input).

## Detalle de alerta (al hacer clic en una fila)

- [ ] **Motivo completo** (texto generado por el engine).
- [ ] **Variables que activaron la alerta**: mostrar qué flags se dispararon (frecuencia, volumen, ausencia, anomalía) con valores reales vs umbrales (leidos del campo `motivo`).
- [ ] **Métricas del cliente-familia**: ratio_promiscuidad, impacto_estimado, urgencia_dias, dias_desde_ultima_compra, perfil_cliente (leal/promiscuo/marginal), freq_media_dias, n_compras_hist.
- [ ] **Métricas del cliente-familia**: ratio_promiscuidad, impacto_estimado, urgencia_dias, dias_desde_ultima_compra.
- [ ] **Historial de compras**: gráfico de líneas (importe por fecha) para ese cliente-familia. Idealmente con plotly para interactividad.

## Acción de feedback

- [ ] **Botón "Venta conseguida"** (feedback = 1): el delegado confirma que la alerta derivó en venta. Se registra `fecha_feedback = today`.
- [ ] **Botón "Sin interés"** (feedback = 0): el cliente no mostró interés. Misma lógica.
- [ ] **Confirmación** antes de enviar (dialog o toast).
- [ ] **Actualización inmediata** en BD y recarga de la tabla (la alerta desaparece de la vista principal porque ya tiene feedback).
- [ ] **Feedback desde fila hija**: poder marcar feedback en cualquier alerta del desplegable, no solo la principal.

## Métricas agregadas (cabecera del dashboard)

- [ ] Total de alertas pendientes hoy.
- [ ] Tasa de conversión: `feedback = 1 / total con feedback` (últimos 30 días).
- [ ] Distribución por tipo: % ventana_captura, % reposicion, % riesgo_fuga, % cliente_perdido.
- [ ] Alertas generadas hoy vs ayer (tendencia).

## Extras

- [ ] Exportar tabla a CSV/Excel.
- [ ] Modo oscuro (tema corporativo Inibsa).
- [ ] Responsive para tablet (los delegados pueden usarlo en movilidad).
