"""Page 1 - Executive Overview."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.risk_engine import network_summary
from src.utils import (
    DISCLAIMER,
    NAVY,
    STATUS_COLORS,
    goto_dealer,
    kpi_card,
    show_df,
    show_plot,
    status_label,
)


def _hero(ctx) -> None:
    st.markdown(
        f"""
<div class="d360-hero">
  <h1>Dealer360</h1>
  <div class="sub">Dealer Health &amp; Action Intelligence</div>
  <div class="tag">Identify emerging dealer risk. Understand the drivers. Prioritise action. · <b>From Dealer Data to Management Action.</b></div>
  <span class="d360-badge">{'Synthetic / Demonstration Data' if ctx.is_demo else 'Uploaded dealer dataset'}</span>
</div>""",
        unsafe_allow_html=True,
    )


def _kpis(df: pd.DataFrame) -> None:
    n = len(df)
    crit = int((df["status"] == "Critical").sum())
    watch = int((df["status"] == "Watch").sum())
    healthy = int((df["status"] == "Healthy").sum())
    p0 = int((df["priority_code"] == "P0").sum())
    avg = df["health_score"].mean()
    cards = [
        ("Total Dealers", f"{n}", "in current view", "neutral"),
        ("Critical", f"{crit}", "health score below threshold", "bad"),
        ("Watchlist", f"{watch}", "deteriorating indicators", "warn"),
        ("Healthy", f"{healthy}", "no major concern", "good"),
        ("Average Health Score", f"{avg:.0f} / 100", "network average", "neutral"),
        ("Immediate Attention", f"{p0}", "P0 dealers - act now", "bad"),
    ]
    for col, (label, value, sub, tone) in zip(st.columns(6), cards):
        col.markdown(kpi_card(label, value, sub, tone), unsafe_allow_html=True)


def _donut(df: pd.DataFrame) -> go.Figure:
    order = ["Critical", "Watch", "Healthy"]
    counts = [int((df["status"] == s).sum()) for s in order]
    fig = go.Figure(
        go.Pie(
            labels=order,
            values=counts,
            hole=0.62,
            marker=dict(colors=[STATUS_COLORS[s] for s in order]),
            sort=False,
            textinfo="value+percent",
            hovertemplate="%{label}: %{value} dealers<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="Risk distribution", font=dict(size=15, color=NAVY)),
        margin=dict(l=10, r=10, t=45, b=10),
        height=360,
        legend=dict(orientation="h", y=-0.05),
        annotations=[dict(text=f"<b>{len(df)}</b><br>dealers", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=NAVY))],
    )
    return fig


def _matrix(df: pd.DataFrame, ctx) -> go.Figure:
    risk_cut = 100 - ctx.cfg.healthy_threshold
    perf_cut = 75
    fig = go.Figure()
    for status in ["Healthy", "Watch", "Critical"]:
        d = df[df["status"] == status]
        fig.add_trace(
            go.Scatter(
                x=d["performance_score"],
                y=d["risk_score"],
                mode="markers",
                name=status,
                marker=dict(size=10, color=STATUS_COLORS[status], opacity=0.85, line=dict(width=1, color="white")),
                customdata=d[["dealer_id", "dealer_name", "health_score", "primary_driver"]].to_numpy(),
                hovertemplate="<b>%{customdata[0]} - %{customdata[1]}</b><br>Performance %{x:.0f} · Risk %{y:.0f}"
                "<br>Health score %{customdata[2]}<br>Main driver: %{customdata[3]}<extra></extra>",
            )
        )
    ymax = max(60, float(df["risk_score"].max()) + 10)
    fig.add_hline(y=risk_cut, line_dash="dash", line_color="#8A97A8")
    fig.add_vline(x=perf_cut, line_dash="dash", line_color="#8A97A8")
    quad = [
        (24, ymax - 3, "Immediate intervention", "left"),
        (101, ymax - 3, "Emerging concern / hidden risk", "right"),
        (101, 2, "Healthy / benchmark", "right"),
        (24, 2, "Needs investigation (not urgent)", "left"),
    ]
    for x, y, text, anchor in quad:
        fig.add_annotation(x=x, y=y, text=f"<i>{text}</i>", showarrow=False, xanchor=anchor, font=dict(size=11, color="#5B6B7F"))
    # label the three highest-risk dealers
    for _, r in df.nlargest(3, "risk_score").iterrows():
        fig.add_annotation(x=r["performance_score"], y=r["risk_score"], text=r["dealer_id"], showarrow=True, arrowhead=0,
                           ax=18, ay=-18, font=dict(size=10, color=NAVY))
    fig.update_layout(
        title=dict(text="Dealer risk vs performance matrix", font=dict(size=15, color=NAVY)),
        xaxis=dict(title="Performance score (sales achievement + momentum)", range=[20, 105], gridcolor="#EEF2F6"),
        yaxis=dict(title="Risk score (100 - health)", range=[0, ymax], gridcolor="#EEF2F6"),
        margin=dict(l=10, r=10, t=45, b=10),
        height=360,
        legend=dict(orientation="h", y=-0.2),
        plot_bgcolor="white",
    )
    return fig


def _regional(df: pd.DataFrame) -> go.Figure:
    """Dealer status mix by region - standard in dealer-network analytics (e.g. Salesforce
    Automotive Cloud's Dealer Performance view breaks down by region), and currently the only
    place in the app that shows the network broken out geographically."""
    order = ["Critical", "Watch", "Healthy"]
    crit_rate = df.groupby("region")["status"].apply(lambda s: (s == "Critical").mean())
    reg_order = crit_rate.sort_values(ascending=False).index.tolist()
    fig = go.Figure()
    for status in order:
        counts = [int(((df["region"] == r) & (df["status"] == status)).sum()) for r in reg_order]
        fig.add_trace(go.Bar(name=status, x=reg_order, y=counts, marker_color=STATUS_COLORS[status],
                             hovertemplate=f"%{{x}}: %{{y}} {status.lower()} dealer(s)<extra></extra>"))
    fig.update_layout(
        barmode="stack",
        title=dict(text="Dealer status by region", font=dict(size=15, color=NAVY)),
        xaxis=dict(title=None, gridcolor="#EEF2F6"),
        yaxis=dict(title="Dealers", gridcolor="#EEF2F6"),
        height=330, margin=dict(l=10, r=10, t=45, b=10),
        legend=dict(orientation="h", y=-0.15),
        plot_bgcolor="white",
    )
    return fig


def _top_table(df: pd.DataFrame) -> None:
    st.subheader("Top dealers requiring attention")
    cand = df[df["priority_code"].isin(["P0", "P1"])].sort_values(
        ["priority_rank", "risk_score", "n_high"], ascending=[True, False, False]
    ).head(10)
    if cand.empty:
        st.success("No dealers currently require immediate or 7-day attention in this view.")
        return
    table = pd.DataFrame(
        {
            "Rank": range(1, len(cand) + 1),
            "Dealer": cand["dealer_id"].to_numpy(),
            "Name": cand["dealer_name"].to_numpy(),
            "Region": cand["region"].to_numpy(),
            "Health Score": cand["health_score"].to_numpy(),
            "Status": [status_label(s) for s in cand["status"]],
            "Primary Concern": cand["primary_driver"].to_numpy(),
            "Priority": cand["priority_label"].to_numpy(),
        }
    )
    selected_id = cand["dealer_id"].iloc[0]
    try:
        event = show_df(
            st, table, hide_index=True, on_select="rerun", selection_mode="single-row", key="overview_top_table",
            column_config={"Health Score": st.column_config.ProgressColumn("Health Score", min_value=0, max_value=100, format="%d")},
        )
        rows = event.selection.rows if event is not None and hasattr(event, "selection") else []
        if rows:
            selected_id = cand["dealer_id"].iloc[rows[0]]
    except Exception:  # older Streamlit without row selection
        show_df(st, table, hide_index=True)
        selected_id = st.selectbox("Select a dealer", cand["dealer_id"].tolist(), key="overview_pick")
    st.button(f"Open {selected_id} in Dealer 360 →", on_click=goto_dealer, args=(selected_id,), type="primary", key="overview_open")
    st.caption("Tip: click a row to select it, then open the dealer. Default = highest-priority dealer.")


def _emerging(df: pd.DataFrame, ctx) -> None:
    st.subheader("Emerging risk indicators")
    summary = network_summary(df, ctx.cuts)
    notes = {
        "Sales declining": "sales growth < 0%",
        "Inventory ageing": ">25% of stock older than 90 days",
        "Payment delays": "average delay > 10 days",
        "High complaints": "complaint rate above network 75th percentile",
        "Hidden market opportunity": "high-potential market but < 85% of target",
    }
    n = max(len(df), 1)
    html = []
    for label, count in summary.items():
        pct = count / n * 100
        html.append(
            f'<div style="margin-bottom:9px"><div style="display:flex;justify-content:space-between;font-size:.92rem">'
            f"<span><b>{label}</b> <span class='small-muted'>({notes[label]})</span></span><b>{count} dealers</b></div>"
            f'<div style="background:#E6ECF3;border-radius:6px;height:8px"><div style="width:{pct:.0f}%;background:#1E5AA8;height:8px;border-radius:6px"></div></div></div>'
        )
    st.markdown("".join(html), unsafe_allow_html=True)


def _hidden_risk(df: pd.DataFrame) -> None:
    st.subheader("Hidden Risk Detection")
    st.caption("Dealers that look healthy on sales but show operational warning signs - sales alone would miss them.")
    hid = df[df["hidden_risk"]].sort_values("risk_score", ascending=False).head(4)
    if hid.empty:
        st.info("No hidden-risk dealers in the current view.")
        return
    for _, r in hid.iterrows():
        bits = []
        if r["inventory_over_90_days_pct"] > 25:
            bits.append(f"Inventory &gt;90d: <b>{r['inventory_over_90_days_pct']:.0f}%</b>")
        if r["payment_delay_days"] > 15:
            bits.append(f"Payment delay: <b>{r['payment_delay_days']:.0f} days</b>")
        if pd.notna(r["complaints_change_pct"]) and r["complaints_change_pct"] > 25:
            bits.append(f"Complaints: <b>{r['complaints_change_pct']:+.0f}%</b>")
        st.markdown(
            f"""<div class="hidden-card"><b>{r['dealer_id']} · {r['dealer_name']}</b> - Health {int(r['health_score'])} ({r['status']})<br>
Sales {r['sales_achievement_pct']:.0f}% of target, {r['sales_growth_pct']:+.0f}% growth &rarr; <i>looks healthy...</i><br>
<b>BUT</b> {' · '.join(bits)} &rarr; <b style="color:#B4531A">Hidden Risk</b></div>""",
            unsafe_allow_html=True,
        )
        st.button(f"Open {r['dealer_id']}", key=f"hidden_open_{r['dealer_id']}", on_click=goto_dealer, args=(r["dealer_id"],))


def render(ctx) -> None:
    df = ctx.df
    _hero(ctx)
    _kpis(df)
    st.write("")
    left, right = st.columns([1, 2])
    with left:
        show_plot(st, _donut(df))
    with right:
        show_plot(st, _matrix(df, ctx))
    st.caption(
        "Reading the matrix: **bottom-right** = healthy benchmarks · **top-left** = immediate intervention · "
        "**top-right** = strong sales but high risk (hidden risk) · **bottom-left** = needs investigation."
    )
    _top_table(df)
    st.write("")
    show_plot(st, _regional(df))
    st.caption("Regions ordered by share of Critical dealers, highest first.")
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        _emerging(df, ctx)
    with c2:
        _hidden_risk(df)
    st.caption(f"{DISCLAIMER} · Dealer health is multidimensional, not sales-only.")
