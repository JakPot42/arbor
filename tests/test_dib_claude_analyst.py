"""Ported from dib_monitor/tests/test_claude_analyst.py."""
import json
import pytest
from unittest.mock import MagicMock, patch
from engines.dib_claude_analyst import (
    extract_financials,
    flag_ownership_concerns,
    AnalystError,
    _parse_json_from_response,
)


def _mock_client(response_text: str):
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = msg
    return client


_VALID_EXTRACTION = json.dumps({
    "revenue_mm": 847.0,
    "total_debt_mm": 1200.0,
    "cash_mm": 89.0,
    "ebitda_mm": 145.0,
    "debt_service_annual_mm": 180.0,
    "covenant_summary": "Net leverage must not exceed 9x",
    "going_concern_flag": False,
    "going_concern_quote": None,
    "near_term_maturity_mm": 400.0,
    "near_term_maturity_date": "March 2027",
    "confidence": "high",
})


class TestExtractFinancials:
    def test_returns_dict_with_expected_keys(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_client(_VALID_EXTRACTION)
            result = extract_financials("Arrowhead Defense", "some filing text")
        assert "revenue_mm" in result
        assert "total_debt_mm" in result
        assert "going_concern_flag" in result

    def test_going_concern_false_parsed_correctly(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_client(_VALID_EXTRACTION)
            result = extract_financials("Arrowhead Defense", "filing")
        assert result["going_concern_flag"] is False

    def test_strips_markdown_fences(self):
        with_fences = "```json\n" + _VALID_EXTRACTION + "\n```"
        result = _parse_json_from_response(with_fences)
        assert isinstance(result, dict)

    def test_raises_analyst_error_on_api_failure(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = RuntimeError("timeout")
            with pytest.raises(AnalystError, match="Claude API error"):
                extract_financials("Company X", "filing text")

    def test_raises_analyst_error_on_non_dict_response(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_client('["not", "a", "dict"]')
            with pytest.raises(AnalystError):
                extract_financials("Company X", "filing text")


class TestFlagOwnershipConcerns:
    def test_empty_owners_returns_empty(self):
        result = flag_ownership_concerns("Company", [])
        assert result == []

    def test_returns_list_of_flagged_owners(self):
        flagged = json.dumps([
            {"owner_name": "Suspect Fund", "flag_reason": "Cayman shell",
             "risk_level": "HIGH", "cfius_flag": True}
        ])
        owners = [{"owner_name": "Suspect Fund", "pct_owned": 7.2}]
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_client(flagged)
            result = flag_ownership_concerns("Arrowhead", owners)
        assert len(result) == 1
        assert result[0]["cfius_flag"] is True

    def test_raises_analyst_error_on_api_failure(self):
        owners = [{"owner_name": "Fund A", "pct_owned": 5.0}]
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = RuntimeError("API down")
            with pytest.raises(AnalystError, match="Claude API error"):
                flag_ownership_concerns("Company", owners)

    def test_non_list_response_returns_empty(self):
        owners = [{"owner_name": "Fund A", "pct_owned": 5.0}]
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_client('{"not": "a list"}')
            result = flag_ownership_concerns("Company", owners)
        assert result == []
