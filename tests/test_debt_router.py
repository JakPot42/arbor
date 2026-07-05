"""Tests for routers/debt.py -- the net-new web layer for Debt Exposure
Monitor (step 4). Real seed data (Meridian Defense Systems) verifies the
dashboard/detail pages render real computed risk data, not mocks.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app


def test_dashboard_renders():
    with TestClient(app) as client:
        resp = client.get("/debt/")
    assert resp.status_code == 200
    assert "Debt Exposure Monitor" in resp.text


def test_dashboard_lists_demo_profile():
    with TestClient(app) as client:
        resp = client.get("/debt/")
    assert "Meridian Defense Systems" in resp.text
    assert "(demo)" in resp.text


def test_demo_profile_detail_shows_real_risk_score():
    with TestClient(app) as client:
        resp = client.get("/debt/")
        # Extract the demo profile's id from its detail link.
        start = resp.text.index("/debt/profile/")
        end = resp.text.index('"', start)
        url = resp.text[start:end]
        detail = client.get(url)

    assert detail.status_code == 200
    assert "Meridian Defense Systems" in detail.text
    assert "China Development Bank" in detail.text
    assert "VTB Bank" in detail.text
    # Demo scenario has real OFAC (VTB) + foreign-state-lender (VTB + CDB)
    # hits -- the risk score must be > 0, not a placeholder.
    assert "score-number" in detail.text


def test_detail_404_for_unknown_profile():
    with TestClient(app) as client:
        resp = client.get("/debt/profile/999999")
    assert resp.status_code == 404


def test_screen_company_not_found_shows_honest_error():
    with patch("engines.debt_pipeline.edgar_client.get_company_candidates", return_value=[]):
        with TestClient(app) as client:
            resp = client.post("/debt/screen", data={"company_query": "Totally Fake Corp XYZ"})
    assert resp.status_code == 200
    assert "No EDGAR-registered company matches" in resp.text


def test_screen_ambiguous_shows_candidates():
    candidates = [
        {"cik": 1, "ticker": "ABCD", "name": "ABC Defense Systems"},
        {"cik": 2, "ticker": "ABCH", "name": "ABC Holdings Group"},
    ]
    with patch("engines.debt_pipeline.edgar_client.get_company_candidates", return_value=candidates):
        with TestClient(app) as client:
            resp = client.post("/debt/screen", data={"company_query": "ABC"})
    assert resp.status_code == 200
    assert "disambiguate" in resp.text.lower()
    assert "ABC Defense Systems" in resp.text


def test_screen_success_persists_and_redirects():
    candidates = [{"cik": 777, "ticker": "TST", "name": "Test Defense Corp"}]
    with patch("engines.debt_pipeline.edgar_client.get_company_candidates", return_value=candidates), \
         patch("engines.debt_pipeline.edgar_client.get_debt_relevant_filings", return_value=[]), \
         patch("engines.debt_pipeline.screen_lenders", return_value=[]), \
         patch("engines.debt_pipeline.trace_client.fetch_bond_activity") as mock_trace:
        from engines.debt_trace_client import TraceResult
        mock_trace.return_value = TraceResult(False, "no agreement", [])
        with TestClient(app) as client:
            resp = client.post("/debt/screen", data={"company_query": "TST"}, follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/debt/profile/")


def test_api_stats():
    with TestClient(app) as client:
        payload = client.get("/debt/api/stats").json()
    assert payload["status"] == "ok"
    assert payload["profiles"] >= 1
    assert payload["demo_mode"] is True
