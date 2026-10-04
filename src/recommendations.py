"""Deterministic recommendation engine (always available; AI is only an enhancement)."""
from __future__ import annotations

SEV_RANK = {"High": 3, "Medium": 2, "Low": 1}

# category -> display order used as a tie-breaker (inventory/payment first, then sales ...)
CATEGORY_ORDER = {"inventory": 1, "payment": 2, "sales": 3, "complaints": 4, "service": 5, "market": 6, "hidden": 0, "growth": 7}

PLAYBOOK = {
    "inventory": {
        "area": "Inventory",
        "owner": "Regional Sales Manager",
        "High": ("Launch targeted inventory liquidation plan and review vehicle mix / order planning.", 7),
        "Medium": ("Review ageing stock and adjust order planning to stop further build-up.", 14),
    },
    "payment": {
        "area": "Payments",
        "owner": "Finance + Regional Manager",
        "High": ("Conduct payment recovery review and establish a payment resolution plan.", 7),
        "Medium": ("Agree a payment schedule and monitor outstanding dues weekly.", 14),
    },
    "sales": {
        "area": "Sales Recovery",
        "owner": "Dealer Principal + Sales Manager",
        "High": ("Investigate lead conversion, competitor activity, local demand changes and sales-team performance.", 14),
        "Medium": ("Review sales pipeline, lead follow-up and target-setting with the dealer.", 14),
    },
    "complaints": {
        "area": "Customer Complaints",
        "owner": "Customer Experience Lead + Dealer Principal",
        "High": ("Perform root-cause analysis of complaints and establish customer recovery actions.", 14),
        "Medium": ("Review complaint themes and set up customer follow-up calls.", 14),
    },
    "service": {
        "area": "Service Performance",
        "owner": "Regional Service Manager",
        "High": ("Conduct service operations review and identify capacity / training bottlenecks.", 14),
        "Medium": ("Review workshop KPIs and agree a training plan for service staff.", 14),
    },
}


def _timeline(days: int) -> str:
    return f"Within {days} days"


def _reason(cat: str, row, reg, cuts: dict, severity: str) -> str:
    if cat == "inventory":
        return f"{row['inventory_over_90_days_pct']:.0f}% of inventory is older than 90 days (regional average {reg['inventory_over_90_days_pct']:.0f}%)."
    if cat == "payment":
        return f"Average payment delay is {row['payment_delay_days']:.0f} days (regional average {reg['payment_delay_days']:.0f} days)."
    if cat == "sales":
        g, a = row["sales_growth_pct"], row["sales_achievement_pct"]
        tail = " despite high local market potential" if row["market_potential"] == "High" else ""
        if g < 0:
            return f"Sales declined {abs(g):.0f}% and achievement is {a:.0f}% of target{tail}."
        return f"Sales achievement is only {a:.0f}% of target{tail}."
    if cat == "service":
        return f"Service score is {row['service_score']:.0f}/100 (regional average {reg['service_score']:.0f})."
    if cat == "complaints":
        cut = cuts["q90"] if severity == "High" else cuts["q75"]
        pct = "90th" if severity == "High" else "75th"
        return (
            f"{row['customer_complaints']:.0f} complaints ({row['complaint_rate']:.0f} per 100 vehicles sold), "
            f"above the network {pct} percentile ({cut:.0f})."
        )
    return ""


def build_actions(row, drivers: list[dict], flags: list[str], hidden: bool, growth_opp: bool, reg, cuts: dict) -> list[dict]:
    """Return an ordered action plan for one dealer."""
    actions: list[dict] = []
    for d in drivers:
        cat = d["key"]
        sev = d["severity"]
        if cat not in PLAYBOOK or sev not in ("High", "Medium"):
            continue
        text, days = PLAYBOOK[cat][sev]
        actions.append(
            {
                "category": cat,
                "area": PLAYBOOK[cat]["area"],
                "action": text,
                "reason": _reason(cat, row, reg, cuts, sev),
                "owner": PLAYBOOK[cat]["owner"],
                "timeline": _timeline(days),
                "days": days,
                "severity": sev,
            }
        )

    # High market potential + poor performance (spec rule)
    if row["market_potential"] == "High" and row["sales_achievement_pct"] < 85:
        actions.append(
            {
                "category": "market",
                "area": "Market Capture",
                "action": "Assess local market capture, competitor activity, lead generation and conversion.",
                "reason": (
                    f"{row['sales_achievement_pct']:.0f}% of target in a high-potential market "
                    f"(sales growth {row['sales_growth_pct']:+.0f}%)."
                ),
                "owner": "Regional Manager + Dealer Principal",
                "timeline": _timeline(14),
                "days": 14,
                "severity": "High" if row["sales_growth_pct"] < 0 else "Medium",
            }
        )

    if hidden:
        issues = []
        if row["inventory_over_90_days_pct"] > 25:
            issues.append(f"{row['inventory_over_90_days_pct']:.0f}% ageing inventory")
        if row["payment_delay_days"] > 15:
            issues.append(f"{row['payment_delay_days']:.0f}-day payment delays")
        if row["complaint_rate"] > cuts["q75"]:
            issues.append("elevated complaints")
        actions.append(
            {
                "category": "hidden",
                "area": "Hidden Risk Review",
                "action": "Hold an operational health review despite strong sales; resolve build-up before it hits sales.",
                "reason": (
                    f"Strong sales ({row['sales_achievement_pct']:.0f}% of target, {row['sales_growth_pct']:+.0f}% growth) "
                    f"mask warning signs: {', '.join(issues) if issues else 'multiple operational signals'}."
                ),
                "owner": "Regional Manager + Finance",
                "timeline": _timeline(7),
                "days": 7,
                "severity": "High",
            }
        )

    if growth_opp:
        actions.append(
            {
                "category": "growth",
                "area": "Growth Support",
                "action": "Offer growth support (local marketing, lead generation, sales capacity) rather than crisis intervention.",
                "reason": (
                    f"Operations are healthy (inventory {row['inventory_over_90_days_pct']:.0f}% >90d, "
                    f"payment delay {row['payment_delay_days']:.0f} days, service {row['service_score']:.0f}) "
                    f"but sales are {row['sales_achievement_pct']:.0f}% of target."
                ),
                "owner": "Regional Sales Manager",
                "timeline": _timeline(30),
                "days": 30,
                "severity": "Low",
            }
        )

    actions.sort(key=lambda a: (a["days"], -SEV_RANK[a["severity"]], CATEGORY_ORDER.get(a["category"], 9)))
    for i, a in enumerate(actions, start=1):
        a["rank"] = i
    return actions


# ---------------------------------------------------------------------------
# Rule-based "management brief" (same JSON schema as the AI layer)
# ---------------------------------------------------------------------------
def action_priority_label(action: dict, dealer_priority: str) -> str:
    if action["severity"] == "High" and action["days"] <= 7 and dealer_priority == "P0":
        return "Immediate"
    if action["days"] <= 14 and action["severity"] in ("High", "Medium"):
        return "Within 7 Days"
    return "Monitor"


def rule_based_brief(row, drivers: list[dict], actions: list[dict]) -> dict:
    status = row["status"]
    top = drivers[:3]
    if top:
        names = ", ".join(d["driver"].lower() for d in top)
        summary = (
            f"{row['dealer_name']} ({row['dealer_id']}) is {status.upper()} with a health score of "
            f"{int(row['health_score'])}/100. Main concerns: {names}."
        )
    else:
        summary = (
            f"{row['dealer_name']} ({row['dealer_id']}) is {status.upper()} with a health score of "
            f"{int(row['health_score'])}/100 and no material risk drivers."
        )
    if row.get("hidden_risk"):
        summary += " Strong sales hide operational warning signs (hidden risk)."
    concerns = [
        {"issue": d["driver"], "evidence": d["detail"], "severity": d["severity"]} for d in top
    ]
    acts = [
        {
            "priority": action_priority_label(a, row["priority_code"]),
            "action": a["action"],
            "reason": a["reason"],
            "owner": a["owner"],
        }
        for a in actions[:3]
    ]
    if not acts:
        # The brief schema (shared with the AI layer) requires at least one action.
        acts = [
            {
                "priority": "Monitor",
                "action": "Continue routine monitoring; no corrective action needed.",
                "reason": "No material risk drivers - all monitored indicators are within acceptable ranges.",
                "owner": "Regional Manager",
            }
        ]
    return {"summary": summary, "concerns": concerns, "actions": acts}
