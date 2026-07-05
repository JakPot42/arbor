"""engines/debt_risk_brief.py — generates the lender-concentration risk
brief. Ported from debt_exposure_monitor/brief.py, renamed (not
`debt_brief.py`) to avoid reading as the OTHER brief tool in Arbor
(Pre-Acquisition Brief Generator, engines/brief_*.py) -- these are two
unrelated documents that happen to share the English word "brief."

Claude only writes prose synthesis of already-computed facts (the risk
score, concentration tier, and screening hits); it never sets the score
or decides which lenders are concerning. DEMO_MODE (default) uses a
deterministic template -- zero API keys needed, matching every other
project in this portfolio.
"""
from __future__ import annotations

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE
from engines.debt_models import SupplierDebtProfile


def _demo_brief(profile: SupplierDebtProfile, risk: dict) -> str:
    lines = [
        f"Lender-Concentration Risk Brief: {profile.company_name}",
        f"Overall risk score: {risk['score']}/100 ({risk['tier']})",
        "",
        f"Disclosed lending relationships: {len(profile.lenders)} across "
        f"{len(risk['concentration']['lender_shares'])} distinct lenders.",
        f"Concentration (relationship-count HHI): {risk['concentration']['hhi']} "
        f"({risk['concentration']['tier']}).",
    ]
    if risk["ofac_hit_count"]:
        lines.append(f"OFAC SDN candidate matches: {risk['ofac_hit_count']} -- verification required.")
    if risk["bis_hit_count"]:
        lines.append(f"BIS export-control list candidate matches: {risk['bis_hit_count']} -- verification required.")
    if risk["foreign_state_hit_count"]:
        lines.append(
            f"Foreign state-connected lender matches: {risk['foreign_state_hit_count']} "
            f"-- not necessarily sanctioned, but a documented ownership/control "
            f"connection to a high-risk-country government worth independent review."
        )
    if not (risk["ofac_hit_count"] or risk["bis_hit_count"] or risk["foreign_state_hit_count"]):
        lines.append("No OFAC, BIS, or foreign state-connected lender matches among disclosed lenders.")
    if not profile.trace_available:
        lines.append(f"FINRA TRACE bond data: unavailable -- {profile.trace_note}")
    return "\n".join(lines)


_SYSTEM_PROMPT = """\
You write a short (3-5 sentence) lender-concentration risk brief for a \
defense-industrial-base financial analyst. You are given already-computed \
facts: a risk score, a concentration tier, and specific screening hits. \
Do NOT recompute or contradict the score or tier -- describe what it means \
and why, citing the specific lenders and hits you're given. Note explicitly \
whether FINRA TRACE bond data was available. Plain prose, no headers, no \
markdown, no invented facts beyond what's provided.
"""


def _claude_brief(profile: SupplierDebtProfile, risk: dict) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = (
            f"Company: {profile.company_name}\n"
            f"Risk score: {risk['score']}/100, tier {risk['tier']}\n"
            f"Concentration: HHI {risk['concentration']['hhi']} ({risk['concentration']['tier']}), "
            f"lender shares: {risk['concentration']['lender_shares']}\n"
            f"OFAC hits: {risk['ofac_hit_count']}, BIS hits: {risk['bis_hit_count']}, "
            f"foreign state-connected lender hits: {risk['foreign_state_hit_count']}\n"
            f"Screening detail: {[(h.list_name, h.lender_name, h.matched_name, h.detail) for h in profile.screening_hits]}\n"
            f"FINRA TRACE available: {profile.trace_available} ({profile.trace_note})\n"
        )
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        # Same doctrine as every Claude call site in this portfolio: catch
        # Exception (SDK raises TypeError on a missing key, not
        # anthropic.APIError), fall back rather than crash.
        return _demo_brief(profile, risk)


def generate_brief(profile: SupplierDebtProfile, risk: dict) -> str:
    return _demo_brief(profile, risk) if DEMO_MODE else _claude_brief(profile, risk)
