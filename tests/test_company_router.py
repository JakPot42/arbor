"""Tests for routers/company.py -- the entity-centric view, the actual
deliverable of the Arbor merger. Exercises real seed data across all
three ported tools (GhostTrace, CFIUS Screener, DIB Monitor) through
TestClient(app), the same discipline used for each tool's own route
tests.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_home_renders():
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "Search a company" in resp.text


def test_home_lists_recently_analyzed_companies():
    """Real seed data across all three tools should populate the recent
    list -- GhostTrace's Harborview, CFIUS's 3 scenarios, DIB's 2
    suppliers."""
    with TestClient(app) as client:
        resp = client.get("/")
    assert "Harborview Capital Partners LP" in resp.text
    assert "Arrowhead Defense Systems" in resp.text
    assert "Meridian Photonics Corporation" in resp.text


def test_search_exact_match_redirects_directly():
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Harborview Capital Partners LP"},
                            follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/company/")


def test_search_no_match_shows_honest_error():
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Totally Unrelated Zebra Corp"})
    assert resp.status_code == 200
    assert "has been analyzed by any tool yet" in resp.text


def test_search_empty_query_redirects_home():
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "   "}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_search_ambiguous_query_shows_disambiguation_list():
    """Two real, distinct seeded companies ('Meridian Photonics
    Corporation' from CFIUS, 'Meridian Propulsion Corp' from DIB) both
    match 'Meridian' -- neither should auto-redirect."""
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Meridian"})
    assert resp.status_code == 200
    assert "Meridian Photonics Corporation" in resp.text
    assert "Meridian Propulsion Corp" in resp.text


def test_search_never_creates_a_company():
    """A search for a company nobody has ever analyzed must not create a
    phantom Company row -- see shared/resolve_company.py's find_companies
    docstring."""
    with TestClient(app) as client:
        before = client.get("/dib/api/stats").json()
        client.post("/search", data={"query": "Nonexistent Zeta Corp XYZ"})
        after = client.get("/dib/api/stats").json()
    assert before == after


def test_company_detail_404_for_unknown_id():
    with TestClient(app) as client:
        resp = client.get("/company/999999")
    assert resp.status_code == 404


def test_company_detail_shows_dib_only_company_with_honest_empty_states():
    """Arrowhead Defense Systems only exists in DIB Monitor's seed data --
    the GhostTrace and CFIUS cards must say so, not silently omit
    themselves or show fabricated data."""
    with TestClient(app) as client:
        home = client.get("/")
        # Find Arrowhead's company id from the recent-companies list.
        resp = client.post("/search", data={"query": "Arrowhead Defense Systems"},
                            follow_redirects=False)
        assert resp.status_code == 303
        detail = client.get(resp.headers["location"])

    assert detail.status_code == 200
    assert "Arrowhead Defense Systems" in detail.text
    assert "Not yet traced" in detail.text
    assert "Not yet screened" in detail.text
    assert "badge-high\">HIGH</span>" in detail.text  # DIB's real combined_risk_level


def test_company_detail_shows_ghosttrace_only_company_with_honest_empty_states():
    """Harborview only exists in GhostTrace's seed data."""
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Harborview Capital Partners LP"},
                            follow_redirects=False)
        detail = client.get(resp.headers["location"])

    assert detail.status_code == 200
    assert "Not yet screened" in detail.text
    assert "Not yet monitored" in detail.text
    assert "badge-high\">HIGH</span>" in detail.text  # GhostTrace's real risk_level


def test_company_detail_shows_cfius_screening_outcome():
    """Meridian Photonics is CFIUS's MANDATORY_DECLARATION seed scenario."""
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Meridian Photonics Corporation"},
                            follow_redirects=False)
        detail = client.get(resp.headers["location"])

    assert detail.status_code == 200
    assert "MANDATORY DECLARATION" in detail.text
    assert "/cfius/screening/" in detail.text


def test_company_detail_links_point_to_real_tool_routes():
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Harborview Capital Partners LP"},
                            follow_redirects=False)
        detail = client.get(resp.headers["location"])

    assert "/ghosttrace/trace/" in detail.text
    assert "/cfius/screen" in detail.text  # "not yet screened" -> start-a-screening link
    assert "/dib/" in detail.text  # "not yet monitored" -> start-monitoring link
    assert "/debt/" in detail.text  # "not yet screened" (debt) -> screen-this-company link
    assert "/brief/" in detail.text  # "not yet analyzed" -> generate-a-brief link


def test_company_detail_shows_debt_profile_only_company_with_honest_empty_states():
    """Meridian Defense Systems (fictional demo entity) only exists in
    Debt Exposure Monitor's seed data (step 4) -- the other four cards
    must say so honestly."""
    with TestClient(app) as client:
        # The exact canonical name, not just "Meridian Defense Systems" --
        # two OTHER unrelated demo companies also start with "Meridian"
        # (CFIUS's Meridian Photonics, DIB's Meridian Propulsion), so a
        # partial query would land on the disambiguation list instead of
        # a direct redirect.
        resp = client.post("/search", data={"query": "Meridian Defense Systems, Inc. (fictional demo entity)"},
                            follow_redirects=False)
        assert resp.status_code == 303
        detail = client.get(resp.headers["location"])

    assert detail.status_code == 200
    assert "Not yet traced" in detail.text
    assert "Not yet monitored" in detail.text
    assert "Not yet analyzed" in detail.text
    assert "/debt/profile/" in detail.text
    assert "badge-high\">HIGH</span>" in detail.text  # Debt Exposure Monitor's real risk tier


def test_company_detail_shows_acquisition_brief_only_company_with_honest_empty_states():
    """Parsons Corporation only exists in Pre-Acquisition Brief
    Generator's seed data (step 4)."""
    with TestClient(app) as client:
        resp = client.post("/search", data={"query": "Parsons Corporation"},
                            follow_redirects=False)
        assert resp.status_code == 303
        detail = client.get(resp.headers["location"])

    assert detail.status_code == 200
    assert "Not yet traced" in detail.text
    assert "Not yet screened" in detail.text
    assert "Not yet monitored" in detail.text
    assert "badge-moderate\">MODERATE</span>" in detail.text  # Brief's real overall_risk_tier
    assert "/brief/" in detail.text
