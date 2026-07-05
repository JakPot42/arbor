"""Ported from debt_exposure_monitor/tests/test_brief.py -- DEMO_MODE
deterministic path only (no network). Renamed test_debt_risk_brief.py to
match engines/debt_risk_brief.py's rename (avoids reading as the OTHER
brief tool, Pre-Acquisition Brief Generator)."""
from __future__ import annotations

from engines.debt_models import LenderRecord, ScreeningHit, SupplierDebtProfile
from engines.debt_risk_brief import generate_brief
from engines.debt_risk_engine import score_debt_profile


def _lender(name):
    return LenderRecord(
        lender_name=name, canonical_name=name, instrument_type="credit_facility",
        role="lender", amount_text="", evidence_quote="", source_filing="10-K",
    )


class TestGenerateBrief:
    def test_mentions_company_name(self):
        profile = SupplierDebtProfile(company_name="Test Defense Co", cik=1, lenders=[_lender("A")], screening_hits=[])
        risk = score_debt_profile(profile)
        text = generate_brief(profile, risk)
        assert "Test Defense Co" in text

    def test_mentions_score_and_tier(self):
        profile = SupplierDebtProfile(company_name="Test Co", cik=1, lenders=[_lender("A")], screening_hits=[])
        risk = score_debt_profile(profile)
        text = generate_brief(profile, risk)
        assert str(risk["score"]) in text
        assert risk["tier"] in text

    def test_mentions_ofac_hit_count_when_present(self):
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1,
            lenders=[_lender("A"), _lender("B"), _lender("C")],
            screening_hits=[ScreeningHit(list_name="OFAC SDN", lender_name="A", matched_name="A", score=95, detail="")],
        )
        risk = score_debt_profile(profile)
        text = generate_brief(profile, risk)
        assert "OFAC" in text

    def test_clean_profile_states_no_matches(self):
        profile = SupplierDebtProfile(company_name="Test Co", cik=1, lenders=[_lender("A")], screening_hits=[])
        risk = score_debt_profile(profile)
        text = generate_brief(profile, risk)
        assert "No OFAC, BIS, or foreign state-connected lender matches" in text

    def test_mentions_trace_unavailability(self):
        profile = SupplierDebtProfile(
            company_name="Test Co", cik=1, lenders=[_lender("A")], screening_hits=[],
            trace_available=False, trace_note="Historical Data Agreement required",
        )
        risk = score_debt_profile(profile)
        text = generate_brief(profile, risk)
        assert "FINRA TRACE" in text
        assert "Historical Data Agreement" in text
