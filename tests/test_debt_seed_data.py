"""Ported from debt_exposure_monitor/tests/test_seed_data.py -- the
fictional demo defense supplier. Also covers load_seed_data(db), which
is net-new (the original CLI had no persistence)."""
from __future__ import annotations

import engines.debt_seed_data as seed_data
from models.company import Company
from models.debt import DebtProfile


class TestDemoLenders:
    def test_includes_a_foreign_state_connected_lender(self):
        names = {l.canonical_name for l in seed_data.DEMO_LENDERS}
        assert "China Development Bank" in names

    def test_includes_an_ofac_relevant_lender(self):
        names = {l.canonical_name for l in seed_data.DEMO_LENDERS}
        assert "VTB Bank" in names

    def test_includes_clean_us_banks_too(self):
        # The demo shouldn't be all-red -- a realistic mix includes normal lenders.
        names = {l.canonical_name for l in seed_data.DEMO_LENDERS}
        assert "JPMorgan Chase Bank, N.A." in names
        assert "Goldman Sachs & Co. LLC" in names

    def test_every_lender_has_an_evidence_quote(self):
        assert all(l.evidence_quote.strip() for l in seed_data.DEMO_LENDERS)

    def test_company_name_marked_fictional(self):
        assert "fictional" in seed_data.DEMO_COMPANY_NAME.lower()


class TestBuildDemoProfile:
    def test_wires_provided_screening_hits(self):
        profile = seed_data.build_demo_profile(screening_hits=["placeholder"])
        assert profile.screening_hits == ["placeholder"]

    def test_trace_marked_unavailable(self):
        profile = seed_data.build_demo_profile(screening_hits=[])
        assert profile.trace_available is False
        assert profile.trace_note


class TestLoadSeedData:
    def test_creates_one_debt_profile(self, db_session):
        seed_data.load_seed_data(db_session)
        assert db_session.query(DebtProfile).filter_by(is_demo=True).count() == 1

    def test_idempotent(self, db_session):
        seed_data.load_seed_data(db_session)
        seed_data.load_seed_data(db_session)
        assert db_session.query(DebtProfile).filter_by(is_demo=True).count() == 1

    def test_resolves_against_shared_company_table(self, db_session):
        seed_data.load_seed_data(db_session)
        row = db_session.query(DebtProfile).filter_by(is_demo=True).first()
        assert row.company_id is not None
        company = db_session.get(Company, row.company_id)
        assert company is not None
        assert company.canonical_name == seed_data.DEMO_COMPANY_NAME
