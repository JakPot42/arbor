"""Ported from cfius_screener/tests/test_app.py -- service layer, seed
data, and web routes. Routes now live under /cfius (route-collision fix
from the architecture review); `main.app`'s lifespan seeds all three
merged tools, not just CFIUS, so TestClient(app) is a bit heavier than the
original but functionally equivalent.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from database import SessionLocal
from engines.cfius_screening_service import findings_of, run_and_store
from engines.cfius_seed_data import load_seed_data
from engines.jurisdiction_engine import TransactionFacts
from main import app
from models.cfius import Screening


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

def test_run_and_store_round_trip():
    db = SessionLocal()
    try:
        row = run_and_store(db, TransactionFacts(
            us_business_name="RoundTrip Inc",
            acquirer_name="Foreign Hold Co",
            acquirer_country="France",
            voting_interest_pct=60.0,
        ))
        assert row.id is not None
        assert row.outcome == "COVERED_VOLUNTARY"
        assert row.covered_basis == "control"
        trail = findings_of(row)
        assert trail and all("citation" in f for f in trail)
        assert json.loads(row.mandatory_reasons_json) == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Seed data — the three demo scenarios must land on their intended branches
# ---------------------------------------------------------------------------

def _seed():
    db = SessionLocal()
    try:
        load_seed_data(db)
        return {s.us_business_name: s for s in db.query(Screening).all()}
    finally:
        db.close()


def test_seed_scenarios_hit_all_three_branches():
    rows = _seed()
    assert len(rows) == 3

    meridian = rows["Meridian Photonics Corporation"]
    assert meridian.outcome == "MANDATORY_DECLARATION"
    assert set(json.loads(meridian.mandatory_reasons_json)) == {
        "substantial_interest", "critical_technology",
    }

    truenorth = rows["TrueNorth Logistics Software LLC"]
    assert truenorth.outcome == "COVERED_VOLUNTARY"
    assert truenorth.covered_basis == "control"
    assert truenorth.excepted_investor

    helix = rows["HelixPrint Genomics Inc."]
    assert helix.outcome == "MANDATORY_DECLARATION"
    assert helix.covered_basis == "covered_investment"
    assert json.loads(helix.mandatory_reasons_json) == ["substantial_interest"]


def test_seed_is_idempotent():
    db = SessionLocal()
    try:
        load_seed_data(db)
        load_seed_data(db)
        assert db.query(Screening).count() == 3
    finally:
        db.close()


def test_seed_resolves_companies():
    """New behavior vs. the original: each seed scenario resolves against
    the shared Company table."""
    from models.company import Company
    db = SessionLocal()
    try:
        load_seed_data(db)
        row = db.query(Screening).filter_by(us_business_name="Meridian Photonics Corporation").first()
        assert row.company_id is not None
        company = db.get(Company, row.company_id)
        assert company.canonical_name == "Meridian Photonics Corporation"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Web routes — now under /cfius (route-collision fix)
# ---------------------------------------------------------------------------

def test_dashboard_and_form_render():
    with TestClient(app) as client:
        assert client.get("/cfius/").status_code == 200
        assert client.get("/cfius/screen").status_code == 200


def test_submit_screening_and_view_result():
    with TestClient(app) as client:
        resp = client.post("/cfius/screen", data={
            "us_business_name": "FormFlow Defense Systems",
            "us_business_description": "Makes ITAR-controlled targeting pods.",
            "acquirer_name": "Overseas Capital",
            "acquirer_country": "China",
            "foreign_govt_ownership_pct": "60",
            "voting_interest_pct": "30",
            "board_seat": "on",
            "produces_critical_tech": "on",
            "export_authorization_required": "on",
        }, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/cfius/screening/")
        detail = client.get(resp.headers["location"])
        assert detail.status_code == 200
        assert "Mandatory declaration required" in detail.text
        assert "31 CFR" in detail.text


def test_missing_required_fields_rejected():
    with TestClient(app) as client:
        resp = client.post("/cfius/screen", data={
            "us_business_name": "   ",
            "acquirer_name": "X",
            "acquirer_country": "China",
            "voting_interest_pct": "10",
        })
        assert resp.status_code == 422


def test_unknown_screening_404():
    with TestClient(app) as client:
        assert client.get("/cfius/screening/99999").status_code == 404


def test_api_stats():
    with TestClient(app) as client:
        payload = client.get("/cfius/api/stats").json()
        assert payload["status"] == "ok"
        # Lifespan seeding ran inside the TestClient context manager.
        assert payload["screenings"] >= 3
