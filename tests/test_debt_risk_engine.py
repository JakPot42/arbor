"""Ported from debt_exposure_monitor/tests/test_risk_engine.py --
deterministic scoring only."""
from __future__ import annotations

from engines.debt_models import LenderRecord, ScreeningHit, SupplierDebtProfile
from engines.debt_risk_engine import compute_concentration, score_debt_profile


def _lender(name, canonical=None):
    return LenderRecord(
        lender_name=name, canonical_name=canonical or name,
        instrument_type="credit_facility", role="lender",
        amount_text="", evidence_quote="", source_filing="10-K",
    )


class TestComputeConcentration:
    def test_no_lenders(self):
        result = compute_concentration([])
        assert result["hhi"] == 0
        assert result["tier"] == "NONE"

    def test_single_lender_max_concentration(self):
        result = compute_concentration([_lender("A"), _lender("A"), _lender("A")])
        assert result["hhi"] == 10000
        assert result["tier"] == "HIGH"

    def test_five_evenly_split_lenders_low_concentration(self):
        lenders = [_lender("A"), _lender("B"), _lender("C"), _lender("D"), _lender("E")]
        result = compute_concentration(lenders)
        assert result["hhi"] == 2000  # 5 equal 20% shares -> 5*400=2000, below the 2500 MODERATE threshold
        assert result["tier"] == "LOW"

    def test_four_evenly_split_lenders_moderate_at_boundary(self):
        lenders = [_lender("A"), _lender("B"), _lender("C"), _lender("D")]
        result = compute_concentration(lenders)
        assert result["hhi"] == 2500  # 4 equal 25% shares -> 4*625=2500, at the MODERATE threshold (inclusive)
        assert result["tier"] == "MODERATE"

    def test_two_evenly_split_lenders_moderate(self):
        lenders = [_lender("A"), _lender("B")]
        result = compute_concentration(lenders)
        assert result["hhi"] == 5000
        assert result["tier"] == "HIGH"  # >= CONCENTRATION_HHI_HIGH

    def test_lender_shares_sum_to_100(self):
        lenders = [_lender("A"), _lender("A"), _lender("B")]
        result = compute_concentration(lenders)
        assert round(sum(result["lender_shares"].values())) == 100


class TestScoreDebtProfile:
    def test_no_hits_low_score(self):
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1,
            lenders=[_lender("A"), _lender("B"), _lender("C"), _lender("D")],
            screening_hits=[],
        )
        risk = score_debt_profile(profile)
        assert risk["ofac_hit_count"] == 0
        assert risk["score"] == 0
        assert risk["tier"] == "LOW"

    def test_ofac_hit_raises_score(self):
        # Four distinct lenders keeps concentration LOW so only the OFAC
        # weight is under test here.
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1,
            lenders=[_lender("A"), _lender("B"), _lender("C"), _lender("D"), _lender("E")],
            screening_hits=[ScreeningHit(list_name="OFAC SDN", lender_name="A", matched_name="A", score=95, detail="")],
        )
        risk = score_debt_profile(profile)
        assert risk["ofac_hit_count"] == 1
        assert risk["score"] == 35

    def test_multiple_signal_types_stack(self):
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1,
            lenders=[_lender("A"), _lender("B"), _lender("C"), _lender("D"), _lender("E")],
            screening_hits=[
                ScreeningHit(list_name="OFAC SDN", lender_name="A", matched_name="A", score=95, detail=""),
                ScreeningHit(list_name="BIS Export Control List", lender_name="A", matched_name="A", score=95, detail=""),
                ScreeningHit(list_name="Foreign State-Connected Lender", lender_name="A", matched_name="A", score=95, detail=""),
            ],
        )
        risk = score_debt_profile(profile)
        assert risk["score"] == 35 + 35 + 20

    def test_high_concentration_adds_points(self):
        # A single lender across every disclosed relationship = 100% share
        # = HHI 10000 = HIGH concentration tier -> +15 points on top of
        # any screening hits.
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1,
            lenders=[_lender("A"), _lender("A"), _lender("A")],
            screening_hits=[],
        )
        risk = score_debt_profile(profile)
        assert risk["concentration"]["tier"] == "HIGH"
        assert risk["score"] == 15

    def test_score_capped_at_100(self):
        hits = [ScreeningHit(list_name="OFAC SDN", lender_name=f"L{i}", matched_name="X", score=95, detail="") for i in range(5)]
        profile = SupplierDebtProfile(company_name="Test Co", cik=1, lenders=[_lender("A")], screening_hits=hits)
        risk = score_debt_profile(profile)
        assert risk["score"] == 100

    def test_tier_boundaries(self):
        from engines.debt_risk_engine import _tier_for_score
        for score, expected_tier in [
            (0, "LOW"), (25, "LOW"), (26, "MEDIUM"), (50, "MEDIUM"),
            (51, "HIGH"), (75, "HIGH"), (76, "CRITICAL"), (100, "CRITICAL"),
        ]:
            assert _tier_for_score(score) == expected_tier
