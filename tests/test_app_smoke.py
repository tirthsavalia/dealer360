"""End-to-end tests: run the real Streamlit app headlessly via AppTest, plus data edge cases."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from streamlit.testing.v1 import AppTest

from src import ai_engine
from src.data_loader import load_default, load_uploaded
from src.recommendations import rule_based_brief
from src.risk_engine import analyze, peer_average
from src.scoring import ScoringConfig
from src.validation import DataValidationError
from views.dealer_360 import _gauge, _radar

# Newer Streamlit resolves relative AppTest paths against the calling file, so use an absolute path.
APP = str(Path(__file__).resolve().parents[1] / "app.py")
TIMEOUT = 60
PAGES = ["overview", "ranking", "dealer_360", "action_center", "methodology"]


def _render_page(page: str) -> None:
    # Runs as its own Streamlit script inside AppTest, so imports must live here.
    import importlib
    from types import SimpleNamespace

    from src.data_loader import load_default
    from src.risk_engine import analyze
    from src.scoring import ScoringConfig, complaint_cuts

    raw, _ = load_default()
    all_df = analyze(raw, ScoringConfig())
    ctx = SimpleNamespace(all_df=all_df, df=all_df, cfg=ScoringConfig(), cuts=complaint_cuts(all_df), is_demo=True)
    importlib.import_module(f"views.{page}").render(ctx)


def _assert_clean(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    banners = [w.value for w in at.warning if "deprecated" in str(w.value).lower()]
    assert not banners, banners


def _sidebar_widget(widgets, label: str):
    return next(w for w in widgets if w.label == label)


def test_app_boots_on_executive_overview():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    _assert_clean(at)
    html = " ".join(m.value for m in at.markdown)
    assert "Total Dealers" in html and ">100<" in html


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(page):
    at = AppTest.from_function(_render_page, kwargs={"page": page}, default_timeout=TIMEOUT).run()
    _assert_clean(at)


def test_open_in_dealer_360_button_navigates():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    at.button(key="overview_open").click().run()
    _assert_clean(at)
    assert [t.value for t in at.title] == ["Dealer 360"]
    assert _sidebar_widget(at.selectbox, "Select dealer").value == "D014"


def test_filters_matching_nothing_show_friendly_warning():
    df = analyze(load_default()[0])
    empty = next(
        ((r, s, p) for r in df.region.unique() for s in ("Critical", "Watch", "Healthy") for p in ("High", "Medium", "Low")
         if df[(df.region == r) & (df.status == s) & (df.market_potential == p)].empty),
        None,
    )
    if empty is None:
        pytest.skip("every region/status/potential combination has dealers")
    region, status, potential = empty
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    _sidebar_widget(at.sidebar.multiselect, "Region").set_value([region])
    _sidebar_widget(at.sidebar.multiselect, "Status").set_value([status])
    _sidebar_widget(at.sidebar.multiselect, "Market Potential").set_value([potential]).run()
    _assert_clean(at)
    assert any("No dealers match" in w.value for w in at.warning)


def test_threshold_slider_extreme_does_not_crash():
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    _sidebar_widget(at.sidebar.slider, "Healthy if health score ≥").set_value(55).run()
    _assert_clean(at)


@pytest.mark.parametrize("healthy,watch", [(55, 20), (70, 50), (90, 85)])
def test_threshold_extremes_classify_every_dealer(healthy, watch):
    res = analyze(load_default()[0], ScoringConfig(healthy_threshold=healthy, watch_threshold=watch))
    assert len(res) == 100
    assert res["status"].isin(["Healthy", "Watch", "Critical"]).all()


def test_dealer_level_builders_handle_every_dealer():
    df = analyze(load_default()[0])
    for _, row in df.iterrows():
        _gauge(row)
        _radar(row)
        peer_average(df, row)
        brief = rule_based_brief(row, row["drivers"], row["actions"])
        ai_engine.validate_brief(brief)
        ai_engine.brief_to_text(brief, row)
        # The payload is sent to the API once a key is configured; it must survive json.dumps.
        json.dumps(ai_engine.dealer_payload(row))


def _sample_upload(fmt: str) -> bytes:
    raw, _ = load_default()
    if fmt == "csv":
        return raw.to_csv(index=False).encode("utf-8")
    buf = io.BytesIO()
    raw.to_excel(buf, index=False)
    return buf.getvalue()


@pytest.mark.parametrize("name,fmt", [("dealers.csv", "csv"), ("dealers.xlsx", "xlsx")])
def test_upload_roundtrip(name, fmt):
    df, _ = load_uploaded(name, _sample_upload(fmt))
    assert len(df) == 100


@pytest.mark.parametrize(
    "name,content",
    [
        ("dealers.csv", b"\x00\xff\xfe not a csv"),
        ("dealers.pdf", b"%PDF-1.4"),
        ("dealers.csv", b"a,b\n1,2\n"),
        ("dealers.csv", b""),
        ("dealers.xlsx", b"not really excel"),
    ],
)
def test_bad_uploads_raise_friendly_error(name, content):
    with pytest.raises(DataValidationError):
        load_uploaded(name, content)


def _fake_sdk(response):
    """A stand-in for the anthropic package whose client returns ``response`` - no network, no cost."""
    create = mock.Mock(return_value=response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return SimpleNamespace(Anthropic=mock.Mock(return_value=client)), create


def _d014_inputs():
    df = analyze(load_default()[0])
    row = df[df.dealer_id == "D014"].iloc[0]
    return ai_engine.dealer_payload(row), rule_based_brief(row, row["drivers"], row["actions"])


def test_ai_brief_success_path_uses_valid_model_and_parses_json(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    payload, fallback = _d014_inputs()
    ai_json = {"summary": "D014 needs intervention.",
               "concerns": [{"issue": "Ageing inventory", "evidence": "31% >90 days", "severity": "High"}],
               "actions": [{"priority": "Immediate", "action": "Inventory plan", "reason": "31% aged", "owner": "RSM"}]}
    response = SimpleNamespace(stop_reason="end_turn", content=[
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text=json.dumps(ai_json)),
    ])
    sdk, create = _fake_sdk(response)
    with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
            mock.patch.dict(sys.modules, {"anthropic": sdk}):
        brief, source, notice = ai_engine.generate_brief(payload, fallback)
    assert source == "ai" and notice is None and brief == ai_json
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["max_tokens"] >= 16000
    assert kwargs["fallbacks"] == "default"


def test_ai_brief_refusal_falls_back_to_rules():
    payload, fallback = _d014_inputs()
    sdk, _ = _fake_sdk(SimpleNamespace(stop_reason="refusal", content=[]))
    with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}, clear=False), \
            mock.patch.dict(sys.modules, {"anthropic": sdk}):
        brief, source, notice = ai_engine.generate_brief(payload, fallback)
    assert source == "rule" and brief is fallback and "declined" in notice
