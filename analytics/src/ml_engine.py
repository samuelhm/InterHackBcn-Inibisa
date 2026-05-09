"""
ML Engine — Smart Demand Signals
=================================

Stub module for machine-learning inference.  Currently returns 0 for every
alert because no model has been trained yet.

When a trained model exists at ``analytics/models/``, this module will:

1.  Load the model on first call (lazy init).
2.  Fetch the alert's features from the database.
3.  Predict ``score_conversion`` (probability of positive feedback).
4.  Return the score so the prioritizer can integrate it.

The score contributes up to 40 points (20 % of 200) to the final priority.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"


class MLEngine:
    """
    Machine-learning inference engine.

    In its current state it always returns ``0.0`` (no model trained).
    When Phase 10 is implemented the model will be loaded from
    ``MODEL_DIR`` and used for prediction.
    """

    def __init__(self):
        self._model = None

    def get_score(self, alert_id: str) -> float:
        """
        Return the ML-predicted conversion probability for an alert.

        Currently returns 0.0 (no model trained).
        When implemented, the score will be between 0 and 1.
        """
        if self._model is None:
            return 0.0
        # Future: model.predict(features) → score_conversion
        return 0.0

    def load_model(self, path: Path | None = None):
        """
        Attempt to load a trained model from disk.

        If no model file is found, ``self._model`` remains None and
        ``get_score`` will continue to return 0.0.
        """
        model_path = path or MODEL_DIR / "model.pkl"
        if not model_path.exists():
            logger.info("No trained model found at %s — ML score will be 0", model_path)
            return
        # Future: import joblib / pickle and load
        # self._model = joblib.load(model_path)
        logger.info("Loaded model from %s", model_path)