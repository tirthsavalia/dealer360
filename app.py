"""Dealer360 - Dealer Health & Action Intelligence (Streamlit entry point).

Run:  streamlit run app.py
"""
from __future__ import annotations

from types import SimpleNamespace

import streamlit as st

st.set_page_config(page_title="Dealer360 - Dealer Health & Action Intelligence", page_icon="🚗", layout="wide",
                   initial_sidebar_state="expanded")

from src.data_loader import load_default, load_uploaded  # noqa: E402
from src.risk_engine import analyze  # noqa: E402
from src.scoring import ScoringConfig, complaint_cuts  # noqa: E402
from src.utils import GLOBAL_CSS, PENDING_PAGE_KEY  # noqa: E402
from src.validation import DataValidationError  # noqa: E402
from views import action_center, dealer_360, methodology, overview, ranking  # noqa: E402

@st.cache_data(show_spinner=False)
def _default_data():
    return load_default()


@st.cache_data(show_spinner=False)
def _uploaded_data(name: str, content: bytes):
    return load_uploaded(name, content)


@st.cache_data(show_spinner="Scoring dealers...")
def _analyze(df, healthy: int, watch: int):
    return analyze(df, ScoringConfig(healthy_threshold=healthy, watch_threshold=watch))


def _sidebar_data():
    """Upload section -> (raw_df, warnings, is_demo, source_label)."""
    st.sidebar.divider()
    st.sidebar.markdown("**Data Source**")
    with st.sidebar.expander("Upload Dealer Data"):
        uploaded = st.file_uploader("CSV or Excel", type=["csv", "xlsx"], key="upload", label_visibility="collapsed")
        st.caption("Required: dealer_id, dealer_name, region, city, market_potential, monthly_sales, monthly_target, "
                   "sales_growth_pct, inventory_over_90_days_pct, payment_delay_days, service_score, customer_complaints.")
        try:
            raw, _ = _default_data()
            st.download_button("Download sample CSV", raw.to_csv(index=False).encode("utf-8"),
                               file_name="dealer360_sample.csv", mime="text/csv", key="sample_dl")
        except Exception:
            pass
    if uploaded is not None:
        try:
            raw, warns = _uploaded_data(uploaded.name, uploaded.getvalue())
            st.sidebar.success(f"● Using uploaded dealer dataset ({uploaded.name})")
            return raw, warns, False, uploaded.name
        except DataValidationError as exc:
            st.sidebar.error(str(exc))
        except Exception:
            st.sidebar.error("Something went wrong reading that file. Please check its format.")
        st.sidebar.info("Falling back to the synthetic demonstration dataset.")
    raw, warns = _default_data()
    st.sidebar.markdown("● **Synthetic Demo Data**  \nUsing synthetic demonstration dataset.")
    return raw, warns, True, "Synthetic Demo Data"


def _guarded(render_fn, ctx, requires_nonempty: bool = True):
    """Wrap a page's render(ctx) so a missing dataset or a rendering bug never shows a raw traceback."""
    def _run() -> None:
        if requires_nonempty and ctx.df.empty:
            st.warning("No dealers match the current sidebar filters. Clear a filter to continue.")
            return
        try:
            render_fn(ctx)
        except Exception:
            import logging

            logging.getLogger("dealer360").exception("Unhandled error while rendering page")  # server log only
            st.error("Something unexpected happened while building this page. Please refresh, or try the synthetic demo data.")
    return _run


def main() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("## 🚗 DEALER360")
        st.caption("Dealer Health & Action Intelligence")

    try:
        raw, warns, is_demo, _ = _sidebar_data()

        with st.sidebar.expander("Advanced: classification thresholds"):
            healthy = st.slider("Healthy if health score ≥", 55, 90, 70)
            watch = st.slider("Watch if health score ≥", 20, healthy - 5, min(50, healthy - 5))
            st.caption("Prototype assumptions - requires historical validation.")
        cfg = ScoringConfig(healthy_threshold=healthy, watch_threshold=watch)

        all_df = _analyze(raw, healthy, watch)
        cuts = complaint_cuts(all_df)

        st.sidebar.divider()
        st.sidebar.markdown("**Filters**")
        regions = st.sidebar.multiselect("Region", sorted(all_df["region"].unique()), placeholder="All regions")
        statuses = st.sidebar.multiselect("Status", ["Critical", "Watch", "Healthy"], placeholder="All statuses")
        potentials = st.sidebar.multiselect("Market Potential", ["High", "Medium", "Low"], placeholder="All")
        df = all_df
        if regions:
            df = df[df["region"].isin(regions)]
        if statuses:
            df = df[df["status"].isin(statuses)]
        if potentials:
            df = df[df["market_potential"].isin(potentials)]
        st.sidebar.caption(f"Showing {len(df)} of {len(all_df)} dealers (Dealer 360 always uses all dealers).")

        if warns:
            with st.sidebar.expander(f"⚠️ Data quality notes ({len(warns)})"):
                for w in warns:
                    st.write(f"- {w}")

        ctx = SimpleNamespace(all_df=all_df, df=df, cfg=cfg, cuts=cuts, is_demo=is_demo)
    except DataValidationError as exc:
        st.error(f"Data problem: {exc}")
        return
    except Exception:
        import logging

        logging.getLogger("dealer360").exception("Unhandled error while preparing data")
        st.error("Something unexpected happened while loading data. Please refresh, or try the synthetic demo data.")
        return

    dealer_360_page = st.Page(_guarded(dealer_360.render, ctx, requires_nonempty=False),
                              title="Dealer 360", icon="🚗", url_path="dealer-360")
    pages = [
        st.Page(_guarded(overview.render, ctx), title="Executive Overview", icon="📊", url_path="overview", default=True),
        st.Page(_guarded(ranking.render, ctx), title="Dealer Ranking", icon="📋", url_path="ranking"),
        dealer_360_page,
        st.Page(_guarded(action_center.render, ctx), title="Action Center", icon="✅", url_path="actions"),
        st.Page(_guarded(methodology.render, ctx, requires_nonempty=False), title="Methodology", icon="📐", url_path="methodology"),
    ]
    nav = st.navigation(pages, position="top")
    if st.session_state.pop(PENDING_PAGE_KEY, None) == dealer_360_page.url_path and nav.url_path != dealer_360_page.url_path:
        st.switch_page(dealer_360_page)
    nav.run()


main()
