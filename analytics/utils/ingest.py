import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')
    db = os.getenv('DB_NAME')
    host = os.getenv('DB_HOST') # En Docker será 'db'
    port = os.getenv('DB_PORT')
    
    return create_engine(f'postgresql://{user}:{password}@{host}:{port}/{db}')

def cargar_maestro_clientes():
    print("Iniciando carga de pestaña 'clientes'...")
    
    # 2. Leer Excel (especificando la pestaña exacta)
    # Nota: Asegúrate de tener instalada la librería 'openpyxl'
    path_excel = "/data/dataset.xlsx"
    df_clientes = pd.read_excel(path_excel, sheet_name='clientes')

    # 3. Limpieza y Transformación básica
    # Renombramos columnas para que coincidan exactamente con tu init.sql
    # Asumiendo que en Excel se llaman: 'id', 'codigo_postal', 'provincia'
    df_clientes = df_clientes[['id', 'codigo_postal', 'provincia']]
    
    # Manejo de nulos (Requisito de robustez del proyecto)
    df_clientes['codigo_postal'] = df_clientes['codigo_postal'].fillna(0).astype(int)
    df_clientes['provincia'] = df_clientes['provincia'].fillna('Desconocida').astype(str)

    # 4. Ingesta en PostgreSQL
    engine = get_connection()
    try:
        # Usamos 'append' para no borrar la estructura del init.sql
        df_clientes.to_sql('cliente', engine, if_exists='append', index=False)
        print(f"Éxito: Se han cargado {len(df_clientes)} clientes correctamente.")
    except Exception as e:
        print(f"Error en la carga: {e}")

if __name__ == "__main__":
    cargar_maestro_clientes()