"""Table-driven tests for the deterministic CFIUS decision tree.

This suite IS the credibility of the project: every branch of the Part 800
analysis, including the boundary values of both substantial-interest
thresholds, asserted explicitly. If a config threshold ever changes, these
tests say exactly which determinations move.
"""

from __future__ import annotations

import pytest

from engines.jurisdiction_engine import (
    Outcome,
    TransactionFacts,
    determine_jurisdiction,
)


def facts(**overrides) -> TransactionFacts:
    """A baseline non-controlling, non-TID, no-rights transaction; each test
    overrides only what its scenario is about."""
    base = dict(
        us_business_name="Target Co",
        acquirer_name="Acquirer Ltd",
        acquirer_country="Germany",
        foreign_govt_ownership_pct=0.0,
        voting_interest_pct=10.0,
    )
    base.update(overrides)
    return TransactionFacts(**base)


# ---------------------------------------------------------------------------
# Threshold questions — jurisdiction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("country", ["United States", "usa", "US", "united states of america"])
def test_domestic_acquirer_not_covered(country):
    d = determine_jurisdiction(facts(acquirer_country=country, voting_interest_pct=100.0))
    assert d.outcome == Outcome.NOT_COVERED
    assert d.findings[-1].step == "foreign_person"


def test_non_us_business_not_covered():
    d = determine_jurisdiction(facts(is_us_business=False, voting_interest_pct=100.0))
    assert d.outcome == Outcome.NOT_COVERED
    assert d.findings[-1].step == "us_business"


def test_minority_no_rights_non_tid_not_covered():
    d = determine_jurisdiction(facts())
    assert d.outcome == Outcome.NOT_COVERED
    assert d.covered_basis is None


def test_minority_with_board_seat_but_non_tid_not_covered():
    # Access rights only create jurisdiction over TID businesses.
    d = determine_jurisdiction(facts(board_seat=True))
    assert d.outcome == Outcome.NOT_COVERED


def test_minority_tid_but_no_access_rights_not_covered():
    d = determine_jurisdiction(facts(sensitive_personal_data=True))
    assert d.outcome == Outcome.NOT_COVERED


# ---------------------------------------------------------------------------
# Control test
# ---------------------------------------------------------------------------

def test_majority_acquisition_is_covered_control():
    d = determine_jurisdiction(facts(voting_interest_pct=60.0))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.covered_basis == "control"


def test_exactly_50_pct_is_control():
    d = determine_jurisdiction(facts(voting_interest_pct=50.0))
    assert d.covered_basis == "control"


def test_49_9_pct_without_rights_is_not_control():
    d = determine_jurisdiction(facts(voting_interest_pct=49.9))
    assert d.covered_basis is None


def test_contractual_rights_create_control_below_majority():
    d = determine_jurisdiction(facts(voting_interest_pct=20.0, contractual_control_rights=True))
    assert d.covered_basis == "control"
    assert d.outcome == Outcome.COVERED_VOLUNTARY


# ---------------------------------------------------------------------------
# Covered investment test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("right", [
    "board_seat", "board_observer", "access_nonpublic_tech_info", "substantive_decision_role",
])
def test_each_access_right_creates_covered_investment_in_tid(right):
    d = determine_jurisdiction(facts(critical_infrastructure=True, **{right: True}))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.covered_basis == "covered_investment"


def test_tid_categories_collected():
    d = determine_jurisdiction(facts(
        produces_critical_tech=True,
        critical_infrastructure=True,
        sensitive_personal_data=True,
        board_seat=True,
    ))
    assert d.is_tid
    assert set(d.tid_categories) == {
        "Critical technologies", "Critical infrastructure", "Sensitive personal data",
    }


# ---------------------------------------------------------------------------
# Mandatory declaration — substantial-interest prong (49% / 25%)
# ---------------------------------------------------------------------------

def test_substantial_interest_triggers_mandatory():
    d = determine_jurisdiction(facts(
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=28.0,
        board_observer=True,
        sensitive_personal_data=True,
    ))
    assert d.outcome == Outcome.MANDATORY_DECLARATION
    assert d.mandatory_reasons == ["substantial_interest"]
    assert d.covered_basis == "covered_investment"


def test_substantial_interest_boundaries_inclusive():
    # Exactly 49% government interest and exactly 25% acquired both count.
    d = determine_jurisdiction(facts(
        foreign_govt_ownership_pct=49.0,
        voting_interest_pct=25.0,
        board_seat=True,
        critical_infrastructure=True,
    ))
    assert d.outcome == Outcome.MANDATORY_DECLARATION


def test_govt_interest_just_below_49_not_mandatory():
    d = determine_jurisdiction(facts(
        foreign_govt_ownership_pct=48.9,
        voting_interest_pct=30.0,
        board_seat=True,
        critical_infrastructure=True,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.mandatory_reasons == []


def test_acquisition_just_below_25_not_mandatory():
    d = determine_jurisdiction(facts(
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=24.9,
        board_seat=True,
        critical_infrastructure=True,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.mandatory_reasons == []


def test_substantial_interest_requires_tid():
    # 100% state-owned acquirer taking 60% of a NON-TID business: covered
    # control transaction, but the substantial-interest prong needs TID.
    d = determine_jurisdiction(facts(
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=60.0,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.covered_basis == "control"


# ---------------------------------------------------------------------------
# Mandatory declaration — critical-technology prong
# ---------------------------------------------------------------------------

def test_critical_tech_with_export_authorization_triggers_mandatory():
    d = determine_jurisdiction(facts(
        voting_interest_pct=60.0,
        produces_critical_tech=True,
        export_authorization_required=True,
    ))
    assert d.outcome == Outcome.MANDATORY_DECLARATION
    assert d.mandatory_reasons == ["critical_technology"]


def test_critical_tech_without_export_authorization_not_mandatory():
    # Critical tech exportable license-free to the acquirer's country (e.g.
    # EAR item with a country exception) → covered, but no mandatory filing.
    d = determine_jurisdiction(facts(
        voting_interest_pct=60.0,
        produces_critical_tech=True,
        export_authorization_required=False,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY


def test_export_flag_alone_without_critical_tech_is_inert():
    d = determine_jurisdiction(facts(
        voting_interest_pct=60.0,
        export_authorization_required=True,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.mandatory_reasons == []


def test_mandatory_prongs_never_run_when_not_covered():
    # Critical tech + export license needed, but a 5% passive stake with no
    # rights: CFIUS has no jurisdiction, so nothing can be mandatory.
    d = determine_jurisdiction(facts(
        voting_interest_pct=5.0,
        produces_critical_tech=True,
        export_authorization_required=True,
    ))
    assert d.outcome == Outcome.NOT_COVERED
    assert d.mandatory_reasons == []
    assert all(not f.step.startswith("mandatory") for f in d.findings)


def test_both_prongs_can_trigger_together():
    d = determine_jurisdiction(facts(
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        board_seat=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    ))
    assert d.outcome == Outcome.MANDATORY_DECLARATION
    assert set(d.mandatory_reasons) == {"substantial_interest", "critical_technology"}


# ---------------------------------------------------------------------------
# Excepted investors (Australia, Canada, New Zealand, United Kingdom)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("country", ["Canada", "canada", "UNITED KINGDOM", "Australia", "New Zealand"])
def test_excepted_state_recognized_case_insensitive(country):
    d = determine_jurisdiction(facts(acquirer_country=country, voting_interest_pct=100.0))
    assert d.excepted_investor


def test_excepted_investor_control_still_covered_but_never_mandatory():
    # Excepted status does NOT remove control jurisdiction — it removes the
    # filing obligation. Even a UK state-backed buyer of critical tech files
    # voluntarily, not mandatorily.
    d = determine_jurisdiction(facts(
        acquirer_country="United Kingdom",
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=100.0,
        produces_critical_tech=True,
        export_authorization_required=True,
    ))
    assert d.outcome == Outcome.COVERED_VOLUNTARY
    assert d.covered_basis == "control"
    assert d.mandatory_reasons == []
    assert any(f.step == "mandatory_exemption" for f in d.findings)


def test_excepted_investor_carved_out_of_covered_investment():
    # The same minority-with-board-seat deal that is covered for a German
    # investor is NOT covered at all for a Canadian one.
    base = dict(voting_interest_pct=15.0, board_seat=True, critical_infrastructure=True)
    german = determine_jurisdiction(facts(acquirer_country="Germany", **base))
    canadian = determine_jurisdiction(facts(acquirer_country="Canada", **base))
    assert german.outcome == Outcome.COVERED_VOLUNTARY
    assert canadian.outcome == Outcome.NOT_COVERED


# ---------------------------------------------------------------------------
# Audit-trail invariants
# ---------------------------------------------------------------------------

def test_every_finding_has_question_determination_and_citation():
    d = determine_jurisdiction(facts(
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        board_seat=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    ))
    assert len(d.findings) >= 6
    for f in d.findings:
        assert f.question and f.determination and f.citation
        assert "800" in f.citation or "Part 800" in f.citation


def test_determinism_same_facts_same_result():
    f = facts(
        foreign_govt_ownership_pct=49.0,
        voting_interest_pct=25.0,
        board_seat=True,
        sensitive_personal_data=True,
    )
    first = determine_jurisdiction(f)
    second = determine_jurisdiction(f)
    assert first.outcome == second.outcome
    assert [x.determination for x in first.findings] == [x.determination for x in second.findings]
