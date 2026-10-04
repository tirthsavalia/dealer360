# Dealer360 — Dealer Health & Action Intelligence

> **From Dealer Data to Management Action.**
> Dealer360 is an explainable dealer-intelligence platform that combines sales, inventory, payment, service and customer signals to identify emerging dealer risk and recommend prioritised management actions.

## ▶ Start here

| | |
|---|---|
| **Live app** (no sign-in) | **<https://dealer360.streamlit.app/>** |
| **Demo video** (1:15) | **<https://youtu.be/g67xDEIv7co>** |

[![Dealer360 demo video](https://img.youtube.com/vi/g67xDEIv7co/hqdefault.jpg)](https://youtu.be/g67xDEIv7co)

- **Problem:** Regional managers have limited time and many dealers, and sales alone hide trouble. A dealer can hit target while stock ages and payments slip.
- **Solution:** Each dealer gets a transparent 0–100 health score built from sales, growth, inventory, payments, service, complaints and market potential. The app explains *why* a dealer is flagged and recommends prioritised actions, each with an owner and a deadline.
- **Business value:** Managers move from 100 dealers to specific next actions, and catch warning signs (hidden risk) before they show up in sales.
- **Key limitation:** Weights and thresholds are prototype assumptions on synthetic data. They need calibrating against real historical dealer outcomes before live use.

> If the app shows *"This app is asleep"*, click the wake-up button and wait about a minute. No account is needed.

**All data is synthetic / demonstration data. All weights and thresholds are prototype assumptions — requires historical validation.**

## Problem

An automobile manufacturer sells through a large dealer network. Some dealers grow; others show declining sales, rising inventory, delayed payments, weak service and more complaints. Sales alone cannot tell a manager whether a dealer is sustainable or heading for trouble, and regional managers have limited time. They need to know:

1. Which dealers need attention?
2. Why?
3. What support or corrective action would help?

## Solution

Dealer360 turns dealer KPIs into a transparent **health score**, ranks dealers by risk, explains the **drivers** behind each flag, compares them with regional / peer / manufacturer benchmarks, and recommends **prioritised, owner-assigned actions**. It also surfaces **hidden risk** — dealers that look strong on sales but show operational warning signs.

```
SEE → UNDERSTAND → PRIORITISE → ACT
```

## Architecture

```
        SYNTHETIC DEALER DATA (CSV / Excel upload)
                       │
            Data validation & normalisation   (src/validation.py)
                       │
              Health score & risk score       (src/scoring.py)      ← deterministic
                       │
      ┌────────────────┴───────────────┐
 Classification                  Risk drivers · flags ·              (src/risk_engine.py)
 (Healthy/Watch/Critical)        hidden risk · priority
      └────────────────┬───────────────┘
                       │
        Recommendation engine (rules)             (src/recommendations.py)
        + optional Claude management brief        (src/ai_engine.py)  ← explains, never scores
                       │
                Streamlit dashboard               (app.py + views/)
```

The system of record is `Data → KPI → Score → Risk`. AI only assists with `Risk → Explanation → Suggested action`, and the app works fully without an API key.

## Features

- **Health scoring** (0–100) with transparent component weights
- **Risk classification** — Healthy ≥ 70, Watch 50–69, Critical < 50 (configurable in the sidebar)
- **Dealer ranking** — sortable/filterable, with priority (P0 / P1 / P2)
- **Risk drivers** — ranked by severity and score points lost
- **Dealer benchmarking** — vs regional average, similar dealers and manufacturer benchmark
- **Emerging-risk flags** — e.g. *Sales decline + inventory build-up*, *Potential financial stress*
- **Hidden Risk Detection** — strong sales, weak operations
- **Management recommendations** — action, reason, owner, timeline (Action Center)
- **AI management brief** — Claude-written, JSON-validated, rule-based fallback
- **What-if simulator** — see which single intervention moves the score most
- **CSV / Excel upload** with validation and data-quality warnings

Pages (top navigation bar): Executive Overview · Dealer Ranking · Dealer 360 · Action Center · Methodology. Data source, classification thresholds and filters live in the sidebar.

## Tech stack

Python · Streamlit · Pandas · NumPy · Plotly · (optional) Anthropic Claude API.

## How to run

```bash
git clone https://github.com/tirthsavalia/dealer360.git
cd dealer360
pip install -r requirements.txt
streamlit run app.py
```

Python 3.12 recommended (tested on 3.9 and 3.12). The synthetic dataset (`data/dealers.csv`) loads automatically — no login, database or API key needed. To regenerate it: `python -m src.generate_data`.

End users never see Python tracebacks (`showErrorDetails = "none"` in `.streamlit/config.toml`); errors go to the server log. To see full errors while developing:

```bash
STREAMLIT_CLIENT_SHOW_ERROR_DETAILS=full streamlit run app.py
```

### Tests

```bash
pip install -r requirements-dev.txt
python -m pyflakes app.py src views tests
python -m pytest -q
```

The suite covers the scoring model and data validation, and runs the real app headlessly with Streamlit's `AppTest`: every page, the "Open in Dealer 360" navigation, empty-filter and threshold edge cases, CSV/Excel uploads (valid and malformed), every dealer's charts and brief, and the AI brief's success/refusal/failure paths against a mocked SDK (no API calls). GitHub Actions runs lint + tests on every push and pull request (`.github/workflows/ci.yml`).

### Deploy (Streamlit Community Cloud)

1. Push this folder to a GitHub repository (public or private).
2. On <https://share.streamlit.io> choose **Create app → Deploy a public app from GitHub**, select the repo, branch `main` and main file `app.py`.
3. Under **Advanced settings**, choose **Python 3.12**.
4. (Optional, can be added any time after deploying) in **Advanced settings → Secrets**, add:

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

   Root-level secrets are exposed as environment variables, which is what `src/ai_engine.py` reads. Without the key, the app runs fully on rule-based recommendations.

Uploads are capped at 10 MB (`server.maxUploadSize`), and developer toolbar items are hidden from viewers (`client.toolbarMode = "viewer"`).

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | No | Enables the AI-written management brief. Without it the app shows rule-based recommendations. |
| `ANTHROPIC_MODEL` | No | Model override (default `claude-opus-5`). |

Copy `.env.example` to `.env` for local use. Keys are never hard-coded.

## Data

`data/dealers.csv` — 100 synthetic dealers across five regions with realistic patterns (not purely random): **12 Critical, 27 Watch, 61 Healthy**, plus handcrafted demo/edge-case dealers:

| Dealer | Story |
|---|---|
| **D014** Mumbai Central Motors | Demo dealer — Critical despite a high-potential market (62% of target, −14% growth, 31% aged inventory, 18-day payment delay) |
| D027, D041 | High sales but risky (hidden risk) |
| D058 | Low sales but healthy — growth opportunity |
| D063 | High market potential + declining performance |
| D077 | Operationally healthy but sales weak — growth support, not crisis |

Required upload columns: `dealer_id, dealer_name, region, city, market_potential, monthly_sales, monthly_target, sales_growth_pct, inventory_over_90_days_pct, payment_delay_days, service_score, customer_complaints`. Optional columns are filled in gracefully when missing.

## Assumptions

Health score = 0.25·Sales achievement + 0.15·Sales growth + 0.15·Inventory health + 0.15·Payment health + 0.10·Service + 0.10·Complaints (network percentile) + 0.10·Market opportunity. Band mappings, benchmarks and thresholds are documented on the in-app **Methodology** page. The market score is an *opportunity* score, not a direct risk score. Complaint rate = complaints per 100 vehicles sold.

## Limitations

- Data is synthetic; scores are illustrative.
- **Weights and thresholds are not calibrated on historical dealer outcomes** and need validation with business stakeholders before real use.
- Point-in-time snapshot; trend is only shown through an optional previous-period score.
- Recommendations are decision support, not automatic decisions.

## Project structure

```
dealer360/
├── app.py                 # Entry point: sidebar, caching, top navigation (st.navigation), error handling
├── views/                 # overview · ranking · dealer_360 · action_center · methodology
├── src/                   # scoring · validation · risk_engine · recommendations · ai_engine · data_loader · generate_data · utils
├── data/dealers.csv
├── tests/                 # unit tests + headless end-to-end AppTest suite
├── .github/workflows/ci.yml
├── .streamlit/config.toml
├── requirements.txt · requirements-dev.txt · .env.example · .gitignore
```

(The page modules live in `views/` rather than `pages/` because Streamlit auto-creates navigation for a `pages/` folder; navigation is defined explicitly in `app.py` instead.)
