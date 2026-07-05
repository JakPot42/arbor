"""engines/brief_uspto_client.py — USPTO PatentsView API client, IP
portfolio for a given company. Ported verbatim from
acquisition_brief/uspto_client.py.
"""
from __future__ import annotations

import time
import requests

from configs.brief import PATENTS_BASE, PATENTS_RATE_LIMIT
from engines.brief_models import IPPortfolio, PatentRecord
from engines.brief_seed_data import DEMO_PATENTS


def fetch_patents(company: str, *, demo_mode: bool = True) -> list[dict]:
    """Return raw patent dicts for the company (demo or live)."""
    if demo_mode:
        return list(DEMO_PATENTS)

    params = {
        "q": f'{{"_contains":{{"assignee_organization":"{company}"}}}}',
        "f": '["patent_id","patent_title","app_date","patent_date","cpc_subgroup_id","cited_patent_count"]',
        "o": '{"per_page":100}',
    }
    time.sleep(PATENTS_RATE_LIMIT)
    resp = requests.get(PATENTS_BASE, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("patents") or []


def build_ip_portfolio(company: str, raw_patents: list[dict]) -> IPPortfolio:
    """Convert raw patent dicts into IPPortfolio dataclass."""
    from configs.brief import IP_STRONG_MIN, IP_MODERATE_MIN, IP_WEAK_MIN, RECENT_YEARS, BASELINE_YEARS, CPC_DOMAINS
    from datetime import date

    records: list[PatentRecord] = []
    for p in raw_patents:
        pid   = p.get("patent_id") or p.get("patent_number") or ""
        title = p.get("title") or p.get("patent_title") or ""
        filing = p.get("filing_date") or p.get("app_date") or ""
        grant  = p.get("grant_date") or p.get("patent_date") or ""
        cpcs: list[str] = p.get("cpc_classes") or []
        if not cpcs:
            raw_cpc = p.get("cpc_subgroup_id")
            if isinstance(raw_cpc, list):
                cpcs = [c.get("cpc_subgroup_id", "") for c in raw_cpc if isinstance(c, dict)]
            elif isinstance(raw_cpc, str):
                cpcs = [raw_cpc]
        citations = int(p.get("forward_citations") or p.get("cited_patent_count") or 0)
        records.append(PatentRecord(
            patent_id=pid, title=title, filing_date=filing,
            grant_date=grant, cpc_classes=cpcs, forward_citations=citations,
        ))

    total = len(records)
    cutoff_year = date.today().year - RECENT_YEARS
    recent = [r for r in records if _year(r.grant_date) >= cutoff_year]
    baseline = [
        r for r in records
        if cutoff_year - BASELINE_YEARS <= _year(r.grant_date) < cutoff_year
    ]

    recent_vel = len(recent) / RECENT_YEARS if RECENT_YEARS else 0.0
    base_vel   = len(baseline) / BASELINE_YEARS if BASELINE_YEARS else 0.0
    vel_change = (recent_vel - base_vel) / base_vel * 100 if base_vel else 0.0

    avg_cit = sum(r.forward_citations for r in records) / total if total else 0.0

    # CPC domain frequency
    domain_counts: dict[str, int] = {}
    for r in records:
        for cpc in r.cpc_classes:
            prefix = cpc[:4] if len(cpc) >= 4 else cpc[:3]
            label = CPC_DOMAINS.get(prefix, f"Other ({prefix})")
            domain_counts[label] = domain_counts.get(label, 0) + 1
    top_domains = [k for k, _ in sorted(domain_counts.items(), key=lambda x: -x[1])[:4]]

    if total >= IP_STRONG_MIN:
        tier = "STRONG"
    elif total >= IP_MODERATE_MIN:
        tier = "MODERATE"
    elif total >= IP_WEAK_MIN:
        tier = "WEAK"
    else:
        tier = "MINIMAL"

    return IPPortfolio(
        company=company,
        total_patents=total,
        recent_patents=len(recent),
        patent_velocity=round(recent_vel, 1),
        baseline_velocity=round(base_vel, 1),
        velocity_change_pct=round(vel_change, 1),
        top_domains=top_domains,
        avg_citations=round(avg_cit, 1),
        strength_tier=tier,
        patents=records,
    )


def _year(date_str: str) -> int:
    """Extract year from YYYY-MM-DD, return 0 on failure."""
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return 0
