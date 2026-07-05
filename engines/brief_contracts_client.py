"""engines/brief_contracts_client.py — USASpending.gov API client,
federal contract award history. Ported verbatim from
acquisition_brief/contracts_client.py.
"""
from __future__ import annotations

import time
import requests

from configs.brief import USASPENDING_BASE, USASPENDING_RATE_LIMIT, CONTRACT_HIGH_DEP_PCT, CONTRACT_MODERATE_PCT
from engines.brief_models import ContractAward, ContractProfile
from engines.brief_seed_data import DEMO_AWARDS


def fetch_awards(company: str, *, demo_mode: bool = True) -> list[dict]:
    """Return raw contract award dicts (demo or live)."""
    if demo_mode:
        return list(DEMO_AWARDS)

    time.sleep(USASPENDING_RATE_LIMIT)
    payload = {
        "filters": {
            "recipient_search_text": [company],
            "award_type_codes": ["A", "B", "C", "D"],
        },
        "fields": ["Award ID", "Awarding Agency", "Award Amount", "Award Date",
                   "Description", "NAICS Code"],
        "page": 1,
        "limit": 50,
        "sort": "Award Amount",
        "order": "desc",
    }
    resp = requests.post(
        f"{USASPENDING_BASE}/search/spending_by_award/",
        json=payload, timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results") or []


def build_contract_profile(company: str, raw_awards: list[dict]) -> ContractProfile:
    """Convert raw award dicts into ContractProfile dataclass."""
    awards: list[ContractAward] = []
    for a in raw_awards:
        agency = (a.get("awarding_agency") or a.get("Awarding Agency") or "Unknown")
        value  = float(a.get("value_usd") or a.get("Award Amount") or 0)
        awards.append(ContractAward(
            award_id=a.get("award_id") or a.get("Award ID") or "",
            awarding_agency=agency,
            value_usd=value,
            award_date=a.get("award_date") or a.get("Award Date") or "",
            description=a.get("description") or a.get("Description") or "",
            naics_code=a.get("naics_code") or a.get("NAICS Code") or "",
        ))

    total_value = sum(a.value_usd for a in awards)
    agency_totals: dict[str, float] = {}
    for a in awards:
        agency_totals[a.awarding_agency] = agency_totals.get(a.awarding_agency, 0) + a.value_usd

    primary_agency = max(agency_totals, key=lambda k: agency_totals[k]) if agency_totals else "Unknown"
    primary_pct    = agency_totals[primary_agency] / total_value if total_value else 0.0

    # Recent awards: those with award_date >= 2 years ago
    from datetime import date
    cutoff = str(date.today().year - 2)
    recent = sum(1 for a in awards if a.award_date[:4] >= cutoff)

    naics_counts: dict[str, int] = {}
    for a in awards:
        if a.naics_code:
            naics_counts[a.naics_code] = naics_counts.get(a.naics_code, 0) + 1
    naics_top = [k for k, _ in sorted(naics_counts.items(), key=lambda x: -x[1])[:3]]

    tier = _dependency_tier(primary_pct)
    return ContractProfile(
        company=company,
        total_awards=len(awards),
        total_value_usd=total_value,
        agency_breakdown=agency_totals,
        primary_agency=primary_agency,
        primary_agency_pct=round(primary_pct, 3),
        recent_awards=recent,
        naics_top=naics_top,
        dependency_tier=tier,
        awards=awards,
    )


def _dependency_tier(primary_pct: float) -> str:
    if primary_pct >= CONTRACT_HIGH_DEP_PCT:
        return "HIGH_DEPENDENCY"
    if primary_pct >= CONTRACT_MODERATE_PCT:
        return "MODERATE"
    return "DIVERSIFIED"
