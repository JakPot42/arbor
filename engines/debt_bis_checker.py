"""engines/debt_bis_checker.py — BIS export-control list fuzzy-match
screening, ported from debt_exposure_monitor/bis_checker.py.

The Commerce Department's Bureau of Industry and Security publishes the
Entity List, Denied Persons List, Unverified List, and Military End User
List as part of the International Trade Administration's Consolidated
Screening List (CSL) -- a single public CSV covering eleven Commerce/
State/Treasury export-control and sanctions lists in one feed. This
module downloads that feed and filters to just the BIS-administered
rows, then applies the identical rapidfuzz token-sort matching
shared/ofac_checker.py uses.

Same "candidates, not confirmed violations" framing as OFAC screening --
every hit requires human verification.

Adds a `reset_cache()` function the original didn't have -- the same
real test-isolation gap found and fixed in shared/edgar_client.py's
`_TICKER_CACHE` during step 1 (a module-level cache with no reset hook
leaks stale rows between tests unless every test controls for it).
"""
from __future__ import annotations

import csv
import io
import logging
import urllib.request

from rapidfuzz import fuzz
from rapidfuzz import process as rfprocess

from configs.debt import BIS_MATCH_THRESHOLD, BIS_SOURCE_MARKERS, CSL_CSV_URL
from shared.entity_resolver import normalize_name

logger = logging.getLogger(__name__)

_bis_entries: list[tuple[str, str, str]] | None = None  # (normalized_name, original_name, source_list)


class BISHit:
    __slots__ = ("entity_name", "matched_name", "score", "source_list")

    def __init__(self, entity_name: str, matched_name: str, score: int, source_list: str):
        self.entity_name = entity_name
        self.matched_name = matched_name
        self.score = score
        self.source_list = source_list

    def __repr__(self) -> str:
        return f"BISHit({self.entity_name!r} ~ {self.matched_name!r}, {self.score}, {self.source_list!r})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, BISHit):
            return NotImplemented
        return (self.entity_name, self.matched_name, self.score, self.source_list) == (
            other.entity_name, other.matched_name, other.score, other.source_list,
        )


def _is_bis_source(source: str) -> bool:
    return any(marker in source for marker in BIS_SOURCE_MARKERS)


def _load() -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    req = urllib.request.Request(
        CSL_CSV_URL,
        headers={"User-Agent": "Arbor portfolio research tool (jak.potvin@gmail.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        for row in csv.DictReader(io.StringIO(content)):
            source = row.get("source", "")
            if not _is_bis_source(source):
                continue
            name = (row.get("name") or "").strip()
            if not name:
                continue
            norm = normalize_name(name)
            key = f"{norm}|{source}"
            if norm and key not in seen:
                seen.add(key)
                entries.append((norm, name, source))
        logger.info("BIS entries loaded: %d", len(entries))
    except Exception as exc:
        logger.warning("Consolidated Screening List unavailable: %s", exc)

    return entries


def _ensure_loaded() -> list[tuple[str, str, str]]:
    global _bis_entries
    if _bis_entries is None:
        _bis_entries = _load()
    return _bis_entries


def screen_entities(entity_names: list[str]) -> list[BISHit]:
    """Fuzzy-match entity names against BIS-administered export-control
    lists (Entity List, Denied Persons List, Unverified List, Military
    End User List). Results are candidates only."""
    entries = _ensure_loaded()
    if not entries:
        return []

    bis_norm_names = [e[0] for e in entries]

    hits: list[BISHit] = []
    for entity_name in entity_names:
        norm_entity = normalize_name(entity_name)
        if not norm_entity:
            continue

        results = rfprocess.extract(
            norm_entity,
            bis_norm_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=BIS_MATCH_THRESHOLD,
            limit=3,
        )
        for _matched_norm, score, idx in results:
            _norm, original, source = entries[idx]
            hits.append(BISHit(
                entity_name=entity_name,
                matched_name=original,
                score=int(score),
                source_list=source,
            ))

    return hits


def reset_cache() -> None:
    """Clear the in-memory BIS entries cache. Used in tests to inject
    mock data -- see shared/ofac_checker.py's identical function."""
    global _bis_entries
    _bis_entries = None
