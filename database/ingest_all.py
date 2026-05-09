import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta, date

DB_USER = os.environ.get("POSTGRES_USER", "admin_inibsa")
DB_PASS = os.environ.get("POSTGRES_PASSWORD", "inibsa_secret_2024")
DB_NAME = os.environ.get("POSTGRES_DB", "inibsa_smart_signals")

EXCEL_PATH = "/data/Datasets.xlsx"
EXCEL_EPOCH = datetime(1899, 12, 30)


def to_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.date() if isinstance(value, datetime) else value
    return (EXCEL_EPOCH + timedelta(days=int(float(value)))).date()


def get_engine():
    url = f"postgresql://{DB_USER}:{DB_PASS}@/{DB_NAME}?host=/var/run/postgresql"
    return create_engine(url)


def database_has_data(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM cliente"))
        count = result.scalar()
        return count > 0


def ingestar_clientes(engine):
    print("[clientes] Leyendo hoja 'Clientes'...")
    df = pd.read_excel(EXCEL_PATH, sheet_name="Clientes")

    col_names = df.columns.tolist()
    codigo_postal_col = col_names[1] if len(col_names) > 1 else None

    df_out = pd.DataFrame()
    df_out["id"] = pd.to_numeric(df[col_names[0]], errors="coerce").astype("Int64")
    if codigo_postal_col:
        df_out["codigo_postal"] = pd.to_numeric(df[codigo_postal_col], errors="coerce").fillna(0).astype(int)
    else:
        df_out["codigo_postal"] = 0
    df_out["provincia"] = df[col_names[2]].fillna("Desconocida").astype(str) if len(col_names) > 2 else "Desconocida"

    df_out = df_out.dropna(subset=["id"])
    df_out = df_out.drop_duplicates(subset=["id"])
    df_out.to_sql("cliente", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[clientes] {len(df_out)} registros insertados.")


def ingestar_productos(engine):
    print("[productos] Leyendo hoja 'Productos'...")
    df = pd.read_excel(EXCEL_PATH, sheet_name="Productos")

    df_out = pd.DataFrame()
    df_out["id"] = pd.to_numeric(df["Id.Prod"], errors="coerce").astype("Int64")
    df_out["bloque_analitico"] = df["Bloque analítico"].fillna("Desconocido").astype(str)
    df_out["categoria_h"] = df["Categoria_H"].fillna("Desconocida").astype(str)
    df_out["familia"] = df["Familia_H"].fillna("Desconocida").astype(str)

    df_out = df_out.dropna(subset=["id"])
    df_out = df_out.drop_duplicates(subset=["id"])
    df_out.to_sql("producto", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[productos] {len(df_out)} registros insertados.")


def ingestar_ventas(engine):
    print("[ventas] Leyendo hoja 'Ventas'...")
    df = pd.read_excel(EXCEL_PATH, sheet_name="Ventas")

    df_out = pd.DataFrame()
    df_out["numero_factura"] = pd.to_numeric(df["Num.Fact"], errors="coerce").astype("Int64")
    df_out["fecha"] = df["Fecha"].apply(to_date)
    df_out["id_cliente"] = pd.to_numeric(df["Id. Cliente"], errors="coerce").astype("Int64")
    df_out["id_producto"] = pd.to_numeric(df["Id. Producto"], errors="coerce").astype("Int64")
    df_out["unidades"] = pd.to_numeric(df["Unidades"], errors="coerce").fillna(0).astype(int)
    df_out["valores_h"] = pd.to_numeric(df["Valores_H"], errors="coerce").fillna(0.0).astype(float)

    df_out = df_out.dropna(subset=["numero_factura", "id_producto"])
    df_out = df_out.drop_duplicates(subset=["numero_factura", "id_producto"])

    existing_ids = set()
    try:
        existing_ids = set(pd.read_sql("SELECT id FROM cliente", engine)["id"].tolist())
    except Exception:
        pass

    missing_ids = set(df_out["id_cliente"].dropna().astype(int).unique()) - existing_ids
    if missing_ids:
        print(f"[ventas] Insertando {len(missing_ids)} clientes faltantes referenciados en ventas...")
        df_missing = pd.DataFrame({"id": list(missing_ids), "codigo_postal": 0, "provincia": "Desconocida"})
        df_missing.to_sql("cliente", engine, if_exists="append", index=False, method="multi", chunksize=500)

    df_out.to_sql("ventas", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[ventas] {len(df_out)} registros insertados.")


def ingestar_campanas(engine):
    print("[campanas] Leyendo hoja 'Campañas'...")
    df = pd.read_excel(EXCEL_PATH, sheet_name="Campañas")

    df_out = pd.DataFrame()
    df_out["campana"] = df["Campaña"].fillna("Desconocida").astype(str)
    df_out["fecha_inicio"] = df["Fecha inicio"].apply(to_date)
    df_out["fecha_fin"] = df["Fecha fin"].apply(to_date)

    df_out.to_sql("campanas", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[campanas] {len(df_out)} registros insertados.")


def ingestar_potencial(engine):
    print("[potencial] Creando tabla si no existe...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS potencial (
                id SERIAL PRIMARY KEY,
                id_cliente INTEGER REFERENCES cliente(id),
                familia TEXT,
                categoria_productos TEXT,
                potencial_h FLOAT
            )
        """))
        conn.commit()

    print("[potencial] Leyendo hoja 'Potencial'...")
    df = pd.read_excel(EXCEL_PATH, sheet_name="Potencial")

    df_out = pd.DataFrame()
    df_out["id_cliente"] = pd.to_numeric(df["Id.Cliente"], errors="coerce").astype("Int64")
    df_out["familia"] = df["Familia"].fillna("Desconocida").astype(str)
    df_out["categoria_productos"] = df["Categoria Productos"].fillna("Desconocida").astype(str)
    df_out["potencial_h"] = pd.to_numeric(df["Potencial_H"], errors="coerce").fillna(0.0).astype(float)

    df_out = df_out.dropna(subset=["id_cliente"])

    existing_ids = set()
    try:
        existing_ids = set(pd.read_sql("SELECT id FROM cliente", engine)["id"].tolist())
    except Exception:
        pass

    df_out = df_out[df_out["id_cliente"].isin(existing_ids)]

    df_out.to_sql("potencial", engine, if_exists="append", index=False, method="multi", chunksize=1000)
    print(f"[potencial] {len(df_out)} registros insertados.")


def main():
    print("=== INGESTA DE DATOS DESDE XLSX A POSTGRESQL ===")
    engine = get_engine()

    if database_has_data(engine):
        print("La base de datos ya contiene datos. No se realiza la ingesta.")
        return

    print("Base de datos vacía. Iniciando ingesta desde Datasets.xlsx...")

    ingestar_clientes(engine)
    ingestar_productos(engine)
    ingestar_campanas(engine)
    ingestar_potencial(engine)
    ingestar_ventas(engine)

    print("=== INGESTA COMPLETADA ===")


if __name__ == "__main__":
    main()
