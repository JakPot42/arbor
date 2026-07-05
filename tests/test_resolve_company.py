from __future__ import annotations

from models.company import Company
from shared.resolve_company import find_companies, resolve_or_create_company


class TestExactCikMatch:
    def test_matches_existing_company_by_cik(self, db_session):
        existing = Company(canonical_name="Boeing Company", cik=12927)
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(db_session, "The Boeing Co", cik=12927)

        assert result.created is False
        assert result.matched_via == "cik"
        assert result.company.id == existing.id

    def test_attaches_alias_on_cik_match(self, db_session):
        existing = Company(canonical_name="Boeing Company", cik=12927)
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(db_session, "The Boeing Co", cik=12927)

        assert "The Boeing Co" in result.company.aliases

    def test_backfills_ticker_when_missing(self, db_session):
        existing = Company(canonical_name="Boeing Company", cik=12927, ticker=None)
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(db_session, "Boeing", cik=12927, ticker="BA")

        assert result.company.ticker == "BA"

    def test_never_overwrites_existing_ticker(self, db_session):
        existing = Company(canonical_name="Boeing Company", cik=12927, ticker="BA")
        db_session.add(existing)
        db_session.flush()

        resolve_or_create_company(db_session, "Boeing", cik=12927, ticker="WRONG")

        db_session.refresh(existing)
        assert existing.ticker == "BA"


class TestKnownAlias:
    def test_ge_power_creates_parent_company(self, db_session):
        result = resolve_or_create_company(db_session, "GE Power")

        assert result.created is True
        assert result.matched_via == "known_alias"
        assert result.company.canonical_name == "General Electric Company"
        assert "GE Power" in result.company.aliases

    def test_ge_aviation_attaches_to_existing_ge_power_resolution(self, db_session):
        first = resolve_or_create_company(db_session, "GE Power")
        second = resolve_or_create_company(db_session, "GE Aviation")

        assert second.created is False
        assert second.company.id == first.company.id
        assert "GE Aviation" in second.company.aliases
        assert "GE Power" in second.company.aliases


class TestFuzzyMatch:
    def test_auto_merge_band_attaches_without_adjudicator(self, db_session):
        existing = Company(canonical_name="Harborview Capital Partners LP")
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(db_session, "Harborview Capital Partners L.P.")

        assert result.created is False
        assert result.matched_via == "auto_merge"
        assert result.company.id == existing.id

    def test_adjudicate_band_does_not_merge_without_adjudicator(self, db_session):
        """The safe default: a missed merge is recoverable, a wrong merge
        is not. Same rule GhostTrace's own entity-match adjudication
        prompt states directly."""
        # Real score, computed not assumed: similarity("Calloway Nominee
        # Services Ltd", "Calloway Nominee Ltd") == 78.0 -- inside the
        # 75-90 adjudicate band, not auto-merge and not distinct.
        existing = Company(canonical_name="Calloway Nominee Services Ltd")
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(db_session, "Calloway Nominee Ltd")

        assert result.created is True
        assert result.matched_via == "new"
        assert result.adjudicate_candidate is not None
        assert result.adjudicate_candidate.id == existing.id

    def test_adjudicate_band_merges_when_adjudicator_says_yes(self, db_session):
        existing = Company(canonical_name="Calloway Nominee Services Ltd")
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(
            db_session, "Calloway Nominee Ltd", adjudicator=lambda a, b: True
        )

        assert result.created is False
        assert result.matched_via == "adjudicated"
        assert result.company.id == existing.id

    def test_adjudicate_band_respects_adjudicator_saying_no(self, db_session):
        existing = Company(canonical_name="Calloway Nominee Services Ltd")
        db_session.add(existing)
        db_session.flush()

        result = resolve_or_create_company(
            db_session, "Calloway Nominee Ltd", adjudicator=lambda a, b: False
        )

        assert result.created is True
        assert result.matched_via == "new"

    def test_unrelated_name_creates_new_company(self, db_session):
        db_session.add(Company(canonical_name="Boeing Company"))
        db_session.flush()

        result = resolve_or_create_company(db_session, "Totally Unrelated Zebra Corp")

        assert result.created is True
        assert result.matched_via == "new"
        assert result.company.canonical_name == "Totally Unrelated Zebra Corp"


class TestBasicCreation:
    def test_first_company_is_created_fresh(self, db_session):
        result = resolve_or_create_company(db_session, "Acme Corp", cik=999, ticker="ACME")

        assert result.created is True
        assert result.matched_via == "new"
        assert result.company.canonical_name == "Acme Corp"
        assert result.company.cik == 999
        assert result.company.ticker == "ACME"

    def test_empty_name_raises(self, db_session):
        import pytest

        with pytest.raises(ValueError):
            resolve_or_create_company(db_session, "   ")


class TestFindCompanies:
    def test_finds_exact_match(self, db_session):
        c = Company(canonical_name="Boeing Company")
        db_session.add(c)
        db_session.flush()

        results = find_companies(db_session, "Boeing Company")

        assert len(results) == 1
        assert results[0][0].id == c.id
        assert results[0][1] == 100.0

    def test_finds_fuzzy_match_above_floor(self, db_session):
        c = Company(canonical_name="Arrowhead Defense Systems")
        db_session.add(c)
        db_session.flush()

        results = find_companies(db_session, "Arrowhead Defense")

        assert len(results) == 1
        assert results[0][0].id == c.id

    def test_unrelated_query_returns_nothing(self, db_session):
        db_session.add(Company(canonical_name="Boeing Company"))
        db_session.flush()

        assert find_companies(db_session, "Totally Unrelated Zebra Corp") == []

    def test_empty_query_returns_nothing(self, db_session):
        db_session.add(Company(canonical_name="Boeing Company"))
        db_session.flush()

        assert find_companies(db_session, "   ") == []

    def test_never_creates_a_company(self, db_session):
        """The whole point of find_companies existing separately from
        resolve_or_create_company: search must have zero write side
        effects."""
        find_companies(db_session, "Nonexistent Company That Should Not Be Created")
        assert db_session.query(Company).count() == 0

    def test_matches_via_alias(self, db_session):
        c = Company(canonical_name="General Electric Company")
        c.aliases = ["GE Power"]
        db_session.add(c)
        db_session.flush()

        results = find_companies(db_session, "GE Power")

        assert len(results) == 1
        assert results[0][0].id == c.id
        assert results[0][1] == 100.0

    def test_results_ranked_best_first(self, db_session):
        exact = Company(canonical_name="Atlas Pension Partners LLC")
        partial = Company(canonical_name="Atlas Capital Ltd")
        db_session.add_all([exact, partial])
        db_session.flush()

        results = find_companies(db_session, "Atlas Pension Partners LLC")

        assert results[0][0].id == exact.id
        assert results[0][1] >= results[-1][1]

    def test_respects_limit(self, db_session):
        for i in range(12):
            db_session.add(Company(canonical_name=f"Atlas Holdings {i} Inc"))
        db_session.flush()

        results = find_companies(db_session, "Atlas Holdings", limit=5)

        assert len(results) == 5
