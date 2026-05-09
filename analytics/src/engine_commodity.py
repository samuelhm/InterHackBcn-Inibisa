"""
Commodity Engine — Smart Demand Signals
========================================
Analyses purchasing patterns for **commodity products** (anestesia, agujas,
desinfeccion, etc.).  Commodities have regular, predictable purchase cycles
so the engine focuses on:

1. **Promiscuity ratio** — how much of a clinic's potential goes to competitors
2. **Capture windows** — opportunity to gain market share from promiscuous clients
3. **Reorder timing** — loyal clients approaching their expected restock date
4. **Standard deterioration** — frequency/volume drops, absence, anomalies

Alert types generated (in order of business value):
  - ``ventana_captura``  — promiscuous client due for purchase  (NEW revenue)
  - ``reposicion``       — loyal client needs restock            (retention)
  - ``riesgo_fuga``      — deterioration detected, still active   (warning)
  - ``cliente_perdido``  — extended absence                      (recovery)

Output rows are ready to be inserted into the ``alertas`` table.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.utils.config import (  # noqa: E402
    COMMODITY as THRESHOLDS,
    DEDUP_WINDOW_DAYS,
    FECHA_HOY,
    MAX_INACTIVE_DAYS,
)
from analytics.utils.db import get_engine  # noqa: E402
from analytics.utils.metrics import (  # noqa: E402
    classify_client_profile,
    compute_frequency_metrics,
    compute_impacto_estimado,
    compute_promiscuity_ratio,
    compute_urgencia_dias,
    compute_volume_metrics,
    compute_z_score,
)

logger = logging.getLogger(__name__)


class CommodityEngine:
    """
    Detection engine for commodity products.

    Parameters
    ----------
    engine : sqlalchemy.Engine, optional
        Database connection.  If *None*, one is created from environment.
    fecha_ref : datetime, optional
        Reference date (default ``FECHA_HOY`` from config).
    """

    def __init__(self, engine=None, fecha_ref: datetime | None = None):
        self.engine = engine or get_engine()
        self.fecha_ref = fecha_ref or FECHA_HOY

    # ── public API ─────────────────────────────────────────

    def get_active_clients(self) -> list[int]:
        """Return IDs of all clients with ≥ 1 purchase in the last year."""
        query = text(
            "SELECT DISTINCT id_cliente FROM ventas "
            "WHERE fecha >= :ref - INTERVAL '1 year'"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"ref": self.fecha_ref.date()})
            return [r[0] for r in rows]

    def get_client_data(self, id_cliente: int) -> pd.DataFrame:
        """Fetch all purchase rows for *id_cliente* joined with product/potencial."""
        query = text(
            """
            SELECT
                v.fecha,
                v.valores_h   AS importe,
                v.unidades,
                v.id_producto,
                p.familia,
                p.bloque_analitico AS bloque,
                p.categoria_h,
                c.provincia,
                pot.potencial_h
            FROM ventas v
            JOIN producto p ON v.id_producto = p.id
            JOIN cliente  c ON v.id_cliente  = c.id
            LEFT JOIN potencial pot
                ON (v.id_cliente  = pot.id_cliente
                AND p.categoria_h = pot.categoria_productos)
            WHERE v.id_cliente = :cid
            ORDER BY v.fecha ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"cid": id_cliente})

    def analyze_client(self, id_cliente: int) -> tuple[list[dict], int]:
        """Analyse all **commodity** families for a single client.

        Returns (alertas, skipped) where skipped is the number of
        alerts that were not created because a pending one already exists.
        """
        df = self.get_client_data(id_cliente)
        if df.empty:
            return [], 0

        df_c = df[df["bloque"].apply(_is_commodity)].copy()
        if df_c.empty:
            return [], 0

        alertas: list[dict] = []
        skipped = 0
        for familia, grp in df_c.groupby("familia"):
            alerta = self._analyze_family(grp, id_cliente, familia)
            if alerta is None:
                continue
            if self._alert_exists(id_cliente, familia):
                skipped += 1
                continue
            alertas.append(alerta)
        return alertas, skipped

    def run(self) -> list[dict]:
        """Run detection across all active clients.  Returns alert rows."""
        clientes = self.get_active_clients()
        logger.info("CommodityEngine — %d active client(s) to analyse", len(clientes))
        todas: list[dict] = []
        total_skipped = 0
        for i, cid in enumerate(clientes):
            alertas, skipped = self.analyze_client(cid)
            todas.extend(alertas)
            total_skipped += skipped
            if (i + 1) % 100 == 0:
                logger.info("  commodity … %d/%d clients processed", i + 1, len(clientes))
        logger.info(
            "CommodityEngine — %d alert(s) generated, %d skipped (already pending)",
            len(todas), total_skipped,
        )
        return todas

    # ── internal ───────────────────────────────────────────

    def _alert_exists(self, id_cliente: int, familia: str) -> bool:
        """Return True if a pending alert already exists for this client-family."""
        query = text(
            "SELECT 1 FROM alertas "
            "WHERE id_cliente = :cid "
            "  AND familia = :fam "
            "  AND feedback IS NULL "
            "  AND fecha >= :since "
            "LIMIT 1"
        )
        since = (self.fecha_ref - timedelta(days=DEDUP_WINDOW_DAYS)).date()
        with self.engine.connect() as conn:
            row = conn.execute(
                query,
                {"cid": str(id_cliente), "fam": familia, "since": since},
            )
            return row.first() is not None

    def _analyze_family(
        self, df: pd.DataFrame, id_cliente: int, familia: str
    ) -> dict | None:
        """Run every detection pattern on one client‑family subset."""
        df = df.sort_values("fecha").copy()
        n = len(df)

        if n < 2:
            return None  # cannot establish a pattern with a single purchase

        # ── computed fields ────────────────────────────────────
        df["gap"] = df["fecha"].diff().dt.days
        freq = compute_frequency_metrics(df)
        vol = compute_volume_metrics(df)
        ultima_fecha = pd.to_datetime(df["fecha"].iloc[-1])
        dias_desde_ultima = (self.fecha_ref - ultima_fecha).days

        provincia = str(df["provincia"].iloc[0])
        potencial_h = float(df["potencial_h"].iloc[0] or 0)

        # Hard cutoff: skip client-families inactive > 1 year
        if dias_desde_ultima > MAX_INACTIVE_DAYS:
            return None

        ratio_p = compute_promiscuity_ratio(vol["total_12m"], potencial_h)
        impacto = compute_impacto_estimado(potencial_h, vol["total_12m"])
        urgencia = compute_urgencia_dias(freq["freq_media"], dias_desde_ultima)
        perfil = classify_client_profile(ratio_p)

        t = THRESHOLDS  # shorthand

        # ── 1. Caida de frecuencia ─────────────────────────────
        caida_f = (
            freq["n_compras"] >= t["caida_frecuencia"]["min_compras"]
            and freq["freq_media"] > 0
            and freq["ultimo_gap"] > freq["freq_media"] * t["caida_frecuencia"]["ratio"]
        )

        # ── 2. Caida de volumen ─────────────────────────────────
        caida_v = (
            n >= t["caida_volumen"]["min_compras"]
            and vol["vol_medio"] > 0
            and vol["ultimo_volumen"] < vol["vol_medio"] * t["caida_volumen"]["ratio"]
        )

        # ── 3. Ausencia de compra ───────────────────────────────
        umbral_ausencia = max(
            t["ausencia"]["min_dias"],
            freq["freq_media"] * t["ausencia"]["freq_multiplier"]
        ) if freq["freq_media"] > 0 else t["ausencia"]["min_dias"]
        es_ausencia = dias_desde_ultima > umbral_ausencia

        # ── 4. Actividad anomala (Z-score) ──────────────────────
        es_anomalo = (
            n >= t["anomalia"]["min_compras"]
            and vol["vol_std"] > 0
            and compute_z_score(vol["ultimo_volumen"], vol["vol_medio"], vol["vol_std"])
            > t["anomalia"]["z_score"]
        )

        # ── 5. Ventana de captura (commodity-specific) ──────────
        ventana = (
            ratio_p >= t["ventana_captura"]["min_promiscuidad"]
            and impacto > 0
            and freq["freq_media"] > 0
            and dias_desde_ultima > freq["freq_media"] * t["ventana_captura"]["cycle_ratio"]
            and dias_desde_ultima < t["ventana_captura"]["max_inactive_days"]
        )

        # ── 6. Reposicion (commodity-specific) ──────────────────
        repos = (
            ratio_p < t["reposicion"]["max_promiscuidad"]
            and freq["freq_media"] > 0
            and dias_desde_ultima > freq["freq_media"] * t["reposicion"]["cycle_ratio"]
            and dias_desde_ultima < t["reposicion"]["max_inactive_days"]
        )

        any_hit = any([caida_f, caida_v, es_ausencia, es_anomalo, ventana, repos])
        if not any_hit:
            return None

        # ── Classify alert type ─────────────────────────────────
        if es_ausencia and dias_desde_ultima > t["perdido_dias"]:
            tipo = "cliente_perdido"
        elif ventana:
            tipo = "ventana_captura"
        elif repos:
            tipo = "reposicion"
        else:
            tipo = "riesgo_fuga"

        # ── Build human-readable motivo ─────────────────────────
        piezas: list[str] = []
        if ventana:
            piezas.append(
                f"Ventana captura: promiscuidad {ratio_p:.0%}, "
                f"gap {dias_desde_ultima}d vs ciclo {freq['freq_media']:.0f}d"
            )
        if repos:
            piezas.append(
                f"Reposicion: gap {dias_desde_ultima}d vs "
                f"ciclo {freq['freq_media']:.0f}d"
            )
        if caida_f:
            piezas.append(
                f"Caida frecuencia: ultimo gap {freq['ultimo_gap']}d "
                f"vs media {freq['freq_media']:.0f}d"
            )
        if caida_v:
            piezas.append(
                f"Caida volumen: {vol['ultimo_volumen']:.0f}EUR "
                f"vs media {vol['vol_medio']:.0f}EUR"
            )
        if es_ausencia:
            piezas.append(f"Ausencia: {dias_desde_ultima}d sin compra")
        if es_anomalo:
            piezas.append("Actividad anomala (Z-score > 2)")

        # ── Confidence ──────────────────────────────────────────
        prob = 0.95 if n >= 12 else 0.90 if n >= 6 else 0.75

        return {
            "id_cliente": str(id_cliente),
            "familia": familia,
            "bloque": "Commodities",
            "provincia": provincia,
            "potencial_h": potencial_h,
            "dias_desde_ultima_compra": int(dias_desde_ultima),
            "impacto_estimado": round(impacto, 2),
            "urgencia_dias": urgencia,
            "ratio_promiscuidad": round(ratio_p, 4),
            "tipo_alerta": tipo,
            "motivo": " | ".join(piezas),
            "probabilidad_deteccion": prob,
            "alerta_frecuencia": caida_f,
            "alerta_volumen": caida_v,
            "alerta_ausencia": es_ausencia,
            "alerta_anomalia": es_anomalo,
            "fecha": self.fecha_ref.date(),
        }


# ── helpers ─────────────────────────────────────────────────

def _is_commodity(bloque_raw) -> bool:
    """Return True if the raw bloque value maps to Commodities."""
    if bloque_raw is None or (isinstance(bloque_raw, float) and pd.isna(bloque_raw)):
        return False
    return "commodit" in str(bloque_raw).strip().lower()
