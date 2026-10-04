"""Deterministic, explainable dealer health scoring.

Everything in this module is a PROTOTYPE ASSUMPTION - REQUIRES HISTORICAL VALIDATION.
The AI layer never touches these numbers (system of record: Data -> KPI -> Score -> Risk).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Prototype assumption: component weights (sum to 1.0).
WEIGHTS = {
    "sales": 0.25,
    "growth": 0.15,
    "inventory": 0.15,
    "payment": 0.15,
    "service": 0.10,
    "complaints": 0.10,
    "market": 0.10,
}

COMPONENT_LABELS = {
    "sales": "Sales Achievement",
    "growth": "Sales Growth",
    "inventory": "Inventory Health",
    "payment": "Payment Health",
    "service": "Service Performance",
    "complaints": "Customer Complaints",
    "market": "Market Opportunity",
}

# Opportunity score, not a direct risk score (see Methodology page).
MARKET_SCORES = {"High": 100, "Medium": 70, "Low": 40}


@dataclass(frozen=True)
class ScoringConfig:
    """Classification thresholds (configurable from the sidebar)."""

    healthy_threshold: int = 70
    watch_threshold: int = 50


# ---------------------------------------------------------------------------
# Component mappings (0-100, higher = healthier)
# ---------------------------------------------------------------------------
def sales_score(achievement_pct) -> np.ndarray:
    v = np.asarray(achievement_pct, dtype=float)
    return np.select([v >= 110, v >= 100, v >= 90, v >= 80, v >= 70], [100, 90, 75, 60, 45], default=25).astype(float)


def growth_score(growth_pct) -> np.ndarray:
    v = np.asarray(growth_pct, dtype=float)
    return np.select([v >= 15, v >= 8, v >= 0, v >= -5, v >= -10], [100, 90, 75, 60, 40], default=20).astype(float)


def inventory_score(over_90_pct) -> np.ndarray:
    v = np.asarray(over_90_pct, dtype=float)
    return np.select([v < 5, v <= 10, v <= 15, v <= 25, v <= 35], [100, 90, 75, 55, 35], default=15).astype(float)


def payment_score(delay_days) -> np.ndarray:
    v = np.asarray(delay_days, dtype=float)
    return np.select([v <= 2, v <= 5, v <= 10, v <= 15, v <= 20], [100, 90, 70, 50, 30], default=10).astype(float)


def service_component(service_score_value) -> np.ndarray:
    return np.clip(np.asarray(service_score_value, dtype=float), 0, 100)


def complaint_cuts(df: pd.DataFrame) -> dict:
    """Network percentiles of complaint rate used for benchmark-based scoring."""
    rate = pd.to_numeric(df["complaint_rate"], errors="coerce").dropna()
    if rate.empty:
        return {"q25": 0.0, "q50": 0.0, "q75": 0.0, "q90": 0.0}
    return {f"q{p}": float(np.percentile(rate, p)) for p in (25, 50, 75, 90)}


def complaint_score(rate, cuts: dict) -> np.ndarray:
    v = np.asarray(rate, dtype=float)
    return np.select(
        [v <= cuts["q25"], v <= cuts["q50"], v <= cuts["q75"], v <= cuts["q90"]],
        [100, 80, 60, 35],
        default=15,
    ).astype(float)


def market_score(potential) -> np.ndarray:
    return pd.Series(potential).map(MARKET_SCORES).fillna(70).to_numpy(dtype=float)


# ---------------------------------------------------------------------------
def classify(health, cfg: ScoringConfig = ScoringConfig()) -> np.ndarray:
    h = np.asarray(health, dtype=float)
    return np.select([h >= cfg.healthy_threshold, h >= cfg.watch_threshold], ["Healthy", "Watch"], default="Critical")


def compute_scores(df: pd.DataFrame, cfg: ScoringConfig = ScoringConfig(), cuts: dict | None = None) -> pd.DataFrame:
    """Add component scores, health score, risk score and status to ``df``."""
    out = df.copy()
    out["sales_achievement_pct"] = out["monthly_sales"] / out["monthly_target"] * 100
    if "complaint_rate" not in out.columns or out["complaint_rate"].isna().all():
        out["complaint_rate"] = out["customer_complaints"] / out["monthly_sales"].clip(lower=1) * 100
    out["complaint_rate"] = out["complaint_rate"].fillna(
        out["customer_complaints"] / out["monthly_sales"].clip(lower=1) * 100
    )
    cuts = cuts or complaint_cuts(out)

    out["s_sales"] = sales_score(out["sales_achievement_pct"])
    out["s_growth"] = growth_score(out["sales_growth_pct"])
    out["s_inventory"] = inventory_score(out["inventory_over_90_days_pct"])
    out["s_payment"] = payment_score(out["payment_delay_days"])
    out["s_service"] = service_component(out["service_score"])
    out["s_complaints"] = complaint_score(out["complaint_rate"], cuts)
    out["s_market"] = market_score(out["market_potential"])

    raw = sum(WEIGHTS[k] * out[f"s_{k}"] for k in WEIGHTS)
    out["health_score"] = np.floor(raw + 0.5).astype(int)  # round half up
    out["risk_score"] = 100 - out["health_score"]
    out["status"] = classify(out["health_score"], cfg)
    # Commercial performance (sales achievement + momentum), x-axis of the risk/performance matrix.
    out["performance_score"] = (
        (WEIGHTS["sales"] * out["s_sales"] + WEIGHTS["growth"] * out["s_growth"])
        / (WEIGHTS["sales"] + WEIGHTS["growth"])
    ).round(1)
    return out
