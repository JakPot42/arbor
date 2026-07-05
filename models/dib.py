"""models/dib.py — ported from dib_monitor/dib_monitor/models.py.

Two real changes from the original, both fixes identified during the
Arbor architecture review, not preserved as-is:

1. **Real ForeignKeys added.** The original had `supplier_id`,
   `assessment_id` as plain `Integer` columns matched by convention only —
   no `ForeignKey()`, no `relationship()`, unlike GhostTrace's equivalent
   (`Entity.trace_id` is a real FK with a real `relationship()`). Every
   supplier_id/assessment_id below is now a real FK with a real
   `relationship()` back to `Supplier`. Cheap to fix now, before any data
   exists to migrate; expensive to discover later.

2. **Converted from classic `Column(...)` style to the `Mapped[]`/
   `mapped_column()` style GhostTrace/CFIUS/Company already use**, so all
   of Arbor's models read consistently. Field names, types, defaults, and
   nullability are otherwise unchanged from the original.

Note on `Supplier.cik`: kept as a `String` (matching the original — DIB
Monitor stores it zero-padded, e.g. "0000320193"), unlike GhostTrace's and
Company's `Integer` CIK. Routers must convert
(`int(cik_str)` if `cik_str` else `None`) before calling
`resolve_or_create_company()`, which expects an int.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Supplier(Base):
    __tablename__ = "dib_suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # NEW: links this supplier to the shared cross-tool Company row.
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    cik: Mapped[str | None] = mapped_column(String, nullable=True)  # zero-padded 10-digit string, per original
    sector: Mapped[str] = mapped_column(String, default="Defense Electronics")
    dib_category: Mapped[str] = mapped_column(String, default="Tier 1 Subcontractor")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    assessments: Mapped[list["FinancialAssessment"]] = relationship(
        "FinancialAssessment", back_populates="supplier", cascade="all, delete-orphan"
    )
    ownership_records: Mapped[list["OwnershipRecord"]] = relationship(
        "OwnershipRecord", back_populates="supplier", cascade="all, delete-orphan"
    )
    earnings_signals: Mapped[list["EarningsSignal"]] = relationship(
        "EarningsSignal", back_populates="supplier", cascade="all, delete-orphan"
    )


class FinancialAssessment(Base):
    __tablename__ = "dib_financial_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("dib_suppliers.id"), nullable=False, index=True)
    filing_type: Mapped[str] = mapped_column(String, default="10-K")
    filing_period: Mapped[str | None] = mapped_column(String, nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # Extracted financial metrics (all in millions USD)
    revenue_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ebitda_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_service_annual_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_to_ebitda: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Claude-extracted narrative fields
    covenant_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    going_concern_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    going_concern_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    near_term_maturity_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    near_term_maturity_date: Mapped[str | None] = mapped_column(String, nullable=True)
    claude_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(String, default="demo")

    # Monte Carlo results
    distress_prob_1yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    distress_prob_2yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    distress_prob_3yr: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Risk scoring
    financial_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    financial_risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    ownership_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ownership_risk_level: Mapped[str | None] = mapped_column(String, nullable=True)
    combined_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    combined_risk_level: Mapped[str | None] = mapped_column(String, nullable=True)

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="assessments")


class OwnershipRecord(Base):
    __tablename__ = "dib_ownership_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("dib_suppliers.id"), nullable=False, index=True)
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("dib_financial_assessments.id"), nullable=True, index=True
    )
    quarter: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_name: Mapped[str] = mapped_column(String, nullable=False)
    owner_type: Mapped[str] = mapped_column(String, default="Institution")
    pct_owned: Mapped[float | None] = mapped_column(Float, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    cfius_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String, nullable=True)

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="ownership_records")


class EarningsSignal(Base):
    __tablename__ = "dib_earnings_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("dib_suppliers.id"), nullable=False, index=True)
    filing_date: Mapped[str | None] = mapped_column(String, nullable=True)
    accession_number: Mapped[str | None] = mapped_column(String, nullable=True)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    export_control_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    supplier_diversion_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    key_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_brief: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_confidence: Mapped[str] = mapped_column(String, default="demo")

    supplier: Mapped[Supplier] = relationship("Supplier", back_populates="earnings_signals")
