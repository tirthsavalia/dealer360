"""Data validation and normalisation. Never raises raw tracebacks to the UI."""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = [
    "dealer_id",
    "dealer_name",
    "region",
    "city",
    "market_potential",
    "monthly_sales",
    "monthly_target",
    "sales_growth_pct",
    "inventory_over_90_days_pct",
    "payment_delay_days",
    "service_score",
    "customer_complaints",
]

OPTIONAL_COLUMNS = [
    "dealer_size",
    "years_with_manufacturer",
    "inventory_units",
    "complaint_rate",
    "complaints_change_pct",
    "customer_satisfaction_score",
    "lead_conversion_pct",
    "market_share_pct",
    "regional_market_growth_pct",
    "previous_health_score",
]

NUMERIC_COLUMNS = [
    "monthly_sales",
    "monthly_target",
    "sales_growth_pct",
    "inventory_over_90_days_pct",
    "payment_delay_days",
    "service_score",
    "customer_complaints",
    "years_with_manufacturer",
    "inventory_units",
    "complaint_rate",
    "complaints_change_pct",
    "customer_satisfaction_score",
    "lead_conversion_pct",
    "market_share_pct",
    "regional_market_growth_pct",
    "previous_health_score",
]

VALID_POTENTIAL = {"high": "High", "medium": "Medium", "med": "Medium", "low": "Low"}


class DataValidationError(Exception):
    """User-facing data problem (message is safe to display)."""


def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in out.columns]
    return out


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Validate and clean a dealer table.

    Returns ``(clean_df, warnings)``. Raises ``DataValidationError`` for blocking problems
    (empty data, missing required columns, nothing usable after cleaning).
    """
    if df is None or len(df) == 0:
        raise DataValidationError("The dataset is empty. Please provide at least one dealer row.")

    out = normalise_columns(df)
    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise DataValidationError(
            "Missing required column(s): " + ", ".join(missing) + ". "
            "Required columns are: " + ", ".join(REQUIRED_COLUMNS) + "."
        )

    warnings: list[str] = []
    n0 = len(out)

    # Text fields
    for col in ("dealer_id", "dealer_name", "region", "city"):
        out[col] = out[col].astype("string").str.strip()
    out["market_potential"] = out["market_potential"].astype("string").str.strip()

    # Numeric coercion
    for col in NUMERIC_COLUMNS:
        if col in out.columns:
            before_null = out[col].isna()
            out[col] = pd.to_numeric(out[col], errors="coerce")
            bad = int((out[col].isna() & ~before_null).sum())
            if bad:
                warnings.append(f"{bad} non-numeric value(s) in '{col}' were treated as missing.")

    # Missing required values -> drop
    req_missing = out[REQUIRED_COLUMNS].isna().any(axis=1) | (out["dealer_id"] == "")
    if req_missing.any():
        warnings.append(f"{int(req_missing.sum())} row(s) dropped because required values were missing.")
        out = out[~req_missing]

    # Duplicate IDs -> keep first
    dup = out["dealer_id"].duplicated(keep="first")
    if dup.any():
        warnings.append(f"{int(dup.sum())} duplicate dealer ID(s) found - kept the first occurrence of each.")
        out = out[~dup]

    # Negative sales / zero target -> drop
    bad_sales = (out["monthly_sales"] < 0) | (out["monthly_target"] <= 0)
    if bad_sales.any():
        warnings.append(
            f"{int(bad_sales.sum())} row(s) dropped because of negative sales or a zero/negative target."
        )
        out = out[~bad_sales]

    # Market potential
    norm = out["market_potential"].str.lower().map(VALID_POTENTIAL)
    invalid_mp = norm.isna()
    if invalid_mp.any():
        warnings.append(
            f"{int(invalid_mp.sum())} invalid market_potential value(s) defaulted to 'Medium' "
            "(valid: High / Medium / Low)."
        )
    out["market_potential"] = norm.fillna("Medium").astype(str)

    # Range checks (clip + warn)
    def _clip(col: str, lo: float | None, hi: float | None, label: str) -> None:
        if col not in out.columns:
            return
        s = out[col]
        mask = pd.Series(False, index=out.index)
        if lo is not None:
            mask |= s < lo
        if hi is not None:
            mask |= s > hi
        mask &= s.notna()
        if mask.any():
            warnings.append(f"{int(mask.sum())} value(s) in '{col}' outside {label} were clipped.")
            out[col] = s.clip(lower=lo, upper=hi)

    _clip("inventory_over_90_days_pct", 0, 100, "0-100%")
    _clip("service_score", 0, 100, "0-100")
    _clip("payment_delay_days", 0, None, ">= 0")
    _clip("customer_complaints", 0, None, ">= 0")
    _clip("lead_conversion_pct", 0, 100, "0-100%")
    _clip("customer_satisfaction_score", 0, 100, "0-100")
    _clip("previous_health_score", 0, 100, "0-100")

    if len(out) == 0:
        raise DataValidationError("No usable dealer rows remain after validation.")

    # Optional columns: make sure they exist so the UI never crashes
    for col in OPTIONAL_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    out["dealer_size"] = out["dealer_size"].fillna("N/A")

    dropped = n0 - len(out)
    if dropped:
        warnings.append(f"{dropped} of {n0} row(s) were removed in total; {len(out)} dealers analysed.")

    # Plain python strings for clean display
    for col in ("dealer_id", "dealer_name", "region", "city", "dealer_size"):
        out[col] = out[col].astype(str)

    return out.reset_index(drop=True), warnings
