"""Ported from debt_exposure_monitor/tests/test_entity_resolver.py --
only the TestDedupeLenders class. normalize_name()/similarity() are now
shared.entity_resolver's (already covered by tests/test_entity_resolver.py
from step 1) since debt_exposure_monitor's own copy was the ORIGINAL
source of the fixed-point suffix-stripping fix reconciled there -- see
engines/debt_entity_resolver.py's module docstring."""
from __future__ import annotations

from engines.debt_entity_resolver import dedupe_lenders


class TestDedupeLenders:
    def test_exact_duplicates_collapse(self):
        result = dedupe_lenders(["JPMorgan Chase Bank, N.A.", "JPMorgan Chase Bank, N.A."])
        assert result["JPMorgan Chase Bank, N.A."] == "JPMorgan Chase Bank, N.A."
        assert len(set(result.values())) == 1

    def test_close_variants_collapse_to_first_seen(self):
        names = ["JPMorgan Chase Bank, N.A.", "JPMorgan Chase Bank N.A."]
        result = dedupe_lenders(names)
        assert len(set(result.values())) == 1
        assert result[names[1]] == names[0]

    def test_distinct_lenders_stay_separate(self):
        names = ["JPMorgan Chase Bank, N.A.", "Bank of America, N.A.", "China Development Bank"]
        result = dedupe_lenders(names)
        assert len(set(result.values())) == 3

    def test_empty_list(self):
        assert dedupe_lenders([]) == {}

    def test_every_input_name_is_a_key(self):
        names = ["Goldman Sachs & Co. LLC", "Wells Fargo Bank, N.A."]
        result = dedupe_lenders(names)
        assert set(result.keys()) == set(names)
