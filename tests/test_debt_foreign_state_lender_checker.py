"""Ported from
debt_exposure_monitor/tests/test_foreign_state_lender_checker.py -- no
network call at all."""
from __future__ import annotations

from engines.debt_foreign_state_lender_checker import screen_entities


class TestScreenEntities:
    def test_known_state_bank_matches(self):
        hits = screen_entities(["China Development Bank"])
        assert len(hits) == 1
        assert hits[0].country == "China"

    def test_unrelated_lender_no_match(self):
        hits = screen_entities(["JPMorgan Chase Bank, N.A."])
        assert hits == []

    def test_multiple_names_multiple_hits(self):
        hits = screen_entities(["China Development Bank", "VTB Bank", "Goldman Sachs & Co. LLC"])
        countries = {h.country for h in hits}
        assert countries == {"China", "Russia"}

    def test_every_hit_has_a_citation(self):
        hits = screen_entities(["Bank Melli Iran"])
        assert hits
        assert all(h.citation for h in hits)

    def test_empty_input(self):
        assert screen_entities([]) == []

    def test_prc_big_four_all_present(self):
        # Sanity check the curated list actually contains all four
        # "Big Four" PRC state commercial banks, not just the policy banks.
        names = ["Bank of China", "Industrial and Commercial Bank of China",
                 "China Construction Bank", "Agricultural Bank of China"]
        for name in names:
            assert screen_entities([name]), f"{name} should match the curated list"
