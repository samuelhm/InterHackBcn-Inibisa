"""
Technical Engine — Smart Demand Signals
========================================
Analyses purchasing patterns for **technical products** (implants,
specialized instruments, rotary files, etc.).  Unlike commodities, technical
products have **variable purchase patterns** driven by clinical cases and
dentist specialty, so the engine focuses on:

1. **Pattern deterioration** — detecting changes in historic behaviour
2. **Abandonment risk**  — identifying clinics that are disengaging
3. **Noise filtering**    — distinguishing real signals from natural variability

Alert types generated:
  - ``reposicion``       — approaching expected re-order based on historic pattern
  - ``riesgo_fuga``      — deterioration detected, clinic still active
  - ``cliente_perdido``  — extended absence

``ventana_captura`` is **not** generated for technical products because
promiscuity is harder to define when purchase volumes depend on clinical
demand rather than steady consumption.

Detection thresholds are **more sensitive** than for commodities: technical
products are "stickier" (a clinic that switches away rarely comes back), so
even small deviations are worth flagging.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.utils.config import (  # noqa: E402
    DEDUP_WINDOW_DAYS,
    FECHA_HOY,
    TECHNICAL as THRESHOLDS,
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


class TechnicalEngine:
    """
    Detection engine for technical products.

    Parameters
    ----------
    engine : sqlalchemy.Engine, optional
    fecha_ref : datetime, optional
    """

    def __init__(self, engine=None, fecha_ref: datetime | None = None):
        self.engine = engine or get_engine()
        self.fecha_ref = fecha_ref or FECHA_HOY

    # ── public API ─────────────────────────────────────────

    def get_active_clients(self) -> list[int]:
        query = text(
            "SELECT DISTINCT id_cliente FROM ventas "
            "WHERE fecha >= :ref - INTERVAL '1 year'"
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query, {"ref": self.fecha_ref.date()})
            return [r[0] for r in rows]

    def get_client_data(self, id_cliente: int) -> pd.DataFrame:
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
                AND p.familia      = pot.familia)
            WHERE v.id_cliente = :cid
            ORDER BY v.fecha ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"cid": id_cliente})

    def analyze_client(self, id_cliente: int) -> tuple[list[dict], int]:
        """Analyse all **technical** families for a single client.

        Returns (alertas, skipped) where skipped is the number of
        alerts that were not created because a pending one already exists.
        """
        df = self.get_client_data(id_cliente)
        if df.empty:
            return [], 0

        df_t = df[df["bloque"].apply(_is_technical)].copy()
        if df_t.empty:
            return [], 0

        alertas: list[dict] = []
        skipped = 0
        for familia, grp in df_t.groupby("familia"):
            alerta = self._analyze_family(grp, id_cliente, familia)
            if alerta is None:
                continue
            if self._alert_exists(id_cliente, familia):
                skipped += 1
                continue
            alertas.append(alerta)
        return alertas, skipped

    def run(self) -> list[dict]:
        clientes = self.get_active_clients()
        logger.info("TechnicalEngine — %d active client(s) to analyse", len(clientes))
        todas: list[dict] = []
        total_skipped = 0
        for i, cid in enumerate(clientes):
            alertas, skipped = self.analyze_client(cid)
            todas.extend(alertas)
            total_skipped += skipped
            if (i + 1) % 100 == 0:
                logger.info("  technical … %d/%d clients processed", i + 1, len(clientes))
        logger.info(
            "TechnicalEngine — %d alert(s) generated, %d skipped (already pending)",
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
        df = df.sort_values("fecha").copy()
        n = len(df)

        if n < 2:
            return None

        # ── computed fields ────────────────────────────────────
        df["gap"] = df["fecha"].diff().dt.days
        freq = compute_frequency_metrics(df)
        vol = compute_volume_metrics(df)
        ultima_fecha = pd.to_datetime(df["fecha"].iloc[-1])
        dias_desde_ultima = (self.fecha_ref - ultima_fecha).days

        provincia = str(df["provincia"].iloc[0])
        potencial_h = float(df["potencial_h"].iloc[0] or 0)

        ratio_p = compute_promiscuity_ratio(vol["total_12m"], potencial_h)
        impacto = compute_impacto_estimado(potencial_h, vol["total_12m"])
        urgencia = compute_urgencia_dias(freq["freq_media"], dias_desde_ultima)
        perfil = classify_client_profile(ratio_p)

        t = THRESHOLDS  # shorthand

        # ── detection flags ────────────────────────────────────
        caida_f = (
            freq["n_compras"] >= t["caida_frecuencia"]["min_compras"]
            and freq["freq_media"] > 0
            and freq["ultimo_gap"] > freq["freq_media"] * t["caida_frecuencia"]["ratio"]
        )

        caida_v = (
            n >= t["caida_volumen"]["min_compras"]
            and vol["vol_medio"] > 0
            and vol["ultimo_volumen"] < vol["vol_medio"] * t["caida_volumen"]["ratio"]
        )

        umbral_ausencia = max(
            t["ausencia"]["min_dias"],
            freq["freq_media"] * t["ausencia"]["freq_multiplier"]
        ) if freq["freq_media"] > 0 else t["ausencia"]["min_dias"]
        es_ausencia = dias_desde_ultima > umbral_ausencia

        es_anomalo = (
            n >= t["anomalia"]["min_compras"]
            and vol["vol_std"] > 0
            and compute_z_score(vol["ultimo_volumen"], vol["vol_medio"], vol["vol_std"])
            > t["anomalia"]["z_score"]
        )

        repos = (
            freq["freq_media"] > 0
            and dias_desde_ultima > freq["freq_media"] * t["reposicion"]["cycle_ratio"]
            and dias_desde_ultima < t["reposicion"]["max_inactive_days"]
        )

        # ── noise filter — skip sporadic buyers ────────────────
        signals = [caida_f, caida_v, es_ausencia, es_anomalo, repos]
        if vol["cv"] > t["noise_filter"]["cv_threshold"]:
            # High CV → variable purchaser.  Require ≥ 2 concurrent signals.
            if sum(signals) < t["noise_filter"]["min_patterns_for_noisy"]:
                return None

        any_hit = any(signals)
        if not any_hit:
            return None

        # ── classify alert type ─────────────────────────────────
        if es_ausencia and dias_desde_ultima > t["perdido_dias"]:
            tipo = "cliente_perdido"
        elif repos:
            tipo = "reposicion"
        else:
            tipo = "riesgo_fuga"

        # ── motivo ──────────────────────────────────────────────
        piezas: list[str] = []
        if caida_f:
            piezas.append(
                f"Caida frecuencia (tecnico): gap {freq['ultimo_gap']}d "
                f"vs media {freq['freq_media']:.0f}d"
            )
        if caida_v:
            piezas.append(
                f"Caida volumen (tecnico): {vol['ultimo_volumen']:.0f}EUR "
                f"vs media {vol['vol_medio']:.0f}EUR"
            )
        if es_ausencia:
            piezas.append(f"Ausencia (tecnico): {dias_desde_ultima}d sin compra")
        if es_anomalo:
            piezas.append("Actividad anomala (tecnico, Z-score > 2)")
        if repos:
            piezas.append(
                f"Reposicion (tecnico): gap {dias_desde_ultima}d vs "
                f"ciclo {freq['freq_media']:.0f}d"
            )

        # ── confidence — lower for technical due to variability ─
        prob = 0.92 if n >= 12 else 0.85 if n >= 6 else 0.70

        return {
            "id_cliente": str(id_cliente),
            "familia": familia,
            "bloque": "Productos Técnicos",
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

def _is_technical(bloque_raw) -> bool:
    """Return True if the raw bloque value maps to Productos Técnicos."""
    if bloque_raw is None or (isinstance(bloque_raw, float) and pd.isna(bloque_raw)):
        return False
    b = str(bloque_raw).strip().lower()
    # Everything that is NOT a commodity is technical
    return "commodit" not in b
