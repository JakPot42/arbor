"""models/debt.py — Debt Exposure Monitor's persistence layer.

Net-new: the original CLI tool had zero persistence at all (pipeline.py's
SupplierDebtProfile was an in-memory dataclass, gone the moment the CLI
process exited). One table, not one table per nested dataclass
(LenderRecord, ScreeningHit) — same convention CFIUS's Screening
(findings_json) and DIB's EarningsSignal (signals_json) already use for
point-in-time nested report data that doesn't need independent relational
identity. `engines/debt_models.py` keeps the original dataclasses as the
pipeline's in-memory working shape; this is the row a completed run gets
persisted into.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DebtProfile(Base):
    __tablename__ = "debt_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(300))
    # Nullable: the demo scenario (a fictional company) has no real CIK,
    # same reasoning as Company.cik being nullable.
    cik: Mapped[int | None] = mapped_column(Integer, nullable=True)

    lenders_json: Mapped[str] = mapped_column(Text, default="[]")
    screening_hits_json: Mapped[str] = mapped_column(Text, default="[]")
    trace_available: Mapped[bool] = mapped_column(Boolean, default=False)
    trace_note: Mapped[str] = mapped_column(Text, default="")

    risk_score_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    brief_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
