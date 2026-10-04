"""Page 5 - Methodology & Assumptions (credibility page)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.ai_engine import ai_available
from src.scoring import COMPONENT_LABELS, MARKET_SCORES, WEIGHTS
from src.utils import show_df

ASSUMPTION = "Prototype Assumption - Requires Historical Validation"


def _health_formula_latex() -> str:
    """Build the weighted health-score sum straight from WEIGHTS/COMPONENT_LABELS so the
    formula shown can never drift from the numbers scoring.py actually uses."""
    terms = " + ".join(rf"{w:.2f}\,S_{{\text{{{COMPONENT_LABELS[k]}}}}}" for k, w in WEIGHTS.items())
    return rf"\text{{Health Score}} = {terms}"


def render(ctx) -> None:
    st.title("Methodology & Assumptions")
    st.warning(
        "**Synthetic / Demonstration Data.** All dealers, names and numbers are generated for this prototype. "
        f"All weights, mappings and thresholds below are **{ASSUMPTION}**."
    )

    st.header("1. The question Dealer360 answers")
    st.markdown(
        "**Which dealers need management attention, why, and what should we do next?**  \n"
        "Dealer health is *multidimensional*: a dealer can look strong on sales today and still be unhealthy tomorrow "
        "(e.g. strong sales + ageing inventory + late payments)."
    )
    st.code("SEE -> UNDERSTAND -> PRIORITISE -> ACT\nData -> KPI -> Score -> Risk  (deterministic)\nRisk -> Explanation -> Suggested action  (rules, optionally AI-assisted)", language="text")

    st.header("2. Health score (0-100, higher = healthier)")
    weights = pd.DataFrame(
        {"Component": [COMPONENT_LABELS[k] for k in WEIGHTS], "Weight": [f"{int(v * 100)}%" for v in WEIGHTS.values()]}
    )
    c1, c2 = st.columns([1, 2])
    with c1:
        show_df(st, weights, hide_index=True)
        st.caption(f"Weights: {ASSUMPTION}.")
    with c2:
        st.latex(_health_formula_latex())
        st.caption("Sₖ = the 0-100 component score below (e.g. S_Sales Achievement). Rounded to the nearest integer.")
        st.latex(r"\text{Risk Score} = 100 - \text{Health Score}")
        st.markdown(
            f"**Classification** (configurable in the sidebar): Healthy ≥ **{ctx.cfg.healthy_threshold}**, "
            f"Watch **{ctx.cfg.watch_threshold}-{ctx.cfg.healthy_threshold - 1}**, Critical < **{ctx.cfg.watch_threshold}**."
        )

    st.subheader("Component mappings")
    st.latex(r"\text{Sales Achievement \%} = \dfrac{\text{Monthly Sales}}{\text{Monthly Target}} \times 100")
    st.latex(r"\text{Complaint Rate} = \dfrac{\text{Customer Complaints}}{\text{Monthly Sales}} \times 100 \quad \text{(per 100 vehicles sold)}")
    maps = pd.DataFrame(
        [
            ["Sales achievement (sales ÷ target)", "≥110% → 100 · 100-109% → 90 · 90-99% → 75 · 80-89% → 60 · 70-79% → 45 · <70% → 25"],
            ["Sales growth", "≥+15% → 100 · +8..+14% → 90 · 0..+7% → 75 · −5..−1% → 60 · −10..−6% → 40 · <−10% → 20"],
            ["Inventory >90 days", "<5% → 100 · 5-10% → 90 · 10-15% → 75 · 15-25% → 55 · 25-35% → 35 · >35% → 15"],
            ["Payment delay", "0-2 d → 100 · 3-5 d → 90 · 6-10 d → 70 · 11-15 d → 50 · 16-20 d → 30 · >20 d → 10"],
            ["Service score", "Used directly (already 0-100)"],
            ["Complaint rate (per 100 vehicles sold)", "Network percentile: ≤P25 → 100 · P25-50 → 80 · P50-75 → 60 · P75-90 → 35 · >P90 → 15"],
            ["Market opportunity", ", ".join(f"{k} → {v}" for k, v in MARKET_SCORES.items()) + "  (an *opportunity* score, not a direct risk score)"],
        ],
        columns=["Component", "Mapping (0-100)"],
    )
    show_df(st, maps, hide_index=True)
    st.caption(f"Mappings: {ASSUMPTION}. The market score avoids blindly punishing low sales in low-potential markets, "
               "and highlights missed opportunity in high-potential ones.")

    st.header("3. Risk drivers & emerging-risk flags")
    st.markdown(
        "Each dealer's metrics are ranked by **severity** (High / Medium / Low) and then by **score points lost**, "
        "so the biggest, most damaging problems appear first:"
    )
    st.latex(r"\text{Points Lost}_k = w_k \times \left(100 - S_k\right)")
    st.caption("wₖ = that component's weight above, Sₖ = that component's 0-100 score. This never changes the Health/Risk Score — it only ranks which driver is shown first.")
    st.markdown("Combination **flags** add context without changing the score:")
    flags = pd.DataFrame(
        [
            ["Sales decline + inventory build-up", "growth < −10% AND inventory >90d > 25%"],
            ["Potential financial stress", "payment delay > 15 days AND health < 60"],
            ["Untapped market opportunity", "High market potential AND growth < 0 AND achievement < 85%"],
            ["Customer experience deterioration", "complaint rate > network P90 AND service < 75"],
            ["Hidden risk behind strong sales", "≥100% of target AND growth ≥ 0 AND (inventory >25% OR payment delay >15 days) plus supporting complaint signals"],
            ["Growth support opportunity", "achievement < 90% AND growth > 0 AND inventory ≤ 15% AND payment ≤ 5 days AND service ≥ 80"],
        ],
        columns=["Flag", "Rule"],
    )
    show_df(st, flags, hide_index=True)

    st.header("4. Action priority framework")
    prio = pd.DataFrame(
        [
            ["P0 - Immediate", "Very low health, severe delay/ageing/decline, or several high-severity drivers at once → management intervention"],
            ["P1 - Within 7 days", "Meaningful deterioration or multiple medium drivers → targeted corrective plan"],
            ["P2 - Monitor", "Isolated warning or mild deterioration → continue monitoring"],
        ],
        columns=["Level", "When"],
    )
    show_df(st, prio, hide_index=True)
    bm = pd.DataFrame(
        {
            "KPI": ["Sales achievement", "Sales growth", "Inventory >90d", "Payment delay", "Service score", "Complaints"],
            "Manufacturer benchmark": ["≥ 95%", "≥ +8%", "< 10%", "< 5 days", "> 85", "< 15"],
        }
    )
    st.markdown("**Manufacturer benchmarks used for comparison** (assumptions)")
    show_df(st, bm, hide_index=True)

    st.header("5. Where AI fits")
    st.markdown(
        "- **Scoring is never done by AI.** Health, risk, status, drivers, flags and priority are deterministic.\n"
        "- **Recommendations** come from a rule-based engine that always works.\n"
        "- **Management brief (optional):** if `ANTHROPIC_API_KEY` is set, Claude turns the structured data into a narrative brief. "
        "The JSON response is validated; on any failure the app silently falls back to rule-based recommendations.\n"
        f"- Current AI status: **{'enabled' if ai_available() else 'not configured (rule-based fallback)'}**."
    )

    st.header("6. Assumptions & limitations")
    st.markdown(
        "- Data is **synthetic**; patterns are designed to be realistic, not real.\n"
        "- Scores are **illustrative**. Weights and thresholds should be **calibrated on historical dealer outcomes** "
        "(defaults, exits, payment defaults, sales collapses) and agreed with business stakeholders.\n"
        "- The model is a point-in-time snapshot; trend is shown only via an optional previous-period score.\n"
        "- Complaint rate = complaints per 100 vehicles sold; percentiles are computed on the loaded network.\n"
        "- Recommendations are **decision support**, not automatic decisions.\n"
        "- **Key limitation:** thresholds and weights are not yet validated against historical outcomes."
    )

    st.header("7. Business value")
    st.markdown(
        "1. **Faster prioritisation** - no manual review of every dealer.\n"
        "2. **Early warning** - hidden risk is flagged before it appears in sales.\n"
        "3. **Explainability** - every flag shows its drivers and benchmarks.\n"
        "4. **Actionability** - owners and timelines for the next step.\n"
        "5. **Better resource allocation** - manager time goes where multiple signals converge."
    )

    st.header("8. Data dictionary & roadmap")
    st.markdown(
        "**Required CSV columns:** `dealer_id, dealer_name, region, city, market_potential, monthly_sales, monthly_target, "
        "sales_growth_pct, inventory_over_90_days_pct, payment_delay_days, service_score, customer_complaints`.  \n"
        "**Optional:** `dealer_size, years_with_manufacturer, inventory_units, complaint_rate, complaints_change_pct, "
        "customer_satisfaction_score, lead_conversion_pct, market_share_pct, regional_market_growth_pct, previous_health_score`."
    )
    st.markdown(
        "**Roadmap:** Prototype (synthetic data, scoring, dashboard) → Pilot (real dealer data) → Predictive risk "
        "(probability of deterioration from history) → Automated early-warning alerts → Prescriptive analytics "
        "(what worked for similar dealers)."
    )
