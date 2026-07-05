"""engines/debt_models.py — Debt Exposure Monitor's original in-memory
dataclasses (debt_exposure_monitor/models.py), ported verbatim. This is
the pipeline's working shape; models/debt.py (SQLAlchemy) is what a
completed run gets persisted into.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LenderRecord:
    """One lender/counterparty extracted from a filing. Claude produces
    these (engines/debt_claude_lender_extractor.py); nothing here scores
    or flags -- that's engines/debt_risk_engine.py's job, working from the
    canonical_name field engines/debt_entity_resolver.dedupe_lenders()
    fills in."""

    lender_name: str
    canonical_name: str
    instrument_type: str      # "credit_facility" | "bond" | "term_loan" | "syndicated_loan" | "other"
    role: str                  # "administrative_agent" | "lender" | "underwriter" | "trustee" | "unspecified"
    amount_text: str
    evidence_quote: str
    source_filing: str         # e.g. "10-K filed 2025-02-14"


@dataclass
class ScreeningHit:
    list_name: str             # "OFAC SDN" | "BIS Export Control List" | "Foreign State-Connected Lender"
    lender_name: str
    matched_name: str
    score: int
    detail: str                 # program / source list / country+basis, depending on list_name
    citation: str = ""


@dataclass
class SupplierDebtProfile:
    company_name: str
    cik: int | None
    lenders: list[LenderRecord] = field(default_factory=list)
    screening_hits: list[ScreeningHit] = field(default_factory=list)
    trace_available: bool = False
    trace_note: str = ""
