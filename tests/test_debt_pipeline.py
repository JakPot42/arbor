"""Ported from debt_exposure_monitor/tests/test_pipeline.py -- every
external call (EDGAR, Claude, screening, TRACE) mocked, so this tests
only the orchestration logic.

Patch targets updated for where engines/debt_pipeline.py actually
imported these names: `import shared.edgar_client as edgar_client`
(patch.object on the same module object works regardless of which name
aliases it), `from engines.debt_claude_lender_extractor import
extract_lenders` and `from engines.debt_screening import screen_lenders`
(both bind new names in debt_pipeline's own namespace, so patched via
"engines.debt_pipeline.X"), and `import engines.debt_trace_client as
trace_client` (patched via "engines.debt_pipeline.trace_client.X").
"""
from __future__ import annotations

from unittest.mock import patch

import shared.edgar_client as edgar_client
import engines.debt_pipeline as pipeline
from engines.debt_models import LenderRecord
from engines.debt_trace_client import TraceResult


def _lender(name):
    return LenderRecord(
        lender_name=name, canonical_name=name, instrument_type="credit_facility",
        role="lender", amount_text="", evidence_quote="", source_filing="10-K",
    )


class TestBuildProfile:
    def test_no_candidates_raises_not_found(self):
        with patch.object(edgar_client, "get_company_candidates", return_value=[]):
            try:
                pipeline.build_profile("Nonexistent Corp")
                assert False, "expected CompanyNotFoundError"
            except pipeline.CompanyNotFoundError:
                pass

    def test_ambiguous_name_match_raises_with_candidates(self):
        # Neither candidate's ticker exactly matches the free-text query --
        # a genuine name-search ambiguity, not a disambiguated ticker search.
        candidates = [
            {"cik": 1, "ticker": "ABCD", "name": "ABC Defense Systems"},
            {"cik": 2, "ticker": "ABCH", "name": "ABC Holdings Group"},
        ]
        with patch.object(edgar_client, "get_company_candidates", return_value=candidates):
            try:
                pipeline.build_profile("ABC")
                assert False, "expected AmbiguousCompanyError"
            except pipeline.AmbiguousCompanyError as exc:
                assert len(exc.candidates) == 2

    def test_exact_ticker_match_not_treated_as_ambiguous(self):
        candidates = [
            {"cik": 1, "ticker": "ABC", "name": "ABC Defense Systems"},
            {"cik": 2, "ticker": "XYZ", "name": "ABC Holdings Group"},
        ]
        with patch.object(edgar_client, "get_company_candidates", return_value=candidates), \
             patch.object(edgar_client, "get_debt_relevant_filings", return_value=[]), \
             patch("engines.debt_pipeline.screen_lenders", return_value=[]), \
             patch("engines.debt_pipeline.trace_client.fetch_bond_activity", return_value=TraceResult(False, "no agreement", [])):
            profile = pipeline.build_profile("ABC")
        assert profile.cik == 1

    def test_full_pipeline_wires_lenders_through_dedup_and_screening(self):
        candidates = [{"cik": 99, "ticker": "MDS", "name": "Meridian Defense Systems"}]
        filings = [{"form": "10-K", "accession_number": "0001-25-000001", "primary_document": "a.htm", "filing_date": "2025-02-14"}]
        extracted = [_lender("JPMorgan Chase Bank, N.A."), _lender("JPMorgan Chase Bank N.A.")]

        with patch.object(edgar_client, "get_company_candidates", return_value=candidates), \
             patch.object(edgar_client, "get_debt_relevant_filings", return_value=filings), \
             patch.object(edgar_client, "fetch_document_text", return_value="filing text"), \
             patch("engines.debt_pipeline.extract_lenders", return_value=extracted), \
             patch("engines.debt_pipeline.screen_lenders", return_value=[]) as mock_screen, \
             patch("engines.debt_pipeline.trace_client.fetch_bond_activity", return_value=TraceResult(False, "no agreement", [])):
            profile = pipeline.build_profile("Meridian Defense")

        assert profile.company_name == "Meridian Defense Systems"
        assert profile.cik == 99
        # dedup should have collapsed the two spelling variants to one canonical name
        assert len({l.canonical_name for l in profile.lenders}) == 1
        # screening should be called with the deduped canonical name list
        mock_screen.assert_called_once()
        called_names = mock_screen.call_args[0][0]
        assert len(called_names) == 1

    def test_trace_unavailability_propagates_to_profile(self):
        candidates = [{"cik": 5, "ticker": "T", "name": "Test Co"}]
        with patch.object(edgar_client, "get_company_candidates", return_value=candidates), \
             patch.object(edgar_client, "get_debt_relevant_filings", return_value=[]), \
             patch("engines.debt_pipeline.screen_lenders", return_value=[]), \
             patch("engines.debt_pipeline.trace_client.fetch_bond_activity", return_value=TraceResult(False, "Historical Data Agreement required", [])):
            profile = pipeline.build_profile("T")
        assert profile.trace_available is False
        assert "Historical Data Agreement" in profile.trace_note
