"""Optional AI management brief (Claude). Falls back to rule-based text; never crashes.

The AI only explains risk and suggests actions - it never changes scores
(system of record: Data -> KPI -> Score -> Risk).
"""
from __future__ import annotations

import json
import os
import re

try:  # optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_NOTICE = "AI recommendations unavailable - showing rule-based management recommendations."

SYSTEM_PROMPT = """You are a regional dealer-management advisor for an automobile manufacturer.

Analyze the supplied dealer performance data (JSON in the user message).

Your task is to:
1. Identify the top 3 business concerns.
2. Explain why each concern matters.
3. Distinguish symptoms from likely root causes.
4. Recommend 3 practical management actions.
5. Prioritize actions as Immediate, Within 7 Days, or Monitor.
6. Avoid inventing facts not present in the data.
7. Keep recommendations practical for a regional manager.
8. Do not make irreversible decisions automatically.
9. Clearly state when the evidence is insufficient.

The health score, status and risk drivers are computed by a deterministic model; do not recompute or contradict them.

Return ONLY valid JSON (no markdown fences) with this shape:
{
  "summary": "...",
  "concerns": [{"issue": "...", "evidence": "...", "severity": "High/Medium/Low"}],
  "actions": [{"priority": "Immediate/Within 7 Days/Monitor", "action": "...", "reason": "...", "owner": "..."}]
}"""

_SEVERITIES = {"High", "Medium", "Low"}
_PRIORITIES = {"Immediate", "Within 7 Days", "Monitor"}


def get_api_key() -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    return key or None


def ai_available() -> bool:
    return get_api_key() is not None


def dealer_payload(row) -> dict:
    """Structured, minimal input for the LLM (no free text from users)."""
    return {
        "dealer_id": row["dealer_id"],
        "dealer_name": row["dealer_name"],
        "region": row["region"],
        "health_score": int(row["health_score"]),
        "status": row["status"],
        "metrics": {
            "sales_achievement": round(float(row["sales_achievement_pct"]), 1),
            "sales_growth": round(float(row["sales_growth_pct"]), 1),
            "inventory_over_90_days": round(float(row["inventory_over_90_days_pct"]), 1),
            "payment_delay_days": round(float(row["payment_delay_days"]), 1),
            "service_score": round(float(row["service_score"]), 1),
            "complaints": int(row["customer_complaints"]),
            "market_potential": row["market_potential"],
        },
        "risk_drivers": [d["driver"] for d in row["drivers"]],
        "emerging_flags": list(row["flags"]),
    }


def validate_brief(data) -> dict:
    """Raise ValueError unless ``data`` matches the expected schema."""
    if not isinstance(data, dict):
        raise ValueError("brief is not an object")
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise ValueError("missing summary")
    concerns, actions = data.get("concerns"), data.get("actions")
    if not isinstance(concerns, list) or not isinstance(actions, list) or not actions:
        raise ValueError("concerns/actions missing")
    for c in concerns:
        if not isinstance(c, dict) or not all(isinstance(c.get(k), str) for k in ("issue", "evidence", "severity")):
            raise ValueError("bad concern")
        if c["severity"] not in _SEVERITIES:
            raise ValueError("bad severity")
    for a in actions:
        if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ("priority", "action", "reason", "owner")):
            raise ValueError("bad action")
        if a["priority"] not in _PRIORITIES:
            raise ValueError("bad priority")
    return data


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def generate_brief(payload: dict, fallback: dict) -> tuple[dict, str, str | None]:
    """Return ``(brief, source, notice)`` where source is ``"ai"`` or ``"rule"``."""
    key = get_api_key()
    if not key:
        return fallback, "rule", FALLBACK_NOTICE
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=1)
        # Opus 5 thinks adaptively by default, and thinking tokens count against
        # max_tokens - a small cap would truncate the JSON. Server-side fallbacks
        # re-run a policy-declined request on another model within the same call.
        msg = client.beta.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if msg.stop_reason == "refusal":
            return fallback, "rule", "AI brief was declined. Showing rule-based management recommendations instead."
        text = "".join(b.text for b in msg.content if b.type == "text")
        return validate_brief(_extract_json(text)), "ai", None
    except Exception as exc:  # network, auth, bad JSON, missing SDK ...
        return fallback, "rule", f"AI brief failed ({type(exc).__name__}). Showing rule-based management recommendations instead."


def brief_to_text(brief: dict, row) -> str:
    """Plain-text management brief (for display / download)."""
    lines = [
        f"DEALER {row['dealer_id']} - {row['dealer_name']} - MANAGEMENT BRIEF",
        "",
        f"Status: {row['status'].upper()}",
        f"Health Score: {int(row['health_score'])}/100",
        "",
        "Summary:",
        brief["summary"],
        "",
        "Key concerns:",
    ]
    for c in brief["concerns"]:
        lines.append(f"- [{c['severity']}] {c['issue']}: {c['evidence']}")
    lines += ["", "Recommended actions:"]
    for i, a in enumerate(brief["actions"], 1):
        lines.append(f"{i}. ({a['priority']}) {a['action']}")
        lines.append(f"   Why: {a['reason']}  |  Owner: {a['owner']}")
    lines += ["", "Decision support only - synthetic demonstration data; scores are prototype assumptions."]
    return "\n".join(lines)
