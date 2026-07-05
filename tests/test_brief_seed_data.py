"""Tests for seed_data.py — structure, coverage, plausibility."""


import pytest
from engines.brief_seed_data import DEMO_PATENTS, DEMO_CASES, DEMO_REGULATORY_DATA, DEMO_AWARDS, DEMO_BRIEF
from configs.brief import DEMO_COMPANY, DEMO_TICKER


# ---------------------------------------------------------------------------
# DEMO_PATENTS
# ---------------------------------------------------------------------------

class TestDemoPatents:
    def test_twentysix_patents(self):
        assert len(DEMO_PATENTS) == 26

    def test_all_have_required_fields(self):
        required = {"patent_id", "title", "filing_date", "grant_date", "cpc_classes", "forward_citations"}
        for p in DEMO_PATENTS:
            for field in required:
                assert field in p, f"Missing {field}"

    def test_patent_ids_unique(self):
        ids = [p["patent_id"] for p in DEMO_PATENTS]
        assert len(ids) == len(set(ids))

    def test_titles_nonempty(self):
        for p in DEMO_PATENTS:
            assert len(p["title"]) > 10

    def test_cpc_classes_are_lists(self):
        for p in DEMO_PATENTS:
            assert isinstance(p["cpc_classes"], list)

    def test_cpc_classes_nonempty(self):
        for p in DEMO_PATENTS:
            assert len(p["cpc_classes"]) >= 1

    def test_filing_dates_valid(self):
        for p in DEMO_PATENTS:
            d = p["filing_date"]
            assert len(d) == 10
            assert d[4] == "-"
            assert 2018 <= int(d[:4]) <= 2025

    def test_grant_dates_valid(self):
        for p in DEMO_PATENTS:
            d = p["grant_date"]
            assert len(d) == 10
            assert d[4] == "-"

    def test_forward_citations_nonnegative(self):
        for p in DEMO_PATENTS:
            assert p["forward_citations"] >= 0

    def test_some_patents_have_citations(self):
        cited = [p for p in DEMO_PATENTS if p["forward_citations"] > 0]
        assert len(cited) >= 10

    def test_max_citation_at_least_10(self):
        assert max(p["forward_citations"] for p in DEMO_PATENTS) >= 10

    def test_recent_patents_exist(self):
        recent = [p for p in DEMO_PATENTS if p["filing_date"][:4] >= "2022"]
        assert len(recent) >= 8

    def test_baseline_patents_exist(self):
        baseline = [p for p in DEMO_PATENTS if "2019" <= p["filing_date"][:4] <= "2022"]
        assert len(baseline) >= 8


# ---------------------------------------------------------------------------
# DEMO_CASES
# ---------------------------------------------------------------------------

class TestDemoCases:
    def test_four_cases(self):
        assert len(DEMO_CASES) == 4

    def test_all_have_required_fields(self):
        required = {"case_id", "case_name", "court", "filed_date", "status", "case_type", "summary"}
        for c in DEMO_CASES:
            for field in required:
                assert field in c, f"Missing {field}"

    def test_case_ids_unique(self):
        ids = [c["case_id"] for c in DEMO_CASES]
        assert len(ids) == len(set(ids))

    def test_statuses_valid(self):
        valid = {"ACTIVE", "CLOSED", "SETTLED", "PENDING"}
        for c in DEMO_CASES:
            assert c["status"] in valid

    def test_case_types_valid(self):
        valid = {"IP_DISPUTE", "CONTRACT", "EMPLOYMENT", "REGULATORY", "SECURITIES"}
        for c in DEMO_CASES:
            assert c["case_type"] in valid

    def test_two_active_cases(self):
        active = [c for c in DEMO_CASES if c["status"] == "ACTIVE"]
        assert len(active) == 2

    def test_one_settled_case(self):
        settled = [c for c in DEMO_CASES if c["status"] == "SETTLED"]
        assert len(settled) == 1

    def test_one_closed_case(self):
        closed = [c for c in DEMO_CASES if c["status"] == "CLOSED"]
        assert len(closed) == 1

    def test_one_ip_dispute(self):
        ip = [c for c in DEMO_CASES if c["case_type"] == "IP_DISPUTE"]
        assert len(ip) == 1

    def test_one_securities_case(self):
        sec = [c for c in DEMO_CASES if c["case_type"] == "SECURITIES"]
        assert len(sec) == 1

    def test_summaries_nonempty(self):
        for c in DEMO_CASES:
            assert len(c["summary"]) > 50

    def test_filed_dates_valid(self):
        for c in DEMO_CASES:
            d = c["filed_date"]
            assert len(d) == 10
            assert 2020 <= int(d[:4]) <= 2025

    def test_ip_dispute_is_closed(self):
        ip = next(c for c in DEMO_CASES if c["case_type"] == "IP_DISPUTE")
        assert ip["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# DEMO_REGULATORY_DATA
# ---------------------------------------------------------------------------

class TestDemoRegulatoryData:
    def test_has_required_keys(self):
        required = {"material_weakness", "going_concern", "export_control_mentions",
                    "government_revenue_pct", "flags"}
        for key in required:
            assert key in DEMO_REGULATORY_DATA

    def test_no_material_weakness(self):
        assert DEMO_REGULATORY_DATA["material_weakness"] is False

    def test_no_going_concern(self):
        assert DEMO_REGULATORY_DATA["going_concern"] is False

    def test_export_control_mentions_positive(self):
        assert DEMO_REGULATORY_DATA["export_control_mentions"] > 0

    def test_government_revenue_high(self):
        pct = DEMO_REGULATORY_DATA["government_revenue_pct"]
        assert 0.70 <= pct <= 1.0

    def test_flags_is_list(self):
        assert isinstance(DEMO_REGULATORY_DATA["flags"], list)

    def test_three_flags(self):
        assert len(DEMO_REGULATORY_DATA["flags"]) == 3

    def test_flags_have_required_fields(self):
        for f in DEMO_REGULATORY_DATA["flags"]:
            for field in {"flag_type", "severity", "description", "filing_period", "excerpt"}:
                assert field in f

    def test_flag_types_valid(self):
        valid = {"MATERIAL_WEAKNESS", "GOING_CONCERN", "EXPORT_CONTROL",
                 "CONTRACT_DEPENDENCY", "SEC_COMMENT"}
        for f in DEMO_REGULATORY_DATA["flags"]:
            assert f["flag_type"] in valid

    def test_severity_valid(self):
        valid = {"HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
        for f in DEMO_REGULATORY_DATA["flags"]:
            assert f["severity"] in valid

    def test_export_control_flag_present(self):
        types = [f["flag_type"] for f in DEMO_REGULATORY_DATA["flags"]]
        assert "EXPORT_CONTROL" in types

    def test_excerpts_nonempty(self):
        for f in DEMO_REGULATORY_DATA["flags"]:
            assert len(f["excerpt"]) > 30


# ---------------------------------------------------------------------------
# DEMO_AWARDS
# ---------------------------------------------------------------------------

class TestDemoAwards:
    def test_fifteen_awards(self):
        assert len(DEMO_AWARDS) == 15

    def test_all_have_required_fields(self):
        required = {"award_id", "awarding_agency", "value_usd", "award_date", "description", "naics_code"}
        for a in DEMO_AWARDS:
            for field in required:
                assert field in a, f"Missing {field} in {a.get('award_id')}"

    def test_award_ids_unique(self):
        ids = [a["award_id"] for a in DEMO_AWARDS]
        assert len(ids) == len(set(ids))

    def test_values_positive(self):
        for a in DEMO_AWARDS:
            assert a["value_usd"] > 0

    def test_total_value_over_1b(self):
        total = sum(a["value_usd"] for a in DEMO_AWARDS)
        assert total > 1_000_000_000

    def test_dod_awards_present(self):
        dod = [a for a in DEMO_AWARDS if "Defense" in a["awarding_agency"]]
        assert len(dod) >= 5

    def test_dhs_awards_present(self):
        dhs = [a for a in DEMO_AWARDS if "Homeland" in a["awarding_agency"]]
        assert len(dhs) >= 2

    def test_dates_valid(self):
        for a in DEMO_AWARDS:
            d = a["award_date"]
            assert len(d) == 10
            assert 2022 <= int(d[:4]) <= 2025

    def test_naics_codes_nonempty(self):
        for a in DEMO_AWARDS:
            assert len(a["naics_code"]) >= 6

    def test_descriptions_nonempty(self):
        for a in DEMO_AWARDS:
            assert len(a["description"]) > 10

    def test_recent_awards_exist(self):
        recent = [a for a in DEMO_AWARDS if a["award_date"][:4] >= "2024"]
        assert len(recent) >= 3

    def test_multiple_naics_codes(self):
        codes = {a["naics_code"] for a in DEMO_AWARDS}
        assert len(codes) >= 2


# ---------------------------------------------------------------------------
# DEMO_BRIEF
# ---------------------------------------------------------------------------

class TestDemoBrief:
    def test_is_string(self):
        assert isinstance(DEMO_BRIEF, str)

    def test_substantial_length(self):
        assert len(DEMO_BRIEF) > 3000

    def test_contains_company_name(self):
        assert DEMO_COMPANY in DEMO_BRIEF

    def test_contains_ticker(self):
        assert DEMO_TICKER in DEMO_BRIEF

    def test_contains_six_sections(self):
        for section in ["I.", "II.", "III.", "IV.", "V.", "VI."]:
            assert section in DEMO_BRIEF, f"Missing section {section}"

    def test_contains_executive_summary(self):
        assert "EXECUTIVE SUMMARY" in DEMO_BRIEF

    def test_contains_ip_section(self):
        assert "IP PORTFOLIO" in DEMO_BRIEF

    def test_contains_litigation_section(self):
        assert "LITIGATION" in DEMO_BRIEF

    def test_contains_regulatory_section(self):
        assert "REGULATORY" in DEMO_BRIEF

    def test_contains_contract_section(self):
        assert "CONTRACT" in DEMO_BRIEF

    def test_contains_diligence_questions(self):
        assert "DILIGENCE" in DEMO_BRIEF

    def test_has_numbered_questions(self):
        for n in ["1.", "2.", "3.", "4.", "5."]:
            assert n in DEMO_BRIEF

    def test_restricted_header(self):
        assert "RESTRICTED" in DEMO_BRIEF or "PRIVILEGED" in DEMO_BRIEF

    def test_contains_memo_header(self):
        assert "TO:" in DEMO_BRIEF
        assert "FROM:" in DEMO_BRIEF
        assert "RE:" in DEMO_BRIEF
        assert "DATE:" in DEMO_BRIEF

    def test_references_itar(self):
        assert "ITAR" in DEMO_BRIEF

    def test_references_dod(self):
        assert "DoD" in DEMO_BRIEF or "Department of Defense" in DEMO_BRIEF


# ---------------------------------------------------------------------------
# load_seed_data(db) -- net-new, the original CLI had no persistence
# ---------------------------------------------------------------------------

class TestLoadSeedData:
    def test_creates_one_acquisition_brief(self, db_session):
        from engines.brief_seed_data import load_seed_data
        from models.brief import AcquisitionBrief
        load_seed_data(db_session)
        assert db_session.query(AcquisitionBrief).filter_by(is_demo=True).count() == 1

    def test_idempotent(self, db_session):
        from engines.brief_seed_data import load_seed_data
        from models.brief import AcquisitionBrief
        load_seed_data(db_session)
        load_seed_data(db_session)
        assert db_session.query(AcquisitionBrief).filter_by(is_demo=True).count() == 1

    def test_resolves_against_shared_company_table(self, db_session):
        from engines.brief_seed_data import load_seed_data
        from models.brief import AcquisitionBrief
        from models.company import Company
        load_seed_data(db_session)
        row = db_session.query(AcquisitionBrief).filter_by(is_demo=True).first()
        assert row.company_id is not None
        company = db_session.get(Company, row.company_id)
        assert company is not None
        assert company.canonical_name == DEMO_COMPANY
