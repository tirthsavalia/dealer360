"""Risk drivers, emerging-risk flags, hidden-risk detection, sustainability and priority."""
from __future__ import annotations

import pandas as pd

from .recommendations import SEV_RANK, build_actions
from .scoring import WEIGHTS, ScoringConfig, complaint_cuts, compute_scores

# Manufacturer benchmarks (prototype assumptions).
BENCHMARKS = {
    "sales_achievement_pct": 95.0,
    "sales_growth_pct": 8.0,
    "inventory_over_90_days_pct": 10.0,
    "payment_delay_days": 5.0,
    "service_score": 85.0,
    "customer_complaints": 15.0,
}

REG_COLS = [
    "sales_achievement_pct",
    "sales_growth_pct",
    "inventory_over_90_days_pct",
    "payment_delay_days",
    "service_score",
    "customer_complaints",
    "complaint_rate",
]

PRIORITY_LABELS = {
    "P0": "P0 - Immediate",
    "P1": "P1 - Within 7 days",
    "P2": "P2 - Monitor",
    "-": "No action",
}

SUSTAINABILITY_TEXT = {
    "Sustainable Growth": "Strong current performance, positive momentum and healthy operations.",
    "Stable": "Adequate performance with no major emerging risk.",
    "Watch": "Some indicators are deteriorating and need monitoring.",
    "At Risk": "Multiple indicators - or a hidden risk behind good sales - suggest future trouble.",
    "Critical": "Multiple severe indicators require immediate management intervention.",
}


def _sev_lower(v, high, med, low):
    return "High" if v < high else "Medium" if v < med else "Low" if v < low else None


def _sev_upper(v, high, med, low):
    return "High" if v > high else "Medium" if v > med else "Low" if v > low else None


def _max_sev(*sevs):
    sevs = [s for s in sevs if s]
    return max(sevs, key=lambda s: SEV_RANK[s]) if sevs else None


def build_drivers(row, cuts: dict, reg) -> list[dict]:
    """Rank the metrics that hurt the dealer's health most (severity, then score points lost)."""
    drivers: list[dict] = []

    g, a = row["sales_growth_pct"], row["sales_achievement_pct"]
    sg, sa = _sev_lower(g, -10, -5, 0), _sev_lower(a, 70, 85, 95)
    sev = _max_sev(sg, sa)
    if sev:
        decline_led = bool(sg) and SEV_RANK[sg] >= SEV_RANK.get(sa, 0)
        drivers.append(
            {
                "key": "sales",
                "driver": "Declining sales" if decline_led else "Sales shortfall vs target",
                "severity": sev,
                "value": f"{g:+.0f}% growth, {a:.0f}% of target",
                "benchmark": f"Region {reg['sales_growth_pct']:+.0f}% growth, {reg['sales_achievement_pct']:.0f}% of target",
                "detail": f"Sales growth {g:+.0f}% (regional {reg['sales_growth_pct']:+.0f}%); achievement {a:.0f}% of target (regional {reg['sales_achievement_pct']:.0f}%)",
                "points_lost": WEIGHTS["sales"] * (100 - row["s_sales"]) + WEIGHTS["growth"] * (100 - row["s_growth"]),
            }
        )

    inv = row["inventory_over_90_days_pct"]
    sev = _sev_upper(inv, 25, 15, 10)
    if sev:
        drivers.append(
            {
                "key": "inventory",
                "driver": "Ageing inventory",
                "severity": sev,
                "value": f"{inv:.0f}%",
                "benchmark": f"Region {reg['inventory_over_90_days_pct']:.0f}%",
                "detail": f"{inv:.0f}% of inventory is older than 90 days (regional benchmark {reg['inventory_over_90_days_pct']:.0f}%)",
                "points_lost": WEIGHTS["inventory"] * (100 - row["s_inventory"]),
            }
        )

    pay = row["payment_delay_days"]
    sev = _sev_upper(pay, 15, 8, 5)
    if sev:
        drivers.append(
            {
                "key": "payment",
                "driver": "Payment delays",
                "severity": sev,
                "value": f"{pay:.0f} days",
                "benchmark": f"Region {reg['payment_delay_days']:.0f} days",
                "detail": f"Average payment delay is {pay:.0f} days (regional benchmark {reg['payment_delay_days']:.0f} days)",
                "points_lost": WEIGHTS["payment"] * (100 - row["s_payment"]),
            }
        )

    svc = row["service_score"]
    sev = _sev_lower(svc, 70, 78, 82)
    if sev:
        drivers.append(
            {
                "key": "service",
                "driver": "Weak service performance",
                "severity": sev,
                "value": f"{svc:.0f}/100",
                "benchmark": f"Region {reg['service_score']:.0f}/100",
                "detail": f"Service score {svc:.0f}/100 (regional benchmark {reg['service_score']:.0f})",
                "points_lost": WEIGHTS["service"] * (100 - row["s_service"]),
            }
        )

    rate = row["complaint_rate"]
    sev = "High" if rate > cuts["q90"] else "Medium" if rate > cuts["q75"] else None
    if sev:
        drivers.append(
            {
                "key": "complaints",
                "driver": "High customer complaints",
                "severity": sev,
                "value": f"{row['customer_complaints']:.0f} complaints ({rate:.0f} per 100 sold)",
                "benchmark": f"Region {reg['customer_complaints']:.0f} complaints",
                "detail": f"{row['customer_complaints']:.0f} complaints this month, {rate:.0f} per 100 vehicles sold (regional average {reg['customer_complaints']:.0f} complaints)",
                "points_lost": WEIGHTS["complaints"] * (100 - row["s_complaints"]),
            }
        )

    drivers.sort(key=lambda d: (-SEV_RANK[d["severity"]], -d["points_lost"]))
    return drivers


def emerging_flags(row, cuts: dict) -> list[str]:
    """Combination warnings. They do NOT change the score - they add explainability."""
    flags = []
    if row["sales_growth_pct"] < -10 and row["inventory_over_90_days_pct"] > 25:
        flags.append("Sales decline + inventory build-up")
    if row["payment_delay_days"] > 15 and row["health_score"] < 60:
        flags.append("Potential financial stress")
    if row["market_potential"] == "High" and row["sales_growth_pct"] < 0 and row["sales_achievement_pct"] < 85:
        flags.append("Untapped market opportunity")
    if row["complaint_rate"] > cuts["q90"] and row["service_score"] < 75:
        flags.append("Customer experience deterioration")
    return flags


def is_hidden_risk(row, cuts: dict) -> bool:
    """Looks healthy on sales (>=100% of target, positive growth) but operations are warning."""
    looks_good = row["sales_achievement_pct"] >= 100 and row["sales_growth_pct"] >= 0
    warning = (
        row["inventory_over_90_days_pct"] > 25
        or row["payment_delay_days"] > 15
        or row["complaint_rate"] > cuts["q75"]
        or (pd.notna(row.get("complaints_change_pct")) and row["complaints_change_pct"] > 25)
    )
    # need at least one hard operational flag, not complaints trend alone
    hard = row["inventory_over_90_days_pct"] > 25 or row["payment_delay_days"] > 15
    return bool(looks_good and warning and hard)


def is_growth_opportunity(row) -> bool:
    """Operationally healthy dealer with weak sales: growth support, not crisis intervention."""
    return bool(
        row["sales_achievement_pct"] < 90
        and row["sales_growth_pct"] > 0
        and row["inventory_over_90_days_pct"] <= 15
        and row["payment_delay_days"] <= 5
        and row["service_score"] >= 80
    )


def sustainability(row, n_high: int, n_med: int, flags: list[str], hidden: bool) -> str:
    status = row["status"]
    if status == "Critical":
        return "Critical"
    if hidden or (
        status == "Watch"
        and (n_high >= 2 or "Potential financial stress" in flags or "Sales decline + inventory build-up" in flags)
    ):
        return "At Risk"
    if status == "Watch":
        return "Watch"
    if row["sales_achievement_pct"] >= 100 and row["sales_growth_pct"] >= 8 and n_high == 0 and n_med == 0:
        return "Sustainable Growth"
    return "Stable"


def priority(row, n_high: int, n_med: int, drivers: list[dict], flags: list[str], hidden: bool) -> str:
    severe = (
        row["payment_delay_days"] > 20
        or row["inventory_over_90_days_pct"] > 35
        or row["sales_growth_pct"] < -15
        or row["sales_achievement_pct"] < 60
    )
    status = row["status"]
    if status == "Critical" and (row["health_score"] < 40 or n_high >= 2 or severe):
        return "P0"
    if severe or n_high >= 3:
        return "P0"
    if status == "Critical" or n_high >= 1 and status == "Watch" or n_med >= 2 and status != "Healthy":
        return "P1"
    informational = ("Untapped market opportunity", "Growth support opportunity")
    if hidden or [f for f in flags if f not in informational]:
        return "P1"
    if status == "Watch" or n_high or n_med or "Growth support opportunity" in flags:
        return "P2"
    return "-"


def analyze(df: pd.DataFrame, cfg: ScoringConfig = ScoringConfig()) -> pd.DataFrame:
    """Full pipeline: scores -> drivers -> flags -> sustainability -> priority -> actions."""
    scored = compute_scores(df, cfg)
    cuts = complaint_cuts(scored)
    reg_means = scored.groupby("region")[REG_COLS].mean()

    cols: dict[str, list] = {
        k: []
        for k in (
            "drivers", "flags", "n_high", "n_med", "primary_driver", "hidden_risk", "growth_opportunity",
            "sustainability", "priority_code", "priority_label", "actions",
        )
    }
    for _, row in scored.iterrows():
        reg = reg_means.loc[row["region"]]
        drivers = build_drivers(row, cuts, reg)
        flags = emerging_flags(row, cuts)
        hidden = is_hidden_risk(row, cuts)
        growth_opp = is_growth_opportunity(row)
        if hidden:
            flags.append("Hidden risk behind strong sales")
        if growth_opp:
            flags.append("Growth support opportunity")
        n_high = sum(d["severity"] == "High" for d in drivers)
        n_med = sum(d["severity"] == "Medium" for d in drivers)
        pr = priority(row, n_high, n_med, drivers, flags, hidden)
        cols["drivers"].append(drivers)
        cols["flags"].append(flags)
        cols["n_high"].append(n_high)
        cols["n_med"].append(n_med)
        cols["primary_driver"].append(drivers[0]["driver"] if drivers else "None")
        cols["hidden_risk"].append(hidden)
        cols["growth_opportunity"].append(growth_opp)
        cols["sustainability"].append(sustainability(row, n_high, n_med, flags, hidden))
        cols["priority_code"].append(pr)
        cols["priority_label"].append(PRIORITY_LABELS[pr])
        row_with_pr = row.copy()
        cols["actions"].append(build_actions(row_with_pr, drivers, flags, hidden, growth_opp, reg, cuts))

    for k, v in cols.items():
        scored[k] = v
    scored["priority_rank"] = scored["priority_code"].map({"P0": 0, "P1": 1, "P2": 2, "-": 3})
    return scored


def network_summary(df: pd.DataFrame, cuts: dict) -> dict[str, int]:
    """Network-level emerging indicators."""
    return {
        "Sales declining": int((df["sales_growth_pct"] < 0).sum()),
        "Inventory ageing": int((df["inventory_over_90_days_pct"] > 25).sum()),
        "Payment delays": int((df["payment_delay_days"] > 10).sum()),
        "High complaints": int((df["complaint_rate"] > cuts["q75"]).sum()),
        "Hidden market opportunity": int(((df["market_potential"] == "High") & (df["sales_achievement_pct"] < 85)).sum()),
    }


def peer_average(all_df: pd.DataFrame, row) -> tuple[pd.Series, str]:
    """Average of similar dealers (same size and market potential; falls back gracefully)."""
    cols = REG_COLS
    peers = all_df[(all_df["dealer_size"] == row["dealer_size"]) & (all_df["market_potential"] == row["market_potential"]) & (all_df["dealer_id"] != row["dealer_id"])]
    label = f"{row['dealer_size']} size, {row['market_potential']} potential"
    if len(peers) < 3:
        peers = all_df[(all_df["market_potential"] == row["market_potential"]) & (all_df["dealer_id"] != row["dealer_id"])]
        label = f"{row['market_potential']} potential"
    if len(peers) < 3:
        peers = all_df[all_df["dealer_id"] != row["dealer_id"]]
        label = "network"
    return peers[cols].mean(), label
