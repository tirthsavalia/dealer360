"""Page 4 - Action Center: what should the regional manager do next?"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.utils import BLUE, chip, goto_dealer, kpi_card, status_label

PRIORITY_HELP = {
    "P0": "Immediate management intervention",
    "P1": "Targeted corrective plan within 7 days",
    "P2": "Continue monitoring",
}


def _flatten(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in d.iterrows():
        for a in r["actions"]:
            rows.append(
                {
                    "Dealer ID": r["dealer_id"], "Dealer": r["dealer_name"], "Region": r["region"],
                    "Status": r["status"], "Dealer Priority": r["priority_label"],
                    "Action #": a["rank"], "Area": a["area"], "Action": a["action"],
                    "Reason": a["reason"], "Owner": a["owner"], "Timeline": a["timeline"],
                }
            )
    return pd.DataFrame(rows)


def render(ctx) -> None:
    df = ctx.df
    st.title("Action Center")
    st.markdown("**What should the regional manager do next?** Prioritised, owner-assigned actions for every Critical and Watch dealer.")

    base = df[df["status"].isin(["Critical", "Watch"])]
    counts = {p: int((base["priority_code"] == p).sum()) for p in ("P0", "P1", "P2")}
    cols = st.columns(4)
    cols[0].markdown(kpi_card("P0 - Immediate", str(counts["P0"]), PRIORITY_HELP["P0"], "bad"), unsafe_allow_html=True)
    cols[1].markdown(kpi_card("P1 - Within 7 days", str(counts["P1"]), PRIORITY_HELP["P1"], "warn"), unsafe_allow_html=True)
    cols[2].markdown(kpi_card("P2 - Monitor", str(counts["P2"]), PRIORITY_HELP["P2"], "neutral"), unsafe_allow_html=True)
    cols[3].markdown(kpi_card("Dealers in plan", str(len(base)), "Critical + Watch", "neutral"), unsafe_allow_html=True)
    st.write("")

    f1, f2 = st.columns([2, 1])
    levels = f1.multiselect("Priority levels", ["P0", "P1", "P2"], default=["P0", "P1"])
    limit_label = f2.selectbox("Show", ["Top 10", "Top 25", "All"], index=0)
    view = base[base["priority_code"].isin(levels)].sort_values(["priority_rank", "risk_score"], ascending=[True, False])
    if limit_label != "All":
        view = view.head(int(limit_label.split()[1]))
    if view.empty:
        st.info("No dealers match the selected priority levels in the current view.")
        return

    flat = _flatten(view)
    st.download_button("Download action plan (CSV)", flat.to_csv(index=False).encode("utf-8"),
                       file_name="dealer360_action_plan.csv", mime="text/csv", key="actions_dl")

    for i, (_, r) in enumerate(view.iterrows()):
        title = f"{status_label(r['status'])} · {r['dealer_id']} - {r['dealer_name']} ({r['region']}) · Health {int(r['health_score'])} · {r['priority_label']}"
        with st.expander(title, expanded=(i < 2)):
            if r["flags"]:
                st.markdown(" ".join(chip(f, "#B4531A") for f in r["flags"]), unsafe_allow_html=True)
            if not r["actions"]:
                st.write("No specific action - continue monitoring.")
            for a in r["actions"]:
                st.markdown(
                    f"""**Priority {a['rank']} - {a['area']}** {chip(a['timeline'], BLUE)}
**Action:** {a['action']}
**Reason:** {a['reason']}
**Owner:** {a['owner']}""",
                    unsafe_allow_html=True,
                )
                st.divider()
            st.button("Open Dealer 360 →", key=f"ac_open_{r['dealer_id']}", on_click=goto_dealer, args=(r["dealer_id"],))
    st.caption("Recommendations are decision support, not automatic decisions. Synthetic / demonstration data.")
