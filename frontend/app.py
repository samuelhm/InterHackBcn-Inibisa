mport streamlit as st
import pandas as pd
import os
from sqlalchemy import create_engine, text

# 1. Configuración y Conexión Directa
st.set_page_config(page_title="Debug DB Inibsa", layout="wide")
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

st.title("Panel de Verificación: Tabla Alertas")

try:
    with engine.connect() as conn:
        # 2. Extracción sin filtros para validar contenido total
        query = text("SELECT * FROM alertas")
        df = pd.read_sql(query, conn)

    if not df.empty:
        # 3. Resumen de datos detectados
        st.success(f"Conexión exitosa. Se han encontrado {len(df)} registros.")
        
        # Agrupación básica para verificar la lógica de bloques[cite: 1, 2]
        st.subheader("Resumen por Bloque")
        st.write(df['bloque'].value_counts())

        # 4. Visualización dei la tabla completa
        st.subheader("Datos en Bruto")
        st.dataframe(df, use_container_width=True)
    else:
        st.warning("La conexión funciona, pero la tabla 'alertas' está vacía.")

except Exception as e:
    st.error(f"Error de base de datos: {e}")