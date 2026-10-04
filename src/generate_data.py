"""Synthetic dealer dataset generator (pattern-based, not purely random).

Run:  python -m src.generate_data
All data is SYNTHETIC / DEMONSTRATION data.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .scoring import compute_scores

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "dealers.csv"

REGION_CITIES = {
    "North": ["Delhi", "Gurugram", "Chandigarh", "Lucknow", "Jaipur"],
    "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi", "Coimbatore"],
    "East": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati"],
    "West": ["Mumbai", "Pune", "Ahmedabad", "Surat", "Nagpur"],
    "Central": ["Bhopal", "Indore", "Raipur", "Jabalpur"],
}
CITY_REGION = {c: r for r, cs in REGION_CITIES.items() for c in cs}
SUFFIXES = ["Central", "Prime", "Star", "Royal", "Metro", "Elite", "Crown", "Apex", "Heritage", "Premier"]
REGION_MARKET_GROWTH = {"North": 6.0, "South": 7.0, "East": 4.0, "West": 5.0, "Central": 3.0}
SIZE_TARGETS = {"Small": (40, 70), "Medium": (70, 120), "Large": (120, 200)}

# Handcrafted demonstration dealers (identity + metrics). Sales are derived from target * achievement.
FIXED = {
    "D014": dict(  # DEMO dealer: critical despite a high-potential market
        dealer_name="Mumbai Central Motors", city="Mumbai", dealer_size="Large", years=12, market_potential="High",
        target=150, ach=62, growth=-14, inv=31, pay=18, service=68, complaints=42, cchange=34,
        share=5.1, conv=9.5, tier="critical",
    ),
    "D027": dict(  # Hidden risk: looks healthy on sales
        dealer_name="Pune Prime Motors", city="Pune", dealer_size="Medium", years=9, market_potential="Medium",
        target=90, ach=108, growth=11, inv=29, pay=17, service=79, complaints=29, cchange=38,
        share=8.6, conv=17.5, tier="watch",
    ),
    "D041": dict(  # Edge case 1: high sales but risky
        dealer_name="Ahmedabad Elite Motors", city="Ahmedabad", dealer_size="Large", years=15, market_potential="Medium",
        target=120, ach=110, growth=12, inv=35, pay=20, service=78, complaints=44, cchange=30,
        share=9.9, conv=18.0, tier="watch",
    ),
    "D058": dict(  # Edge case 2: low sales but healthy (growth opportunity)
        dealer_name="Bengaluru Metro Motors", city="Bengaluru", dealer_size="Medium", years=4, market_potential="High",
        target=100, ach=85, growth=9, inv=4, pay=0.5, service=86, complaints=9, cchange=-10,
        share=7.5, conv=19.0, tier="healthy",
    ),
    "D063": dict(  # Edge case 3: high potential + declining performance, moderate operations
        dealer_name="Indore Royal Motors", city="Indore", dealer_size="Large", years=7, market_potential="High",
        target=140, ach=78, growth=-6, inv=14, pay=6, service=78, complaints=28, cchange=8,
        share=4.2, conv=11.0, tier="watch",
    ),
    "D077": dict(  # Edge case 4: operationally healthy but sales weak
        dealer_name="Jaipur Star Motors", city="Jaipur", dealer_size="Small", years=6, market_potential="Medium",
        target=60, ach=78, growth=3, inv=6, pay=1, service=88, complaints=4, cchange=-5,
        share=6.1, conv=17.0, tier="healthy",
    ),
}

WATCH_SUBTYPES = ["hidden"] * 3 + ["inventory"] * 5 + ["payment"] * 4 + ["complaints"] * 4 + ["sales"] * 4 + ["mixed"] * 4


def _u(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def _draw_metrics(rng, tier: str, sub: str) -> dict:
    """Draw operating metrics with realistic co-movement for a tier/archetype."""
    if tier == "critical":
        m = dict(ach=_u(rng, 48, 74), growth=_u(rng, -22, -7), inv=_u(rng, 24, 46), pay=_u(rng, 12, 30),
                 service=_u(rng, 52, 74), rate=_u(rng, 24, 48), cchange=_u(rng, 10, 45))
        mp_p = [0.4, 0.4, 0.2]
    elif tier == "watch":
        m = dict(ach=_u(rng, 80, 95), growth=_u(rng, -8, 4), inv=_u(rng, 10, 22), pay=_u(rng, 3, 11),
                 service=_u(rng, 72, 84), rate=_u(rng, 14, 28), cchange=_u(rng, -5, 25))
        mp_p = [0.3, 0.45, 0.25]
        if sub == "hidden":
            m.update(ach=_u(rng, 100, 112), growth=_u(rng, 3, 13), rate=_u(rng, 24, 40), cchange=_u(rng, 22, 45))
            if rng.random() < 0.5:
                m.update(inv=_u(rng, 27, 36), pay=_u(rng, 8, 14))
            else:
                m.update(pay=_u(rng, 16, 21), inv=_u(rng, 12, 20))
        elif sub == "inventory":
            m.update(inv=_u(rng, 24, 34), growth=_u(rng, -6, 3))
        elif sub == "payment":
            m.update(pay=_u(rng, 13, 19), ach=_u(rng, 85, 98))
        elif sub == "complaints":
            m.update(rate=_u(rng, 30, 42), service=_u(rng, 66, 76), cchange=_u(rng, 15, 40))
        elif sub == "sales":
            m.update(ach=_u(rng, 70, 84), growth=_u(rng, -9, -2))
    else:  # healthy
        m = dict(ach=_u(rng, 94, 116), growth=_u(rng, 1, 16), inv=_u(rng, 2, 12), pay=_u(rng, 0, 5),
                 service=_u(rng, 82, 95), rate=_u(rng, 6, 16), cchange=_u(rng, -30, 8))
        mp_p = [0.3, 0.45, 0.25]
    m["market_potential"] = str(rng.choice(["High", "Medium", "Low"], p=mp_p))
    return m


def _identity(rng, used: set[str]) -> dict:
    cities = list(CITY_REGION)
    for _ in range(200):
        city = str(rng.choice(cities))
        suffix = str(rng.choice(SUFFIXES))
        name = f"{city} {suffix} Motors"
        if name not in used:
            used.add(name)
            break
    size = str(rng.choice(["Small", "Medium", "Large"], p=[0.3, 0.45, 0.25]))
    return dict(dealer_name=name, city=city, dealer_size=size, years=int(rng.integers(1, 26)))


def _assemble(did: str, ident: dict, m: dict, rng) -> dict:
    region = CITY_REGION[ident["city"]]
    if "target" in m:
        target = float(m["target"])
    else:
        lo, hi = SIZE_TARGETS[ident["dealer_size"]]
        target = float(int(rng.integers(lo, hi + 1)))
    sales = int(round(target * m["ach"] / 100))
    complaints = int(m["complaints"]) if "complaints" in m else max(1, int(round(m["rate"] * sales / 100)))
    rate = round(complaints / max(sales, 1) * 100, 1)
    inv_units = int(round(sales * (1.2 + float(rng.uniform(0, 0.8))) * (1 + m["inv"] / 60)))
    tier_conv = {"critical": (8, 14), "watch": (12, 19), "healthy": (16, 26)}[m["tier"]]
    conv = m.get("conv", round(_u(rng, *tier_conv), 1))
    share_base = {"High": (9, 14), "Medium": (6, 10), "Low": (3, 7)}[m["market_potential"]]
    share = m.get("share", round(_u(rng, *share_base) * min(max(m["ach"] / 95, 0.6), 1.15), 1))
    service = round(m["service"], 0)
    csat = round(min(98, max(40, 45 + service * 0.5 + float(rng.normal(0, 3)))), 0)
    return dict(
        dealer_id=did,
        dealer_name=ident["dealer_name"],
        region=region,
        city=ident["city"],
        market_potential=m["market_potential"],
        dealer_size=ident["dealer_size"],
        years_with_manufacturer=ident["years"],
        monthly_sales=sales,
        monthly_target=int(target),
        sales_growth_pct=round(m["growth"], 1),
        inventory_units=inv_units,
        inventory_over_90_days_pct=round(m["inv"], 1),
        payment_delay_days=round(m["pay"], 1),
        service_score=service,
        customer_complaints=complaints,
        complaint_rate=rate,
        complaints_change_pct=round(m["cchange"], 1),
        customer_satisfaction_score=csat,
        lead_conversion_pct=conv,
        market_share_pct=share,
        regional_market_growth_pct=round(REGION_MARKET_GROWTH[region] + float(rng.normal(0, 0.6)), 1),
    )


def generate(seed: int = 42) -> pd.DataFrame:
    """Build the 100-dealer synthetic dataset (12 critical / 27 watch / 61 healthy)."""
    rng = np.random.default_rng(seed)
    ids = [f"D{i:03d}" for i in range(1, 101)]
    free = [i for i in ids if i not in FIXED]
    rng.shuffle(free)
    plan: dict[str, tuple[str, str]] = {did: (f["tier"], "fixed") for did, f in FIXED.items()}
    n_crit, n_watch = 11, 24
    for did in free[:n_crit]:
        plan[did] = ("critical", "base")
    for did, sub in zip(free[n_crit:n_crit + n_watch], rng.permutation(WATCH_SUBTYPES)):
        plan[did] = ("watch", str(sub))
    for did in free[n_crit + n_watch:]:
        plan[did] = ("healthy", "base")

    used_names = {f["dealer_name"] for f in FIXED.values()}
    idents, metrics = {}, {}
    for did in ids:
        tier, sub = plan[did]
        if did in FIXED:
            f = FIXED[did]
            idents[did] = dict(dealer_name=f["dealer_name"], city=f["city"], dealer_size=f["dealer_size"], years=f["years"])
            metrics[did] = dict(f)
        else:
            idents[did] = _identity(rng, used_names)
            m = _draw_metrics(rng, tier, sub)
            m["tier"] = tier
            metrics[did] = m

    target_status = {"critical": "Critical", "watch": "Watch", "healthy": "Healthy"}
    scored = None
    for _ in range(60):
        # per-dealer seeded RNG keeps re-assembly deterministic while metrics are re-drawn
        rows = [_assemble(d, idents[d], metrics[d], np.random.default_rng(seed * 1000 + int(d[1:]))) for d in ids]
        df = pd.DataFrame(rows)
        scored = compute_scores(df)
        bad = []
        for d, st_, hs in zip(scored["dealer_id"], scored["status"], scored["health_score"]):
            tier, sub = plan[d]
            if st_ != target_status[tier]:
                bad.append(d)
            elif tier == "critical" and d != "D014" and hs < 38:
                bad.append(d)  # keep the demo dealer the most urgent
        bad = [d for d in bad if d not in FIXED]
        if not bad:
            break
        for d in bad:
            tier, sub = plan[d]
            m = _draw_metrics(rng, tier, sub)
            m["tier"] = tier
            metrics[d] = m

    # Previous-period health score: critical dealers deteriorated, healthy ones were stable.
    prev = []
    for st_, hs in zip(scored["status"], scored["health_score"]):
        delta = {"Critical": _u(rng, 6, 18), "Watch": _u(rng, -3, 10), "Healthy": _u(rng, -6, 4)}[st_]
        prev.append(int(np.clip(round(hs + delta), 0, 100)))
    df["previous_health_score"] = prev
    return df


def main() -> None:
    df = generate()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_PATH, index=False)
    scored = compute_scores(df)
    print(f"Wrote {len(df)} dealers to {DATA_PATH}")
    print(scored["status"].value_counts().to_string())


if __name__ == "__main__":
    main()
