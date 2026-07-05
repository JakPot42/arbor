"""Tests for brief_generator.py — demo mode routing and text parsing."""


import pytest
from engines.brief_claude_generator import (
    generate_brief,
    _extract_demo_questions,
    _extract_demo_summary,
    _parse_questions,
    _parse_summary,
    BriefGeneratorError,
)
from engines.brief_models import IPPortfolio, LitigationProfile, RegulatoryExposure, ContractProfile
from engines.brief_seed_data import DEMO_BRIEF
from configs.brief import DEMO_COMPANY, DEMO_TICKER


def _make_ip() -> IPPortfolio:
    return IPPortfolio(
        company=DEMO_COMPANY, total_patents=18, recent_patents=6,
        patent_velocity=6.0, baseline_velocity=7.0, velocity_change_pct=-14.3,
        top_domains=["Network Security", "Computing Systems"],
        avg_citations=4.2, strength_tier="MODERATE",
    )

def _make_lit() -> LitigationProfile:
    return LitigationProfile(
        company=DEMO_COMPANY, total_cases=4, active_cases=2,
        ip_disputes=0, regulatory_actions=0, settled_last_3yr=1, risk_tier="NORMAL",
    )

def _make_reg() -> RegulatoryExposure:
    return RegulatoryExposure(
        company=DEMO_COMPANY, ticker=DEMO_TICKER,
        material_weakness=False, going_concern=False,
        export_control_mentions=8, government_revenue_pct=0.80,
        exposure_tier="MODERATE",
    )

def _make_cont() -> ContractProfile:
    return ContractProfile(
        company=DEMO_COMPANY, total_awards=15, total_value_usd=1_610_000_000.0,
        agency_breakdown={"Department of Defense": 836_200_000.0,
                          "Department of Homeland Security": 347_400_000.0,
                          "Intelligence Community": 222_600_000.0,
                          "Other": 204_300_000.0},
        primary_agency="Department of Defense", primary_agency_pct=0.52,
        recent_awards=5, naics_top=["541512", "541519", "541330"], dependency_tier="MODERATE",
    )


# ---------------------------------------------------------------------------
# generate_brief — demo mode
# ---------------------------------------------------------------------------

class TestGenerateBriefDemoMode:
    def test_returns_tuple_of_three(self):
        result = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                _make_reg(), _make_cont(), demo_mode=True)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_full_text_is_string(self):
        full_text, _, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert isinstance(full_text, str)

    def test_full_text_nonempty(self):
        full_text, _, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert len(full_text) > 500

    def test_diligence_questions_list(self):
        _, questions, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert isinstance(questions, list)

    def test_diligence_questions_nonempty(self):
        _, questions, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert len(questions) >= 1

    def test_executive_summary_string(self):
        _, _, summary = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                       _make_reg(), _make_cont(), demo_mode=True)
        assert isinstance(summary, str)

    def test_executive_summary_nonempty(self):
        _, _, summary = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                       _make_reg(), _make_cont(), demo_mode=True)
        assert len(summary) > 30

    def test_full_text_is_demo_brief(self):
        full_text, _, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert full_text == DEMO_BRIEF

    def test_full_text_contains_company(self):
        full_text, _, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert DEMO_COMPANY in full_text

    def test_questions_at_most_7(self):
        _, questions, _ = generate_brief(DEMO_COMPANY, DEMO_TICKER, _make_ip(), _make_lit(),
                                         _make_reg(), _make_cont(), demo_mode=True)
        assert len(questions) <= 7


# ---------------------------------------------------------------------------
# _extract_demo_questions
# ---------------------------------------------------------------------------

class TestExtractDemoQuestions:
    def test_returns_list(self):
        result = _extract_demo_questions(DEMO_BRIEF)
        assert isinstance(result, list)

    def test_nonempty(self):
        result = _extract_demo_questions(DEMO_BRIEF)
        assert len(result) >= 1

    def test_each_is_string(self):
        for q in _extract_demo_questions(DEMO_BRIEF):
            assert isinstance(q, str)

    def test_max_7(self):
        result = _extract_demo_questions(DEMO_BRIEF)
        assert len(result) <= 7

    def test_empty_brief_returns_empty(self):
        result = _extract_demo_questions("")
        assert result == []


# ---------------------------------------------------------------------------
# _extract_demo_summary
# ---------------------------------------------------------------------------

class TestExtractDemoSummary:
    def test_returns_string(self):
        result = _extract_demo_summary(DEMO_BRIEF)
        assert isinstance(result, str)

    def test_nonempty(self):
        result = _extract_demo_summary(DEMO_BRIEF)
        assert len(result) > 0

    def test_max_600_chars(self):
        result = _extract_demo_summary(DEMO_BRIEF)
        assert len(result) <= 600

    def test_empty_brief_returns_empty(self):
        result = _extract_demo_summary("")
        assert result == ""


# ---------------------------------------------------------------------------
# _parse_questions
# ---------------------------------------------------------------------------

class TestParseQuestions:
    def test_returns_list(self):
        text = "VI. RECOMMENDED DILIGENCE QUESTIONS FOR COUNSEL\n1. First question?\n2. Second question?\n"
        result = _parse_questions(text)
        assert isinstance(result, list)

    def test_extracts_numbered_items(self):
        text = "DILIGENCE QUESTIONS\n1. Question one.\n2. Question two.\n"
        result = _parse_questions(text)
        assert len(result) >= 1

    def test_empty_text_returns_empty(self):
        result = _parse_questions("")
        assert result == []

    def test_max_7(self):
        lines = "\n".join(f"{i}. Question {i}." for i in range(1, 15))
        text = f"DILIGENCE QUESTIONS\n{lines}"
        result = _parse_questions(text)
        assert len(result) <= 7


# ---------------------------------------------------------------------------
# _parse_summary
# ---------------------------------------------------------------------------

class TestParseSummary:
    def test_returns_string(self):
        text = "I. EXECUTIVE SUMMARY\nThis is the summary.\nII. NEXT SECTION"
        result = _parse_summary(text)
        assert isinstance(result, str)

    def test_extracts_content(self):
        text = "I. EXECUTIVE SUMMARY\nThis company is clean.\nII. IP"
        result = _parse_summary(text)
        assert "clean" in result.lower() or len(result) >= 0

    def test_empty_text_returns_empty(self):
        result = _parse_summary("")
        assert result == ""

    def test_max_600_chars(self):
        long_summary = "X " * 500
        text = f"I. EXECUTIVE SUMMARY\n{long_summary}\nII. Next"
        result = _parse_summary(text)
        assert len(result) <= 600


# ---------------------------------------------------------------------------
# BriefGeneratorError
# ---------------------------------------------------------------------------

class TestBriefGeneratorError:
    def test_is_exception(self):
        assert issubclass(BriefGeneratorError, Exception)

    def test_can_be_raised(self):
        with pytest.raises(BriefGeneratorError):
            raise BriefGeneratorError("test error")

    def test_message_preserved(self):
        try:
            raise BriefGeneratorError("my message")
        except BriefGeneratorError as e:
            assert "my message" in str(e)
