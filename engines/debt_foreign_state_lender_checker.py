"""engines/debt_foreign_state_lender_checker.py — flags lenders that are
majority state-owned or state-controlled by a nation on
configs.debt.HIGH_RISK_COUNTRIES. Ported from
debt_exposure_monitor/foreign_state_lender_checker.py.

This is deliberately a DIFFERENT signal than OFAC/BIS screening
(shared/ofac_checker.py, engines/debt_bis_checker.py): most institutions
on configs.debt.FOREIGN_STATE_LENDERS are NOT sanctioned (China is not
comprehensively sanctioned the way Russia/Iran/North Korea are), so a
Chinese state policy bank becoming a defense supplier's primary lender
produces zero OFAC/BIS hits. That's exactly the gap this project exists
to close. No network call: the list is small, curated, and cited
(configs/debt.py), not downloaded.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from configs.debt import FOREIGN_STATE_LENDER_MATCH_THRESHOLD, FOREIGN_STATE_LENDERS
from shared.entity_resolver import normalize_name


class ForeignStateLenderHit:
    __slots__ = ("entity_name", "matched_name", "score", "country", "basis", "citation")

    def __init__(self, entity_name: str, matched_name: str, score: int, country: str, basis: str, citation: str):
        self.entity_name = entity_name
        self.matched_name = matched_name
        self.score = score
        self.country = country
        self.basis = basis
        self.citation = citation

    def __eq__(self, other) -> bool:
        if not isinstance(other, ForeignStateLenderHit):
            return NotImplemented
        return (self.entity_name, self.matched_name, self.score) == (other.entity_name, other.matched_name, other.score)


def screen_entities(entity_names: list[str]) -> list[ForeignStateLenderHit]:
    hits: list[ForeignStateLenderHit] = []
    for entity_name in entity_names:
        norm_entity = normalize_name(entity_name)
        if not norm_entity:
            continue
        for record in FOREIGN_STATE_LENDERS:
            norm_known = normalize_name(record["name"])
            score = fuzz.token_sort_ratio(norm_entity, norm_known)
            if score >= FOREIGN_STATE_LENDER_MATCH_THRESHOLD:
                hits.append(ForeignStateLenderHit(
                    entity_name=entity_name,
                    matched_name=record["name"],
                    score=int(score),
                    country=record["country"],
                    basis=record["basis"],
                    citation=record["citation"],
                ))
    return hits
