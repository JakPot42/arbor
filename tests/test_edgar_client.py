"""Tests for shared/edgar_client.py -- all HTTP mocked, no real EDGAR calls.

Covers the actual fix this file exists for (a real, working rate limiter,
where DIB Monitor's original client had none at all) and both filing-
selection strategies (get_ownership_filings / get_debt_relevant_filings),
proving each still produces exactly the behavior its source project
documented before being unified into one parameterized get_filings().
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import shared.edgar_client as edgar_client
from config import MAX_10K_10Q_PER_TRACE, MAX_8K_PER_TRACE, MAX_FILINGS_PER_TRACE
from shared.edgar_client import (
    _RateLimiter,
    _norm,
    _strip_html,
    fetch_document_text,
    find_exhibit_21,
    get_company_candidates,
    get_debt_relevant_filings,
    get_filings,
    get_ownership_filings,
)


@pytest.fixture(autouse=True)
def _reset_ticker_cache():
    """_TICKER_CACHE is a module-level singleton (deliberately, so every
    request shares one in-memory cache) -- but that means it leaks between
    tests unless reset. GhostTrace's own test suite doesn't reset this
    either (grepped directly, zero hits); it just hasn't hit a test
    ordering that exposes it. Found here because test_respects_limit
    picked up a previous test's cached rows and never called the freshly
    mocked _get at all."""
    edgar_client._TICKER_CACHE["rows"] = []
    edgar_client._TICKER_CACHE["fetched_at"] = 0.0
    yield


def _submissions_payload(rows: list[tuple[str, str, str, str]]) -> dict:
    """rows: (form, accession, primary_doc, date) -- builds EDGAR's parallel arrays."""
    return {
        "filings": {
            "recent": {
                "form": [r[0] for r in rows],
                "accessionNumber": [r[1] for r in rows],
                "primaryDocument": [r[2] for r in rows],
                "filingDate": [r[3] for r in rows],
            }
        }
    }


def _mock_get(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return MagicMock(return_value=resp)


# ---------------------------------------------------------------------------
# Rate limiter -- the actual fix. DIB Monitor's original edgar_client.py had
# no equivalent of this class at all.
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_enforces_minimum_spacing(self):
        rl = _RateLimiter(max_per_second=50)  # 20ms interval
        rl.wait()
        start = time.monotonic()
        rl.wait()
        assert time.monotonic() - start >= 0.018

    def test_no_sleep_when_interval_already_elapsed(self):
        rl = _RateLimiter(max_per_second=50)
        rl.wait()
        time.sleep(0.05)
        start = time.monotonic()
        rl.wait()
        assert time.monotonic() - start < 0.01

    def test_safe_under_concurrent_callers(self):
        rl = _RateLimiter(max_per_second=100)  # 10ms interval
        timestamps: list[float] = []
        lock = threading.Lock()

        def worker():
            rl.wait()
            with lock:
                timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        timestamps.sort()
        gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
        assert all(g >= 0.008 for g in gaps), f"requests too close together: {gaps}"


class TestNorm:
    def test_strips_punctuation_and_case(self):
        assert _norm("Tesla, Inc.") == "tesla inc"


class TestGetCompanyCandidates:
    def test_exact_ticker_match_ranked_first(self):
        payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 1, "ticker": "ZZZ", "title": "AAPL Holdings"},
        }
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_company_candidates("AAPL")
        assert out[0]["ticker"] == "AAPL"

    def test_empty_query_returns_empty(self):
        assert get_company_candidates("   ") == []

    def test_respects_limit(self):
        payload = {str(i): {"cik_str": i, "ticker": f"T{i}", "title": f"Acme {i}"} for i in range(20)}
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_company_candidates("Acme", limit=3)
        assert len(out) == 3


# ---------------------------------------------------------------------------
# get_filings -- the generic function -- and the two named strategies that
# must reproduce each source project's original, documented behavior.
# ---------------------------------------------------------------------------

class TestGetFilingsGeneric:
    def test_single_per_form_keeps_only_latest(self):
        payload = _submissions_payload([
            ("10-K", "acc-new", "a.htm", "2026-03-01"),
            ("10-K", "acc-old", "b.htm", "2025-03-01"),
        ])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_filings(1, ["10-K"], single_per_form={"10-K"})
        assert len(out) == 1
        assert out[0]["accession_number"] == "acc-new"

    def test_max_per_form_caps_independently(self):
        payload = _submissions_payload(
            [("10-K", f"k{i}", f"{i}.htm", "2026-01-01") for i in range(5)]
            + [("8-K", f"e{i}", f"{i}.htm", "2026-01-01") for i in range(5)]
        )
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_filings(1, ["10-K", "8-K"], max_per_form={"10-K": 2, "8-K": 3})
        assert sum(1 for f in out if f["form"] == "10-K") == 2
        assert sum(1 for f in out if f["form"] == "8-K") == 3

    def test_max_total_stops_across_all_forms(self):
        payload = _submissions_payload([("SC 13D", f"a{i}", f"{i}.htm", "2026-01-01") for i in range(25)])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_filings(1, ["SC 13D"], max_total=10)
        assert len(out) == 10

    def test_form_not_in_list_excluded(self):
        payload = _submissions_payload([("4", "a1", "a.htm", "2026-01-01"), ("10-K", "a2", "b.htm", "2026-01-01")])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_filings(1, ["10-K"])
        assert len(out) == 1
        assert out[0]["form"] == "10-K"


class TestGetOwnershipFilings:
    """Must reproduce GhostTrace's exact documented behavior: every
    13D/13G kept, only the latest 10-K/DEF 14A, capped at
    MAX_FILINGS_PER_TRACE total."""

    def test_filters_to_target_forms_and_keeps_latest_10k_only(self):
        payload = _submissions_payload([
            ("8-K", "acc-1", "a.htm", "2026-06-01"),
            ("SC 13D", "acc-2", "b.htm", "2026-05-20"),
            ("10-K", "acc-3", "c.htm", "2026-03-01"),
            ("10-K", "acc-4", "d.htm", "2025-03-01"),
            ("DEF 14A", "acc-5", "e.htm", "2026-04-01"),
            ("SC 13G", "acc-6", "f.htm", "2026-02-11"),
        ])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_ownership_filings(320193)
        forms = [f["form"] for f in out]
        assert forms == ["SC 13D", "10-K", "DEF 14A", "SC 13G"]
        assert all(f["accession_number"] != "acc-4" for f in out)

    def test_keeps_multiple_13ds(self):
        payload = _submissions_payload([("SC 13D", f"acc-{i}", f"{i}.htm", "2026-01-01") for i in range(4)])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_ownership_filings(1)
        assert len(out) == 4

    def test_respects_total_cap(self):
        payload = _submissions_payload([("SC 13D", f"acc-{i}", f"{i}.htm", "2026-01-01") for i in range(25)])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_ownership_filings(1)
        assert len(out) == MAX_FILINGS_PER_TRACE

    def test_empty_history(self):
        with patch("shared.edgar_client._get", _mock_get({"filings": {"recent": {}}})):
            assert get_ownership_filings(1) == []


class TestGetDebtRelevantFilings:
    """Must reproduce Debt Exposure Monitor's exact documented behavior:
    10-K/10-Q capped at MAX_10K_10Q_PER_TRACE each, 8-K capped at
    MAX_8K_PER_TRACE, no total cap."""

    def test_caps_10k_and_10q_independently(self):
        payload = _submissions_payload(
            [("10-K", f"k{i}", f"{i}.htm", "2026-01-01") for i in range(5)]
            + [("10-Q", f"q{i}", f"{i}.htm", "2026-01-01") for i in range(5)]
        )
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_debt_relevant_filings(1)
        assert sum(1 for f in out if f["form"] == "10-K") == MAX_10K_10Q_PER_TRACE
        assert sum(1 for f in out if f["form"] == "10-Q") == MAX_10K_10Q_PER_TRACE

    def test_caps_8k_at_higher_limit(self):
        payload = _submissions_payload([("8-K", f"e{i}", f"{i}.htm", "2026-01-01") for i in range(10)])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_debt_relevant_filings(1)
        assert len(out) == MAX_8K_PER_TRACE

    def test_excludes_ownership_forms(self):
        payload = _submissions_payload([("SC 13D", "a1", "a.htm", "2026-01-01"), ("10-K", "a2", "b.htm", "2026-01-01")])
        with patch("shared.edgar_client._get", _mock_get(payload)):
            out = get_debt_relevant_filings(1)
        assert len(out) == 1
        assert out[0]["form"] == "10-K"


class TestFindExhibit21:
    def test_finds_ex21_variant(self):
        assert find_exhibit_21(["doc.htm", "ex21_1.htm"]) == "ex21_1.htm"

    def test_returns_none_when_absent(self):
        assert find_exhibit_21(["doc.htm", "ex10_1.htm"]) is None


class TestStripHtml:
    def test_strips_script_and_style(self):
        html = "<html><head><style>.x{}</style></head><body><script>bad()</script>Hello <b>World</b></body></html>"
        assert "bad()" not in _strip_html(html)
        assert "Hello" in _strip_html(html)
        assert "World" in _strip_html(html)


class TestFetchDocumentText:
    def test_strips_html_for_htm_documents(self):
        resp = MagicMock()
        resp.text = "<p>Filing text</p>"
        with patch("shared.edgar_client._get", MagicMock(return_value=resp)):
            text = fetch_document_text(1, "0001-23-456789", "doc.htm")
        assert text == "Filing text"

    def test_leaves_plain_text_untouched(self):
        resp = MagicMock()
        resp.text = "Plain filing text"
        with patch("shared.edgar_client._get", MagicMock(return_value=resp)):
            text = fetch_document_text(1, "0001-23-456789", "doc.txt")
        assert text == "Plain filing text"
