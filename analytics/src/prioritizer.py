"""
Prioritizer — Smart Demand Signals
===================================

Assigns a priority score (0-200) to each unprioritized alert by combining
five weighted factors plus an ML contribution:

    Factor              Weight    Max pts   Rationale
    ─────────────────── ────────  ────────  ──────────────────────────────
    tipo_alerta          30 %       60      Alert type is strongest signal
    potencial_h          17.5 %     35      Higher potential → more revenue
    impacto_estimado     12.5 %     25      Missed revenue = opportunity
    urgencia             10 %       20      Time sensitivity
    perfil_cliente       10 %       20      Client loyalty profile
    ml_score             20 %       40      ML conversion probability
    ─────────────────── ────────  ────────  ──────────────────────────────
    TOTAL               100 %      200

Before training data is available, ``ml_score`` uses a heuristic based on
alert type, profile, impact, and urgency. As delegates register feedback,
the XGBoost model trains on real outcomes and progressively replaces
the heuristic — the system improves daily.

All weights are configured in ``analytics/utils/config.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.src.ml_engine import MLEngine  # noqa: E402
from analytics.utils.config import (  # noqa: E402
    ALERT_TYPE_BASE_SCORES,
    PRIORITY_WEIGHTS,
    PROFILE_MULTIPLIERS,
)
from analytics.utils.db import get_engine  # noqa: E402

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _normalize(series: pd.Series) -> pd.Series:
    """Min-max normalise a Series to [0, 1]. Returns 0.5 if constant."""
    mn, mx = series.min(), series.max()
    if mn == mx:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


# ═══════════════════════════════════════════════════════════════
# Prioritizer
# ═══════════════════════════════════════════════════════════════

class Prioritizer:
    """
    Assigns a priority score (0-200) to every alert with
    ``prioridad IS NULL`` and writes it back to the database.

    Parameters
    ----------
    engine : sqlalchemy.Engine, optional
    """

    def __init__(self, engine=None):
        self.engine = engine or get_engine()
        self.ml = MLEngine()

    # ── public API ─────────────────────────────────────────

    def run(self) -> int:
        """
        Prioritise all unprioritised alerts.

        Returns the number of alerts prioritised.
        """
        df = self._load()
        if df.empty:
            logger.info("Prioritizer — no unprioritised alerts, skipping.")
            return 0

        df = self._score(df)
        self._update(df)

        logger.info(
            "Prioritizer — %d alert(s) prioritised  "
            "(avg %.0f, min %d, max %d)",
            len(df),
            df["prioridad"].mean(),
            df["prioridad"].min(),
            df["prioridad"].max(),
        )
        return len(df)

    # ── internal ───────────────────────────────────────────

    def _load(self) -> pd.DataFrame:
        """Read all alerts that need prioritisation (no priority AND no feedback)."""
        query = text(
            """
            SELECT id_alerta, tipo_alerta, bloque, provincia,
                   potencial_h, impacto_estimado, urgencia_dias,
                   ratio_promiscuidad, perfil_cliente,
                   freq_media_dias, n_compras_hist,
                   dias_desde_ultima_compra
            FROM alertas
            WHERE prioridad IS NULL
              AND feedback IS NULL
            """
        )
        return pd.read_sql(query, self.engine)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate priority for every row in *df*."""

        # 1. Alert type base score (already 0-1 scale)
        df["tipo_score"] = df["tipo_alerta"].map(ALERT_TYPE_BASE_SCORES).fillna(0.50)

        # 2. Potencial_h  — normalise across the batch
        df["potencial_norm"] = _normalize(df["potencial_h"])

        # 3. Impacto estimado — normalise across the batch
        df["impacto_norm"] = _normalize(df["impacto_estimado"])

        # 4. Urgency — fewer days = more urgent = higher score
        #    urgencia_dias is SMALLINT [1, 90]
        df["urgencia_score"] = (90 - df["urgencia_dias"]) / 89.0

        # 5. Client profile — simple lookup
        df["perfil_score"] = (
            df["perfil_cliente"]
            .map(PROFILE_MULTIPLIERS)
            .fillna(0.50)
        )

        # 6. ML score — XGBoost probability or cold-start heuristic
        df["ml_score"] = self.ml.predict_batch(df)

        # ── Weighted sum ────────────────────────────────────────
        w = PRIORITY_WEIGHTS
        df["prioridad_raw"] = (
            df["tipo_score"]      * w["tipo_alerta"]      * 200
            + df["potencial_norm"] * w["potencial_h"]      * 200
            + df["impacto_norm"]   * w["impacto_estimado"]  * 200
            + df["urgencia_score"] * w["urgencia"]          * 200
            + df["perfil_score"]   * w["perfil_cliente"]    * 200
            + df["ml_score"]       * w["ml_score"]          * 200
        )

        df["prioridad"] = (
            df["prioridad_raw"]
            .clip(0, 200)
            .round()
            .astype(int)
        )

        df["score_conversion"] = df["ml_score"].round(4)

        return df

    def _update(self, df: pd.DataFrame):
        """Write ``prioridad`` and ``score_conversion`` back to the DB."""
        with self.engine.connect() as conn:
            trans = conn.begin()
            try:
                for _, row in df.iterrows():
                    conn.execute(
                        text(
                            "UPDATE alertas "
                            "SET prioridad = :p, score_conversion = :s "
                            "WHERE id_alerta = :id"
                        ),
                        {
                            "p": int(row["prioridad"]),
                            "s": float(row["score_conversion"]),
                            "id": str(row["id_alerta"]),
                        },
                    )
                trans.commit()
            except Exception:
                trans.rollback()
                logger.exception("Prioritizer UPDATE failed — rolled back")
                raise