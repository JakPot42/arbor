"""shared/ofac_checker.py — OFAC SDN fuzzy-match screening, one copy for
GhostTrace and CFIUS Screener (both used this independently before the
merge; DIB Monitor never had one).

Reconciles two copies, not just moves one: GhostTrace's version used its
own project's `entity_resolver.normalize_name()` (the old, single-pass,
buggy version); CFIUS Screener's version deliberately inlined a SEPARATE
`_normalize()` specifically to avoid that dependency, and in doing so
added international corporate-suffix coverage (`pte`, `pty`, `jsc`, `ooo`,
`pjsc`, `sas`, `spa` — OFAC's SDN list has plenty of non-US/non-UK
entities) that GhostTrace's list never had. This version uses
`shared/entity_resolver.py`'s reconciled `normalize_name()` (fixed-point
suffix stripping) with CFIUS's extra suffixes folded into
`config.NORMALIZE_SUFFIXES` — the dependency CFIUS avoided is no longer a
reason to duplicate logic, since there's only one shared copy to depend on
now.

Downloads sdn.csv + alt.csv on first `screen_entities()` call per process
and caches in memory — same behavior both originals had.

ALL hits are candidates — fuzzy name matching cannot confirm legal
identity. Human verification is required before any compliance action.
"""
from __future__ import annotations

import csv
import io
import logging
import urllib.request
from typing import NamedTuple

from rapidfuzz import fuzz
from rapidfuzz import process as rfprocess

from config import OFAC_MATCH_THRESHOLD, OFAC_SDN_ALT_URL, OFAC_SDN_CSV_URL
from shared.entity_resolver import normalize_name

logger = logging.getLogger(__name__)

_sdn_entries: list[tuple[str, str, str, str]] | None = None


class OFACHit(NamedTuple):
    entity_name: str   # name submitted for screening
    sdn_name: str      # matching SDN list name
    score: int         # 0-100 fuzzy similarity
    sdn_program: str   # sanctions program (e.g. SDGT, IRAN, RUSSIA)
    sdn_type: str      # individual | entity | vessel | aircraft | alias


def _fetch_csv_rows(url: str) -> list[list[str]]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Arbor portfolio research tool (jak.potvin@gmail.com)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        content = resp.read().decode("utf-8", errors="replace")
    return list(csv.reader(io.StringIO(content)))


def _load() -> list[tuple[str, str, str, str]]:
    """Download and parse SDN primary names and aliases into (norm, original, program, type)."""
    entries: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()

    try:
        for row in _fetch_csv_rows(OFAC_SDN_CSV_URL):
            if len(row) < 2:
                continue
            name = row[1].strip().strip('"')
            program = row[3].strip().strip('"') if len(row) > 3 else ""
            sdn_type = row[2].strip().strip('"').lower() if len(row) > 2 else "entity"
            if not name or name in ("-0-", "SDN Name", "Name"):
                continue
            norm = normalize_name(name)
            if norm and norm not in seen:
                seen.add(norm)
                entries.append((norm, name, program, sdn_type))
        logger.info("OFAC SDN primary: %d names loaded", len(entries))
    except Exception as exc:
        logger.warning("OFAC SDN primary list unavailable: %s", exc)

    before = len(entries)
    try:
        for row in _fetch_csv_rows(OFAC_SDN_ALT_URL):
            if len(row) < 4:
                continue
            name = row[3].strip().strip('"')
            if not name or name in ("-0-", "Alternate Name", "Alternate name"):
                continue
            norm = normalize_name(name)
            if norm and norm not in seen:
                seen.add(norm)
                entries.append((norm, name, "", "alias"))
        logger.info("OFAC SDN aliases: %d additional loaded", len(entries) - before)
    except Exception as exc:
        logger.warning("OFAC SDN alias list unavailable: %s", exc)

    return entries


def _ensure_loaded() -> list[tuple[str, str, str, str]]:
    global _sdn_entries
    if _sdn_entries is None:
        _sdn_entries = _load()
    return _sdn_entries


def screen_entities(entity_names: list[str]) -> list[OFACHit]:
    """Fuzzy-match entity names against the OFAC SDN list.

    Returns OFACHit records for every name/SDN pair whose token_sort_ratio
    meets OFAC_MATCH_THRESHOLD. Results are candidates — human verification
    required before any compliance action.
    """
    entries = _ensure_loaded()
    if not entries:
        return []

    sdn_norm_names = [e[0] for e in entries]
    hits: list[OFACHit] = []

    for entity_name in entity_names:
        norm = normalize_name(entity_name)
        if not norm:
            continue
        results = rfprocess.extract(
            norm,
            sdn_norm_names,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=OFAC_MATCH_THRESHOLD,
            limit=3,
        )
        for _matched_norm, score, idx in results:
            _, original, program, sdn_type = entries[idx]
            hits.append(OFACHit(
                entity_name=entity_name,
                sdn_name=original,
                score=int(score),
                sdn_program=program,
                sdn_type=sdn_type,
            ))

    return hits


def reset_cache() -> None:
    """Clear the in-memory SDN cache. Used in tests to inject mock data."""
    global _sdn_entries
    _sdn_entries = None
