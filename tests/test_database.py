from __future__ import annotations

from sqlalchemy import inspect, text

from database import engine, get_db, init_db


def test_init_db_creates_companies_table():
    init_db()
    inspector = inspect(engine)
    assert "companies" in inspector.get_table_names()


def test_get_db_yields_a_working_session():
    gen = get_db()
    session = next(gen)
    try:
        assert session is not None
        session.execute(text("SELECT 1"))
    finally:
        gen.close()
