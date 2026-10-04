"""Page 3 - Dealer 360: why is this dealer flagged, and what next?"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import ai_engine
from src.recommendations import rule_based_brief
from src.risk_engine import BENCHMARKS, REG_COLS, SUSTAINABILITY_TEXT, peer_average
from src.scoring import (
    COMPONENT_LABELS,
    WEIGHTS,
    compute_scores,
    growth_score,
    inventory_score,
    payment_score,
    sales_score,
)
from src.utils import (
    BLUE,
    GREY,
    NAVY,
    SEVERITY_COLOR,
    SEVERITY_EMOJI,
    STATUS_COLORS,
    chip,
    fmt_num,
    kpi_card,
    show_df,
    show_plot,
)

SUST_COLORS = {
    "Sustainable Growth": "#2E7D32",
    "Stable": "#4F8A5B",
    "Watch": "#E59A0B",
    "At Risk": "#D2691E",
    "Critical": "#C62828",
}


def _banner(row) -> None:
    color = STATUS_COLORS[row["status"]]
    prev = row.get("previous_health_score")
    trend = ""
    if pd.notna(prev):
        delta = int(row["health_score"]) - int(prev)
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "■"
        trend = f" · {arrow} {delta:+d} vs previous period ({int(prev)})"
    st.markdown(
        f'<div class="status-banner" style="background:{color}"><div class="st">{row["status"].upper()}</div>'
        f'<div class="hs">Health Score: <b>{int(row["health_score"])} / 100</b> · Risk Score {int(row["risk_score"])}{trend}</div></div>',
        unsafe_allow_html=True,
    )


def _profile(row) -> None:
    years = fmt_num(row["years_with_manufacturer"], 0, " yrs")
    st.markdown(
        f"""<div class="panel"><b style="font-size:1.15rem;color:{NAVY}">{row['dealer_id']} - {row['dealer_name']}</b><br>
<span class="small-muted">Region</span> <b>{row['region']}</b> ({row['city']}) &nbsp;|&nbsp;
<span class="small-muted">Market potential</span> <b>{row['market_potential']}</b> &nbsp;|&nbsp;
<span class="small-muted">Dealer size</span> <b>{row['dealer_size']}</b> &nbsp;|&nbsp;
<span class="small-muted">With manufacturer</span> <b>{years}</b></div>""",
        unsafe_allow_html=True,
    )


def _kpis(row) -> None:
    def tone(bad: bool, warn: bool = False) -> str:
        return "bad" if bad else "warn" if warn else "good"

    cards = [
        ("Sales Achievement", f"{row['sales_achievement_pct']:.0f}%", f"{int(row['monthly_sales'])} of {int(row['monthly_target'])} units",
         tone(row["sales_achievement_pct"] < 70, row["sales_achievement_pct"] < 90)),
        ("Sales Growth", f"{row['sales_growth_pct']:+.0f}%", "vs previous period", tone(row["sales_growth_pct"] < -10, row["sales_growth_pct"] < 0)),
        ("Inventory >90 Days", f"{row['inventory_over_90_days_pct']:.0f}%", "of stock", tone(row["inventory_over_90_days_pct"] > 25, row["inventory_over_90_days_pct"] > 15)),
        ("Payment Delay", f"{row['payment_delay_days']:.0f} days", "average", tone(row["payment_delay_days"] > 15, row["payment_delay_days"] > 8)),
        ("Service Score", f"{row['service_score']:.0f} / 100", "workshop quality", tone(row["service_score"] < 70, row["service_score"] < 80)),
        ("Complaints", f"{row['customer_complaints']:.0f}", f"{row['complaint_rate']:.0f} per 100 sold", "bad" if row["s_complaints"] <= 15 else "warn" if row["s_complaints"] <= 35 else "good"),
    ]
    for col, (label, value, sub, t) in zip(st.columns(6), cards):
        col.markdown(kpi_card(label, value, sub, t), unsafe_allow_html=True)


def _drivers(row) -> None:
    st.subheader("Why this dealer needs attention")
    drivers = row["drivers"][:5]
    if not drivers:
        st.success("No material risk drivers: all monitored indicators are within acceptable ranges.")
    for i, d in enumerate(drivers, start=1):
        color = SEVERITY_COLOR[d["severity"]]
        st.markdown(
            f"""<div class="driver" style="border-left-color:{color}">
<div class="t">{i}. {d['driver']} {chip(SEVERITY_EMOJI[d['severity']] + ' ' + d['severity'], color)}</div>
<div class="d">{d['detail']}</div>
<div class="d"><b>Dealer:</b> {d['value']} &nbsp;|&nbsp; <b>{d['benchmark']}</b></div></div>""",
            unsafe_allow_html=True,
        )
    if row["flags"]:
        st.markdown("**Emerging risk flags**")
        st.markdown(" ".join(chip(f, "#B4531A" if "opportunity" not in f.lower() else "#1E5AA8") for f in row["flags"]), unsafe_allow_html=True)
        st.caption("Flags highlight risky combinations. They do not change the score.")


def _gauge(row) -> go.Figure:
    """Health Score as an at-a-glance gauge, with a delta vs the previous period when available."""
    prev = row.get("previous_health_score")
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta" if pd.notna(prev) else "gauge+number",
        value=float(row["health_score"]),
        number={"suffix": " / 100", "font": {"size": 32, "color": NAVY}},
        delta={"reference": float(prev) if pd.notna(prev) else 0, "position": "bottom",
              "increasing": {"color": STATUS_COLORS["Healthy"]}, "decreasing": {"color": STATUS_COLORS["Critical"]}},
        title={"text": "HEALTH SCORE", "font": {"size": 12, "color": GREY}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": GREY, "tickfont": {"color": GREY, "size": 10}},
            "bar": {"color": NAVY, "thickness": 0.28},
            "bgcolor": "white",
            "borderwidth": 0,
            "steps": [
                {"range": [0, 50], "color": "#FBEAEA"},
                {"range": [50, 70], "color": "#FDF3DC"},
                {"range": [70, 100], "color": "#E7F3EC"},
            ],
            "threshold": {"line": {"color": STATUS_COLORS[row["status"]], "width": 4}, "thickness": 0.85,
                         "value": float(row["health_score"])},
        },
    ))
    fig.update_layout(height=235, margin=dict(l=25, r=25, t=45, b=10), paper_bgcolor="white")
    return fig


def _benchmark_component_scores() -> dict:
    """Manufacturer benchmark KPIs run through the SAME deterministic scoring functions as every
    dealer, so the radar compares like-for-like rather than inventing a second formula."""
    return {
        "sales": float(sales_score([BENCHMARKS["sales_achievement_pct"]])[0]),
        "growth": float(growth_score([BENCHMARKS["sales_growth_pct"]])[0]),
        "inventory": float(inventory_score([BENCHMARKS["inventory_over_90_days_pct"]])[0]),
        "payment": float(payment_score([BENCHMARKS["payment_delay_days"]])[0]),
        "service": float(BENCHMARKS["service_score"]),
        # customer_complaints benchmark is an absolute count, not a network-relative rate, so it
        # isn't comparable through complaint_score(); use the 25th-50th percentile band score (80)
        # as the reference "benchmark-good" point instead - clearly labelled below.
        "complaints": 80.0,
    }


def _radar(row) -> go.Figure:
    keys = [k for k in WEIGHTS if k != "market"]
    labels = [COMPONENT_LABELS[k] for k in keys]
    bench = _benchmark_component_scores()
    dealer_vals = [float(row[f"s_{k}"]) for k in keys]
    bench_vals = [bench[k] for k in keys]
    theta = labels + [labels[0]]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=bench_vals + [bench_vals[0]], theta=theta, name="Manufacturer benchmark",
                                  line=dict(color=GREY, dash="dash", width=1.5), fill=None,
                                  hovertemplate="%{theta}<br>Benchmark: %{r:.0f}<extra></extra>"))
    fig.add_trace(go.Scatterpolar(r=dealer_vals + [dealer_vals[0]], theta=theta, name=row["dealer_id"],
                                  line=dict(color=BLUE, width=2), fill="toself", fillcolor="rgba(30,90,168,0.18)",
                                  hovertemplate="%{theta}<br>Dealer: %{r:.0f}<extra></extra>"))
    fig.update_layout(
        title=dict(text="KPI profile vs benchmark", font=dict(size=13, color=GREY)),
        polar=dict(radialaxis=dict(range=[0, 100], tickfont=dict(size=9, color=GREY), gridcolor="#E6ECF3"),
                  angularaxis=dict(tickfont=dict(size=10, color=NAVY)), bgcolor="white"),
        height=235, margin=dict(l=45, r=45, t=40, b=20), legend=dict(orientation="h", y=-0.18, font=dict(size=10)),
        paper_bgcolor="white",
    )
    return fig


def _score_chart(row) -> None:
    st.subheader("How the health score is built")
    keys = list(WEIGHTS)
    earned = [WEIGHTS[k] * row[f"s_{k}"] for k in keys]
    lost = [WEIGHTS[k] * 100 - e for k, e in zip(keys, earned)]
    labels = [f"{COMPONENT_LABELS[k]} ({int(WEIGHTS[k] * 100)}%)" for k in keys]
    fig = go.Figure()
    fig.add_bar(y=labels, x=earned, orientation="h", name="Points earned", marker_color=BLUE,
                hovertemplate="%{y}: %{x:.1f} pts earned<extra></extra>")
    fig.add_bar(y=labels, x=lost, orientation="h", name="Points lost", marker_color="#D5DCE6",
                hovertemplate="%{y}: %{x:.1f} pts lost<extra></extra>")
    fig.update_layout(barmode="stack", height=340, margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(autorange="reversed"), xaxis=dict(title="Points (max = weight)"),
                      legend=dict(orientation="h", y=-0.2), plot_bgcolor="white")
    show_plot(st, fig)
    st.caption("Transparent, deterministic scoring - the AI layer never changes these numbers.")


def _benchmark_table(row, all_df, ctx) -> None:
    st.subheader("Benchmarking")
    reg = all_df[all_df["region"] == row["region"]][REG_COLS].mean()
    peers, peer_label = peer_average(all_df, row)
    spec = [
        ("Sales Achievement (%)", "sales_achievement_pct", True, "≥ 95%", 0),
        ("Sales Growth (%)", "sales_growth_pct", True, "≥ +8%", 1),
        ("Inventory >90d (%)", "inventory_over_90_days_pct", False, "< 10%", 0),
        ("Payment Delay (days)", "payment_delay_days", False, "< 5", 0),
        ("Service Score", "service_score", True, "> 85", 0),
        ("Complaints (count)", "customer_complaints", False, "< 15", 0),
    ]
    rows = []
    for label, col, higher_better, bench_txt, dec in spec:
        bench = BENCHMARKS[col]
        v = row[col]
        ok = v >= bench if higher_better else v <= bench
        rows.append(
            {
                "KPI": label,
                "Dealer": round(float(v), dec),
                "Regional Avg": round(float(reg[col]), dec),
                f"Similar dealers ({peer_label})": round(float(peers[col]), dec),
                "Manufacturer Benchmark": bench_txt,
                "Assessment": "✅ Meets benchmark" if ok else "⚠️ Off benchmark",
            }
        )
    show_df(st, pd.DataFrame(rows), hide_index=True)

    ctx_bits = [f"Local market potential: **{row['market_potential']}**"]
    if pd.notna(row["market_share_pct"]):
        net_share = all_df["market_share_pct"].mean()
        ctx_bits.append(f"market share **{row['market_share_pct']:.1f}%**" + (f" (network {net_share:.1f}%)" if pd.notna(net_share) else ""))
    if pd.notna(row["lead_conversion_pct"]):
        ctx_bits.append(f"lead conversion **{row['lead_conversion_pct']:.1f}%**")
    if pd.notna(row["regional_market_growth_pct"]):
        ctx_bits.append(f"regional market growth **{row['regional_market_growth_pct']:+.1f}%** vs dealer sales growth **{row['sales_growth_pct']:+.1f}%**")
    st.markdown(" · ".join(ctx_bits))


def _sustainability(row) -> None:
    st.subheader("Sustainability assessment")
    level = row["sustainability"]
    reasons = [f"{row['n_high']} high-severity and {row['n_med']} medium-severity risk driver(s)."]
    if row["hidden_risk"]:
        reasons.append("Strong sales are masking operational warning signs (inventory / payments / complaints).")
    if row["growth_opportunity"]:
        reasons.append("Operations are healthy; weak sales point to a growth-support opportunity rather than a crisis.")
    if pd.notna(row["previous_health_score"]):
        d = int(row["health_score"]) - int(row["previous_health_score"])
        reasons.append(f"Health score moved {d:+d} points vs the previous period.")
    st.markdown(
        f"""<div class="panel">{chip(level, SUST_COLORS[level])} &nbsp; <b>{SUSTAINABILITY_TEXT[level]}</b><br>
<span class="small-muted">{' '.join(reasons)}</span><br>
<span class="small-muted">Priority: <b>{row['priority_label']}</b></span></div>""",
        unsafe_allow_html=True,
    )


def _actions(row) -> None:
    st.subheader("Recommended action plan")
    actions = row["actions"]
    if not actions:
        st.success("No corrective action needed - continue routine monitoring.")
        return
    for a in actions:
        st.markdown(
            f"""<div class="panel"><b>Priority {a['rank']} - {a['area']}</b> {chip(a['timeline'], BLUE)}<br>
<b>Action:</b> {a['action']}<br><b>Reason:</b> {a['reason']}<br><b>Owner:</b> {a['owner']}</div>""",
            unsafe_allow_html=True,
        )


def _brief(row) -> None:
    st.subheader("Management brief")
    key = f"brief_{row['dealer_id']}"
    if ai_engine.ai_available():
        st.caption("AI brief enabled (Claude). The AI explains and suggests - it never changes the score.")
    else:
        st.caption("No ANTHROPIC_API_KEY set - the brief will use the rule-based recommendation engine.")
    if st.button("Generate Management Brief", key=f"brief_btn_{row['dealer_id']}", type="primary"):
        fallback = rule_based_brief(row, row["drivers"], row["actions"])
        with st.spinner("Preparing brief..."):
            st.session_state[key] = ai_engine.generate_brief(ai_engine.dealer_payload(row), fallback)
    if key in st.session_state:
        brief, source, notice = st.session_state[key]
        if notice:
            st.info(notice)
        st.markdown(f"**{'AI-generated' if source == 'ai' else 'Rule-based'} brief**")
        st.markdown(brief["summary"])
        if brief["concerns"]:
            st.markdown("**Key concerns**")
            for c in brief["concerns"]:
                st.markdown(f"- **{c['issue']}** ({c['severity']}): {c['evidence']}")
        st.markdown("**Recommended actions**")
        for i, a in enumerate(brief["actions"], 1):
            st.markdown(f"{i}. **[{a['priority']}]** {a['action']}  \n   _Why:_ {a['reason']} · _Owner:_ {a['owner']}")
        st.download_button("Download brief (.txt)", ai_engine.brief_to_text(brief, row).encode("utf-8"),
                           file_name=f"{row['dealer_id']}_management_brief.txt", key=f"brief_dl_{row['dealer_id']}")


def _simulate(row, ctx, **changes) -> pd.Series:
    d = {
        "monthly_target": float(row["monthly_target"]),
        "monthly_sales": float(row["monthly_target"]) * float(changes.get("ach", row["sales_achievement_pct"])) / 100,
        "sales_growth_pct": float(changes.get("growth", row["sales_growth_pct"])),
        "inventory_over_90_days_pct": float(changes.get("inv", row["inventory_over_90_days_pct"])),
        "payment_delay_days": float(changes.get("pay", row["payment_delay_days"])),
        "service_score": float(changes.get("service", row["service_score"])),
        "customer_complaints": float(row["customer_complaints"]),
        "complaint_rate": float(changes.get("rate", row["complaint_rate"])),
        "market_potential": row["market_potential"],
    }
    return compute_scores(pd.DataFrame([d]), ctx.cfg, ctx.cuts).iloc[0]


def _whatif(row, ctx) -> None:
    with st.expander("What-if simulator - which intervention moves the score most?"):
        c = st.columns(5)
        inv = c[0].slider("Inventory >90d (%)", 0, 60, int(min(60, row["inventory_over_90_days_pct"])), key=f"wi_inv_{row['dealer_id']}")
        pay = c[1].slider("Payment delay (days)", 0, 40, int(min(40, row["payment_delay_days"])), key=f"wi_pay_{row['dealer_id']}")
        growth = c[2].slider("Sales growth (%)", -30, 30, int(max(-30, min(30, row["sales_growth_pct"]))), key=f"wi_gr_{row['dealer_id']}")
        ach = c[3].slider("Sales achievement (%)", 30, 130, int(max(30, min(130, row["sales_achievement_pct"]))), key=f"wi_ach_{row['dealer_id']}")
        svc = c[4].slider("Service score", 30, 100, int(max(30, min(100, row["service_score"]))), key=f"wi_svc_{row['dealer_id']}")
        sim = _simulate(row, ctx, inv=inv, pay=pay, growth=growth, ach=ach, service=svc)
        delta = int(sim["health_score"]) - int(row["health_score"])
        a, b = st.columns(2)
        a.markdown(kpi_card("Current health score", f"{int(row['health_score'])}", row["status"], "neutral"), unsafe_allow_html=True)
        b.markdown(kpi_card("Simulated health score", f"{int(sim['health_score'])}", f"{sim['status']} · {delta:+d} pts",
                            "good" if delta > 0 else "bad" if delta < 0 else "neutral"), unsafe_allow_html=True)
        st.markdown("**Single-lever impact** (move one indicator to the manufacturer benchmark)")
        levers = {
            "Inventory >90d -> 10%": dict(inv=min(row["inventory_over_90_days_pct"], 10)),
            "Payment delay -> 5 days": dict(pay=min(row["payment_delay_days"], 5)),
            "Sales achievement -> 95%": dict(ach=max(row["sales_achievement_pct"], 95)),
            "Sales growth -> +8%": dict(growth=max(row["sales_growth_pct"], 8)),
            "Service score -> 85": dict(service=max(row["service_score"], 85)),
            "Complaint rate -> network median": dict(rate=min(row["complaint_rate"], ctx.cuts["q50"])),
        }
        out = []
        for name, ch in levers.items():
            s = _simulate(row, ctx, **ch)
            out.append({"Intervention": name, "New health score": int(s["health_score"]), "Gain (pts)": int(s["health_score"]) - int(row["health_score"]), "New status": s["status"]})
        out_df = pd.DataFrame(out).sort_values("Gain (pts)", ascending=False)
        show_df(st, out_df, hide_index=True)
        st.caption("Illustrative: recomputed with the same deterministic scoring model.")


def render(ctx) -> None:
    all_df = ctx.all_df
    st.title("Dealer 360")
    order = all_df.sort_values(["priority_rank", "risk_score"], ascending=[True, False])["dealer_id"].tolist()
    info = {r.dealer_id: f"{r.dealer_id} - {r.dealer_name} ({r.status}, {int(r.health_score)})" for r in all_df.itertuples()}
    current = st.session_state.get("selected_dealer")
    if current not in order:
        current = "D014" if "D014" in order else order[0]
    did = st.selectbox("Select dealer", order, index=order.index(current), format_func=lambda x: info[x])
    st.session_state["selected_dealer"] = did
    row = all_df[all_df["dealer_id"] == did].iloc[0]

    _banner(row)
    _profile(row)
    _kpis(row)
    st.write("")
    g1, g2 = st.columns([1, 1.3])
    with g1:
        show_plot(st, _gauge(row))
    with g2:
        show_plot(st, _radar(row))
        st.caption("Benchmark complaints uses the 25th-50th percentile score band (80) as a reference point; the manufacturer benchmark is an absolute count, not a network-relative rate.")
    st.write("")
    left, right = st.columns([1.15, 1])
    with left:
        _drivers(row)
    with right:
        _score_chart(row)
    _benchmark_table(row, all_df, ctx)
    _sustainability(row)
    _actions(row)
    _brief(row)
    _whatif(row, ctx)
    st.caption("Decision support, not automatic decisions · Synthetic / demonstration data · Thresholds are prototype assumptions.")
