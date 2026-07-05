"""engines/brief_engine.py — deterministic aggregation engine, assembles
AcquisitionBrief from domain profiles. Ported verbatim from
acquisition_brief/brief_engine.py.
"""
from __future__ import annotations

from datetime import date

from engines.brief_models import (
    AcquisitionBrief, IPPortfolio, LitigationProfile,
    RegulatoryExposure, ContractProfile,
)

_RISK_ORDER = ["CLEAN", "LOW", "MODERATE", "HIGH", "CRITICAL"]
_IP_ORDER   = {"STRONG": 0, "MODERATE": 1, "WEAK": 2, "MINIMAL": 3}
_LIT_ORDER  = {"CLEAR": 0, "NORMAL": 1, "ELEVATED": 2, "CRITICAL": 3}
_REG_ORDER  = {"CLEAN": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3}
_CON_ORDER  = {"DIVERSIFIED": 0, "MODERATE": 1, "HIGH_DEPENDENCY": 2}


def compute_overall_risk(
    ip: IPPortfolio,
    lit: LitigationProfile,
    reg: RegulatoryExposure,
    cont: ContractProfile,
) -> str:
    """Escalation rule: overall risk = max of component signals, one grade bump on double-escalation."""
    scores = [
        _IP_ORDER.get(ip.strength_tier, 2),
        _LIT_ORDER.get(lit.risk_tier, 1),
        _REG_ORDER.get(reg.exposure_tier, 1),
        _CON_ORDER.get(cont.dependency_tier, 1),
    ]
    # Map component scores -> CLEAN/LOW/MODERATE/HIGH/CRITICAL
    # IP/litigation use different scales; normalise to 0-4 RISK_ORDER index
    component_risks = [
        _ip_to_risk(ip.strength_tier),
        _lit_to_risk(lit.risk_tier),
        _reg_to_risk(reg.exposure_tier),
        _con_to_risk(cont.dependency_tier),
    ]
    max_idx   = max(_RISK_ORDER.index(r) for r in component_risks)
    elevated  = sum(1 for r in component_risks if _RISK_ORDER.index(r) >= 2)  # >= MODERATE
    # Bump one grade if >=3 components at MODERATE or above
    final_idx = min(max_idx + 1, 4) if elevated >= 3 else max_idx
    return _RISK_ORDER[final_idx]


def build_brief(
    company: str,
    ticker: str,
    ip: IPPortfolio,
    lit: LitigationProfile,
    reg: RegulatoryExposure,
    cont: ContractProfile,
    full_text: str,
    diligence_questions: list[str],
    executive_summary: str,
) -> AcquisitionBrief:
    overall = compute_overall_risk(ip, lit, reg, cont)
    return AcquisitionBrief(
        company=company,
        ticker=ticker,
        prepared_date=str(date.today()),
        ip_portfolio=ip,
        litigation_profile=lit,
        regulatory_exposure=reg,
        contract_profile=cont,
        overall_risk_tier=overall,
        diligence_questions=diligence_questions,
        executive_summary=executive_summary,
        full_text=full_text,
    )


# --- helpers ---

def _ip_to_risk(tier: str) -> str:
    return {"STRONG": "CLEAN", "MODERATE": "LOW", "WEAK": "MODERATE", "MINIMAL": "HIGH"}.get(tier, "MODERATE")

def _lit_to_risk(tier: str) -> str:
    return {"CLEAR": "CLEAN", "NORMAL": "LOW", "ELEVATED": "MODERATE", "CRITICAL": "HIGH"}.get(tier, "MODERATE")

def _reg_to_risk(tier: str) -> str:
    return {"CLEAN": "CLEAN", "LOW": "LOW", "MODERATE": "MODERATE", "HIGH": "HIGH"}.get(tier, "MODERATE")

def _con_to_risk(tier: str) -> str:
    return {"DIVERSIFIED": "CLEAN", "MODERATE": "LOW", "HIGH_DEPENDENCY": "HIGH"}.get(tier, "MODERATE")
