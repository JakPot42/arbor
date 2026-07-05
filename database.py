"""database.py — SQLAlchemy engine and session plumbing.

Adopts ghosttrace/cfius_screener's convention verbatim (the two were
already line-for-line identical) rather than dib_monitor's third variant
(Base defined in models.py, no sessionmaker, lazy module-global engine,
hardcoded db-url string) — 2-of-3 agreement plus this is the more
idiomatic SQLAlchemy 2.0 pattern. One Base here means every tool's models
(models/company.py, models/ghosttrace.py, models/cfius.py, ...) register
on the same metadata, so init_db() creates every table in one call.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Every models module must be imported here (not just at call sites)
    # so its tables register on Base.metadata before create_all() runs —
    # same reason ghosttrace/cfius_screener's own init_db() imports models
    # inline rather than relying on some other module having imported them
    # first.
    from models.company import Company  # noqa: F401
    from models.ghosttrace import Entity, Filing, OwnershipLink, Trace  # noqa: F401
    from models.cfius import Screening  # noqa: F401
    from models.dib import EarningsSignal, FinancialAssessment, OwnershipRecord, Supplier  # noqa: F401

    Base.metadata.create_all(bind=engine)
