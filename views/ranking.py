"""Page 2 - Dealer Ranking: who should management look at first?"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.utils import goto_dealer, show_df, status_label

SORT_OPTIONS = {
    "Risk Score": ("risk_score", False),
    "Health Score": ("health_score", True),
    "Sales Growth": ("sales_growth_pct", True),
    "Inventory Ageing": ("inventory_over_90_days_pct", False),
    "Payment Delay": ("payment_delay_days", False),
    "Complaints": ("complaint_rate", False),
}


def render(ctx) -> None:
    df = ctx.df
    st.title("Dealer Ranking")
    st.markdown("**Who should management look at first?** Filter, sort and open any dealer.")

    c1, c2, c3 = st.columns(3)
    regions = c1.multiselect("Region", sorted(df["region"].unique()), default=[], placeholder="All regions")
    statuses = c2.multiselect("Status", ["Critical", "Watch", "Healthy"], default=[], placeholder="All statuses")
    potentials = c3.multiselect("Market potential", ["High", "Medium", "Low"], default=[], placeholder="All")

    all_drivers = sorted({d["driver"] for ds in df["drivers"] for d in ds})
    c4, c5, c6 = st.columns(3)
    driver = c4.selectbox("Risk driver", ["Any"] + all_drivers)
    min_risk = c5.slider("Minimum risk score", 0, 100, 0)
    max_health = c6.slider("Maximum health score", 0, 100, 100)

    c7, c8 = st.columns([2, 1])
    sort_label = c7.selectbox("Sort by", list(SORT_OPTIONS), index=0)
    direction = c8.radio("Order", ["Worst first", "Best first"], horizontal=True)

    view = df.copy()
    if regions:
        view = view[view["region"].isin(regions)]
    if statuses:
        view = view[view["status"].isin(statuses)]
    if potentials:
        view = view[view["market_potential"].isin(potentials)]
    if driver != "Any":
        view = view[view["drivers"].apply(lambda ds: any(d["driver"] == driver for d in ds))]
    view = view[(view["risk_score"] >= min_risk) & (view["health_score"] <= max_health)]

    col, worst_asc = SORT_OPTIONS[sort_label]
    ascending = worst_asc if direction == "Worst first" else not worst_asc
    view = view.sort_values([col, "risk_score"], ascending=[ascending, False])

    st.caption(f"Showing **{len(view)}** of {len(df)} dealers")
    if view.empty:
        st.info("No dealers match these filters. Try widening them.")
        return

    table = pd.DataFrame(
        {
            "Dealer ID": view["dealer_id"].to_numpy(),
            "Dealer Name": view["dealer_name"].to_numpy(),
            "Region": view["region"].to_numpy(),
            "Health Score": view["health_score"].to_numpy(),
            "Risk Score": view["risk_score"].to_numpy(),
            "Status": [status_label(s) for s in view["status"]],
            "Sales Achievement %": view["sales_achievement_pct"].round(0).to_numpy(),
            "Sales Growth %": view["sales_growth_pct"].round(1).to_numpy(),
            "Inventory >90d %": view["inventory_over_90_days_pct"].round(0).to_numpy(),
            "Payment Delay (days)": view["payment_delay_days"].round(0).to_numpy(),
            "Service Score": view["service_score"].round(0).to_numpy(),
            "Complaint Rate": view["complaint_rate"].round(1).to_numpy(),
            "Market Potential": view["market_potential"].to_numpy(),
            "Primary Risk Driver": view["primary_driver"].to_numpy(),
            "Recommended Priority": view["priority_label"].to_numpy(),
        }
    )
    cfg = {
        "Health Score": st.column_config.ProgressColumn("Health Score", min_value=0, max_value=100, format="%d"),
        "Risk Score": st.column_config.NumberColumn("Risk Score", format="%d"),
        "Sales Achievement %": st.column_config.NumberColumn("Sales Achievement %", format="%d%%"),
        "Sales Growth %": st.column_config.NumberColumn("Sales Growth %", format="%+.1f%%"),
        "Inventory >90d %": st.column_config.NumberColumn("Inventory >90d %", format="%d%%"),
        "Complaint Rate": st.column_config.NumberColumn("Complaint Rate", help="Complaints per 100 vehicles sold", format="%.1f"),
    }
    chosen = view["dealer_id"].iloc[0]
    try:
        event = show_df(st, table, hide_index=True, height=520, column_config=cfg, on_select="rerun",
                        selection_mode="single-row", key="ranking_table")
        rows = event.selection.rows if event is not None and hasattr(event, "selection") else []
        if rows:
            chosen = view["dealer_id"].iloc[rows[0]]
    except Exception:
        show_df(st, table, hide_index=True, height=520, column_config=cfg)
        chosen = st.selectbox("Select a dealer", view["dealer_id"].tolist(), key="ranking_pick")

    b1, b2 = st.columns([1, 1])
    b1.button(f"Open {chosen} in Dealer 360 →", on_click=goto_dealer, args=(chosen,), type="primary", key="ranking_open")
    b2.download_button("Download this table (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name="dealer360_ranking.csv", mime="text/csv", key="ranking_dl")
    st.caption("Click a column header to re-sort. Complaint rate = complaints per 100 vehicles sold. "
               "Synthetic / demonstration data; thresholds are prototype assumptions.")
