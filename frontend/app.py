import streamlit as st
import os
import time
from sqlalchemy import create_engine, text

db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

# Lógica de conexión con reintentos (Máximo 10 intentos)
def connect_with_retry(max_retries=10, sleep_time=5):
    for i in range(max_retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            if i < max_retries - 1:
                st.warning(f"Esperando a la base de datos (Intento {i+1}/{max_retries})...")
                time.sleep(sleep_time)
            else:
                return False

if connect_with_retry():
    st.success("funciona")
    # Aquí irá la lógica de Commodities y Productos Técnicos
else:
    st.error("No se pudo establecer conexión tras varios intentos.")