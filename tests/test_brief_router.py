"""Tests for routers/brief.py -- the net-new web layer for
Pre-Acquisition Brief Generator (step 4). Real seed data (Parsons
Corporation demo brief) verifies the dashboard/detail pages render real
computed data, not mocks.
"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from main import app


def test_dashboard_renders():
    with TestClient(app) as client:
        resp = client.get("/brief/")
    assert resp.status_code == 200
    assert "Pre-Acquisition Brief Generator" in resp.text


def test_dashboard_lists_demo_brief():
    with TestClient(app) as client:
        resp = client.get("/brief/")
    assert "Parsons Corporation" in resp.text
    assert "(demo)" in resp.text


def test_demo_brief_detail_shows_real_data():
    with TestClient(app) as client:
        resp = client.get("/brief/")
        match = re.search(r'href="(/brief/\d+)"', resp.text)
        assert match, "expected a numeric brief detail link on the dashboard"
        detail = client.get(match.group(1))

    assert detail.status_code == 200
    assert "Parsons Corporation" in detail.text
    assert "MODERATE" in detail.text
    assert "Diligence" in detail.text


def test_detail_404_for_unknown_brief():
    with TestClient(app) as client:
        resp = client.get("/brief/999999")
    assert resp.status_code == 404


def test_generate_demo_brief_persists_and_redirects():
    with TestClient(app) as client:
        resp = client.post("/brief/generate", data={
            "company": "Test Aerospace Corp",
            "ticker": "TAC",
            "demo": "true",
        }, follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/brief/")

        detail = client.get(resp.headers["location"])
    assert detail.status_code == 200
    assert "Test Aerospace Corp" in detail.text


def test_api_stats():
    with TestClient(app) as client:
        payload = client.get("/brief/api/stats").json()
    assert payload["status"] == "ok"
    assert payload["briefs"] >= 1
    assert payload["demo_mode"] is True
