"""engines/brief_courtlistener_client.py — CourtListener API client,
litigation history for a given company. Ported verbatim from
acquisition_brief/courtlistener_client.py.
"""
from __future__ import annotations

import time
import requests

from configs.brief import COURTLISTENER_BASE, COURTLISTENER_RATE_LIMIT
from engines.brief_models import LitigationCase, LitigationProfile
from engines.brief_seed_data import DEMO_CASES

_CASE_TYPE_MAP = {
    "patent": "IP_DISPUTE",
    "trademark": "IP_DISPUTE",
    "copyright": "IP_DISPUTE",
    "securities": "SECURITIES",
    "sec": "SECURITIES",
    "labor": "EMPLOYMENT",
    "employment": "EMPLOYMENT",
    "wage": "EMPLOYMENT",
    "contract": "CONTRACT",
    "regulatory": "REGULATORY",
    "enforcement": "REGULATORY",
}


def fetch_cases(company: str, *, demo_mode: bool = True) -> list[dict]:
    """Return raw case dicts for the company (demo or live)."""
    if demo_mode:
        return list(DEMO_CASES)

    time.sleep(COURTLISTENER_RATE_LIMIT)
    resp = requests.get(
        f"{COURTLISTENER_BASE}/dockets/",
        params={"party_name": company, "order_by": "-date_filed", "format": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("results") or []


def build_litigation_profile(company: str, raw_cases: list[dict]) -> LitigationProfile:
    """Convert raw case dicts into LitigationProfile dataclass."""
    cases: list[LitigationCase] = []
    for c in raw_cases:
        status    = (c.get("status") or "UNKNOWN").upper()
        case_type = _infer_type(c)
        cases.append(LitigationCase(
            case_id=c.get("case_id") or c.get("docket_number") or "",
            case_name=c.get("case_name") or c.get("case_name_short") or "",
            court=c.get("court") or c.get("court_citation_string") or "",
            filed_date=c.get("filed_date") or c.get("date_filed") or "",
            status=status,
            case_type=case_type,
            summary=c.get("summary") or c.get("nature_of_suit") or "",
        ))

    total       = len(cases)
    active      = sum(1 for c in cases if c.status in {"ACTIVE", "PENDING"})
    ip_disp     = sum(1 for c in cases if c.case_type == "IP_DISPUTE" and c.status in {"ACTIVE", "PENDING"})
    reg_act     = sum(1 for c in cases if c.case_type == "REGULATORY" and c.status in {"ACTIVE", "PENDING"})
    settled_3yr = sum(1 for c in cases if c.status == "SETTLED")

    tier = _litigation_tier(active, ip_disp, reg_act)
    return LitigationProfile(
        company=company,
        total_cases=total,
        active_cases=active,
        ip_disputes=ip_disp,
        regulatory_actions=reg_act,
        settled_last_3yr=settled_3yr,
        risk_tier=tier,
        cases=cases,
    )


def _infer_type(c: dict) -> str:
    text = " ".join([
        str(c.get("case_type") or ""),
        str(c.get("summary") or ""),
        str(c.get("nature_of_suit") or ""),
        str(c.get("case_name") or ""),
    ]).lower()
    for keyword, ctype in _CASE_TYPE_MAP.items():
        if keyword in text:
            return ctype
    return "CONTRACT"


def _litigation_tier(active: int, ip_disputes: int, reg_actions: int) -> str:
    from configs.brief import LIT_CRITICAL_ACTIVE, LIT_ELEVATED_ACTIVE, LIT_ELEVATED_REGULATORY
    if active >= LIT_CRITICAL_ACTIVE or (ip_disputes >= 2 and reg_actions >= 1):
        return "CRITICAL"
    if active >= LIT_ELEVATED_ACTIVE or reg_actions >= LIT_ELEVATED_REGULATORY or ip_disputes >= 1:
        return "ELEVATED"
    if active > 0:
        return "NORMAL"
    return "CLEAR"
