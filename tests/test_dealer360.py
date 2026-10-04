"""Core tests (unittest style: run with `python -m unittest` or `pytest`)."""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest import mock

import pandas as pd

from src import ai_engine
from src.generate_data import generate
from src.recommendations import rule_based_brief
from src.risk_engine import analyze
from src.validation import DataValidationError, validate

BASE = dict(
    dealer_id="X1", dealer_name="Test Motors", region="West", city="Pune", market_potential="Medium",
    monthly_sales=100, monthly_target=100, sales_growth_pct=5, inventory_over_90_days_pct=8,
    payment_delay_days=2, service_score=88, customer_complaints=8,
)


def make(rows: list[dict]) -> pd.DataFrame:
    out = []
    for i, r in enumerate(rows):
        d = dict(BASE)
        d.update(r)
        d["dealer_id"] = d.get("dealer_id", f"X{i}") if "dealer_id" in r else f"X{i}"
        out.append(d)
    return pd.DataFrame(out)


def run(rows: list[dict]) -> pd.DataFrame:
    # surround with neutral peers so complaint percentiles are meaningful
    peers = [dict(dealer_id=f"P{i}", customer_complaints=8 + i % 5) for i in range(12)]
    df = make(peers + rows)
    clean, _ = validate(df)
    return analyze(clean)


class TestScoring(unittest.TestCase):
    def test_1_high_performer_scores_high(self):
        res = run([dict(dealer_id="TOP", monthly_sales=118, sales_growth_pct=14, inventory_over_90_days_pct=3,
                        payment_delay_days=1, service_score=92, customer_complaints=2, market_potential="High")])
        r = res[res.dealer_id == "TOP"].iloc[0]
        self.assertGreaterEqual(r["health_score"], 85)
        self.assertEqual(r["status"], "Healthy")

    def test_2_deteriorating_dealer_is_critical(self):
        res = run([dict(dealer_id="BAD", monthly_sales=55, sales_growth_pct=-20, inventory_over_90_days_pct=42,
                        payment_delay_days=28, service_score=55, customer_complaints=40, market_potential="Low")])
        r = res[res.dealer_id == "BAD"].iloc[0]
        self.assertEqual(r["status"], "Critical")
        self.assertEqual(r["priority_code"], "P0")

    def test_3_high_sales_but_poor_operations_not_healthy(self):
        res = run([dict(dealer_id="RISKY", monthly_sales=110, sales_growth_pct=12, inventory_over_90_days_pct=35,
                        payment_delay_days=20, service_score=78, customer_complaints=40, market_potential="Medium")])
        r = res[res.dealer_id == "RISKY"].iloc[0]
        self.assertNotEqual(r["status"], "Healthy")
        self.assertTrue(r["hidden_risk"])
        self.assertEqual(r["sustainability"], "At Risk")

    def test_4_missing_optional_fields_do_not_crash(self):
        df = make([dict(dealer_id=f"A{i}") for i in range(5)])
        self.assertNotIn("complaint_rate", df.columns)
        clean, _ = validate(df)
        res = analyze(clean)
        self.assertEqual(len(res), 5)
        self.assertTrue(res["health_score"].between(0, 100).all())

    def test_5_invalid_required_columns_give_useful_error(self):
        df = make([{}]).drop(columns=["payment_delay_days", "service_score"])
        with self.assertRaises(DataValidationError) as ctx:
            validate(df)
        self.assertIn("payment_delay_days", str(ctx.exception))
        with self.assertRaises(DataValidationError):
            validate(pd.DataFrame())

    def test_6_no_api_key_still_gives_recommendations(self):
        res = run([dict(dealer_id="BAD", monthly_sales=60, sales_growth_pct=-15, inventory_over_90_days_pct=30,
                        payment_delay_days=18, service_score=68, customer_complaints=30, market_potential="High")])
        r = res[res.dealer_id == "BAD"].iloc[0]
        self.assertGreater(len(r["actions"]), 0)
        fallback = rule_based_brief(r, r["drivers"], r["actions"])
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            brief, source, notice = ai_engine.generate_brief(ai_engine.dealer_payload(r), fallback)
        self.assertEqual(source, "rule")
        self.assertIn("rule-based", notice)
        ai_engine.validate_brief(brief)  # fallback conforms to the AI schema


class TestValidationAndAI(unittest.TestCase):
    def test_data_quality_warnings(self):
        df = make([dict(dealer_id="A"), dict(dealer_id="A"), dict(dealer_id="B", monthly_target=0),
                   dict(dealer_id="C", service_score=140, market_potential="huge"),
                   dict(dealer_id="D", payment_delay_days=-3)])
        clean, warns = validate(df)
        text = " ".join(warns)
        self.assertIn("duplicate", text)
        self.assertIn("target", text)
        self.assertIn("market_potential", text)
        self.assertNotIn("B", clean.dealer_id.tolist())
        self.assertLessEqual(clean.service_score.max(), 100)
        self.assertGreaterEqual(clean.payment_delay_days.min(), 0)

    def test_ai_failure_falls_back(self):
        df, _ = validate(make([dict(dealer_id="A", monthly_sales=60)] * 1))
        r = analyze(df).iloc[0]
        fallback = rule_based_brief(r, r["drivers"], r["actions"])
        fake_sdk = types.SimpleNamespace(Anthropic=mock.Mock(side_effect=RuntimeError("boom")))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}), \
                mock.patch.dict(sys.modules, {"anthropic": fake_sdk}):
            brief, source, notice = ai_engine.generate_brief(ai_engine.dealer_payload(r), fallback)
        self.assertEqual(source, "rule")
        self.assertIn("failed", notice)

    def test_validate_brief_rejects_bad_schema(self):
        with self.assertRaises(ValueError):
            ai_engine.validate_brief({"summary": "x", "concerns": [], "actions": [{"priority": "Soon"}]})


class TestSyntheticDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = analyze(validate(generate())[0])

    def test_size_and_mix(self):
        counts = self.res["status"].value_counts().to_dict()
        self.assertEqual(len(self.res), 100)
        self.assertTrue(10 <= counts["Critical"] <= 15)
        self.assertTrue(20 <= counts["Watch"] <= 30)
        self.assertTrue(55 <= counts["Healthy"] <= 70)

    def test_demo_dealer_d014(self):
        r = self.res[self.res.dealer_id == "D014"].iloc[0]
        self.assertEqual(r["dealer_name"], "Mumbai Central Motors")
        self.assertEqual(r["status"], "Critical")
        self.assertTrue(30 <= r["health_score"] <= 40)
        self.assertEqual(self.res.sort_values("risk_score", ascending=False).iloc[0]["dealer_id"], "D014")
        keys = [d["key"] for d in r["drivers"]]
        for k in ("sales", "inventory", "payment"):
            self.assertIn(k, keys)
        self.assertEqual([a["category"] for a in r["actions"][:3]], ["inventory", "payment", "sales"])

    def test_edge_cases(self):
        by = self.res.set_index("dealer_id")
        self.assertTrue(by.loc["D027", "hidden_risk"])
        self.assertTrue(by.loc["D041", "hidden_risk"])
        self.assertNotEqual(by.loc["D041", "status"], "Healthy")
        self.assertEqual(by.loc["D058", "status"], "Healthy")
        self.assertTrue(by.loc["D058", "growth_opportunity"])
        self.assertIn("Untapped market opportunity", by.loc["D063", "flags"])
        self.assertTrue(by.loc["D077", "growth_opportunity"])
        self.assertEqual(by.loc["D077", "status"], "Healthy")


if __name__ == "__main__":
    unittest.main()
