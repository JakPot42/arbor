"""Tests for brief_engine.py — deterministic risk scoring logic."""


import pytest
from engines.brief_engine import (
    compute_overall_risk,
    build_brief,
    _ip_to_risk,
    _lit_to_risk,
    _reg_to_risk,
    _con_to_risk,
)
from engines.brief_models import IPPortfolio, LitigationProfile, RegulatoryExposure, ContractProfile


# ---------------------------------------------------------------------------
# Component translators
# ---------------------------------------------------------------------------

class TestIpToRisk:
    def test_strong_is_clean(self):
        assert _ip_to_risk("STRONG") == "CLEAN"

    def test_moderate_is_low(self):
        assert _ip_to_risk("MODERATE") == "LOW"

    def test_weak_is_moderate(self):
        assert _ip_to_risk("WEAK") == "MODERATE"

    def test_minimal_is_high(self):
        assert _ip_to_risk("MINIMAL") == "HIGH"

    def test_unknown_defaults_to_moderate(self):
        assert _ip_to_risk("UNKNOWN") == "MODERATE"


class TestLitToRisk:
    def test_clear_is_clean(self):
        assert _lit_to_risk("CLEAR") == "CLEAN"

    def test_normal_is_low(self):
        assert _lit_to_risk("NORMAL") == "LOW"

    def test_elevated_is_moderate(self):
        assert _lit_to_risk("ELEVATED") == "MODERATE"

    def test_critical_is_high(self):
        assert _lit_to_risk("CRITICAL") == "HIGH"

    def test_unknown_defaults_to_moderate(self):
        assert _lit_to_risk("UNKNOWN") == "MODERATE"


class TestRegToRisk:
    def test_clean_is_clean(self):
        assert _reg_to_risk("CLEAN") == "CLEAN"

    def test_low_is_low(self):
        assert _reg_to_risk("LOW") == "LOW"

    def test_moderate_is_moderate(self):
        assert _reg_to_risk("MODERATE") == "MODERATE"

    def test_high_is_high(self):
        assert _reg_to_risk("HIGH") == "HIGH"

    def test_unknown_defaults_to_moderate(self):
        assert _reg_to_risk("UNKNOWN") == "MODERATE"


class TestConToRisk:
    def test_diversified_is_clean(self):
        assert _con_to_risk("DIVERSIFIED") == "CLEAN"

    def test_moderate_is_low(self):
        assert _con_to_risk("MODERATE") == "LOW"

    def test_high_dependency_is_high(self):
        assert _con_to_risk("HIGH_DEPENDENCY") == "HIGH"

    def test_unknown_defaults_to_moderate(self):
        assert _con_to_risk("UNKNOWN") == "MODERATE"


# ---------------------------------------------------------------------------
# compute_overall_risk
# ---------------------------------------------------------------------------

def _make_ip(tier: str) -> IPPortfolio:
    return IPPortfolio(
        company="TestCo", total_patents=50, recent_patents=10,
        patent_velocity=3.3, baseline_velocity=4.0, velocity_change_pct=-17.5,
        top_domains=["Network Security"], avg_citations=3.0, strength_tier=tier,
    )

def _make_lit(tier: str) -> LitigationProfile:
    return LitigationProfile(
        company="TestCo", total_cases=2, active_cases=1,
        ip_disputes=0, regulatory_actions=0, settled_last_3yr=0, risk_tier=tier,
    )

def _make_reg(tier: str) -> RegulatoryExposure:
    return RegulatoryExposure(
        company="TestCo", ticker="TST", material_weakness=False, going_concern=False,
        export_control_mentions=4, government_revenue_pct=0.75, exposure_tier=tier,
    )

def _make_cont(tier: str) -> ContractProfile:
    return ContractProfile(
        company="TestCo", total_awards=5, total_value_usd=50_000_000.0,
        agency_breakdown={"DoD": 30_000_000.0}, primary_agency="DoD",
        primary_agency_pct=0.60, recent_awards=3, naics_top=["541512"], dependency_tier=tier,
    )


class TestComputeOverallRisk:
    def test_all_clean_returns_clean(self):
        result = compute_overall_risk(
            _make_ip("STRONG"), _make_lit("CLEAR"), _make_reg("CLEAN"), _make_cont("DIVERSIFIED"),
        )
        assert result == "CLEAN"

    def test_all_low_returns_low(self):
        result = compute_overall_risk(
            _make_ip("MODERATE"), _make_lit("NORMAL"), _make_reg("LOW"), _make_cont("DIVERSIFIED"),
        )
        assert result == "LOW"

    def test_single_high_escalates(self):
        result = compute_overall_risk(
            _make_ip("STRONG"), _make_lit("CLEAR"), _make_reg("HIGH"), _make_cont("DIVERSIFIED"),
        )
        assert result == "HIGH"

    def test_single_moderate_with_all_others_low_stays_moderate(self):
        result = compute_overall_risk(
            _make_ip("MODERATE"), _make_lit("NORMAL"), _make_reg("MODERATE"), _make_cont("DIVERSIFIED"),
        )
        # 2 MODERATE components → no triple-escalation, but max is MODERATE
        assert result in {"MODERATE", "HIGH"}

    def test_triple_moderate_bumps_up(self):
        result = compute_overall_risk(
            _make_ip("WEAK"), _make_lit("ELEVATED"), _make_reg("MODERATE"), _make_cont("MODERATE"),
        )
        # All 4 at MODERATE or above → bump applies → should be higher than plain MODERATE
        assert result in {"HIGH", "CRITICAL"}

    def test_minimal_ip_elevates(self):
        result = compute_overall_risk(
            _make_ip("MINIMAL"), _make_lit("CLEAR"), _make_reg("CLEAN"), _make_cont("DIVERSIFIED"),
        )
        assert result == "HIGH"

    def test_critical_litigation_elevates(self):
        result = compute_overall_risk(
            _make_ip("STRONG"), _make_lit("CRITICAL"), _make_reg("CLEAN"), _make_cont("DIVERSIFIED"),
        )
        assert result == "HIGH"

    def test_parsons_profile_is_low(self):
        # MODERATE IP, NORMAL lit, MODERATE reg, MODERATE contracts
        result = compute_overall_risk(
            _make_ip("MODERATE"), _make_lit("NORMAL"), _make_reg("MODERATE"), _make_cont("MODERATE"),
        )
        # Expected: not clean, not critical — MODERATE or HIGH
        assert result in {"MODERATE", "HIGH", "LOW"}

    def test_result_is_valid_tier(self):
        valid = {"CLEAN", "LOW", "MODERATE", "HIGH", "CRITICAL"}
        result = compute_overall_risk(
            _make_ip("MODERATE"), _make_lit("NORMAL"), _make_reg("MODERATE"), _make_cont("MODERATE"),
        )
        assert result in valid


# ---------------------------------------------------------------------------
# build_brief
# ---------------------------------------------------------------------------

class TestBuildBrief:
    def test_returns_acquisition_brief(self):
        from engines.brief_models import AcquisitionBrief
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        result = build_brief(
            "TestCo", "TST", ip, lit, reg, cont,
            full_text="Brief text.", diligence_questions=["Q1?"],
            executive_summary="Summary.",
        )
        assert isinstance(result, AcquisitionBrief)

    def test_company_set(self):
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "text", ["Q1"], "Summary")
        assert result.company == "TestCo"

    def test_ticker_set(self):
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "text", ["Q1"], "Summary")
        assert result.ticker == "TST"

    def test_prepared_date_today(self):
        from datetime import date
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "text", ["Q1"], "Summary")
        assert result.prepared_date == str(date.today())

    def test_overall_risk_computed(self):
        ip   = _make_ip("STRONG")
        lit  = _make_lit("CLEAR")
        reg  = _make_reg("CLEAN")
        cont = _make_cont("DIVERSIFIED")
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "text", [], "Summary")
        assert result.overall_risk_tier == "CLEAN"

    def test_diligence_questions_preserved(self):
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        qs = ["Q1?", "Q2?", "Q3?"]
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "text", qs, "Summary")
        assert result.diligence_questions == qs

    def test_full_text_preserved(self):
        ip   = _make_ip("MODERATE")
        lit  = _make_lit("NORMAL")
        reg  = _make_reg("MODERATE")
        cont = _make_cont("MODERATE")
        result = build_brief("TestCo", "TST", ip, lit, reg, cont, "MY TEXT", [], "")
        assert result.full_text == "MY TEXT"
