"""models/cfius.py — ported from cfius_screener/models.py, unchanged
shape, plus Screening.company_id -> Company. CFIUS's own facts mirror
jurisdiction_engine.TransactionFacts exactly, as in the original.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Screening(Base):
    __tablename__ = "cfius_screenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # NEW: links this screening to the shared cross-tool Company row (the
    # US business being screened -- CFIUS's own schema never had a CIK
    # field, only us_business_name below, so this is the first structured
    # cross-tool join key this data has ever had).
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)

    # --- facts (mirror jurisdiction_engine.TransactionFacts) ---------------
    us_business_name: Mapped[str] = mapped_column(String(300))
    us_business_description: Mapped[str] = mapped_column(Text, default="")
    acquirer_name: Mapped[str] = mapped_column(String(300))
    acquirer_country: Mapped[str] = mapped_column(String(100))
    foreign_govt_ownership_pct: Mapped[float] = mapped_column(Float, default=0.0)
    voting_interest_pct: Mapped[float] = mapped_column(Float, default=0.0)
    contractual_control_rights: Mapped[bool] = mapped_column(Boolean, default=False)
    board_seat: Mapped[bool] = mapped_column(Boolean, default=False)
    board_observer: Mapped[bool] = mapped_column(Boolean, default=False)
    access_nonpublic_tech_info: Mapped[bool] = mapped_column(Boolean, default=False)
    substantive_decision_role: Mapped[bool] = mapped_column(Boolean, default=False)
    produces_critical_tech: Mapped[bool] = mapped_column(Boolean, default=False)
    export_authorization_required: Mapped[bool] = mapped_column(Boolean, default=False)
    critical_infrastructure: Mapped[bool] = mapped_column(Boolean, default=False)
    sensitive_personal_data: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- determination ------------------------------------------------------
    outcome: Mapped[str] = mapped_column(String(40))
    covered_basis: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_tid: Mapped[bool] = mapped_column(Boolean, default=False)
    tid_categories_json: Mapped[str] = mapped_column(Text, default="[]")
    excepted_investor: Mapped[bool] = mapped_column(Boolean, default=False)
    mandatory_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    findings_json: Mapped[str] = mapped_column(Text, default="[]")

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Milestone 2 additions (nullable — only set on AI-intake path) -------
    intake_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    memo_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Milestone 3 additions ----------------------------------------------
    risk_score_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ofac_hits_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ofac_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
