"""models/brief.py — Pre-Acquisition Brief Generator's persistence layer.

Net-new: the original CLI tool had zero persistence (every dataclass in
its models.py -- IPPortfolio, LitigationProfile, RegulatoryExposure,
ContractProfile, AcquisitionBrief -- existed only for the duration of one
CLI invocation). One table, not five, following the same JSON-blob
convention as models/debt.py: each domain profile's summary fields plus
its nested list (patents/cases/awards) are stored as one JSON column
under a single AcquisitionBrief row per analysis run, rather than four
more relational tables for what is fundamentally point-in-time report
data. `engines/brief_models.py` keeps the original dataclasses as the
pipeline's in-memory working shape.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AcquisitionBrief(Base):
    __tablename__ = "brief_acquisition_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(300))
    # No CIK anywhere in this tool's original codebase (per the Arbor
    # architecture review) -- company resolution here is name-only, same
    # as CFIUS Screener.
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    prepared_date: Mapped[str] = mapped_column(String(20))

    ip_json: Mapped[str] = mapped_column(Text)
    litigation_json: Mapped[str] = mapped_column(Text)
    regulatory_json: Mapped[str] = mapped_column(Text)
    contract_json: Mapped[str] = mapped_column(Text)

    overall_risk_tier: Mapped[str] = mapped_column(String(20))
    diligence_questions_json: Mapped[str] = mapped_column(Text, default="[]")
    executive_summary: Mapped[str] = mapped_column(Text)
    full_text: Mapped[str] = mapped_column(Text)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
