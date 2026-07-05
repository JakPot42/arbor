from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from models.company import Company


def test_aliases_defaults_to_empty_list(db_session):
    c = Company(canonical_name="Acme Corp")
    db_session.add(c)
    db_session.flush()
    assert c.aliases == []


def test_aliases_round_trip(db_session):
    c = Company(canonical_name="Acme Corp")
    c.aliases = ["Acme", "Acme Corporation"]
    db_session.add(c)
    db_session.flush()
    db_session.refresh(c)
    assert c.aliases == ["Acme", "Acme Corporation"]


def test_cik_is_nullable(db_session):
    c = Company(canonical_name="No CIK Yet Inc")
    db_session.add(c)
    db_session.flush()
    assert c.id is not None
    assert c.cik is None


def test_multiple_null_ciks_allowed(db_session):
    # Standard SQL: a UNIQUE constraint permits multiple NULLs.
    db_session.add(Company(canonical_name="Company A"))
    db_session.add(Company(canonical_name="Company B"))
    db_session.flush()  # must not raise


def test_duplicate_cik_rejected(db_session):
    db_session.add(Company(canonical_name="Company A", cik=123))
    db_session.flush()
    db_session.add(Company(canonical_name="Company A Duplicate", cik=123))
    with pytest.raises(IntegrityError):
        db_session.flush()
