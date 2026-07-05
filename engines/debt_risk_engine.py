"""engines/debt_risk_engine.py — deterministic lender-concentration and
counterparty risk scoring, ported verbatim from
debt_exposure_monitor/risk_engine.py. Claude never scores; every number
here comes from counting and thresholds in configs/debt.py. "Claude
extracts, rules decide."
"""
from __future__ import annotations

from collections import Counter

from configs.debt import (
    CONCENTRATION_HHI_HIGH,
    CONCENTRATION_HHI_MODERATE,
    RISK_TIER_DEFAULT,
    RISK_TIERS,
    RISK_WEIGHT_BIS_HIT,
    RISK_WEIGHT_FOREIGN_STATE_LENDER,
    RISK_WEIGHT_HIGH_CONCENTRATION,
    RISK_WEIGHT_OFAC_HIT,
)
from engines.debt_models import LenderRecord, SupplierDebtProfile


def compute_concentration(lenders: list[LenderRecord]) -> dict:
    """Herfindahl-Hirschman Index (HHI) over each lender's SHARE OF
    DISCLOSED LENDING RELATIONSHIPS (a count-based proxy), not dollar
    volume -- disclosure text rarely gives clean per-lender dollar splits
    for a syndicate, so this substitutes relationship count. Disclosed
    simplification, not hidden: a lender named on 3 of 5 disclosed
    facilities is treated as having a 60% "share" for concentration
    purposes, which is a real signal (repeat exposure) even though it
    isn't a true dollar-weighted HHI. Scale and interpretation thresholds
    (5000/2500) follow the DOJ/FTC Horizontal Merger Guidelines convention
    for HHI (0-10000 scale; >2500 moderately concentrated, >5000 highly
    concentrated) -- reused here as a familiar, real reference scale, not
    because this is a merger-control HHI in the antitrust sense.
    """
    if not lenders:
        return {"hhi": 0, "tier": "NONE", "lender_shares": {}}

    counts = Counter(l.canonical_name for l in lenders)
    total = sum(counts.values())
    shares = {name: count / total for name, count in counts.items()}
    hhi = sum((share * 100) ** 2 for share in shares.values())

    if hhi >= CONCENTRATION_HHI_HIGH:
        tier = "HIGH"
    elif hhi >= CONCENTRATION_HHI_MODERATE:
        tier = "MODERATE"
    else:
        tier = "LOW"

    return {
        "hhi": round(hhi),
        "tier": tier,
        "lender_shares": {name: round(share * 100, 1) for name, share in shares.items()},
    }


def _tier_for_score(score: int) -> str:
    for ceiling, tier in RISK_TIERS:
        if score <= ceiling:
            return tier
    return RISK_TIER_DEFAULT


def score_debt_profile(profile: SupplierDebtProfile) -> dict:
    concentration = compute_concentration(profile.lenders)

    ofac_hits = [h for h in profile.screening_hits if h.list_name == "OFAC SDN"]
    bis_hits = [h for h in profile.screening_hits if h.list_name == "BIS Export Control List"]
    foreign_state_hits = [h for h in profile.screening_hits if h.list_name == "Foreign State-Connected Lender"]

    points = 0
    points += len(ofac_hits) * RISK_WEIGHT_OFAC_HIT
    points += len(bis_hits) * RISK_WEIGHT_BIS_HIT
    points += len(foreign_state_hits) * RISK_WEIGHT_FOREIGN_STATE_LENDER
    if concentration["tier"] == "HIGH":
        points += RISK_WEIGHT_HIGH_CONCENTRATION
    score = min(100, points)

    return {
        "score": score,
        "tier": _tier_for_score(score),
        "concentration": concentration,
        "ofac_hit_count": len(ofac_hits),
        "bis_hit_count": len(bis_hits),
        "foreign_state_hit_count": len(foreign_state_hits),
    }
