"""
Ported from dib_monitor/tests/test_earnings.py -- the two P10 enrichments:
  1. Earnings call transcript ingestion (8-K Exhibit 99 via EDGAR + Claude signals)
  2. Portfolio mode (aggregate risk table + Claude portfolio brief)

Uses the shared conftest.py `db_session` fixture (one shared Base/engine
for every tool's tables) instead of the original's own isolated in-memory
engine.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from models.dib import EarningsSignal, Supplier
from engines.dib_seed_data import load_seed_data
from engines.dib_claude_analyst import (
    AnalystError,
    extract_earnings_signals,
    generate_portfolio_brief,
    _parse_json_from_response,
)
from engines.dib_edgar_client import fetch_latest_8k_exhibit99, EdgarError


@pytest.fixture
def seeded_db(db_session):
    load_seed_data(db_session)
    return db_session


def _mock_claude(response_text: str):
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = msg
    return client


# ── EarningsSignal model ──────────────────────────────────────────────────────

class TestEarningsSignalModel:
    def test_model_creates_and_stores(self, db_session):
        s = Supplier(name="Test Corp")
        db_session.add(s)
        db_session.commit()
        es = EarningsSignal(
            supplier_id=s.id,
            filing_date="2026-01-28",
            signals_json=json.dumps(["Supply chain diversion from PRC supplier"]),
            export_control_flag=True,
            supplier_diversion_flag=True,
            key_quote="We are diversifying away from our current PRC supplier.",
            extraction_confidence="high",
        )
        db_session.add(es)
        db_session.commit()
        loaded = db_session.query(EarningsSignal).filter(EarningsSignal.supplier_id == s.id).first()
        assert loaded is not None
        assert loaded.export_control_flag is True
        assert loaded.supplier_diversion_flag is True

    def test_signals_json_roundtrip(self, db_session):
        s = Supplier(name="Test Corp 2")
        db_session.add(s)
        db_session.commit()
        signals = ["Signal A", "Signal B", "Signal C"]
        es = EarningsSignal(supplier_id=s.id, signals_json=json.dumps(signals))
        db_session.add(es)
        db_session.commit()
        loaded = db_session.query(EarningsSignal).filter(EarningsSignal.supplier_id == s.id).first()
        assert json.loads(loaded.signals_json) == signals

    def test_defaults_are_false(self, db_session):
        s = Supplier(name="Test Corp 3")
        db_session.add(s)
        db_session.commit()
        es = EarningsSignal(supplier_id=s.id)
        db_session.add(es)
        db_session.commit()
        assert es.export_control_flag is False
        assert es.supplier_diversion_flag is False
        assert es.extraction_confidence == "demo"

    def test_multiple_signals_per_supplier(self, db_session):
        s = Supplier(name="Test Corp 4")
        db_session.add(s)
        db_session.commit()
        for i in range(3):
            db_session.add(EarningsSignal(supplier_id=s.id, filing_date=f"2026-0{i+1}-01"))
        db_session.commit()
        count = db_session.query(EarningsSignal).filter(EarningsSignal.supplier_id == s.id).count()
        assert count == 3


# ── Seed data: EarningsSignal ─────────────────────────────────────────────────

class TestSeedEarningsSignal:
    def test_arrowhead_has_earnings_signal(self, seeded_db):
        arrowhead = seeded_db.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == arrowhead.id)
            .first()
        )
        assert signal is not None

    def test_arrowhead_signal_has_export_control_flag(self, seeded_db):
        arrowhead = seeded_db.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == arrowhead.id)
            .first()
        )
        assert signal.export_control_flag is True

    def test_arrowhead_signal_has_supplier_diversion_flag(self, seeded_db):
        arrowhead = seeded_db.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == arrowhead.id)
            .first()
        )
        assert signal.supplier_diversion_flag is True

    def test_arrowhead_signal_has_key_quote(self, seeded_db):
        arrowhead = seeded_db.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == arrowhead.id)
            .first()
        )
        assert signal.key_quote is not None
        assert len(signal.key_quote) > 10

    def test_arrowhead_signal_has_signals_array(self, seeded_db):
        arrowhead = seeded_db.query(Supplier).filter(Supplier.name.like("%Arrowhead%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == arrowhead.id)
            .first()
        )
        parsed = json.loads(signal.signals_json)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1

    def test_meridian_has_no_earnings_signal(self, seeded_db):
        meridian = seeded_db.query(Supplier).filter(Supplier.name.like("%Meridian%")).first()
        signal = (
            seeded_db.query(EarningsSignal)
            .filter(EarningsSignal.supplier_id == meridian.id)
            .first()
        )
        assert signal is None

    def test_seed_idempotent_with_earnings_signals(self, db_session):
        load_seed_data(db_session)
        load_seed_data(db_session)
        count = db_session.query(EarningsSignal).count()
        assert count == 1  # only Arrowhead gets a signal


# ── extract_earnings_signals ──────────────────────────────────────────────────

_VALID_SIGNALS_RESPONSE = json.dumps({
    "signals": [
        "Diversifying away from PRC semiconductor suppliers due to BIS restrictions",
        "Expects $20M incremental sourcing cost from domestic qualification",
    ],
    "export_control_flag": True,
    "supplier_diversion_flag": True,
    "key_quote": "We are no longer comfortable with single-country concentration.",
    "confidence": "high",
})


class TestExtractEarningsSignals:
    def test_returns_dict_with_expected_keys(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude(_VALID_SIGNALS_RESPONSE)
            result = extract_earnings_signals("Arrowhead Defense", "some transcript text")
        assert "signals" in result
        assert "export_control_flag" in result
        assert "supplier_diversion_flag" in result
        assert "key_quote" in result

    def test_export_control_flag_parsed_correctly(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude(_VALID_SIGNALS_RESPONSE)
            result = extract_earnings_signals("Arrowhead Defense", "transcript")
        assert result["export_control_flag"] is True

    def test_signals_is_a_list(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude(_VALID_SIGNALS_RESPONSE)
            result = extract_earnings_signals("Arrowhead Defense", "transcript")
        assert isinstance(result["signals"], list)
        assert len(result["signals"]) == 2

    def test_no_signals_returns_empty_list(self):
        clean = json.dumps({
            "signals": [],
            "export_control_flag": False,
            "supplier_diversion_flag": False,
            "key_quote": None,
            "confidence": "medium",
        })
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude(clean)
            result = extract_earnings_signals("Clean Corp", "transcript")
        assert result["signals"] == []
        assert result["export_control_flag"] is False

    def test_strips_markdown_fences(self):
        with_fences = "```json\n" + _VALID_SIGNALS_RESPONSE + "\n```"
        result = _parse_json_from_response(with_fences)
        assert isinstance(result, dict)

    def test_raises_analyst_error_on_api_failure(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = RuntimeError("timeout")
            with pytest.raises(AnalystError, match="Claude API error"):
                extract_earnings_signals("Company X", "transcript")

    def test_raises_analyst_error_on_non_dict_response(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude('["not", "a", "dict"]')
            with pytest.raises(AnalystError):
                extract_earnings_signals("Company X", "transcript")

    def test_transcript_truncated_to_8000_chars(self):
        long_text = "x" * 20_000
        captured_prompt = []
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            def capture_call(**kwargs):
                captured_prompt.append(kwargs["messages"][0]["content"])
                msg = MagicMock()
                msg.content = [MagicMock(text=_VALID_SIGNALS_RESPONSE)]
                return msg
            MockAnthropic.return_value.messages.create.side_effect = capture_call
            extract_earnings_signals("Company X", long_text)
        assert len(long_text) > 8_000
        assert long_text[:8_001] not in captured_prompt[0]


# ── generate_portfolio_brief ──────────────────────────────────────────────────

_SAMPLE_PORTFOLIO = [
    {
        "name": "Arrowhead Defense Systems",
        "dib_category": "Tier 1 Subcontractor",
        "sector": "Defense Electronics",
        "combined_risk_level": "HIGH",
        "financial_risk_score": 72,
        "ownership_risk_score": 65,
        "distress_prob_1yr": 0.12,
        "distress_prob_3yr": 0.41,
        "cfius_flag_count": 1,
        "earnings_signals": ["Diversifying from PRC semiconductor suppliers"],
    },
    {
        "name": "Meridian Propulsion Corp",
        "dib_category": "Critical Sole-Source Supplier",
        "sector": "Aerospace Propulsion",
        "combined_risk_level": "LOW",
        "financial_risk_score": 14,
        "ownership_risk_score": 0,
        "distress_prob_1yr": 0.02,
        "distress_prob_3yr": 0.09,
        "cfius_flag_count": 0,
        "earnings_signals": [],
    },
]

_BRIEF_TEXT = (
    "Arrowhead poses the primary risk in this portfolio driven by HIGH leverage "
    "and a CFIUS-flagged owner.\n\n"
    "The supply chain diversification disclosed in Arrowhead's earnings call signals "
    "potential production disruption.\n\n"
    "Recommend immediate attention to Arrowhead's Q3 2026 refinancing and CFIUS screening."
)


class TestGeneratePortfolioBrief:
    def test_returns_string(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value = _mock_claude(_BRIEF_TEXT)
            result = generate_portfolio_brief(_SAMPLE_PORTFOLIO)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_portfolio_returns_without_claude_call(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            result = generate_portfolio_brief([])
        assert "No suppliers" in result
        MockAnthropic.return_value.messages.create.assert_not_called()

    def test_raises_analyst_error_on_api_failure(self):
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.side_effect = RuntimeError("API down")
            with pytest.raises(AnalystError, match="Claude API error"):
                generate_portfolio_brief(_SAMPLE_PORTFOLIO)

    def test_portfolio_data_included_in_prompt(self):
        captured_prompt = []
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            def capture_call(**kwargs):
                captured_prompt.append(kwargs["messages"][0]["content"])
                msg = MagicMock()
                msg.content = [MagicMock(text=_BRIEF_TEXT)]
                return msg
            MockAnthropic.return_value.messages.create.side_effect = capture_call
            generate_portfolio_brief(_SAMPLE_PORTFOLIO)
        assert "ARROWHEAD DEFENSE SYSTEMS" in captured_prompt[0]
        assert "MERIDIAN PROPULSION CORP" in captured_prompt[0]

    def test_cfius_count_reflected_in_prompt(self):
        captured_prompt = []
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            def capture_call(**kwargs):
                captured_prompt.append(kwargs["messages"][0]["content"])
                msg = MagicMock()
                msg.content = [MagicMock(text=_BRIEF_TEXT)]
                return msg
            MockAnthropic.return_value.messages.create.side_effect = capture_call
            generate_portfolio_brief(_SAMPLE_PORTFOLIO)
        assert "CFIUS flags: 1" in captured_prompt[0]

    def test_earnings_signals_reflected_in_prompt(self):
        captured_prompt = []
        with patch("engines.dib_claude_analyst.anthropic.Anthropic") as MockAnthropic:
            def capture_call(**kwargs):
                captured_prompt.append(kwargs["messages"][0]["content"])
                msg = MagicMock()
                msg.content = [MagicMock(text=_BRIEF_TEXT)]
                return msg
            MockAnthropic.return_value.messages.create.side_effect = capture_call
            generate_portfolio_brief(_SAMPLE_PORTFOLIO)
        assert "Diversifying from PRC" in captured_prompt[0]


# ── fetch_latest_8k_exhibit99 ─────────────────────────────────────────────────

class TestFetch8kExhibit99:
    def _make_submissions_json(self, form="8-K"):
        return json.dumps({
            "filings": {
                "recent": {
                    "form": [form],
                    "accessionNumber": ["0001234567-26-000128"],
                    "primaryDocument": ["form8k.htm"],
                    "filingDate": ["2026-01-28"],
                }
            }
        }).encode()

    def _make_index_json(self):
        return json.dumps({
            "documents": [
                {"sequence": "1", "type": "8-K", "filename": "form8k.htm"},
                {"sequence": "2", "type": "EX-99.1", "filename": "ex991.htm"},
            ]
        }).encode()

    def test_returns_dict_with_text_date_accession(self):
        exhibit_text = (b"Exhibit 99.1 earnings release content about supply chain. "
                        b"We are diversifying our semiconductor sourcing away from PRC suppliers. " * 3)
        call_responses = [
            self._make_submissions_json(),
            self._make_index_json(),
            exhibit_text,
        ]
        call_iter = iter(call_responses)

        with patch("engines.dib_edgar_client._get", side_effect=lambda *a, **kw: next(call_iter)):
            result = fetch_latest_8k_exhibit99("1234567")

        assert result is not None
        assert "text" in result
        assert "filed_date" in result
        assert "accession" in result
        assert result["filed_date"] == "2026-01-28"
        assert result["accession"] == "0001234567-26-000128"
        assert "supply chain" in result["text"]

    def test_returns_none_when_no_8k_found(self):
        no_8k = json.dumps({
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q"],
                    "accessionNumber": ["0001234567-26-000100", "0001234567-26-000050"],
                    "primaryDocument": ["form10k.htm", "form10q.htm"],
                    "filingDate": ["2026-01-01", "2025-10-01"],
                }
            }
        }).encode()

        with patch("engines.dib_edgar_client._get", return_value=no_8k):
            result = fetch_latest_8k_exhibit99("9999999")

        assert result is None

    def test_returns_none_on_edgar_error(self):
        with patch("engines.dib_edgar_client._get", side_effect=EdgarError("HTTP 404")):
            result = fetch_latest_8k_exhibit99("0000001")

        assert result is None

    def test_falls_back_to_primary_doc_when_index_fails(self):
        primary_doc_text = (b"Primary 8-K document with earnings language. " * 10)
        call_responses = [
            self._make_submissions_json(),      # submissions JSON
            EdgarError("index not found"),      # index JSON fails
            primary_doc_text,                   # fallback: primary doc
        ]

        def side_effect(*args, **kwargs):
            resp = next(call_iter)
            if isinstance(resp, Exception):
                raise resp
            return resp

        call_iter = iter(call_responses)
        with patch("engines.dib_edgar_client._get", side_effect=side_effect):
            result = fetch_latest_8k_exhibit99("1234567")

        assert result is not None
        assert "8-K document" in result["text"]

    def test_text_truncated_to_max_chars(self):
        long_exhibit = ("A" * 20_000).encode()
        call_responses = [
            self._make_submissions_json(),
            self._make_index_json(),
            long_exhibit,
        ]
        call_iter = iter(call_responses)

        with patch("engines.dib_edgar_client._get", side_effect=lambda *a, **kw: next(call_iter)):
            result = fetch_latest_8k_exhibit99("1234567", max_chars=500)

        assert result is not None
        assert len(result["text"]) <= 500
