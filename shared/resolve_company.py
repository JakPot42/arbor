"""shared/resolve_company.py — live company resolution.

This is what makes P71's (entity_graph) thesis actually true for Arbor
instead of aspirationally true: entity_graph's own adapters are static
transcriptions of each source project's seed_data.py, built once and
never re-run against a live database (see sources/ghosttrace.py's own
docstring: "a static transcription... rather than a live import of its
runtime"). Every one of Arbor's five tool routers calls
`resolve_or_create_company()` at write time, before persisting its own
tool-specific row — so the Company table is a living record of every
resolution decision, not a one-shot batch job.

Resolution order, cheapest/most-certain signal first:
  1. Exact CIK match, if the caller has one -- the strongest possible
     signal (only 3 of 5 source projects ever populate a CIK, and 2 of
     those only outside demo mode, so this is a fast path, not the only
     path).
  2. Known-alias lookup (config.KNOWN_ALIASES) -- catches a subsidiary
     name that shares no normalized tokens with its parent's name, which
     fuzzy scoring alone cannot bridge.
  3. Fuzzy match against every existing company's canonical_name + aliases.
     >= FUZZY_AUTO_MERGE_THRESHOLD merges automatically. Between that and
     FUZZY_ADJUDICATE_THRESHOLD is ambiguous -- an optional `adjudicator`
     callback may decide it (same signature P71's resolve_entities() uses:
     (name_a, name_b) -> bool), but the default with no adjudicator is to
     NOT merge. A missed merge is recoverable (the same company shows up
     as two rows until something resolves it); a wrong merge silently
     blends two real companies' records together and is much harder to
     notice or undo -- same "wrong merge is worse than a missed merge"
     rule GhostTrace's own claude_extractor.py states directly for its
     entity-match adjudication prompt.
  4. No match clears the adjudicate band -> create a new Company row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from config import MIN_QUERY_SCORE
from models.company import Company
from shared.entity_resolver import MatchBand, match_band, normalize_name, resolve_known_alias, similarity

# Adjudicator signature matches entity_graph's: (name_a, name_b) -> same entity?
Adjudicator = Callable[[str, str], bool]


@dataclass
class CompanyResolution:
    company: Company
    created: bool
    matched_via: str  # "cik" | "known_alias" | "auto_merge" | "adjudicated" | "new"
    match_score: float | None = None
    # Populated only when the adjudicate band fired with no adjudicator
    # available to decide it -- surfaced so a caller can show "possible
    # match, not merged" the same way GhostTrace shows OFAC hits as
    # candidates rather than confirmed matches, instead of silently
    # discarding the near-miss.
    adjudicate_candidate: Company | None = None


def _all_existing(db: Session) -> list[Company]:
    return db.query(Company).all()


def _best_fuzzy_match(name: str, candidates: list[Company]) -> tuple[Company | None, float]:
    best: Company | None = None
    best_score = 0.0
    for candidate in candidates:
        for variant in [candidate.canonical_name, *candidate.aliases]:
            score = similarity(name, variant)
            if score > best_score:
                best_score = score
                best = candidate
    return best, best_score


def _attach_alias(company: Company, name: str) -> None:
    if name != company.canonical_name and name not in company.aliases:
        company.aliases = [*company.aliases, name]


def _backfill_identifiers(company: Company, cik: int | None, ticker: str | None) -> None:
    """A company first resolved by fuzzy name match (no CIK yet) gets
    strengthened once a later call supplies one -- never overwrites an
    existing value, only fills a gap."""
    if cik is not None and company.cik is None:
        company.cik = cik
    if ticker is not None and company.ticker is None:
        company.ticker = ticker


def resolve_or_create_company(
    db: Session,
    name: str,
    *,
    cik: int | None = None,
    ticker: str | None = None,
    adjudicator: Adjudicator | None = None,
) -> CompanyResolution:
    name = name.strip()
    if not name:
        raise ValueError("resolve_or_create_company: name is required")

    # 1. Exact CIK match.
    if cik is not None:
        existing = db.query(Company).filter_by(cik=cik).first()
        if existing is not None:
            _attach_alias(existing, name)
            _backfill_identifiers(existing, cik, ticker)
            return CompanyResolution(company=existing, created=False, matched_via="cik")

    # 2. Known-alias lookup.
    known_parent = resolve_known_alias(name)
    if known_parent is not None:
        existing = (
            db.query(Company)
            .filter(Company.canonical_name.ilike(known_parent))
            .first()
        )
        if existing is None:
            # Fall back to normalized comparison in Python -- ilike() won't
            # catch every normalization difference (punctuation, suffixes).
            existing = next(
                (c for c in _all_existing(db) if normalize_name(c.canonical_name) == normalize_name(known_parent)),
                None,
            )
        if existing is not None:
            _attach_alias(existing, name)
            _backfill_identifiers(existing, cik, ticker)
            return CompanyResolution(company=existing, created=False, matched_via="known_alias")
        new_company = Company(canonical_name=known_parent, cik=cik, ticker=ticker)
        new_company.aliases = [name] if name != known_parent else []
        db.add(new_company)
        db.flush()
        return CompanyResolution(company=new_company, created=True, matched_via="known_alias")

    # 3. Fuzzy match against every existing company.
    best, best_score = _best_fuzzy_match(name, _all_existing(db))
    if best is not None:
        band = match_band(best_score)
        if band == MatchBand.AUTO_MERGE:
            _attach_alias(best, name)
            _backfill_identifiers(best, cik, ticker)
            return CompanyResolution(company=best, created=False, matched_via="auto_merge", match_score=best_score)
        if band == MatchBand.ADJUDICATE:
            if adjudicator is not None and adjudicator(name, best.canonical_name):
                _attach_alias(best, name)
                _backfill_identifiers(best, cik, ticker)
                return CompanyResolution(
                    company=best, created=False, matched_via="adjudicated", match_score=best_score
                )
            # No adjudicator, or adjudicator said no: create a new row but
            # surface the near-miss rather than silently dropping it.
            new_company = Company(canonical_name=name, cik=cik, ticker=ticker)
            db.add(new_company)
            db.flush()
            return CompanyResolution(
                company=new_company,
                created=True,
                matched_via="new",
                match_score=best_score,
                adjudicate_candidate=best,
            )

    # 4. No match at all -- new company.
    new_company = Company(canonical_name=name, cik=cik, ticker=ticker)
    db.add(new_company)
    db.flush()
    return CompanyResolution(company=new_company, created=True, matched_via="new")


def find_companies(db: Session, query: str, limit: int = 8) -> list[tuple[Company, float]]:
    """Read-only search against existing Company rows -- for
    routers/company.py's search box, NOT for any tool's write path.

    Deliberately does not call resolve_or_create_company(): a search is
    not an assertion that a company exists, so it must never create one.
    Ranked by fuzzy score (canonical_name + aliases, same measure
    resolve_or_create_company uses), floored at MIN_QUERY_SCORE so an
    unrelated query doesn't return noise -- SequenceMatcher finds some
    overlapping characters even between unrelated strings. Same role
    entity_graph's (P71) own find_entity() plays for its CLI `query`
    command.
    """
    query = query.strip()
    if not query:
        return []

    scored: list[tuple[Company, float]] = []
    for company in _all_existing(db):
        best_for_company = max(
            (similarity(query, variant) for variant in [company.canonical_name, *company.aliases]),
            default=0.0,
        )
        if best_for_company >= MIN_QUERY_SCORE:
            scored.append((company, best_for_company))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]
