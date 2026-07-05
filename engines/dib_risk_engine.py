"""
engines/dib_risk_engine.py — ported verbatim from
dib_monitor/dib_monitor/risk_engine.py (renamed on import only, to avoid
colliding with cfius_risk_engine.py / ghosttrace_risk_engine.py).

Deterministic risk scoring for DIB supplier financial and ownership risk.
Claude never makes a risk determination — only extracts text and flags.
All scoring logic is in this file, citing the weights in configs/dib.py.
"""
from __future__ import annotations
from configs.dib import (
    RISK_THRESHOLDS,
    HIGH_RISK_COUNTRIES,
    LEVERAGE_WEIGHT,
    DISTRESS_WEIGHT_1YR,
    DISTRESS_WEIGHT_3YR,
    GOING_CONCERN_WEIGHT,
    MATURITY_WEIGHT,
    CFIUS_OWNER_WEIGHT,
    FOREIGN_GOV_OWNER_WEIGHT,
    HIGH_RISK_COUNTRY_WEIGHT,
    CONCENTRATION_WEIGHT_25PCT,
    CONCENTRATION_WEIGHT_10PCT,
    CONCENTRATION_WEIGHT_5PCT,
)


def _score_to_level(score: int) -> str:
    if score >= RISK_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    if score >= RISK_THRESHOLDS["HIGH"]:
        return "HIGH"
    if score >= RISK_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def compute_financial_risk(
    debt_to_ebitda: float | None,
    distress_prob_1yr: float,
    distress_prob_3yr: float,
    going_concern_flag: bool,
    near_term_maturity_mm: float | None,
) -> tuple[int, str]:
    """
    Returns (score 0–100, level string LOW/MEDIUM/HIGH/CRITICAL).
    """
    score = 0

    # Leverage component (0–30 pts): based on Debt/EBITDA ratio
    if debt_to_ebitda is not None:
        if debt_to_ebitda > 8.0:
            score += LEVERAGE_WEIGHT            # 30
        elif debt_to_ebitda > 6.0:
            score += int(LEVERAGE_WEIGHT * 0.75)   # 22
        elif debt_to_ebitda > 4.0:
            score += int(LEVERAGE_WEIGHT * 0.50)   # 15
        elif debt_to_ebitda > 2.0:
            score += int(LEVERAGE_WEIGHT * 0.25)   # 7

    # Monte Carlo distress probability (0–40 pts total)
    score += min(int(distress_prob_1yr * DISTRESS_WEIGHT_1YR * 4), DISTRESS_WEIGHT_1YR)
    score += min(int(distress_prob_3yr * DISTRESS_WEIGHT_3YR * 4), DISTRESS_WEIGHT_3YR)

    # Going concern flag (0–20 pts)
    if going_concern_flag:
        score += GOING_CONCERN_WEIGHT

    # Near-term debt maturity (0–10 pts): any scheduled maturity within 24 months
    if near_term_maturity_mm and near_term_maturity_mm > 0:
        score += MATURITY_WEIGHT

    score = min(score, 100)
    return score, _score_to_level(score)


def compute_ownership_risk(owners: list[dict]) -> tuple[int, str]:
    """
    owners: list of dicts with keys owner_name, pct_owned, country,
            cfius_flag, owner_type.
    Returns (score 0–100, level string).
    """
    score = 0

    for owner in owners:
        pct = owner.get("pct_owned") or 0
        country = owner.get("country") or ""
        cfius = owner.get("cfius_flag", False)
        owner_type = owner.get("owner_type", "")

        if cfius:
            score += CFIUS_OWNER_WEIGHT
        if "government" in owner_type.lower() and country.lower() not in {"us", "united states", "usa"}:
            score += FOREIGN_GOV_OWNER_WEIGHT
        if any(c.lower() in country.lower() for c in HIGH_RISK_COUNTRIES):
            score += HIGH_RISK_COUNTRY_WEIGHT

        # Concentration scoring
        if pct >= 25:
            score += CONCENTRATION_WEIGHT_25PCT
        elif pct >= 10:
            score += CONCENTRATION_WEIGHT_10PCT
        elif pct >= 5:
            score += CONCENTRATION_WEIGHT_5PCT

    score = min(score, 100)
    return score, _score_to_level(score)


def compute_combined_risk(financial_score: int, ownership_score: int) -> tuple[int, str]:
    """
    Blended risk: 60% financial, 40% ownership. Level is the higher of the two.
    """
    blended = int(financial_score * 0.6 + ownership_score * 0.4)
    blended = min(blended, 100)
    # Promote to the highest constituent level (if either component is CRITICAL, combined is at least HIGH)
    f_level = _score_to_level(financial_score)
    o_level = _score_to_level(ownership_score)
    b_level = _score_to_level(blended)
    level_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    max_level = max(f_level, o_level, b_level, key=lambda x: level_order.index(x))
    return blended, max_level
