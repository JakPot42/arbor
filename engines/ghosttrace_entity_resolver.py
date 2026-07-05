"""engines/ghosttrace_entity_resolver.py — ported from
ghosttrace/entity_resolver.py, WITHIN-TRACE entity deduplication (distinct
from shared/resolve_company.py's cross-tool Company resolution).

Genuinely distinct logic kept verbatim: `_jurisdictions_conflict()` (two
same-named entities in different jurisdictions is a classic shell pattern
and must never auto-merge, even at a high fuzzy score), `_merge_into()`/
`_new_canonical()` (fold sightings, track roles/sources), `resolve_entities()`/
`rewrite_links()` (the batch orchestration + relationship-endpoint rewrite).
GhostTrace's own FUZZY_AUTO_MERGE_THRESHOLD=92/FUZZY_ADJUDICATE_THRESHOLD=75
(configs/ghosttrace.py) are kept as this engine's own independently-tuned
values, not the shared cross-tool 90/75.

**One real change from the original, not preserved verbatim:** this module
no longer defines its own `normalize_name()`/`similarity()`. The original
copy had the single-pass suffix-stripping bug documented in
shared/entity_resolver.py's module docstring (mishandles stacked suffixes
like "Bank, N.A.") — GhostTrace's within-trace resolution has been running
with that bug in production the whole time. Porting it forward unfixed
while the fix sits right there in shared/entity_resolver.py would defeat
the entire point of centralizing that module. This engine now calls
shared/entity_resolver.py's already-reconciled, fixed-point functions
directly instead.
"""
from __future__ import annotations

from typing import Callable

from configs.ghosttrace import FUZZY_ADJUDICATE_THRESHOLD, FUZZY_AUTO_MERGE_THRESHOLD
from shared.entity_resolver import similarity

# Adjudicator signature: (name_a, name_b) -> bool (same entity?)
Adjudicator = Callable[[str, str], bool]


def _jurisdictions_conflict(a: str | None, b: str | None) -> bool:
    """True when both jurisdictions are stated and genuinely disagree.
    Substring containment ('Cayman Islands' vs 'Grand Cayman, Cayman
    Islands') is not a conflict. Two same-named entities in different
    jurisdictions is a classic shell pattern — they must never auto-merge."""
    if not a or not b:
        return False
    ja, jb = a.strip().lower(), b.strip().lower()
    if not ja or not jb:
        return False
    return ja not in jb and jb not in ja


def _merge_into(canonical: dict, raw: dict) -> None:
    """Fold a new sighting into an existing canonical entity. Later sightings
    fill gaps but never overwrite known values."""
    if raw["name"] not in canonical["aliases"] and raw["name"] != canonical["canonical_name"]:
        canonical["aliases"].append(raw["name"])
    for field in ("jurisdiction", "address", "entity_type"):
        if not canonical.get(field) and raw.get(field):
            canonical[field] = raw[field]
    role = raw.get("role")
    if role and role not in canonical["roles"]:
        canonical["roles"].append(role)
    for src in raw.get("sources") or ([raw["source"]] if raw.get("source") else []):
        if src and src not in canonical["sources"]:
            canonical["sources"].append(src)


def _new_canonical(raw: dict) -> dict:
    sources = list(raw.get("sources") or ([raw["source"]] if raw.get("source") else []))
    return {
        "canonical_name": raw["name"],
        "aliases": [],
        "entity_type": raw.get("entity_type"),
        "jurisdiction": raw.get("jurisdiction"),
        "address": raw.get("address"),
        "roles": [raw["role"]] if raw.get("role") else [],
        "sources": sources,
    }


def resolve_entities(
    raw_entities: list[dict],
    adjudicator: Adjudicator | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Collapse name variants into canonical entities.

    Returns (resolved_entities, alias_map) where alias_map maps every raw
    name to its canonical name — used to rewrite relationship endpoints.

    With no adjudicator, the ambiguous band stays unmerged: a missed merge
    is recoverable, a wrong merge poisons the graph.
    """
    resolved: list[dict] = []
    alias_map: dict[str, str] = {}
    verdict_cache: dict[frozenset[str], bool] = {}

    def _ask(name_a: str, name_b: str) -> bool:
        if adjudicator is None:
            return False
        key = frozenset((name_a, name_b))
        if key not in verdict_cache:
            verdict_cache[key] = adjudicator(name_a, name_b)
        return verdict_cache[key]

    for raw in raw_entities:
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        raw = {**raw, "name": name}

        best: dict | None = None
        best_score = 0.0
        for canonical in resolved:
            for variant in [canonical["canonical_name"], *canonical["aliases"]]:
                score = similarity(name, variant)
                if score > best_score:
                    best_score = score
                    best = canonical

        merged = False
        if best is not None:
            conflict = _jurisdictions_conflict(
                raw.get("jurisdiction"), best.get("jurisdiction")
            )
            if best_score >= FUZZY_AUTO_MERGE_THRESHOLD and not conflict:
                merged = True
            elif best_score >= FUZZY_ADJUDICATE_THRESHOLD or (
                best_score >= FUZZY_AUTO_MERGE_THRESHOLD and conflict
            ):
                merged = _ask(name, best["canonical_name"])

        if merged and best is not None:
            _merge_into(best, raw)
            alias_map[name] = best["canonical_name"]
        else:
            entity = _new_canonical(raw)
            resolved.append(entity)
            alias_map[name] = entity["canonical_name"]

    return resolved, alias_map


def rewrite_links(raw_links: list[dict], alias_map: dict[str, str]) -> list[dict]:
    """Rewrite relationship endpoints to canonical names and dedupe.

    A link whose endpoints collapse to the same entity (self-ownership after
    merging) is dropped — it's a resolution artifact, not a finding.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for link in raw_links:
        owner = alias_map.get((link.get("owner") or "").strip(), link.get("owner"))
        owned = alias_map.get((link.get("owned") or "").strip(), link.get("owned"))
        if not owner or not owned or owner == owned:
            continue
        key = (owner, owned)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "owner": owner,
            "owned": owned,
            "ownership_pct": link.get("ownership_pct"),
            "evidence_quote": link.get("evidence_quote"),
            "source": link.get("source"),
        })
    return out
