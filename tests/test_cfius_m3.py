"""Ported from cfius_screener/tests/test_m3.py -- TVC risk scoring and
OFAC SDN screening. No test makes a real network call -- urllib is
mocked for OFAC tests.

**One real adaptation, not just a path fix:** the original's
`test_ofac_normalize_strips_suffix` tested CFIUS's own inline
`_normalize()`, which no longer exists -- shared/ofac_checker.py uses the
one reconciled `shared.entity_resolver.normalize_name()` instead (see that
module's docstring for why). Re-pointed at the reconciled function; all
four original assertions still hold with the same expected output.

**A real test-isolation bug found while verifying step 4 end-to-end, not
by inspection:** the individual OFAC tests below call `reset_cache()`
before injecting their own small fake SDN list, but had no teardown --
so whichever mocked test ran last in the full suite left that tiny fake
list cached in shared/ofac_checker.py's process-wide `_sdn_entries`
singleton. `engines/debt_seed_data.py`'s real seeding (which screens
Meridian Defense Systems' demo lenders against the REAL live OFAC list)
then silently got the stale fake list instead -- "VTB Bank" was never in
it, so its risk score came out MEDIUM instead of the correct HIGH, with
no error raised anywhere. Fixed with a module-scoped autouse fixture that
resets the cache both before AND after every test in this file, instead
of trusting each test to remember its own teardown.
"""
from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from database import SessionLocal
from fastapi.testclient import TestClient
from engines.jurisdiction_engine import TransactionFacts, determine_jurisdiction
from engines.cfius_risk_engine import score_transaction
from engines.cfius_screening_service import ofac_hits_of, risk_score_of, run_and_store


@pytest.fixture(autouse=True)
def _reset_ofac_cache():
    from shared.ofac_checker import reset_cache
    reset_cache()
    yield
    reset_cache()
from main import app
from models.cfius import Screening


# ---------------------------------------------------------------------------
# Risk engine — scoring logic
# ---------------------------------------------------------------------------

def _facts(**overrides) -> TransactionFacts:
    base = dict(
        us_business_name="Target Co",
        acquirer_name="Acquirer Ltd",
        acquirer_country="Germany",
        foreign_govt_ownership_pct=0.0,
        voting_interest_pct=10.0,
    )
    base.update(overrides)
    return TransactionFacts(**base)


def test_no_risk_factors_scores_low():
    facts = _facts()
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    assert score["tier"] == "LOW"
    assert score["total"] < 25
    assert score["factors"] == []


def test_high_risk_country_adds_threat():
    facts = _facts(acquirer_country="China")
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    threat_factors = [f for f in score["factors"] if f["dimension"] == "threat"]
    assert any("high-risk" in f["name"].lower() for f in threat_factors)
    assert score["threat"] >= 30


def test_russia_also_high_risk():
    facts = _facts(acquirer_country="Russia")
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    assert score["threat"] >= 30


def test_high_risk_country_case_insensitive():
    facts = _facts(acquirer_country="china")
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    assert score["threat"] >= 30


def test_soe_acquirer_adds_threat():
    facts = _facts(foreign_govt_ownership_pct=49.0)  # at threshold
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    assert any("state-owned" in f["name"].lower() or "sovereign" in f["name"].lower()
               for f in score["factors"] if f["dimension"] == "threat")
    assert score["threat"] >= 20


def test_soe_below_threshold_no_threat():
    facts = _facts(foreign_govt_ownership_pct=48.9)
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    soe_factors = [f for f in score["factors"]
                   if f["dimension"] == "threat" and "state-owned" in f["name"].lower()]
    assert soe_factors == []


def test_critical_tech_adds_vulnerability():
    facts = _facts(produces_critical_tech=True)
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    vuln = [f for f in score["factors"] if f["dimension"] == "vulnerability"]
    assert any("critical technologies" in f["name"].lower() for f in vuln)


def test_control_acquired_adds_vulnerability():
    facts = _facts(voting_interest_pct=51.0)
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    vuln = [f for f in score["factors"] if f["dimension"] == "vulnerability"]
    assert any("control" in f["name"].lower() for f in vuln)


def test_tid_classification_adds_consequence():
    facts = _facts(sensitive_personal_data=True)
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    cons = [f for f in score["factors"] if f["dimension"] == "consequence"]
    assert any("tid" in f["name"].lower() for f in cons)


def test_mandatory_filing_adds_consequence():
    facts = _facts(
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        board_seat=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    )
    det = determine_jurisdiction(facts)
    assert det.mandatory_reasons
    score = score_transaction(facts, det)
    cons = [f for f in score["factors"] if f["dimension"] == "consequence"]
    assert any("mandatory" in f["name"].lower() for f in cons)


def test_total_capped_at_100():
    facts = _facts(
        acquirer_country="China",
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=51.0,
        contractual_control_rights=True,
        board_seat=True,
        access_nonpublic_tech_info=True,
        substantive_decision_role=True,
        produces_critical_tech=True,
        export_authorization_required=True,
        critical_infrastructure=True,
        sensitive_personal_data=True,
    )
    det = determine_jurisdiction(facts)
    score = score_transaction(facts, det)
    assert score["total"] == 100
    assert score["tier"] == "CRITICAL"


def test_tier_thresholds():
    facts_low = _facts()
    det = determine_jurisdiction(facts_low)
    assert score_transaction(facts_low, det)["tier"] == "LOW"

    facts_crit = _facts(
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        board_seat=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    )
    det = determine_jurisdiction(facts_crit)
    assert score_transaction(facts_crit, det)["tier"] == "CRITICAL"


def test_seed_scenario_scores():
    """The three seed scenarios should hit expected tiers."""
    meridian_facts = TransactionFacts(
        us_business_name="Meridian Photonics Corporation",
        acquirer_name="Golden Harbor Capital Pte. Ltd.",
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        board_seat=True,
        access_nonpublic_tech_info=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    )
    meridian_det = determine_jurisdiction(meridian_facts)
    assert score_transaction(meridian_facts, meridian_det)["tier"] == "CRITICAL"

    truenorth_facts = TransactionFacts(
        us_business_name="TrueNorth Logistics Software LLC",
        acquirer_name="Laurentide Pension Investment Board",
        acquirer_country="Canada",
        foreign_govt_ownership_pct=0.0,
        voting_interest_pct=100.0,
    )
    truenorth_det = determine_jurisdiction(truenorth_facts)
    assert score_transaction(truenorth_facts, truenorth_det)["tier"] == "LOW"

    helix_facts = TransactionFacts(
        us_business_name="HelixPrint Genomics Inc.",
        acquirer_name="Al Dhafra Strategic Investments PJSC",
        acquirer_country="United Arab Emirates",
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=28.0,
        board_observer=True,
        sensitive_personal_data=True,
    )
    helix_det = determine_jurisdiction(helix_facts)
    helix_score = score_transaction(helix_facts, helix_det)
    assert helix_score["tier"] in ("HIGH", "CRITICAL")


def test_run_and_store_persists_risk_score():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="Risk Store Test Corp",
            acquirer_name="Beijing Ventures",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        assert row.risk_score_json is not None
        risk = risk_score_of(row)
        assert risk is not None
        assert "tier" in risk
        assert "factors" in risk
        assert risk["threat"] >= 30  # China is high-risk
    finally:
        db.close()


# ---------------------------------------------------------------------------
# OFAC checker — unit tests with mocked network
# ---------------------------------------------------------------------------

def _make_sdn_csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    return buf.getvalue().encode()


def _mock_urlopen_factory(sdn_content: bytes, alt_content: bytes = b""):
    def side_effect(req, timeout=30):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        content = sdn_content if "sdn.csv" in url else alt_content
        mock_resp = MagicMock()
        mock_resp.read.return_value = content
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp
    return side_effect


def test_ofac_no_match():
    from shared.ofac_checker import reset_cache, screen_entities
    reset_cache()

    sdn = _make_sdn_csv([
        ["1", "Innocent Bystander Corp", "entity", "SDGT"],
    ])
    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=_mock_urlopen_factory(sdn)):
        hits = screen_entities(["Completely Different Name LLC"])
    assert hits == []


def test_ofac_exact_match():
    from shared.ofac_checker import reset_cache, screen_entities
    reset_cache()

    sdn = _make_sdn_csv([
        ["42", "Global Sanctions Target Corp", "entity", "IRAN"],
    ])
    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=_mock_urlopen_factory(sdn)):
        hits = screen_entities(["Global Sanctions Target Corp"])
    assert len(hits) == 1
    assert hits[0].sdn_name == "Global Sanctions Target Corp"
    assert hits[0].score == 100
    assert hits[0].sdn_program == "IRAN"


def test_ofac_fuzzy_match():
    from shared.ofac_checker import reset_cache, screen_entities
    reset_cache()

    sdn = _make_sdn_csv([
        ["7", "Crimson Holdings Ltd", "entity", "RUSSIA"],
    ])
    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=_mock_urlopen_factory(sdn)):
        hits = screen_entities(["Crimson Holdings Limited"])
    assert len(hits) >= 1


def test_ofac_sdn_unavailable_returns_empty():
    from shared.ofac_checker import reset_cache, screen_entities
    reset_cache()

    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=Exception("network error")):
        hits = screen_entities(["Some Entity"])
    assert hits == []


def test_ofac_normalize_strips_suffix():
    """Points at the reconciled shared.entity_resolver.normalize_name()
    now (see module docstring) -- same four assertions, same expected
    output as CFIUS's own now-retired inline _normalize()."""
    from shared.entity_resolver import normalize_name
    assert normalize_name("Apex Holdings LLC") == "apex"
    assert normalize_name("The Big Corp Inc") == "big"
    assert normalize_name("Global GMBH") == "global"
    assert normalize_name("Crimson Holdings Ltd") == "crimson"


# ---------------------------------------------------------------------------
# Web routes — OFAC screening, now under /cfius
# ---------------------------------------------------------------------------

def test_ofac_screen_route_stores_results():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="OFACRouteTest Corp",
            acquirer_name="Clean Acquirer LLC",
            acquirer_country="France",
            voting_interest_pct=10.0,
        ))
        sid = row.id
    finally:
        db.close()

    from shared.ofac_checker import reset_cache
    reset_cache()

    sdn = _make_sdn_csv([["1", "Unrelated Name", "entity", "SDGT"]])
    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=_mock_urlopen_factory(sdn)):
        with TestClient(app) as client:
            resp = client.post(f"/cfius/screening/{sid}/ofac-screen",
                               follow_redirects=False)

    assert resp.status_code == 303

    db = SessionLocal()
    try:
        row = db.get(Screening, sid)
        assert row.ofac_checked_at is not None
        assert row.ofac_hits_json is not None
        assert ofac_hits_of(row) == []  # no match expected
    finally:
        db.close()


def test_ofac_screen_failure_redirects_with_error():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="OFACFail Corp",
            acquirer_name="Buyer",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        sid = row.id
    finally:
        db.close()

    from shared.ofac_checker import reset_cache
    reset_cache()

    with patch("shared.ofac_checker.urllib.request.urlopen",
               side_effect=Exception("network error")):
        with TestClient(app) as client:
            resp = client.post(f"/cfius/screening/{sid}/ofac-screen",
                               follow_redirects=False)

    assert resp.status_code == 303


def test_result_page_shows_risk_score():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="RiskDisplay Corp",
            acquirer_name="Beijing Capital",
            acquirer_country="China",
            voting_interest_pct=60.0,
        ))
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}")

    assert resp.status_code == 200
    assert "National security risk assessment" in resp.text
    assert "CRITICAL" in resp.text or "HIGH" in resp.text or "MEDIUM" in resp.text


def test_result_page_shows_ofac_not_yet_run():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="OFACNotYet Corp",
            acquirer_name="Buyer",
            acquirer_country="Germany",
            voting_interest_pct=10.0,
        ))
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}")

    assert resp.status_code == 200
    assert "OFAC SDN screening" in resp.text
    assert "Screen against OFAC SDN list" in resp.text


def test_result_page_shows_ofac_results_when_screened():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="OFACDone Corp",
            acquirer_name="Buyer",
            acquirer_country="France",
            voting_interest_pct=10.0,
        ))
        row.ofac_hits_json = json.dumps([])
        from datetime import datetime, timezone
        row.ofac_checked_at = datetime.now(timezone.utc)
        db.commit()
        sid = row.id
    finally:
        db.close()

    with TestClient(app) as client:
        resp = client.get(f"/cfius/screening/{sid}")

    assert resp.status_code == 200
    assert "No candidate SDN matches found" in resp.text
