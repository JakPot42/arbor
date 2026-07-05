"""engines/brief_claude_generator.py — Claude Haiku synthesis, generates
pre-acquisition brief from structured domain data. Ported from
acquisition_brief/brief_generator.py.

**Two real drift bugs fixed here, not preserved:** the original hardcoded
the model string literal (`"claude-haiku-4-5-20251001"`) directly at the
call site instead of importing `config.CLAUDE_MODEL` -- flagged during
the Arbor architecture review as a real drift risk (if the portfolio-wide
pinned model ever changes, this call site would silently keep using the
old one). Also read its API key via `os.getenv("ANTHROPIC_API_KEY", "")`
directly instead of the shared `config.ANTHROPIC_API_KEY` every other
Claude call site in Arbor uses. Both fixed to match the rest of the
portfolio's convention; no other logic changed.
"""
from __future__ import annotations

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from engines.brief_models import AcquisitionBrief, IPPortfolio, LitigationProfile, RegulatoryExposure, ContractProfile
from engines.brief_seed_data import DEMO_BRIEF


class BriefGeneratorError(Exception):
    pass


def generate_brief(
    company: str,
    ticker: str,
    ip: IPPortfolio,
    lit: LitigationProfile,
    reg: RegulatoryExposure,
    cont: ContractProfile,
    *,
    demo_mode: bool = True,
) -> tuple[str, list[str], str]:
    """Return (full_text, diligence_questions, executive_summary).

    In demo mode returns the pre-baked DEMO_BRIEF; in live mode calls Claude Haiku.
    """
    if demo_mode:
        questions = _extract_demo_questions(DEMO_BRIEF)
        summary   = _extract_demo_summary(DEMO_BRIEF)
        return DEMO_BRIEF, questions, summary

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = _build_prompt(company, ticker, ip, lit, reg, cont)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        full_text = msg.content[0].text.strip()
        questions = _parse_questions(full_text)
        summary   = _parse_summary(full_text)
        return full_text, questions, summary
    except Exception as exc:
        raise BriefGeneratorError(f"Claude API error: {exc}") from exc


def _build_prompt(
    company: str, ticker: str,
    ip: IPPortfolio, lit: LitigationProfile,
    reg: RegulatoryExposure, cont: ContractProfile,
) -> str:
    top_cases = "\n".join(
        f"  - {c.case_name} ({c.court}, {c.filed_date}, {c.status}, {c.case_type}): {c.summary[:150]}..."
        for c in lit.cases[:4]
    )
    top_flags = "\n".join(
        f"  - {f.flag_type} ({f.severity}, {f.filing_period}): {f.description}"
        for f in reg.flags
    )
    agency_lines = "\n".join(
        f"  - {agency}: ${val:,.0f} ({val/cont.total_value_usd*100:.0f}%)"
        for agency, val in sorted(cont.agency_breakdown.items(), key=lambda x: -x[1])
    ) if cont.total_value_usd > 0 else "  - No awards"

    return f"""You are an M&A intelligence analyst preparing a pre-acquisition brief.
Generate a structured 6-section brief for the following target company.

TARGET: {company} (NYSE: {ticker})

IP PORTFOLIO ({ip.strength_tier}):
  Total patents: {ip.total_patents}
  Recent patents (last 3yr): {ip.recent_patents} ({ip.patent_velocity:.1f}/yr)
  Baseline velocity: {ip.baseline_velocity:.1f}/yr (velocity change: {ip.velocity_change_pct:+.1f}%)
  Top domains: {', '.join(ip.top_domains)}
  Avg forward citations: {ip.avg_citations:.1f}

LITIGATION ({lit.risk_tier}):
  Total cases: {lit.total_cases}, Active: {lit.active_cases}
  IP disputes: {lit.ip_disputes}, Regulatory actions: {lit.regulatory_actions}
  Settled last 3yr: {lit.settled_last_3yr}
  Cases:
{top_cases}

REGULATORY EXPOSURE ({reg.exposure_tier}):
  Material weakness: {reg.material_weakness}
  Going concern: {reg.going_concern}
  Export control mentions: {reg.export_control_mentions}
  Government revenue: {reg.government_revenue_pct*100:.0f}%
  Flags:
{top_flags}

CONTRACT PROFILE ({cont.dependency_tier}):
  Total awards analyzed: {cont.total_awards}
  Total value: ${cont.total_value_usd:,.0f}
  Primary agency: {cont.primary_agency} ({cont.primary_agency_pct*100:.0f}%)
  Recent awards (2yr): {cont.recent_awards}
  Agency breakdown:
{agency_lines}

Write a structured pre-acquisition intelligence brief with these exact sections:
I. EXECUTIVE SUMMARY (2-3 sentences, overall risk tier, key finding)
II. IP PORTFOLIO ASSESSMENT
III. LITIGATION RISK PROFILE
IV. REGULATORY EXPOSURE
V. GOVERNMENT CONTRACT DEPENDENCY PROFILE
VI. RECOMMENDED DILIGENCE QUESTIONS FOR COUNSEL (exactly 5 numbered questions)

Use professional government/legal memo tone. Be specific -- cite numbers. Each section 3-5 sentences.
End with PREPARED BY: Pre-Acquisition Intelligence Unit"""


def _extract_demo_questions(text: str) -> list[str]:
    """Extract numbered questions from the pre-baked brief."""
    lines = text.split("\n")
    questions: list[str] = []
    in_section = False
    for line in lines:
        if "RECOMMENDED DILIGENCE QUESTIONS" in line:
            in_section = True
            continue
        if in_section:
            stripped = line.strip()
            if stripped and stripped[0].isdigit() and "." in stripped[:3]:
                # Take first sentence of each numbered item
                q = stripped.split(":")[0] if ":" in stripped else stripped.split(".")[1].strip()
                if q:
                    questions.append(stripped[:200])
    return questions[:7]


def _extract_demo_summary(text: str) -> str:
    """Extract the executive summary paragraph from the pre-baked brief."""
    lines = text.split("\n")
    in_summary = False
    paragraphs: list[str] = []
    for line in lines:
        if "I. EXECUTIVE SUMMARY" in line:
            in_summary = True
            continue
        if in_summary:
            if line.strip().startswith("II.") or line.strip().startswith("━"):
                break
            if line.strip():
                paragraphs.append(line.strip())
    return " ".join(paragraphs)[:600]


def _parse_questions(text: str) -> list[str]:
    lines = text.split("\n")
    questions: list[str] = []
    in_section = False
    for line in lines:
        if "DILIGENCE QUESTIONS" in line.upper():
            in_section = True
            continue
        if in_section and line.strip():
            s = line.strip()
            if s and s[0].isdigit():
                questions.append(s[:200])
    return questions[:7]


def _parse_summary(text: str) -> str:
    lines = text.split("\n")
    in_summary = False
    parts: list[str] = []
    for line in lines:
        if "EXECUTIVE SUMMARY" in line.upper():
            in_summary = True
            continue
        if in_summary:
            if line.strip().startswith("II."):
                break
            if line.strip():
                parts.append(line.strip())
    return " ".join(parts)[:600]
