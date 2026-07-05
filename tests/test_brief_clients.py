"""Tests for all four data clients — DEMO_MODE routing and model construction."""


import pytest
from configs.brief import DEMO_COMPANY, DEMO_TICKER


# ---------------------------------------------------------------------------
# USPTO client
# ---------------------------------------------------------------------------

class TestFetchPatentsDemoMode:
    def test_returns_list(self):
        from engines.brief_uspto_client import fetch_patents
        result = fetch_patents(DEMO_COMPANY, demo_mode=True)
        assert isinstance(result, list)

    def test_returns_26_patents(self):
        from engines.brief_uspto_client import fetch_patents
        result = fetch_patents(DEMO_COMPANY, demo_mode=True)
        assert len(result) == 26

    def test_all_have_patent_id(self):
        from engines.brief_uspto_client import fetch_patents
        for p in fetch_patents(DEMO_COMPANY, demo_mode=True):
            assert p.get("patent_id"), "Missing patent_id"

    def test_all_have_cpc_classes(self):
        from engines.brief_uspto_client import fetch_patents
        for p in fetch_patents(DEMO_COMPANY, demo_mode=True):
            assert isinstance(p.get("cpc_classes"), list)

    def test_unknown_company_still_returns_demo(self):
        from engines.brief_uspto_client import fetch_patents
        result = fetch_patents("UNKNOWN CORP", demo_mode=True)
        assert len(result) == 26


class TestBuildIPPortfolio:
    def test_returns_ip_portfolio(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        from engines.brief_models import IPPortfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert isinstance(result, IPPortfolio)

    def test_company_set(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.company == DEMO_COMPANY

    def test_total_patents_26(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.total_patents == 26

    def test_strength_tier_valid(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.strength_tier in {"STRONG", "MODERATE", "WEAK", "MINIMAL"}

    def test_parsons_is_moderate(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.strength_tier == "MODERATE"

    def test_recent_patents_positive(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.recent_patents >= 0

    def test_avg_citations_positive(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert result.avg_citations > 0

    def test_top_domains_nonempty(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert len(result.top_domains) >= 1

    def test_patents_list_populated(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert len(result.patents) == 26

    def test_empty_patent_list(self):
        from engines.brief_uspto_client import build_ip_portfolio
        result = build_ip_portfolio("Empty Corp", [])
        assert result.total_patents == 0
        assert result.strength_tier == "MINIMAL"

    def test_velocity_fields_are_floats(self):
        from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
        patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
        result = build_ip_portfolio(DEMO_COMPANY, patents)
        assert isinstance(result.patent_velocity, float)
        assert isinstance(result.baseline_velocity, float)


# ---------------------------------------------------------------------------
# CourtListener client
# ---------------------------------------------------------------------------

class TestFetchCasesDemoMode:
    def test_returns_list(self):
        from engines.brief_courtlistener_client import fetch_cases
        result = fetch_cases(DEMO_COMPANY, demo_mode=True)
        assert isinstance(result, list)

    def test_returns_four_cases(self):
        from engines.brief_courtlistener_client import fetch_cases
        result = fetch_cases(DEMO_COMPANY, demo_mode=True)
        assert len(result) == 4

    def test_all_have_case_id(self):
        from engines.brief_courtlistener_client import fetch_cases
        for c in fetch_cases(DEMO_COMPANY, demo_mode=True):
            assert c.get("case_id")

    def test_unknown_company_returns_demo(self):
        from engines.brief_courtlistener_client import fetch_cases
        result = fetch_cases("UNKNOWN CORP", demo_mode=True)
        assert len(result) == 4


class TestBuildLitigationProfile:
    def test_returns_litigation_profile(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        from engines.brief_models import LitigationProfile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert isinstance(result, LitigationProfile)

    def test_company_set(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.company == DEMO_COMPANY

    def test_total_cases_four(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.total_cases == 4

    def test_active_cases_two(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.active_cases == 2

    def test_ip_disputes_zero_active(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        # IP dispute is CLOSED, so active IP disputes = 0
        assert result.ip_disputes == 0

    def test_regulatory_actions_zero(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.regulatory_actions == 0

    def test_risk_tier_normal(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.risk_tier == "NORMAL"

    def test_cases_list_populated(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert len(result.cases) == 4

    def test_empty_cases_list(self):
        from engines.brief_courtlistener_client import build_litigation_profile
        result = build_litigation_profile("Clean Corp", [])
        assert result.total_cases == 0
        assert result.risk_tier == "CLEAR"

    def test_settled_count(self):
        from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
        cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
        result = build_litigation_profile(DEMO_COMPANY, cases)
        assert result.settled_last_3yr == 1


# ---------------------------------------------------------------------------
# EDGAR client
# ---------------------------------------------------------------------------

class TestFetchRegulatoryDataDemoMode:
    def test_returns_dict(self):
        from engines.brief_edgar_client import fetch_regulatory_data
        result = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        from engines.brief_edgar_client import fetch_regulatory_data
        result = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        for key in {"material_weakness", "going_concern", "export_control_mentions",
                    "government_revenue_pct", "flags"}:
            assert key in result

    def test_no_material_weakness(self):
        from engines.brief_edgar_client import fetch_regulatory_data
        result = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        assert result["material_weakness"] is False

    def test_no_going_concern(self):
        from engines.brief_edgar_client import fetch_regulatory_data
        result = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        assert result["going_concern"] is False


class TestBuildRegulatoryExposure:
    def test_returns_regulatory_exposure(self):
        from engines.brief_edgar_client import fetch_regulatory_data, build_regulatory_exposure
        from engines.brief_models import RegulatoryExposure
        raw = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        result = build_regulatory_exposure(DEMO_COMPANY, DEMO_TICKER, raw)
        assert isinstance(result, RegulatoryExposure)

    def test_exposure_tier_moderate(self):
        from engines.brief_edgar_client import fetch_regulatory_data, build_regulatory_exposure
        raw = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        result = build_regulatory_exposure(DEMO_COMPANY, DEMO_TICKER, raw)
        assert result.exposure_tier == "MODERATE"

    def test_flags_list_populated(self):
        from engines.brief_edgar_client import fetch_regulatory_data, build_regulatory_exposure
        raw = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
        result = build_regulatory_exposure(DEMO_COMPANY, DEMO_TICKER, raw)
        assert len(result.flags) == 3

    def test_material_weakness_triggers_high(self):
        from engines.brief_edgar_client import build_regulatory_exposure
        raw = {"material_weakness": True, "going_concern": False,
               "export_control_mentions": 0, "government_revenue_pct": 0.0, "flags": []}
        result = build_regulatory_exposure("TestCo", "TST", raw)
        assert result.exposure_tier == "HIGH"

    def test_going_concern_triggers_high(self):
        from engines.brief_edgar_client import build_regulatory_exposure
        raw = {"material_weakness": False, "going_concern": True,
               "export_control_mentions": 0, "government_revenue_pct": 0.0, "flags": []}
        result = build_regulatory_exposure("TestCo", "TST", raw)
        assert result.exposure_tier == "HIGH"

    def test_no_flags_is_clean(self):
        from engines.brief_edgar_client import build_regulatory_exposure
        raw = {"material_weakness": False, "going_concern": False,
               "export_control_mentions": 0, "government_revenue_pct": 0.0, "flags": []}
        result = build_regulatory_exposure("TestCo", "TST", raw)
        assert result.exposure_tier == "CLEAN"


# ---------------------------------------------------------------------------
# USASpending client
# ---------------------------------------------------------------------------

class TestFetchAwardsDemoMode:
    def test_returns_list(self):
        from engines.brief_contracts_client import fetch_awards
        result = fetch_awards(DEMO_COMPANY, demo_mode=True)
        assert isinstance(result, list)

    def test_returns_15_awards(self):
        from engines.brief_contracts_client import fetch_awards
        result = fetch_awards(DEMO_COMPANY, demo_mode=True)
        assert len(result) == 15

    def test_all_have_award_id(self):
        from engines.brief_contracts_client import fetch_awards
        for a in fetch_awards(DEMO_COMPANY, demo_mode=True):
            assert a.get("award_id")

    def test_unknown_company_returns_demo(self):
        from engines.brief_contracts_client import fetch_awards
        result = fetch_awards("UNKNOWN CORP", demo_mode=True)
        assert len(result) == 15


class TestBuildContractProfile:
    def test_returns_contract_profile(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        from engines.brief_models import ContractProfile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert isinstance(result, ContractProfile)

    def test_total_awards_15(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert result.total_awards == 15

    def test_primary_agency_is_dod(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert "Defense" in result.primary_agency or "DoD" in result.primary_agency

    def test_dependency_tier_moderate(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert result.dependency_tier == "MODERATE"

    def test_total_value_positive(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert result.total_value_usd > 0

    def test_awards_list_populated(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert len(result.awards) == 15

    def test_empty_awards(self):
        from engines.brief_contracts_client import build_contract_profile
        result = build_contract_profile("Empty Corp", [])
        assert result.total_awards == 0
        assert result.total_value_usd == 0.0

    def test_agency_breakdown_dict(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert isinstance(result.agency_breakdown, dict)
        assert len(result.agency_breakdown) >= 3

    def test_naics_top_populated(self):
        from engines.brief_contracts_client import fetch_awards, build_contract_profile
        awards = fetch_awards(DEMO_COMPANY, demo_mode=True)
        result = build_contract_profile(DEMO_COMPANY, awards)
        assert len(result.naics_top) >= 1

    def test_high_dep_threshold(self):
        from engines.brief_contracts_client import build_contract_profile
        awards = [
            {"award_id": f"A{i}", "awarding_agency": "DoD",
             "value_usd": 1_000_000.0, "award_date": "2023-01-01",
             "description": "Services", "naics_code": "541512"}
            for i in range(10)
        ]
        result = build_contract_profile("TestCo", awards)
        assert result.dependency_tier == "HIGH_DEPENDENCY"
        assert result.primary_agency_pct == 1.0
