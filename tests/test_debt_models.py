"""Ported from debt_exposure_monitor/tests/test_models.py -- the
in-memory pipeline dataclasses (engines/debt_models.py), not the
SQLAlchemy persistence model (models/debt.py)."""
from __future__ import annotations

from engines.debt_models import LenderRecord, ScreeningHit, SupplierDebtProfile


class TestSupplierDebtProfile:
    def test_defaults(self):
        profile = SupplierDebtProfile(company_name="X", cik=1)
        assert profile.lenders == []
        assert profile.screening_hits == []
        assert profile.trace_available is False
        assert profile.trace_note == ""

    def test_cik_can_be_none_for_demo_entities(self):
        profile = SupplierDebtProfile(company_name="Fictional Co", cik=None)
        assert profile.cik is None


class TestLenderRecord:
    def test_all_fields_settable(self):
        record = LenderRecord(
            lender_name="A", canonical_name="A", instrument_type="bond",
            role="underwriter", amount_text="$1", evidence_quote="q", source_filing="10-K",
        )
        assert record.instrument_type == "bond"


class TestScreeningHit:
    def test_citation_defaults_empty(self):
        hit = ScreeningHit(list_name="OFAC SDN", lender_name="A", matched_name="B", score=90, detail="d")
        assert hit.citation == ""
