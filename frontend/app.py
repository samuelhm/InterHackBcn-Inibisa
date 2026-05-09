import streamlit as st
import pandas as pd
import os
import time
from sqlalchemy import create_engine, text
from datetime import date

# Configuración de página y conexión
st.set_page_config(page_title="Inibsa Smart Demand", layout="wide")
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

def connect_with_retry(max_retries=5, sleep_time=3):
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            time.sleep(sleep_time)
    return False

if connect_with_retry():
    # 1. CARGA DE DATOS: Solo alertas sin feedback procesado
    query = "SELECT * FROM alertas WHERE feedback IS NULL"
    df_alertas = pd.read_sql(query, engine)

    # 2. SIDEBAR: FILTROS OPERATIVOS
    st.sidebar.header("Control Comercial")
    # Filtro por Bloque (Commodity/Technical) según definición del esquema
    tipo_prod = st.sidebar.multiselect(
        "Filtrar por Bloque:", 
        ["Commodity", "Technical"], 
        default=["Commodity", "Technical"]
    )

    # Filtrado dinámico del DataFrame
    df_view = df_alertas[df_alertas['bloque'].isin(tipo_prod)]

    # 3. KPIs: RESUMEN DE IMPACTO ECONÓMICO Y PRIORIDAD
    col1, col2, col3 = st.columns(3)
    if not df_view.empty:
        # impacto_estimado representa el valor potencial de la intervención
        col1.metric("Potencial de Captura", f"{df_view['impacto_estimado'].sum():,.0f} €")
        # prioridad se mide de 0 a 200 en tu esquema
        col2.metric("Alertas Críticas", len(df_view[df_view['prioridad'] < 50]))
        col3.metric("Clínicas a Intervenir", df_view['id_cliente'].nunique())

    # 4. CAPA DE ACTIVACIÓN: DIFERENCIACIÓN POR DINÁMICA DE COMPRA
    tab1, tab2 = st.tabs(["📦 Commodities", "⚙️ Productos Técnicos"])

    with tab1:
        st.subheader("Señales de Reposición y Captura")
        st.write("Detección de demanda desviada a la competencia.")
        st.dataframe(df_view[df_view['bloque'] == 'Commodity'], use_container_width=True)

    with tab2:
        st.subheader("Detección Temprana de Riesgo")
        st.write("Identificación de señales de abandono o caída de actividad.")
        st.dataframe(df_view[df_view['bloque'] == 'Technical'], use_container_width=True)

    # 5. FEEDBACK LOOP: REGISTRO DE ACCIÓN Y APRENDIZAJE
    st.divider()
    st.subheader("📝 Gestión de Alertas")
    
    if not df_view.empty:
        with st.form("feedback_form"):
            # Identificación única por id_alerta (UUID)
            selected_id = st.selectbox("Seleccionar Alerta (ID):", df_view['id_alerta'].tolist())
            
            # El esquema acepta feedback (0, 1) y fecha_feedback
            res_feedback = st.radio("¿Intervención exitosa?", [1, 0], format_func=lambda x: "Venta/Recuperación" if x == 1 else "Sin éxito")
            
            if st.form_submit_button("Registrar Resultado Comercial"):
                with engine.begin() as conn:
                    stmt = text("""
                        UPDATE alertas 
                        SET feedback = :f, fecha_feedback = :d, updated_at = now() 
                        WHERE id_alerta = :id
                    """)
                    conn.execute(stmt, {"f": res_feedback, "d": date.today(), "id": selected_id})
                st.success(f"Feedback registrado. Los datos se usarán para re-entrenar el modelo.")
                st.rerun()
    else:
        st.info("No hay señales comerciales pendientes para el día de hoy.")

else:
    st.error("No se pudo conectar con la base de datos de Inibsa.")