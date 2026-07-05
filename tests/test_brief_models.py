"""Tests for models.py — dataclass construction and field types."""


import pytest
from engines.brief_models import (
    PatentRecord, IPPortfolio, LitigationCase, LitigationProfile,
    RegulatoryFlag, RegulatoryExposure, ContractAward, ContractProfile,
    AcquisitionBrief,
)


def _make_patent(**kw) -> PatentRecord:
    defaults = {
        "patent_id": "US11111111", "title": "Test Patent",
        "filing_date": "2022-01-01", "grant_date": "2022-06-01",
        "cpc_classes": ["H04L63/08"], "forward_citations": 3,
    }
    return PatentRecord(**{**defaults, **kw})


def _make_ip(**kw) -> IPPortfolio:
    defaults = {
        "company": "TestCo", "total_patents": 50, "recent_patents": 15,
        "patent_velocity": 5.0, "baseline_velocity": 6.0,
        "velocity_change_pct": -16.7, "top_domains": ["Network Security"],
        "avg_citations": 3.5, "strength_tier": "MODERATE",
    }
    return IPPortfolio(**{**defaults, **kw})


def _make_case(**kw) -> LitigationCase:
    defaults = {
        "case_id": "cl-001", "case_name": "Doe v. TestCo",
        "court": "U.S.D.C. E.D. Va.", "filed_date": "2023-01-01",
        "status": "ACTIVE", "case_type": "CONTRACT", "summary": "Breach claim.",
    }
    return LitigationCase(**{**defaults, **kw})


def _make_lit(**kw) -> LitigationProfile:
    defaults = {
        "company": "TestCo", "total_cases": 2, "active_cases": 1,
        "ip_disputes": 0, "regulatory_actions": 0,
        "settled_last_3yr": 1, "risk_tier": "NORMAL",
    }
    return LitigationProfile(**{**defaults, **kw})


def _make_flag(**kw) -> RegulatoryFlag:
    defaults = {
        "flag_type": "EXPORT_CONTROL", "severity": "MEDIUM",
        "description": "ITAR compliance required",
        "filing_period": "FY2024", "excerpt": "Subject to ITAR regulations.",
    }
    return RegulatoryFlag(**{**defaults, **kw})


def _make_reg(**kw) -> RegulatoryExposure:
    defaults = {
        "company": "TestCo", "ticker": "TST",
        "material_weakness": False, "going_concern": False,
        "export_control_mentions": 4, "government_revenue_pct": 0.75,
        "exposure_tier": "MODERATE",
    }
    return RegulatoryExposure(**{**defaults, **kw})


def _make_award(**kw) -> ContractAward:
    defaults = {
        "award_id": "N00-001", "awarding_agency": "Department of Defense",
        "value_usd": 10_000_000.0, "award_date": "2023-06-01",
        "description": "IT services", "naics_code": "541512",
    }
    return ContractAward(**{**defaults, **kw})


def _make_cont(**kw) -> ContractProfile:
    defaults = {
        "company": "TestCo", "total_awards": 5, "total_value_usd": 50_000_000.0,
        "agency_breakdown": {"Department of Defense": 30_000_000.0},
        "primary_agency": "Department of Defense", "primary_agency_pct": 0.60,
        "recent_awards": 3, "naics_top": ["541512"], "dependency_tier": "HIGH_DEPENDENCY",
    }
    return ContractProfile(**{**defaults, **kw})


def _make_brief(**kw) -> AcquisitionBrief:
    defaults = {
        "company": "TestCo", "ticker": "TST", "prepared_date": "2026-06-24",
        "ip_portfolio": _make_ip(), "litigation_profile": _make_lit(),
        "regulatory_exposure": _make_reg(), "contract_profile": _make_cont(),
        "overall_risk_tier": "LOW", "diligence_questions": ["Q1?"],
        "executive_summary": "Summary here.", "full_text": "Full brief text.",
    }
    return AcquisitionBrief(**{**defaults, **kw})


# ---------------------------------------------------------------------------
# PatentRecord
# ---------------------------------------------------------------------------
class TestPatentRecord:
    def test_construction(self):
        p = _make_patent()
        assert p.patent_id == "US11111111"

    def test_cpc_classes_list(self):
        p = _make_patent()
        assert isinstance(p.cpc_classes, list)

    def test_forward_citations_int(self):
        p = _make_patent()
        assert isinstance(p.forward_citations, int)

    def test_zero_citations_allowed(self):
        p = _make_patent(forward_citations=0)
        assert p.forward_citations == 0


# ---------------------------------------------------------------------------
# IPPortfolio
# ---------------------------------------------------------------------------
class TestIPPortfolio:
    def test_construction(self):
        ip = _make_ip()
        assert ip.company == "TestCo"

    def test_default_patents_list(self):
        ip = _make_ip()
        assert ip.patents == []

    def test_patents_can_be_set(self):
        p = _make_patent()
        ip = _make_ip(patents=[p])
        assert len(ip.patents) == 1

    def test_strength_tiers(self):
        for tier in ["STRONG", "MODERATE", "WEAK", "MINIMAL"]:
            ip = _make_ip(strength_tier=tier)
            assert ip.strength_tier == tier

    def test_velocity_change_negative(self):
        ip = _make_ip(velocity_change_pct=-14.3)
        assert ip.velocity_change_pct < 0

    def test_top_domains_list(self):
        ip = _make_ip(top_domains=["Network Security", "Computing Systems"])
        assert len(ip.top_domains) == 2


# ---------------------------------------------------------------------------
# LitigationCase
# ---------------------------------------------------------------------------
class TestLitigationCase:
    def test_construction(self):
        c = _make_case()
        assert c.status == "ACTIVE"

    def test_all_statuses(self):
        for s in ["ACTIVE", "CLOSED", "SETTLED", "PENDING"]:
            c = _make_case(status=s)
            assert c.status == s

    def test_all_case_types(self):
        for t in ["IP_DISPUTE", "CONTRACT", "EMPLOYMENT", "REGULATORY", "SECURITIES"]:
            c = _make_case(case_type=t)
            assert c.case_type == t


# ---------------------------------------------------------------------------
# LitigationProfile
# ---------------------------------------------------------------------------
class TestLitigationProfile:
    def test_construction(self):
        lit = _make_lit()
        assert lit.total_cases == 2

    def test_default_cases_list(self):
        lit = _make_lit()
        assert lit.cases == []

    def test_cases_can_be_set(self):
        c = _make_case()
        lit = _make_lit(cases=[c])
        assert len(lit.cases) == 1

    def test_risk_tiers(self):
        for tier in ["CLEAR", "NORMAL", "ELEVATED", "CRITICAL"]:
            lit = _make_lit(risk_tier=tier)
            assert lit.risk_tier == tier


# ---------------------------------------------------------------------------
# RegulatoryFlag
# ---------------------------------------------------------------------------
class TestRegulatoryFlag:
    def test_construction(self):
        f = _make_flag()
        assert f.flag_type == "EXPORT_CONTROL"

    def test_all_severities(self):
        for s in ["HIGH", "MEDIUM", "LOW", "INFORMATIONAL"]:
            f = _make_flag(severity=s)
            assert f.severity == s


# ---------------------------------------------------------------------------
# RegulatoryExposure
# ---------------------------------------------------------------------------
class TestRegulatoryExposure:
    def test_construction(self):
        reg = _make_reg()
        assert reg.material_weakness is False

    def test_default_flags_list(self):
        reg = _make_reg()
        assert reg.flags == []

    def test_flags_can_be_set(self):
        f = _make_flag()
        reg = _make_reg(flags=[f])
        assert len(reg.flags) == 1

    def test_gov_revenue_float(self):
        reg = _make_reg(government_revenue_pct=0.80)
        assert isinstance(reg.government_revenue_pct, float)

    def test_exposure_tiers(self):
        for tier in ["HIGH", "MODERATE", "LOW", "CLEAN"]:
            reg = _make_reg(exposure_tier=tier)
            assert reg.exposure_tier == tier


# ---------------------------------------------------------------------------
# ContractAward
# ---------------------------------------------------------------------------
class TestContractAward:
    def test_construction(self):
        a = _make_award()
        assert a.awarding_agency == "Department of Defense"

    def test_value_float(self):
        a = _make_award()
        assert isinstance(a.value_usd, float)


# ---------------------------------------------------------------------------
# ContractProfile
# ---------------------------------------------------------------------------
class TestContractProfile:
    def test_construction(self):
        c = _make_cont()
        assert c.total_awards == 5

    def test_default_awards_list(self):
        c = _make_cont()
        assert c.awards == []

    def test_awards_can_be_set(self):
        a = _make_award()
        c = _make_cont(awards=[a])
        assert len(c.awards) == 1

    def test_dependency_tiers(self):
        for tier in ["HIGH_DEPENDENCY", "MODERATE", "DIVERSIFIED"]:
            c = _make_cont(dependency_tier=tier)
            assert c.dependency_tier == tier

    def test_agency_breakdown_dict(self):
        c = _make_cont()
        assert isinstance(c.agency_breakdown, dict)


# ---------------------------------------------------------------------------
# AcquisitionBrief
# ---------------------------------------------------------------------------
class TestAcquisitionBrief:
    def test_construction(self):
        b = _make_brief()
        assert b.company == "TestCo"

    def test_diligence_questions_list(self):
        b = _make_brief()
        assert isinstance(b.diligence_questions, list)

    def test_overall_risk_tiers(self):
        for tier in ["CLEAN", "LOW", "MODERATE", "HIGH", "CRITICAL"]:
            b = _make_brief(overall_risk_tier=tier)
            assert b.overall_risk_tier == tier

    def test_prepared_date_string(self):
        b = _make_brief()
        assert isinstance(b.prepared_date, str)

    def test_full_text_string(self):
        b = _make_brief()
        assert isinstance(b.full_text, str)
