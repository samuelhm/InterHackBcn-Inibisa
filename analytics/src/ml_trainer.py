"""
ML Trainer — Smart Demand Signals
==================================

Nightly training pipeline for the XGBoost conversion-prediction model.

Based on the XGBoost approach validated in the team's Colab notebook [1]_,
which demonstrated that gradient-boosted trees with ``scale_pos_weight``
effectively predict client churn and conversion in Inibsa's domain.

Key adaptations from the notebook's approach:
  - Per-alert features (tipo_alerta, bloque, provincia, perfil_cliente, etc.)
    instead of monthly client aggregates (Valores_H, Media_6m, Pendiente_6m).
  - Real delegate feedback as the target variable (0/1) instead of the
    synthetic ``Alerta_Caida_Tendencia`` derived from rolling regression.
  - OneHotEncoder for categoricals + StandardScaler for numerics, following
    the same standardisation approach used in the notebook's PCA pipeline.
  - ``scale_pos_weight`` for class imbalance, as validated in section 16
    of the notebook.
  - Model persistence to ``analytics/models/`` for次日 inference by
    the ``MLEngine``.

The model trains on the ``alertas_feedback`` view (alerts with real delegate
feedback) and saves:
  - ``model.pkl`` — trained XGBClassifier
  - ``preprocessor.pkl`` — fitted ColumnTransformer
  - ``metadata.json`` — training date, sample count, accuracy, recall

.. [1] https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text
from xgboost import XGBClassifier

from analytics.src.ml_engine import (
    CATEGORICAL_FEATURES,
    MIN_FEEDBACK_SAMPLES,
    NUMERIC_FEATURES,
    ALL_FEATURES,
    MODEL_DIR,
)

logger = logging.getLogger(__name__)


def train_model(engine) -> bool:
    """
    Train (or retrain) the XGBoost model on delegate feedback data.

    This function:
      1. Reads all alerts with ``feedback IS NOT NULL`` from the database.
      2. If insufficient samples, logs a warning and returns ``False``.
      3. Preprocesses features (OneHotEncoder + StandardScaler).
      4. Trains an XGBClassifier with ``scale_pos_weight`` for class imbalance.
      5. Evaluates on a held-out test set.
      6. Saves model, preprocessor, and metadata to ``analytics/models/``.

    The approaches and hyperparameters are based on the methodology
    validated in the team's Colab notebook [1]_ (sections 15–18), which
    demonstrated that XGBoost with ``scale_pos_weight`` achieves robust
    churn prediction for Inibsa's client portfolio.

    Parameters
    ----------
    engine : sqlalchemy.Engine
        Database connection.

    Returns
    -------
    bool
        ``True`` if a new model was trained and saved, ``False`` otherwise.

    .. [1] https://colab.research.google.com/drive/17rKhS8rg9h9sSauN2RcDm1YtS-wXB1b_
    """
    logger.info("ML Trainer — starting training pipeline")

    # ── 1. Load feedback data ────────────────────────────────
    df = _load_feedback(engine)
    if df is None or len(df) < MIN_FEEDBACK_SAMPLES:
        n = 0 if df is None else len(df)
        logger.warning(
            "ML Trainer — only %d feedback samples (need %d), "
            "skipping training. Cold-start heuristic will be used.",
            n, MIN_FEEDBACK_SAMPLES,
        )
        return False

    logger.info("ML Trainer — %d feedback samples loaded", len(df))

    # ── 2. Prepare features and target ───────────────────────
    X, y, preprocessor = _prepare_features(df)
    if X is None:
        logger.error("ML Trainer — feature preparation failed")
        return False

    # ── 3. Train/test split ─────────────────────────────────
    stratify = y if y.nunique() > 1 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=stratify,
    )

    # ── 4. Compute class-imbalance weight ────────────────────
    # scale_pos_weight = n_negative / n_positive
    # This is the approach validated in the Colab notebook (section 16)
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    if n_pos == 0:
        logger.warning("ML Trainer — no positive samples in training data, skipping")
        return False

    scale_pos_weight = n_neg / n_pos
    logger.info(
        "ML Trainer — class balance: %d neg / %d pos (scale_pos_weight=%.2f)",
        n_neg, n_pos, scale_pos_weight,
    )

    # ── 5. Train XGBoost ────────────────────────────────────
    model = XGBClassifier(
        objective="binary:logistic",
        scale_pos_weight=scale_pos_weight,
        n_estimators=100,
        learning_rate=0.1,
        max_depth=4,
        random_state=42,
        eval_metric="logloss",
    )

    model.fit(X_train, y_train)

    # ── 6. Evaluate ──────────────────────────────────────────
    y_pred = model.predict(X_test)
    report = classification_report(
        y_test, y_pred, output_dict=True, zero_division=0,
    )
    accuracy = report.get("accuracy", 0.0)
    recall_1 = report.get("1", {}).get("recall", 0.0)
    precision_1 = report.get("1", {}).get("precision", 0.0)

    logger.info(
        "ML Trainer — evaluation: accuracy=%.3f, precision(1)=%.3f, recall(1)=%.3f",
        accuracy, precision_1, recall_1,
    )

    # ── 7. Feature importance ────────────────────────────────
    importance = model.feature_importances_
    feature_names = _get_feature_names(preprocessor)
    top_features = sorted(
        zip(feature_names, importance), key=lambda x: x[1], reverse=True,
    )[:10]
    logger.info("ML Trainer — top 10 features:")
    for name, imp in top_features:
        logger.info("  %-30s %.4f", name, imp)

    # ── 8. Save model, preprocessor, metadata ────────────────
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    import joblib
    joblib.dump(model, MODEL_DIR / "model.pkl")
    joblib.dump(preprocessor, MODEL_DIR / "preprocessor.pkl")

    metadata = {
        "training_date": datetime.now().isoformat(),
        "n_samples": len(df),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "scale_pos_weight": round(scale_pos_weight, 4),
        "accuracy": round(accuracy, 4),
        "precision_1": round(precision_1, 4),
        "recall_1": round(recall_1, 4),
        "features": ALL_FEATURES,
        "xgboost_params": {
            "n_estimators": 100,
            "learning_rate": 0.1,
            "max_depth": 4,
            "objective": "binary:logistic",
            "scale_pos_weight": round(scale_pos_weight, 4),
        },
    }

    with open(MODEL_DIR / "metadata.json", "w") as fh:
        json.dump(metadata, fh, indent=2)

    logger.info(
        "ML Trainer — model saved to %s (accuracy=%.3f, recall=%.3f)",
        MODEL_DIR, accuracy, recall_1,
    )
    return True


def _load_feedback(engine) -> pd.DataFrame | None:
    """
    Load alerts with feedback from the database.

    Uses the same feature columns as the Prioritizer so that the model
    trains on exactly the data it will see at inference time.
    """
    query = text(
        """
        SELECT tipo_alerta, bloque, provincia, perfil_cliente,
               potencial_h, impacto_estimado, urgencia_dias,
               ratio_promiscuidad, dias_desde_ultima_compra,
               freq_media_dias, n_compras_hist, feedback
        FROM alertas
        WHERE feedback IS NOT NULL
        """
    )
    try:
        df = pd.read_sql(query, engine)
        return df
    except Exception:
        logger.error("ML Trainer — failed to load feedback data", exc_info=True)
        return None


def _prepare_features(df: pd.DataFrame):
    """
    Build feature matrix and target vector from feedback data.

    Returns
    -------
    X : np.ndarray, y : pd.Series, preprocessor : ColumnTransformer
    """
    available = [c for c in ALL_FEATURES if c in df.columns]
    missing = set(ALL_FEATURES) - set(available)
    if missing:
        logger.warning("ML Trainer — missing feature columns: %s", missing)

    df = df.dropna(subset=["feedback"]).copy()
    df["feedback"] = df["feedback"].astype(int)
    y = df["feedback"]

    X_raw = df[available].copy()

    for col in NUMERIC_FEATURES:
        if col in X_raw.columns:
            X_raw[col] = pd.to_numeric(X_raw[col], errors="coerce").fillna(0)

    for col in CATEGORICAL_FEATURES:
        if col in X_raw.columns:
            X_raw[col] = X_raw[col].astype(str).fillna("unknown")

    cat_cols = [c for c in CATEGORICAL_FEATURES if c in available]
    num_cols = [c for c in NUMERIC_FEATURES if c in available]

    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", StandardScaler(), num_cols),
        ],
    )

    try:
        X_transformed = preprocessor.fit_transform(X_raw)
        return X_transformed, y, preprocessor
    except Exception:
        logger.error("ML Trainer — feature preprocessing failed", exc_info=True)
        return None, None, None


def _get_feature_names(preprocessor: ColumnTransformer) -> list[str]:
    """Extract feature names from a fitted ColumnTransformer."""
    names = []
    for name, transformer, cols in preprocessor.transformers_:
        if name == "cat":
            if hasattr(transformer, "get_feature_names_out"):
                names.extend(transformer.get_feature_names_out(cols).tolist())
            else:
                names.extend(cols)
        elif name == "num":
            names.extend(cols)
    return names