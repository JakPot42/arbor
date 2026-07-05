"""engines/cfius_risk_engine.py — ported verbatim from
cfius_screener/risk_engine.py (renamed on import only, to avoid colliding
with dib_risk_engine.py / ghosttrace_risk_engine.py — all three source
projects independently named this file "risk_engine.py").

No web, no database, no Claude. Every weight comes from configs/cfius.py.
Rules score; Claude (if invoked) explains.

Three analytic dimensions — Threat / Vulnerability / Consequence:

  THREAT        — How adversarial is the acquirer and its principals?
  VULNERABILITY — How much sensitive access does this deal confer?
  CONSEQUENCE   — How damaging would exploitation be at a national level?

The score is a supplement to the jurisdictional determination, NOT a
substitute. A NOT_COVERED deal can carry high risk; a MANDATORY deal
involving an excepted Five-Eyes ally carries less risk than the mandatory
label alone suggests. Use both outputs together.
"""

from __future__ import annotations

from configs.cfius import (
    CONTROL_MAJORITY_PCT,
    RISK_HIGH_RISK_COUNTRIES,
    RISK_SOE_THRESHOLD,
    RISK_TIER_CRITICAL,
    RISK_TIER_HIGH,
    RISK_TIER_MEDIUM,
    RISK_WEIGHT_BOARD_ACCESS,
    RISK_WEIGHT_CONTROL_ACQUIRED,
    RISK_WEIGHT_CRITICAL_INFRA,
    RISK_WEIGHT_CRITICAL_TECH,
    RISK_WEIGHT_DATA_EXPLOITATION,
    RISK_WEIGHT_DECISION_ROLE,
    RISK_WEIGHT_EXPORT_AUTH,
    RISK_WEIGHT_HIGH_RISK_COUNTRY,
    RISK_WEIGHT_INFRA_DISRUPTION,
    RISK_WEIGHT_MANDATORY_FILING,
    RISK_WEIGHT_SENSITIVE_DATA,
    RISK_WEIGHT_SOE_ACQUIRER,
    RISK_WEIGHT_TECH_INFO_ACCESS,
    RISK_WEIGHT_TECH_TRANSFER,
    RISK_WEIGHT_TID_CLASSIFICATION,
)
from engines.jurisdiction_engine import Determination, TransactionFacts

_HIGH_RISK_LOWER = {c.lower() for c in RISK_HIGH_RISK_COUNTRIES}


def score_transaction(facts: TransactionFacts, determination: Determination) -> dict:
    """Return a risk score dict for the transaction.

    Structure:
      {
        "threat": int,
        "vulnerability": int,
        "consequence": int,
        "total": int,          # min(100, threat+vulnerability+consequence)
        "tier": str,           # LOW / MEDIUM / HIGH / CRITICAL
        "factors": [{"dimension": str, "name": str, "points": int}, ...]
      }

    Same facts → same score every time. No randomness, no LLM.
    """
    factors: list[dict] = []

    def _add(dimension: str, name: str, points: int) -> None:
        factors.append({"dimension": dimension, "name": name, "points": points})

    # -----------------------------------------------------------------------
    # THREAT — who is the acquirer?
    # -----------------------------------------------------------------------
    if facts.acquirer_country.strip().lower() in _HIGH_RISK_LOWER:
        _add(
            "threat",
            f"Acquirer home country ({facts.acquirer_country}) is a"
            " designated high-risk state",
            RISK_WEIGHT_HIGH_RISK_COUNTRY,
        )

    if facts.foreign_govt_ownership_pct >= RISK_SOE_THRESHOLD:
        _add(
            "threat",
            f"Foreign government holds {facts.foreign_govt_ownership_pct:g}% of"
            " the acquirer (state-owned enterprise or sovereign wealth fund)",
            RISK_WEIGHT_SOE_ACQUIRER,
        )

    # -----------------------------------------------------------------------
    # VULNERABILITY — what does this deal hand over?
    # -----------------------------------------------------------------------
    if facts.produces_critical_tech:
        _add(
            "vulnerability",
            "Target produces export-controlled critical technologies",
            RISK_WEIGHT_CRITICAL_TECH,
        )

    if facts.export_authorization_required:
        _add(
            "vulnerability",
            f"Exporting those technologies to {facts.acquirer_country}"
            " would require a US export authorization",
            RISK_WEIGHT_EXPORT_AUTH,
        )

    if facts.critical_infrastructure:
        _add(
            "vulnerability",
            "Target owns or operates critical infrastructure",
            RISK_WEIGHT_CRITICAL_INFRA,
        )

    if facts.sensitive_personal_data:
        _add(
            "vulnerability",
            "Target maintains sensitive personal data on >1 million individuals",
            RISK_WEIGHT_SENSITIVE_DATA,
        )

    acquires_control = (
        facts.voting_interest_pct >= CONTROL_MAJORITY_PCT
        or facts.contractual_control_rights
    )
    if acquires_control:
        _add(
            "vulnerability",
            "Transaction confers control of the US business on the acquirer",
            RISK_WEIGHT_CONTROL_ACQUIRED,
        )

    if facts.board_seat or facts.board_observer:
        _add(
            "vulnerability",
            "Acquirer receives a board seat or board observer seat",
            RISK_WEIGHT_BOARD_ACCESS,
        )

    if facts.access_nonpublic_tech_info:
        _add(
            "vulnerability",
            "Acquirer receives access to material non-public technical information",
            RISK_WEIGHT_TECH_INFO_ACCESS,
        )

    if facts.substantive_decision_role:
        _add(
            "vulnerability",
            "Acquirer receives a role in substantive business decision-making",
            RISK_WEIGHT_DECISION_ROLE,
        )

    # -----------------------------------------------------------------------
    # CONSEQUENCE — what could a hostile actor do with that access?
    # -----------------------------------------------------------------------
    if determination.is_tid:
        cats = ", ".join(determination.tid_categories)
        _add(
            "consequence",
            f"Target is a TID US business ({cats}) — CFIUS-recognized"
            " sensitive business type",
            RISK_WEIGHT_TID_CLASSIFICATION,
        )

    if determination.mandatory_reasons:
        _add(
            "consequence",
            "Mandatory CFIUS declaration triggered — legally recognized"
            " severity level under 31 CFR § 800.401",
            RISK_WEIGHT_MANDATORY_FILING,
        )

    if facts.produces_critical_tech and facts.export_authorization_required:
        _add(
            "consequence",
            "Critical technology + export authorization required ="
            " direct adversarial technology transfer risk",
            RISK_WEIGHT_TECH_TRANSFER,
        )

    if facts.critical_infrastructure:
        _add(
            "consequence",
            "Critical infrastructure acquisition creates national-level"
            " disruption potential",
            RISK_WEIGHT_INFRA_DISRUPTION,
        )

    if facts.sensitive_personal_data:
        _add(
            "consequence",
            "Sensitive personal data on >1 million Americans creates"
            " mass exploitation and coercion risk",
            RISK_WEIGHT_DATA_EXPLOITATION,
        )

    # -----------------------------------------------------------------------
    # Totals
    # -----------------------------------------------------------------------
    threat = sum(f["points"] for f in factors if f["dimension"] == "threat")
    vulnerability = sum(f["points"] for f in factors if f["dimension"] == "vulnerability")
    consequence = sum(f["points"] for f in factors if f["dimension"] == "consequence")
    total = min(100, threat + vulnerability + consequence)

    if total >= RISK_TIER_CRITICAL:
        tier = "CRITICAL"
    elif total >= RISK_TIER_HIGH:
        tier = "HIGH"
    elif total >= RISK_TIER_MEDIUM:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return {
        "threat": threat,
        "vulnerability": vulnerability,
        "consequence": consequence,
        "total": total,
        "tier": tier,
        "factors": factors,
    }
