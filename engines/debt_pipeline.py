"""engines/debt_pipeline.py — orchestrates a live trace: EDGAR fetch ->
Claude extraction -> lender deduplication -> OFAC/BIS/foreign-state
screening -> FINRA TRACE status. Ported from debt_exposure_monitor/pipeline.py.

Uses shared/edgar_client.py (get_company_candidates, get_debt_relevant_filings,
fetch_document_text) instead of a second EDGAR client -- Debt Exposure
Monitor's original edgar_client.py is exactly what shared/edgar_client.py's
get_debt_relevant_filings() strategy was built from in step 1.
"""
from __future__ import annotations

import shared.edgar_client as edgar_client
import engines.debt_trace_client as trace_client
from engines.debt_claude_lender_extractor import extract_lenders
from engines.debt_entity_resolver import dedupe_lenders
from engines.debt_models import SupplierDebtProfile
from engines.debt_screening import screen_lenders


class CompanyNotFoundError(Exception):
    pass


class AmbiguousCompanyError(Exception):
    def __init__(self, candidates: list[dict]):
        self.candidates = candidates
        super().__init__(f"{len(candidates)} candidates match; disambiguate by ticker or exact name.")


def build_profile(company_query: str) -> SupplierDebtProfile:
    candidates = edgar_client.get_company_candidates(company_query)
    if not candidates:
        raise CompanyNotFoundError(f"No EDGAR-registered company matches {company_query!r}.")
    if len(candidates) > 1 and candidates[0]["ticker"].lower() != company_query.strip().lower():
        raise AmbiguousCompanyError(candidates)

    company = candidates[0]
    cik = company["cik"]

    filings = edgar_client.get_debt_relevant_filings(cik)

    all_lenders = []
    for filing in filings:
        text = edgar_client.fetch_document_text(cik, filing["accession_number"], filing["primary_document"])
        label = f"{filing['form']} filed {filing['filing_date']}"
        all_lenders.extend(extract_lenders(text, label))

    name_map = dedupe_lenders([l.lender_name for l in all_lenders])
    for lender in all_lenders:
        lender.canonical_name = name_map[lender.lender_name]

    canonical_names = sorted({l.canonical_name for l in all_lenders})
    hits = screen_lenders(canonical_names)

    trace = trace_client.fetch_bond_activity(cik)

    return SupplierDebtProfile(
        company_name=company["name"],
        cik=cik,
        lenders=all_lenders,
        screening_hits=hits,
        trace_available=trace.available,
        trace_note=trace.reason,
    )
