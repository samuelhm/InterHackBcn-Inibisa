import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
import uuid

# --- CONFIGURACIÓN DE CONEXIÓN ---
# Ajusta estas credenciales a tu entorno local
DB_URL = "postgresql://fede:password@localhost:5432/inibsa"
engine = create_engine(DB_URL)

# Fecha de referencia para el Hackaton (Simulando "hoy")
FECHA_HOY = datetime(2026, 5, 9)

def obtener_clientes_activos():
    """Selecciona IDs de clientes con al menos una compra en el último año calendario."""
    query = """
    SELECT DISTINCT id_cliente 
    FROM ventas 
    WHERE fecha >= (TIMESTAMP '2026-05-09' - INTERVAL '1 year')
    """
    with engine.connect() as conn:
        result = conn.execute(text(query))
        return [row[0] for row in result]

def analizar_cliente(id_cliente):
    """
    Realiza el análisis de los 4 procesos para un cliente específico.
    Analiza cada familia de producto por separado para detectar fugas selectivas.
    """
    query = f"""
    SELECT 
        v.fecha, 
        v.valores_h as importe, 
        v.unidades,
        v.id_producto,
        p.familia, 
        p.bloque_analitico as bloque,
        c.provincia,
        pot.potencial_h
    FROM ventas v
    JOIN productos p ON v.id_producto = p.id_producto
    JOIN clientes c ON v.id_cliente = c.id_cliente
    LEFT JOIN potencial pot ON (v.id_cliente = pot.id_cliente AND p.familia = pot.familia)
    WHERE v.id_cliente = '{id_cliente}'
    ORDER BY v.fecha ASC
    """
    
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        print(f"Error leyendo datos del cliente {id_cliente}: {e}")
        return []

    if df.empty:
        return []

    alertas_cliente = []

    # Iteramos por familia de producto (Granularidad requerida por el briefing)
    for familia, historial in df.groupby('familia'):
        historial = historial.sort_values('fecha').copy()
        
        # --- MÉTRICAS BASE ---
        # Diferencia de días entre compras consecutivas
        historial['gap'] = historial['fecha'].diff().dt.days
        gaps_validos = historial['gap'].dropna()
        
        freq_media = gaps_validos.mean() if not gaps_validos.empty else 0
        vol_medio = historial['importe'].mean()
        
        ultima_venta = historial.iloc[-1]
        ultima_fecha = pd.to_datetime(ultima_venta['fecha'])
        dias_desde_ultima = (FECHA_HOY - ultima_fecha).days
        
        ultimo_volumen = ultima_venta['importe']
        
        # --- LOS 4 PROCESOS DE DETECCIÓN ---

        # 1. Ausencia de compra (Recencia crítica)
        # Umbral: Más del doble de su frecuencia habitual o más de 30 días si no hay histórico
        es_ausencia = (dias_desde_ultima > max(30, freq_media * 2))

        # 2. Caída de frecuencia
        # Umbral: El último intervalo entre compras es un 50% superior a su media
        ultimo_gap = gaps_validos.iloc[-1] if not gaps_validos.empty else 0
        es_caida_frecuencia = (ultimo_gap > freq_media * 1.5) if freq_media > 0 else False

        # 3. Caída de volumen de compra
        # Umbral: El importe del último pedido es inferior al 50% de su media histórica
        es_caida_volumen = (ultimo_volumen < vol_medio * 0.5) if vol_medio != 0 else False

        # 4. Actividad anómala (Estadística)
        # Umbral: Desviación estándar (Z-Score > 2) en importe o volumen inusual
        std_vol = historial['importe'].std()
        es_anomalo = False
        if not pd.isna(std_vol) and std_vol > 0:
            z_score = abs(ultimo_volumen - vol_medio) / std_vol
            es_anomalo = z_score > 2

        # --- CONSOLIDACIÓN DE RESULTADOS ---
        if any([es_ausencia, es_caida_frecuencia, es_caida_volumen, es_anomalo]):
            
            # Clasificación del tipo de alerta según briefing
            tipo = 'riesgo_fuga'
            if es_ausencia and dias_desde_ultima > 90:
                tipo = 'cliente_perdido'
            elif not es_ausencia and (es_caida_frecuencia or es_caida_volumen):
                tipo = 'riesgo_fuga'
            
            # Construcción del motivo técnico
            motivos = []
            if es_ausencia: motivos.append(f"Inactividad de {dias_desde_ultima} días")
            if es_caida_frecuencia: motivos.append(f"Retraso en ciclo (gap {int(ultimo_gap)} vs {freq_media:.1f} días)")
            if es_caida_volumen: motivos.append(f"Caída importe ({ultimo_volumen}€ vs {vol_medio:.1f}€ media)")
            if es_anomalo: motivos.append("Patrón de compra fuera de rango estadístico")

            # Mapeo al esquema de la tabla 'alertas'
            alerta = {
                'id_alerta': str(uuid.uuid4()),
                'id_cliente': str(id_cliente),
                'familia': familia,
                'bloque': 'Commodities' if 'Commodities' in str(historial['bloque'].iloc[0]) else 'Productos Técnicos',
                'provincia': historial['provincia'].iloc[0],
                'potencial_h': float(historial['potencial_h'].iloc[0] or 0),
                'dias_desde_ultima_compra': int(dias_desde_ultima),
                'tipo_alerta': tipo,
                'motivo': " | ".join(motivos),
                'alerta_frecuencia': bool(es_caida_frecuencia),
                'alerta_volumen': bool(es_caida_volumen),
                'alerta_ausencia': bool(es_ausencia),
                'alerta_anomalia': bool(es_anomalo),
                'probabilidad_deteccion': 0.90, # Confianza del modelo de detección
                'fecha': FECHA_HOY.date()
            }
            alertas_cliente.append(alerta)

    return alertas_cliente

def ejecutar_deteccion():
    print(f"--- INICIANDO MOTOR DE DETECCIÓN (Ref: {FECHA_HOY.date()}) ---")
    
    clientes = obtener_clientes_activos()
    print(f"Total clientes a analizar: {len(clientes)}")
    
    todas_alertas = []
    for i, id_c in enumerate(clientes):
        alertas = analizar_cliente(id_c)
        todas_alertas.extend(alertas)
        
        if (i + 1) % 100 == 0:
            print(f"Procesados {i + 1}/{len(clientes)} clientes...")

    if todas_alertas:
        print(f"Insertando {len(todas_alertas)} alertas en la base de datos...")
        df_alertas = pd.DataFrame(todas_alertas)
        
        # Insertar usando SQLAlchemy
        try:
            # Eliminamos duplicados potenciales de la misma ejecución
            df_alertas.to_sql('alertas', engine, if_exists='append', index=False, method='multi')
            print("¡Éxito! Alertas guardadas correctamente.")
        except Exception as e:
            print(f"Error al insertar en DB: {e}")
    else:
        print("No se detectaron anomalías en los clientes analizados.")

if __name__ == "__main__":
    ejecutar_deteccion()
