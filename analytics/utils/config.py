"""
Shared configuration for Smart Demand Signals analytics.

All priority weights are expressed as contributions to the 0–200 scale.
Total max score breakdown:

    Component         Max Points   Weight    Rationale
    ─────────────────────────────────────────────────────────
    tipo_alerta            60       30%      Alert type is the strongest signal
    potencial_h            35       17.5%    Higher potential → more revenue at stake
    impacto_estimado       25       12.5%    Missed revenue → concrete opportunity
    urgencia               20       10%      Time sensitivity
    perfil_cliente         20       10%      Client loyalty profile matters
    ml_score               40       20%      ML prediction (0 until implemented)
    ─────────────────────────────────────────────────────────
    TOTAL                 200       100%

Note on ML weight (40 pts / 20%):
    Currently `score_conversion` returns 0 because the ML model is not yet
    implemented, so this factor contributes nothing for now.  When ML is
    deployed it will be the second-most important factor after alert type,
    capturing patterns learned from real delegate feedback.
"""

# ═══════════════════════════════════════════════════════════════
# Priority weights (sum = 1.0, mapped to 0–200)
# ═══════════════════════════════════════════════════════════════

PRIORITY_WEIGHTS = {
    "tipo_alerta": 0.30,
    "potencial_h": 0.175,
    "impacto_estimado": 0.125,
    "urgencia": 0.10,
    "perfil_cliente": 0.10,
    "ml_score": 0.20,
}

# Base score per alert type (fraction of tipo_alerta weight)
# ventana_captura = 1.00 * 0.30 * 200 = 60 points
# reposicion      = 0.83 * 0.30 * 200 = 50 points
# riesgo_fuga     = 0.67 * 0.30 * 200 = 40 points
# cliente_perdido = 0.50 * 0.30 * 200 = 30 points
ALERT_TYPE_BASE_SCORES = {
    "ventana_captura": 1.00,
    "reposicion": 0.83,
    "riesgo_fuga": 0.67,
    "cliente_perdido": 0.50,
}

# ═══════════════════════════════════════════════════════════════
# Client profile thresholds (based on ratio_promiscuidad)
# ═══════════════════════════════════════════════════════════════
#
# ratio_promiscuidad = 1 - (compras_12m / potencial_h)
#   0.0  → 100 % of potential already captured by Inibsa
#   1.0  →   0 % captured, everything goes to competitors

CLIENT_PROFILE = {
    "leal_max": 0.30,       # ratio < 0.30 → >70 % bought from us
    "promiscuo_max": 0.70,  # 0.30 ≤ ratio ≤ 0.70 → 30–70 % from us
    # > 0.70 → marginal
}

# Profile priority multipliers (for perfil_cliente factor)
PROFILE_MULTIPLIERS = {
    "leal": 1.00,
    "promiscuo": 0.80,
    "marginal": 0.50,
}

# ═══════════════════════════════════════════════════════════════
# Detection thresholds — Commodities
# ═══════════════════════════════════════════════════════════════

COMMODITY = {
    "ventana_captura": {
        "min_promiscuidad": 0.30,
        "cycle_ratio": 0.7,
        "max_inactive_days": 180,
    },
    "reposicion": {
        "max_promiscuidad": 0.30,
        "cycle_ratio": 0.6,
        "max_inactive_days": 90,
    },
    "caida_frecuencia": {
        "ratio": 1.5,
        "min_compras": 3,
    },
    "caida_volumen": {
        "ratio": 0.5,
        "min_compras": 3,
    },
    "ausencia": {
        "min_dias": 30,
        "freq_multiplier": 2.0,
    },
    "anomalia": {
        "z_score": 2.0,
        "min_compras": 5,
    },
    "perdido_dias": 90,
}

# ═══════════════════════════════════════════════════════════════
# Detection thresholds — Technical
# ═══════════════════════════════════════════════════════════════

TECHNICAL = {
    "reposicion": {
        "cycle_ratio": 0.9,
        "max_inactive_days": 180,
    },
    "caida_frecuencia": {
        "ratio": 1.3,
        "min_compras": 3,
    },
    "caida_volumen": {
        "ratio": 0.6,
        "min_compras": 3,
    },
    "ausencia": {
        "min_dias": 45,
        "freq_multiplier": 1.5,
    },
    "anomalia": {
        "z_score": 2.0,
        "min_compras": 5,
    },
    "perdido_dias": 90,
    "noise_filter": {
        "cv_threshold": 1.0,
        "min_patterns_for_noisy": 2,
    },
}

# ═══════════════════════════════════════════════════════════════
# Reference date for the hackathon
# ═══════════════════════════════════════════════════════════════

import os
from datetime import datetime

FECHA_HOY = datetime.fromisoformat(
    os.getenv("FECHA_HOY", "2026-05-09")
)

# ═══════════════════════════════════════════════════════════════
# Deduplication
# ═══════════════════════════════════════════════════════════════

DEDUP_WINDOW_DAYS = 7  # Skip creation if a pending alert exists
                       # for the same client-family within this window
