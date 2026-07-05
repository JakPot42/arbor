"""Ported from
debt_exposure_monitor/tests/test_claude_lender_extractor.py -- mocked
anthropic client, no real API call. Patch target stays "anthropic.Anthropic"
(the global module) since engines/debt_claude_lender_extractor.py does
`import anthropic` inside the function body, same as the original."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from engines.debt_claude_lender_extractor import ExtractionError, extract_lenders


def _mock_anthropic_client(payload: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=payload)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


class TestExtractLenders:
    def test_parses_valid_json_response(self):
        payload = json.dumps([
            {
                "lender_name": "JPMorgan Chase Bank, N.A.",
                "instrument_type": "credit_facility",
                "role": "administrative_agent",
                "amount_text": "$150,000,000",
                "evidence_quote": "JPMorgan Chase Bank, N.A. serving as Administrative Agent",
            }
        ])
        mock_client = _mock_anthropic_client(payload)
        with patch("anthropic.Anthropic", return_value=mock_client):
            records = extract_lenders("some filing text", "10-K filed 2025-02-14")
        assert len(records) == 1
        assert records[0].lender_name == "JPMorgan Chase Bank, N.A."
        assert records[0].source_filing == "10-K filed 2025-02-14"

    def test_empty_lender_name_filtered_out(self):
        payload = json.dumps([{"lender_name": "", "instrument_type": "bond", "role": "unspecified", "amount_text": "", "evidence_quote": ""}])
        mock_client = _mock_anthropic_client(payload)
        with patch("anthropic.Anthropic", return_value=mock_client):
            records = extract_lenders("text", "10-K")
        assert records == []

    def test_no_lenders_named_returns_empty_list(self):
        mock_client = _mock_anthropic_client("[]")
        with patch("anthropic.Anthropic", return_value=mock_client):
            records = extract_lenders("generic text with no lender names", "10-K")
        assert records == []

    def test_api_failure_raises_extraction_error_not_silent(self):
        with patch("anthropic.Anthropic", side_effect=Exception("no api key")):
            try:
                extract_lenders("text", "10-K")
                assert False, "expected ExtractionError"
            except ExtractionError as exc:
                assert "10-K" in str(exc)

    def test_malformed_json_raises_extraction_error(self):
        mock_client = _mock_anthropic_client("not valid json")
        with patch("anthropic.Anthropic", return_value=mock_client):
            try:
                extract_lenders("text", "8-K")
                assert False, "expected ExtractionError"
            except ExtractionError:
                pass
