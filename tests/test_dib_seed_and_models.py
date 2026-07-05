"""Ported from dib_monitor/tests/test_seed_and_models.py. Uses the shared
conftest.py `db_session` fixture instead of the original's own isolated
in-memory engine."""
import pytest

from models.dib import FinancialAssessment, OwnershipRecord, Supplier
from engines.dib_seed_data import load_seed_data


class TestSeedData:
    def test_seed_creates_two_suppliers(self, db_session):
        load_seed_data(db_session)
        assert db_session.query(Supplier).count() == 2

    def test_seed_idempotent(self, db_session):
        load_seed_data(db_session)
        load_seed_data(db_session)
        assert db_session.query(Supplier).count() == 2

    def test_arrowhead_is_high_risk(self, db_session):
        load_seed_data(db_session)
        arrowhead = db_session.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        assert arrowhead is not None
        assessment = (
            db_session.query(FinancialAssessment)
            .filter(FinancialAssessment.supplier_id == arrowhead.id)
            .first()
        )
        assert assessment.combined_risk_level in ("HIGH", "CRITICAL")

    def test_meridian_is_low_risk(self, db_session):
        load_seed_data(db_session)
        meridian = db_session.query(Supplier).filter(Supplier.name.like("%Meridian%")).first()
        assert meridian is not None
        assessment = (
            db_session.query(FinancialAssessment)
            .filter(FinancialAssessment.supplier_id == meridian.id)
            .first()
        )
        assert assessment.combined_risk_level == "LOW"

    def test_arrowhead_has_cfius_flagged_owner(self, db_session):
        load_seed_data(db_session)
        arrowhead = db_session.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        flagged = (
            db_session.query(OwnershipRecord)
            .filter(
                OwnershipRecord.supplier_id == arrowhead.id,
                OwnershipRecord.cfius_flag.is_(True),
            )
            .count()
        )
        assert flagged >= 1

    def test_meridian_has_no_cfius_flags(self, db_session):
        load_seed_data(db_session)
        meridian = db_session.query(Supplier).filter(Supplier.name.like("%Meridian%")).first()
        flagged = (
            db_session.query(OwnershipRecord)
            .filter(
                OwnershipRecord.supplier_id == meridian.id,
                OwnershipRecord.cfius_flag.is_(True),
            )
            .count()
        )
        assert flagged == 0

    def test_distress_probabilities_stored(self, db_session):
        load_seed_data(db_session)
        arrowhead = db_session.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        a = (
            db_session.query(FinancialAssessment)
            .filter(FinancialAssessment.supplier_id == arrowhead.id)
            .first()
        )
        assert a.distress_prob_1yr is not None
        assert a.distress_prob_3yr > a.distress_prob_1yr

    def test_assessment_has_debt_to_ebitda(self, db_session):
        load_seed_data(db_session)
        arrowhead = db_session.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        a = (
            db_session.query(FinancialAssessment)
            .filter(FinancialAssessment.supplier_id == arrowhead.id)
            .first()
        )
        assert a.debt_to_ebitda is not None
        assert a.debt_to_ebitda > 6.0  # Arrowhead is highly leveraged

    def test_seed_resolves_companies(self, db_session):
        """New behavior vs. the original: each seeded supplier resolves
        against the shared Company table."""
        from models.company import Company
        load_seed_data(db_session)
        arrowhead = db_session.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        assert arrowhead.company_id is not None
        company = db_session.get(Company, arrowhead.company_id)
        assert company is not None
        assert company.canonical_name == "Arrowhead Defense Systems"


class TestModels:
    def test_supplier_defaults(self, db_session):
        s = Supplier(name="Test Corp")
        db_session.add(s)
        db_session.commit()
        assert s.sector == "Defense Electronics"
        assert s.dib_category == "Tier 1 Subcontractor"
        assert s.is_demo is False

    def test_ownership_record_cfius_default_false(self, db_session):
        s = Supplier(name="Test Corp")
        db_session.add(s)
        db_session.commit()
        o = OwnershipRecord(supplier_id=s.id, owner_name="Vanguard", pct_owned=10.0)
        db_session.add(o)
        db_session.commit()
        assert o.cfius_flag is False
