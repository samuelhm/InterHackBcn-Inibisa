"""
Shared metric-computation functions used by both engines.

All functions are pure (no side-effects, no I/O) and receive raw data,
returning computed scalar values.
"""

import numpy as np
import pandas as pd


# ── Frequency metrics ──────────────────────────────────────

def compute_frequency_metrics(df: pd.DataFrame) -> dict:
    """
    Compute purchase-frequency statistics.

    Expects df sorted by 'fecha' ascending with a 'gap' column
    (days between consecutive purchases).

    Returns dict with keys: freq_media, freq_std, ultimo_gap, n_compras
    """
    gaps = df["gap"].dropna()

    if len(gaps) == 0:
        return {"freq_media": 0.0, "freq_std": 0.0, "ultimo_gap": 0, "n_compras": len(df)}

    return {
        "freq_media": float(gaps.mean()),
        "freq_std": float(gaps.std()) if len(gaps) > 1 else 0.0,
        "ultimo_gap": int(gaps.iloc[-1]),
        "n_compras": len(df),
    }


# ── Volume metrics ─────────────────────────────────────────

def compute_volume_metrics(df: pd.DataFrame, col: str = "importe") -> dict:
    """
    Compute purchase-volume statistics.

    Returns dict with keys: vol_medio, vol_std, ultimo_volumen,
    total_12m, cv (coefficient of variation).
    """
    valores = df[col].astype(float)

    if len(valores) == 0:
        return {"vol_medio": 0.0, "vol_std": 0.0, "ultimo_volumen": 0.0,
                "total_12m": 0.0, "cv": 0.0}

    vol_medio = float(valores.mean())
    vol_std = float(valores.std()) if len(valores) > 1 else 0.0
    cv = round(vol_std / vol_medio, 4) if vol_medio > 0 else 0.0

    return {
        "vol_medio": vol_medio,
        "vol_std": vol_std,
        "ultimo_volumen": float(valores.iloc[-1]),
        "total_12m": float(valores.sum()),
        "cv": cv,
    }


# ── Promiscuity & impact ───────────────────────────────────

def compute_promiscuity_ratio(total_comprado_12m: float,
                              potencial_h: float) -> float:
    """
    Proportion of a clinic's potential that goes to competitors.

        1 - (what_they_buy_from_us / what_they_could_buy)

    Returns a value clamped to [0, 1].
      0 = 100 % loyal (buys everything from us)
      1 =   0 % captured (everything goes to competitors)
    """
    if potencial_h is None or potencial_h <= 0:
        return 0.0
    if total_comprado_12m is None or total_comprado_12m < 0:
        total_comprado_12m = 0.0
    ratio = 1.0 - (total_comprado_12m / potencial_h)
    return max(0.0, min(1.0, ratio))


def compute_impacto_estimado(potencial_h: float,
                             total_comprado_12m: float) -> float:
    """
    Estimated lost revenue (€) — money left on the table.

        impacto = potencial_h - total_comprado_12m

    Clamped to ≥ 0.
    """
    if potencial_h is None or potencial_h <= 0:
        return 0.0
    if total_comprado_12m is None:
        total_comprado_12m = 0.0
    return max(0.0, potencial_h - total_comprado_12m)


# ── Urgency ────────────────────────────────────────────────

def compute_urgencia_dias(freq_media: float,
                          dias_desde_ultima: float) -> int:
    """
    Days of margin before the expected next purchase.

        urgencia = freq_media - dias_desde_ultima

    Negative → overdue (should have bought already)
    Positive → still within the expected cycle

    Clamped to [1, 90] per database constraint.
    """
    if freq_media <= 0:
        # Without a recognizable cycle, use a default window
        return max(1, min(90, max(1, 30 - int(dias_desde_ultima))))
    raw = int(round(freq_media - dias_desde_ultima))
    return max(1, min(90, max(1, raw)))


# ── Statistical anomaly ────────────────────────────────────

def compute_z_score(value: float, mean: float, std: float) -> float:
    """Z-score: how many standard deviations 'value' is from 'mean'."""
    if std is None or std <= 0:
        return 0.0
    return abs(value - mean) / std


# ── Client profile classification ──────────────────────────

def classify_client_profile(ratio_promiscuidad: float) -> str:
    """
    Classify a client based on their promiscuity ratio.

        leal      : ratio < 0.30  → buys >70 % of potential from us
        promiscuo : 0.30 ≤ ratio ≤ 0.70
        marginal  : ratio > 0.70  → buys <30 % from us
    """
    if ratio_promiscuidad < 0.30:
        return "leal"
    if ratio_promiscuidad <= 0.70:
        return "promiscuo"
    return "marginal"


# ── Coefficient of variation ───────────────────────────────

def compute_cv(series: pd.Series) -> float:
    """Coefficient of variation = std / mean. Measures relative variability."""
    mean = series.mean()
    if pd.isna(mean) or mean == 0:
        return 0.0
    std = series.std()
    return float(std / mean) if not pd.isna(std) and std > 0 else 0.0
