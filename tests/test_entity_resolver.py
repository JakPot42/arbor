"""Tests for shared/entity_resolver.py -- including the exact two real cases
the reconciliation exists because of: Debt Exposure Monitor's stacked-suffix
fix ("Bank, N.A.") and entity_graph's known-alias gap ("GE Power")."""
from __future__ import annotations

from shared.entity_resolver import MatchBand, match_band, normalize_name, resolve_known_alias, similarity


class TestNormalizeName:
    def test_strips_punctuation_and_case(self):
        assert normalize_name("Tesla, Inc.") == "tesla"

    def test_drops_leading_the(self):
        assert normalize_name("The Boeing Company") == "boeing"

    def test_single_suffix(self):
        assert normalize_name("Acme Corp") == "acme"

    def test_stacked_suffix_wells_fargo_bank_na(self):
        """The exact real regression: GhostTrace's original single-pass
        stripper left this as "wells fargo bank" (only stripped "N.A.",
        never re-ran to also strip "bank"). The fixed-point loop must
        strip BOTH."""
        assert normalize_name("Wells Fargo Bank, N.A.") == "wells fargo"

    def test_stacked_suffix_jpmorgan_chase_bank_na(self):
        assert normalize_name("JPMorgan Chase Bank, N.A.") == "jpmorgan chase"

    def test_multi_token_suffix_llp(self):
        assert normalize_name("Smith & Jones L.L.P.") == "smith jones"


class TestSimilarity:
    def test_identical_after_normalization_scores_100(self):
        assert similarity("Acme Corp", "ACME CORPORATION") == 100.0

    def test_word_order_does_not_defeat_match(self):
        score = similarity("Capital Partners Harborview", "Harborview Capital Partners")
        assert score >= 90.0

    def test_unrelated_names_score_low(self):
        assert similarity("Acme Corp", "Zebra Holdings") < 50.0

    def test_empty_name_scores_zero(self):
        assert similarity("", "Acme Corp") == 0.0


class TestResolveKnownAlias:
    def test_ge_power_resolves_to_parent(self):
        """The real, disclosed gap entity_graph's KNOWN_ALIASES table
        exists to fix: fuzzy matching alone can't bridge these (confirmed
        below), so a curated table is checked first."""
        assert resolve_known_alias("GE Power") == "General Electric Company"

    def test_ge_power_fuzzy_score_is_actually_below_adjudicate_band(self):
        """Proves the gap is real rather than assumed -- same discipline
        as entity_graph's own test suite."""
        score = similarity("GE Power", "General Electric Company")
        assert score < 75.0

    def test_unknown_name_returns_none(self):
        assert resolve_known_alias("Totally Unrelated Company") is None


class TestMatchBand:
    def test_high_score_is_auto_merge(self):
        assert match_band(95.0) == MatchBand.AUTO_MERGE

    def test_mid_score_is_adjudicate(self):
        assert match_band(80.0) == MatchBand.ADJUDICATE

    def test_low_score_is_distinct(self):
        assert match_band(30.0) == MatchBand.DISTINCT

    def test_exact_threshold_boundaries(self):
        assert match_band(90.0) == MatchBand.AUTO_MERGE
        assert match_band(75.0) == MatchBand.ADJUDICATE
        assert match_band(74.9) == MatchBand.DISTINCT
