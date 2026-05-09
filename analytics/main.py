#!/usr/bin/env python3
"""
Daily pipeline orchestrator — Smart Demand Signals.

Runs detection engines (commodity + technical), inserts alerts into
the ``alertas`` table, then prioritises them.  Scheduled to run at
startup and then every day at 20:00 (UTC).
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

# Ensure the project root (/app) is on sys.path so that
#   from analytics.src.engine_commodity import ...
# works inside the container (and from any directory outside it).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.src.engine_commodity import CommodityEngine  # noqa: E402
from analytics.src.engine_technical import TechnicalEngine  # noqa: E402
from analytics.src.ml_trainer import train_model  # noqa: E402
from analytics.src.prioritizer import Prioritizer  # noqa: E402
from analytics.utils.config import FECHA_HOY  # noqa: E402
from analytics.utils.db import get_engine  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")

SCHEDULE_HOUR = 20      # run daily at this hour
SCHEDULE_MINUTE = 0
DB_RETRY_DELAY = 3      # seconds between connection retries
DB_RETRY_MAX = 20       # max attempts before giving up


# ═══════════════════════════════════════════════════════════════
# Database helpers
# ═══════════════════════════════════════════════════════════════

def wait_for_db(engine, max_retries: int = DB_RETRY_MAX,
                delay: int = DB_RETRY_DELAY):
    """Block until the database accepts connections."""
    for attempt in range(1, max_retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection OK")
            return
        except Exception:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Could not reach database after {max_retries} attempts"
                )
            logger.warning(
                "DB not ready (attempt %d/%d), retrying in %ds …",
                attempt, max_retries, delay,
            )
            time.sleep(delay)


# ═══════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════

def run_pipeline(engine):
    """Execute detection → insert → prioritisation cycle once."""
    logger.info("=== Pipeline start ===")

    # ── Step 1: Detection ──────────────────────────────────────────
    commodity = CommodityEngine(engine=engine, fecha_ref=FECHA_HOY)
    technical = TechnicalEngine(engine=engine, fecha_ref=FECHA_HOY)

    alerts_c = commodity.run()
    alerts_t = technical.run()
    all_alerts = alerts_c + alerts_t

    logger.info("Total alerts generated: %d", len(all_alerts))

    if all_alerts:
        # Safety dedup within the same run
        df = pd.DataFrame(all_alerts)
        before = len(df)
        df = df.drop_duplicates(subset=["id_cliente", "familia"])
        if len(df) < before:
            logger.info("Dropped %d intra-run duplicates", before - len(df))

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                df.to_sql(
                    "alertas",
                    conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=500,
                )
                trans.commit()
                logger.info("Inserted %d alert(s) into alertas table", len(df))
            except Exception:
                trans.rollback()
                logger.exception("Insert failed — transaction rolled back")

    # ── Step 2: Prioritisation ──────────────────────────────────────
    prioritizer = Prioritizer(engine=engine)
    n_prio = prioritizer.run()
    if n_prio:
        logger.info("Prioritised %d alert(s)", n_prio)

    # ── Step 3: ML model training (nightly) ───────────────────────
    #   Train on accumulated delegate feedback so the model improves
    #   over time.  On the first run (no feedback yet) this will skip.
    #   The trained model is loaded by MLEngine in the next pipeline run.
    try:
        trained = train_model(engine)
        if trained:
            logger.info("ML model trained and saved for next run")
        else:
            logger.info("ML training skipped (insufficient feedback data)")
    except Exception:
        logger.warning("ML training failed (non-fatal)", exc_info=True)

    logger.info("=== Pipeline end ===")


# ═══════════════════════════════════════════════════════════════
# Scheduler
# ═══════════════════════════════════════════════════════════════

def _seconds_until(hour: int, minute: int) -> float:
    """Return seconds until the next occurrence of *hour*:*minute*."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

def main():
    logger.info("Analytics container starting — PID %d", __import__("os").getpid())
    engine = get_engine()
    wait_for_db(engine)

    # Immediate run so the frontend has data on first launch
    logger.info("Running initial pipeline on startup …")
    run_pipeline(engine)

    # Loop: wait until next 20:00, run again
    while True:
        wait = _seconds_until(SCHEDULE_HOUR, SCHEDULE_MINUTE)
        logger.info(
            "Next pipeline scheduled in %.1f h (today at %02d:%02d)",
            wait / 3600, SCHEDULE_HOUR, SCHEDULE_MINUTE,
        )
        time.sleep(wait)
        run_pipeline(engine)


if __name__ == "__main__":
    main()
