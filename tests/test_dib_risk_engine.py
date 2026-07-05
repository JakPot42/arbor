"""Ported from dib_monitor/tests/test_risk_engine.py."""
import pytest
from engines.dib_risk_engine import (
    compute_financial_risk,
    compute_ownership_risk,
    compute_combined_risk,
)


class TestComputeFinancialRisk:
    def test_low_risk_healthy_company(self):
        score, level = compute_financial_risk(
            debt_to_ebitda=2.0,
            distress_prob_1yr=0.01,
            distress_prob_3yr=0.03,
            going_concern_flag=False,
            near_term_maturity_mm=None,
        )
        assert level == "LOW"
        assert score < 25

    def test_high_risk_leveraged_company(self):
        score, level = compute_financial_risk(
            debt_to_ebitda=9.0,
            distress_prob_1yr=0.20,
            distress_prob_3yr=0.45,
            going_concern_flag=False,
            near_term_maturity_mm=400.0,
        )
        assert level in ("HIGH", "CRITICAL")
        assert score >= 50

    def test_going_concern_flag_raises_score(self):
        score_no_gc, _ = compute_financial_risk(2.0, 0.02, 0.05, False, None)
        score_gc, _ = compute_financial_risk(2.0, 0.02, 0.05, True, None)
        assert score_gc > score_no_gc

    def test_near_term_maturity_adds_points(self):
        score_no_mat, _ = compute_financial_risk(3.0, 0.05, 0.10, False, None)
        score_mat, _ = compute_financial_risk(3.0, 0.05, 0.10, False, 200.0)
        assert score_mat > score_no_mat

    def test_score_capped_at_100(self):
        score, _ = compute_financial_risk(
            debt_to_ebitda=20.0,
            distress_prob_1yr=1.0,
            distress_prob_3yr=1.0,
            going_concern_flag=True,
            near_term_maturity_mm=1000.0,
        )
        assert score <= 100

    def test_none_debt_to_ebitda_does_not_raise(self):
        score, level = compute_financial_risk(None, 0.05, 0.10, False, None)
        assert isinstance(score, int)

    def test_critical_threshold(self):
        _, level = compute_financial_risk(
            debt_to_ebitda=10.0,
            distress_prob_1yr=0.50,
            distress_prob_3yr=0.80,
            going_concern_flag=True,
            near_term_maturity_mm=500.0,
        )
        assert level == "CRITICAL"


class TestComputeOwnershipRisk:
    def test_empty_owners_is_low(self):
        score, level = compute_ownership_risk([])
        assert score == 0
        assert level == "LOW"

    def test_cfius_flagged_owner_raises_score(self):
        owners = [{"owner_name": "Suspect Fund", "pct_owned": 7.0, "country": "Cayman Islands",
                   "cfius_flag": True, "owner_type": "Hedge Fund"}]
        score, level = compute_ownership_risk(owners)
        assert score > 0
        assert level in ("MEDIUM", "HIGH", "CRITICAL")

    def test_clean_us_owners_is_low(self):
        owners = [
            {"owner_name": "Vanguard", "pct_owned": 12.0, "country": "United States",
             "cfius_flag": False, "owner_type": "Institution"},
            {"owner_name": "BlackRock", "pct_owned": 8.0, "country": "United States",
             "cfius_flag": False, "owner_type": "Institution"},
        ]
        score, level = compute_ownership_risk(owners)
        assert level == "LOW"

    def test_high_risk_country_adds_points(self):
        owners_clean = [{"owner_name": "X", "pct_owned": 5.0, "country": "Canada",
                         "cfius_flag": False, "owner_type": "Institution"}]
        owners_risky = [{"owner_name": "X", "pct_owned": 5.0, "country": "China",
                         "cfius_flag": False, "owner_type": "Institution"}]
        score_clean, _ = compute_ownership_risk(owners_clean)
        score_risky, _ = compute_ownership_risk(owners_risky)
        assert score_risky > score_clean

    def test_ownership_score_capped_at_100(self):
        owners = [
            {"owner_name": f"Suspect {i}", "pct_owned": 30.0, "country": "China",
             "cfius_flag": True, "owner_type": "Foreign Government"}
            for i in range(10)
        ]
        score, _ = compute_ownership_risk(owners)
        assert score <= 100


class TestComputeCombinedRisk:
    def test_blended_between_components(self):
        score, _ = compute_combined_risk(60, 40)
        assert score == 52

    def test_level_not_lower_than_highest_component(self):
        _, level = compute_combined_risk(60, 10)
        assert level in ("MEDIUM", "HIGH", "CRITICAL")

    def test_capped_at_100(self):
        score, _ = compute_combined_risk(100, 100)
        assert score <= 100
