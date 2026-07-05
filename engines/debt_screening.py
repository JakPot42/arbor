"""engines/debt_screening.py — runs every lender name through all three
checkers (OFAC, BIS, foreign-state-connected) and normalizes the results
into one list of ScreeningHit. Ported from
debt_exposure_monitor/screening.py. No fuzzy-matching logic lives here --
that's each checker's job; this module only orchestrates and reshapes.
"""
from __future__ import annotations

import engines.debt_bis_checker as bis_checker
import engines.debt_foreign_state_lender_checker as foreign_state_lender_checker
import shared.ofac_checker as ofac_checker
from engines.debt_models import ScreeningHit


def screen_lenders(lender_names: list[str]) -> list[ScreeningHit]:
    hits: list[ScreeningHit] = []

    for h in ofac_checker.screen_entities(lender_names):
        hits.append(ScreeningHit(
            list_name="OFAC SDN",
            lender_name=h.entity_name,
            matched_name=h.sdn_name,
            score=h.score,
            detail=f"Program: {h.sdn_program or 'unspecified'} ({h.sdn_type})",
            citation="U.S. Treasury OFAC Specially Designated Nationals List (sdn.csv/alt.csv)",
        ))

    for h in bis_checker.screen_entities(lender_names):
        hits.append(ScreeningHit(
            list_name="BIS Export Control List",
            lender_name=h.entity_name,
            matched_name=h.matched_name,
            score=h.score,
            detail=h.source_list,
            citation="Consolidated Screening List (International Trade Administration / BIS)",
        ))

    for h in foreign_state_lender_checker.screen_entities(lender_names):
        hits.append(ScreeningHit(
            list_name="Foreign State-Connected Lender",
            lender_name=h.entity_name,
            matched_name=h.matched_name,
            score=h.score,
            detail=f"{h.country}: {h.basis}",
            citation=h.citation,
        ))

    return hits
