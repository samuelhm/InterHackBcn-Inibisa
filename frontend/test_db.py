import os
import psycopg2
from sqlalchemy import create_engine

def check_connection():
    # Extraer URL del entorno (inyectada por Docker)
    db_url = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
    
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print("✅ Conexión exitosa a la base de datos de Inibsa.")
    except Exception as e:
        print(f"❌ Error detectado: {e}")

if __name__ == "__main__":
    check_connection()