"""
ML Engine — Smart Demand Signals
=================================

Binary classification model that predicts the probability of a delegate
successfully converting an alert into a sale (``score_conversion`` in [0, 1]).

Architecture
------------
Based on the XGBoost approach validated in the team's exploratory Colab
notebook [1]_, which demonstrated that gradient-boosted trees with
class-imbalance weighting (``scale_pos_weight``) effectively identify
at-risk client relationships in Inibsa's dental clinic portfolio.

The notebook validated:
  - XGBoost as the algorithm of choice for churn / conversion prediction
  - ``scale_pos_weight`` to compensate for imbalanced positive/negative labels
  - Feature importance analysis showing trend-based signals as the strongest
    predictors of conversion
  - A 0–200 scoring system consistent with our 6-factor priority framework
  - Continuous retraining from delegate feedback (the feedback loop)

Our implementation adapts those findings to a per-alert architecture:

  - **Features** are per-alert (tipo_alerta, bloque, provincia, perfil_cliente,
    numeric metrics) rather than monthly client aggregates.
  - **Target** is the real delegate feedback (``0 = no conversion``, ``1 = conversion``)
    rather than the synthetic ``Alerta_Caida_Tendencia`` flag.
  - **Output** feeds into the 6-factor prioritizer at 20 % weight (up to 40 pts).

Cold-start strategy
-------------------
When there is insufficient feedback data (< ``MIN_FEEDBACK_SAMPLES`` rows),
the engine falls back to a rule-based heuristic derived from the same
feature importance insights validated by the Colab notebook:

  - Alert type as the primary signal (ventana_captura highest, cliente_perdido lowest)
  - Client profile modulation (leal > promiscuo > marginal)
  - Impact and urgency as secondary signals

As delegates register feedback through the dashboard, the XGBoost model
trains on real outcomes and progressively replaces the heuristic.

.. [1] https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"

# ═══════════════════════════════════════════════════════════════
# Minimum feedback rows required to train a real model.
# Below this threshold the heuristic is used instead.
# ═══════════════════════════════════════════════════════════════
MIN_FEEDBACK_SAMPLES = 30

# ═══════════════════════════════════════════════════════════════
# Feature definitions — must match the columns selected from alertas
# in both the Prioritizer._load() query and the ml_trainer query.
# ═══════════════════════════════════════════════════════════════
CATEGORICAL_FEATURES = ["tipo_alerta", "bloque", "provincia", "perfil_cliente"]
NUMERIC_FEATURES = [
    "potencial_h", "impacto_estimado", "urgencia_dias",
    "ratio_promiscuidad", "dias_desde_ultima_compra",
    "freq_media_dias", "n_compras_hist",
]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# ═══════════════════════════════════════════════════════════════
# Cold-start heuristic configuration
#
# Base conversion probabilities by alert type, derived from business
# knowledge and the XGBoost feature-importance analysis in the Colab
# notebook [1] which identified alert type / trend direction as the
# strongest predictor of client conversion.
# ═══════════════════════════════════════════════════════════════
COLD_START_ALERT_PROBS = {
    "ventana_captura": 0.65,
    "reposicion": 0.55,
    "riesgo_fuga": 0.40,
    "cliente_perdido": 0.20,
}

COLD_START_PROFILE_MULT = {
    "leal": 1.15,
    "promiscuo": 1.00,
    "marginal": 0.80,
}


def _safe_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalise to [0, 1]. Returns 0.5 if constant."""
    mn, mx = series.min(), series.max()
    if pd.isna(mn) or pd.isna(mx) or mn == mx:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


class MLEngine:
    """
    ML inference engine for Smart Demand Signals.

    Loads a trained XGBoost model from ``analytics/models/`` if available;
    otherwise falls back to a heuristic-based cold-start strategy.

    Inspired by the XGBoost + ``scale_pos_weight`` approach validated in
    the team's Colab notebook [1], adapted to our per-alert architecture
    with real delegate feedback as the training target.

    .. [1] https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_
    """

    def __init__(self):
        self._model = None
        self._preprocessor = None
        self._metadata: dict | None = None
        self._load_model()

    # ── model io ──────────────────────────────────────────

    def _load_model(self):
        """Try to load the latest trained model + preprocessor from disk."""
        model_path = MODEL_DIR / "model.pkl"
        preproc_path = MODEL_DIR / "preprocessor.pkl"
        meta_path = MODEL_DIR / "metadata.json"

        if not model_path.exists() or not preproc_path.exists():
            logger.info(
                "ML Engine — no trained model found at %s, using cold-start heuristic",
                MODEL_DIR,
            )
            return

        try:
            import joblib
            self._model = joblib.load(model_path)
            self._preprocessor = joblib.load(preproc_path)
            if meta_path.exists():
                with open(meta_path) as fh:
                    self._metadata = json.load(fh)
            logger.info(
                "ML Engine — loaded model trained on %s "
                "(%d samples, accuracy=%.3f, recall=%.3f)",
                self._metadata.get("training_date", "unknown") if self._metadata else "?",
                self._metadata.get("n_samples", 0) if self._metadata else 0,
                self._metadata.get("accuracy", 0) if self._metadata else 0,
                self._metadata.get("recall", 0) if self._metadata else 0,
            )
        except Exception:
            logger.warning(
                "ML Engine — failed to load model, falling back to heuristic",
                exc_info=True,
            )
            self._model = None
            self._preprocessor = None

    # ── public api ────────────────────────────────────────

    def predict_batch(self, df: pd.DataFrame) -> pd.Series:
        """
        Predict conversion probability for a batch of alerts.

        Parameters
        ----------
        df : DataFrame
            Must contain at least the columns listed in ``ALL_FEATURES``.

        Returns
        -------
        pd.Series
            Float scores in [0, 1], one per row of *df*.
        """
        if df.empty:
            return pd.Series(dtype=float, name="ml_score")

        if self._model is not None and self._preprocessor is not None:
            return self._predict_ml(df)
        return self._predict_heuristic(df)

    def get_score(self, alert_id: str) -> float:
        """
        Single-alert prediction — **deprecated**, use ``predict_batch`` instead.

        Kept for backward compatibility but always returns 0.0.
        The Prioritizer should call ``predict_batch`` for efficiency.
        """
        logger.warning("get_score() is deprecated — use predict_batch() instead")
        return 0.0

    # ── ml path ────────────────────────────────────────────

    def _predict_ml(self, df: pd.DataFrame) -> pd.Series:
        """Predict using the trained XGBoost model."""
        try:
            X = self._preprocess(df)
            probs = self._model.predict_proba(X)[:, 1]
            return pd.Series(probs, index=df.index, name="ml_score").clip(0.01, 0.99)
        except Exception:
            logger.warning(
                "ML prediction failed, falling back to heuristic", exc_info=True
            )
            return self._predict_heuristic(df)

    def _preprocess(self, df: pd.DataFrame) -> np.ndarray:
        """Transform raw alert features using the fitted preprocessor."""
        available = [c for c in ALL_FEATURES if c in df.columns]
        X = df[available].copy()

        for col in NUMERIC_FEATURES:
            if col in X.columns:
                X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0)
        for col in CATEGORICAL_FEATURES:
            if col in X.columns:
                X[col] = X[col].astype(str).fillna("unknown")

        return self._preprocessor.transform(X)

    # ── heuristic path (cold start) ───────────────────────

    def _predict_heuristic(self, df: pd.DataFrame) -> pd.Series:
        """
        Rule-based cold-start heuristic used when no ML model is trained.

        Derived from the feature-importance insights in the Colab notebook [1]_,
        which showed that alert type and client profile are the strongest
        predictors of conversion, followed by urgency and impact signals.

        Base probabilities are modulated by:
          - Client profile (leal > promiscuo > marginal)
          - Normalised impact estimate (higher → easier sell)
          - Normalised urgency (more urgent → better timing)

        .. [1] https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_
        """
        base = df["tipo_alerta"].map(COLD_START_ALERT_PROBS).fillna(0.35)

        profile_mult = (
            df["perfil_cliente"]
            .map(COLD_START_PROFILE_MULT)
            .fillna(1.0)
        )

        impact_norm = _safe_normalize(
            pd.to_numeric(df["impacto_estimado"], errors="coerce").fillna(0)
        )
        urgency_norm = (90 - pd.to_numeric(df["urgencia_dias"], errors="coerce").fillna(45)) / 89.0

        # Weighted combination reflecting Colab feature importance:
        # alert type dominates, with impact and urgency as secondary signals
        score = base * profile_mult + 0.10 * impact_norm + 0.08 * urgency_norm

        return score.clip(0.05, 0.95).rename("ml_score")

    # ── introspection ──────────────────────────────────────

    @property
    def is_trained(self) -> bool:
        """True if a model is loaded and ready for inference."""
        return self._model is not None

    @property
    def metadata(self) -> dict | None:
        """Training metadata dict, or ``None`` if no model is loaded."""
        return self._metadata