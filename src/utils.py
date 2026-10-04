"""UI helpers: colours, formatting, KPI cards, version-tolerant Streamlit wrappers."""
from __future__ import annotations

import inspect
import math

import plotly.io as pio

_FONT_FAMILY = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
pio.templates["dealer360"] = pio.templates["plotly_white"]
pio.templates["dealer360"].layout.font = dict(family=_FONT_FAMILY, color="#0B1F3A")
pio.templates.default = "dealer360"

NAVY = "#0B1F3A"
BLUE = "#1E5AA8"
GREY = "#5B6B7F"
LIGHT = "#F3F6FA"
STATUS_COLORS = {"Critical": "#C62828", "Watch": "#E59A0B", "Healthy": "#2E7D32"}
STATUS_EMOJI = {"Critical": "🔴", "Watch": "🟠", "Healthy": "🟢"}
SEVERITY_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}
SEVERITY_COLOR = {"High": "#C62828", "Medium": "#E59A0B", "Low": "#C9A400"}
TONE_COLOR = {"neutral": BLUE, "bad": STATUS_COLORS["Critical"], "warn": STATUS_COLORS["Watch"], "good": STATUS_COLORS["Healthy"]}

DISCLAIMER = "Synthetic / Demonstration Data · Scores are prototype assumptions - requires historical validation"

GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
.stApp, .stApp *:not(code):not(pre):not([data-testid="stIconMaterial"]):not([data-testid="stIconMaterial"] *) {{
  font-family: 'Inter', system-ui, -apple-system, "Segoe UI", sans-serif; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1400px; }}
h1, h2, h3, h4 {{ color: {NAVY}; letter-spacing: -0.01em; }}
.d360-hero {{ background: linear-gradient(120deg, {NAVY} 0%, #14396b 100%); border-radius: 14px;
  padding: 22px 28px; margin-bottom: 18px; color: #fff; box-shadow: 0 8px 24px rgba(11,31,58,.22); }}
.d360-hero h1 {{ color: #fff; margin: 0; font-size: 2.15rem; font-weight: 800; }}
.d360-hero .sub {{ font-size: 1.05rem; opacity: .95; margin-top: 2px; }}
.d360-hero .tag {{ font-size: .85rem; opacity: .75; margin-top: 6px; }}
.d360-badge {{ display:inline-block; background:#ffffff22; border:1px solid #ffffff55; color:#fff;
  padding: 2px 10px; border-radius: 999px; font-size: .75rem; margin-top: 10px; }}
.kpi {{ background:#fff; border:1px solid #E1E8F0; border-left: 5px solid {BLUE}; border-radius: 10px;
  padding: 12px 14px; height: 100%; box-shadow: 0 1px 2px rgba(11,31,58,.05);
  transition: box-shadow .15s ease, transform .15s ease; }}
.kpi:hover {{ box-shadow: 0 6px 16px rgba(11,31,58,.14); transform: translateY(-1px); }}
.kpi .l {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .05em; color: {GREY}; font-weight: 600; }}
.kpi .v {{ font-size: 1.75rem; font-weight: 800; color: {NAVY}; line-height: 1.2; font-variant-numeric: tabular-nums; }}
.kpi .s {{ font-size: .78rem; color: {GREY}; }}
.panel {{ background:{LIGHT}; border:1px solid #E1E8F0; border-radius: 12px; padding: 14px 16px; margin-bottom: 10px; }}
.chip {{ display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .78rem; font-weight: 600;
  color:#fff; margin-right: 6px; }}
.status-banner {{ border-radius: 12px; padding: 16px 20px; color:#fff; margin-bottom: 12px;
  box-shadow: 0 4px 14px rgba(11,31,58,.15); }}
.status-banner .st {{ font-size: 1.6rem; font-weight: 800; letter-spacing: .04em; }}
.status-banner .hs {{ font-size: 1.05rem; opacity: .95; }}
.driver {{ border-left: 5px solid #ccc; background:#fff; border:1px solid #E1E8F0; border-radius: 10px;
  padding: 10px 14px; margin-bottom: 8px; transition: box-shadow .15s ease; }}
.driver:hover {{ box-shadow: 0 3px 10px rgba(11,31,58,.08); }}
.driver .t {{ font-weight: 700; color:{NAVY}; }}
.driver .d {{ color:{GREY}; font-size: .88rem; }}
.hidden-card {{ background:#fff; border:1px solid #F0C36D; border-left: 5px solid {STATUS_COLORS['Watch']};
  border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; font-size: .9rem; }}
.small-muted {{ color:{GREY}; font-size:.8rem; }}
.stPlotlyChart {{ background:#fff; border:1px solid #E1E8F0; border-radius: 12px; padding: 4px 4px 0; }}
div[data-testid="stMetric"] {{ background:#fff; border:1px solid #E1E8F0; border-radius: 10px; padding: 8px 10px; }}
</style>
"""


def fmt_pct(v, digits: int = 0, signed: bool = False) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    return f"{v:+.{digits}f}%" if signed else f"{v:.{digits}f}%"


def fmt_num(v, digits: int = 0, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "N/A"
    return f"{v:.{digits}f}{suffix}"


def kpi_card(label: str, value: str, sub: str = "", tone: str = "neutral") -> str:
    color = TONE_COLOR.get(tone, BLUE)
    return (
        f'<div class="kpi" style="border-left-color:{color}"><div class="l">{label}</div>'
        f'<div class="v">{value}</div><div class="s">{sub}&nbsp;</div></div>'
    )


def chip(text: str, color: str) -> str:
    return f'<span class="chip" style="background:{color}">{text}</span>'


def status_label(status: str) -> str:
    return f"{STATUS_EMOJI.get(status, '')} {status}"


PENDING_PAGE_KEY = "_pending_page"


def goto_dealer(dealer_id: str) -> None:
    """Button callback: open ``dealer_id`` in Dealer 360.

    st.switch_page() can't be called here: inside an on_click callback its rerun
    request is swallowed by the rerun Streamlit is already about to do, so the
    page never changes. Record the intent instead; app.py switches pages in the
    normal script flow.
    """
    import streamlit as st

    st.session_state["selected_dealer"] = dealer_id
    st.session_state[PENDING_PAGE_KEY] = "dealer-360"


# ---------------------------------------------------------------------------
# Streamlit wrappers tolerant to API changes across versions
# ---------------------------------------------------------------------------
def show_df(st, data, **kwargs):
    if "width" in inspect.signature(st.dataframe).parameters:
        return st.dataframe(data, width="stretch", **kwargs)
    return st.dataframe(data, use_container_width=True, **kwargs)


def show_plot(st, fig, **kwargs):
    # st.plotly_chart silently swallows an unrecognised `width` kwarg into its own
    # **kwargs and shows an on-screen deprecation banner instead of raising - a plain
    # try/except can't detect that, so check the installed signature instead.
    if "width" in inspect.signature(st.plotly_chart).parameters:
        return st.plotly_chart(fig, width="stretch", **kwargs)
    return st.plotly_chart(fig, use_container_width=True, **kwargs)
