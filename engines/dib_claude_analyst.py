"""
engines/dib_claude_analyst.py — ported from
dib_monitor/dib_monitor/claude_analyst.py (import paths only).

Claude Haiku extracts structured financial data and ownership flags
from 10-K/10-Q filing text.

Claude proposes; deterministic code scores. Same pattern as all prior projects.
"""
from __future__ import annotations
import json
import re
from typing import Optional

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from configs.dib import CLAUDE_MAX_TOKENS


class AnalystError(Exception):
    pass


_EXTRACTION_PROMPT = """\
You are a financial analyst specializing in defense-sector suppliers and SEC filings.

Extract the following financial data from the 10-K/10-Q excerpt below for {company_name}.
All dollar amounts should be in millions USD.

FILING EXCERPT:
{filing_text}

Return ONLY valid JSON with these exact keys (use null for any field you cannot find):
{{
  "revenue_mm": <float or null>,
  "total_debt_mm": <float or null>,
  "cash_mm": <float or null>,
  "ebitda_mm": <float or null>,
  "debt_service_annual_mm": <float or null>,
  "covenant_summary": "<string summarizing any financial maintenance covenants, or null>",
  "going_concern_flag": <true or false>,
  "going_concern_quote": "<direct quote of going concern language, or null>",
  "near_term_maturity_mm": <float: debt maturing within 24 months in $M, or null>,
  "near_term_maturity_date": "<string: maturity date if found, or null>",
  "confidence": "<high|medium|low>"
}}"""

_OWNERSHIP_FLAG_PROMPT = """\
You are a national security financial intelligence analyst.

For the institutional owners listed below, flag any that appear to:
1. Be controlled by or affiliated with a foreign government (China, Russia, Iran, North Korea)
2. Have names suggesting shell company structures or obscure beneficial ownership
3. Represent CFIUS-relevant national security concerns given they hold equity in a US defense supplier

COMPANY: {company_name}
OWNERS:
{owners_list}

Return a JSON array. Only include owners with genuine concerns.
Each element: {{"owner_name": "...", "flag_reason": "...", "risk_level": "HIGH|MEDIUM|LOW", "cfius_flag": true|false}}
If no owners are flagged, return an empty array []."""


_EARNINGS_SIGNAL_PROMPT = """\
You are a national security supply chain analyst reviewing an 8-K earnings call transcript \
or press release from a defense contractor supplier.

Your job: extract qualitative forward-looking signals that reveal supply chain risk in ways \
that formal 10-K filings miss. Executives often speak candidly about operational challenges, \
supplier changes, and geopolitical exposures in earnings calls.

Look specifically for:
1. Supply chain diversification language — "diversifying away from", "reducing reliance on", \
"qualifying alternate sources for", named suppliers being replaced
2. Export control impacts — BIS export controls, EAR/ITAR restrictions affecting sourcing, \
technology licensing issues, semiconductor or advanced component restrictions
3. Sole-source or concentration risk disclosures — single-country dependencies, \
named critical suppliers, program risks tied to a single source
4. Geopolitical exposure — China/Taiwan/Russia supply chain exposure, tariff impacts, \
sanctions compliance costs, "decoupling" language
5. Financial stress signals — cash flow pressure, contract delays, pricing pressure, \
lender conversations not yet in a formal 10-K

COMPANY: {company_name}

8-K EXHIBIT 99 TEXT (earnings call transcript / press release):
{transcript_text}

Return ONLY valid JSON:
{{
  "signals": ["<specific extracted signal 1>", "<specific extracted signal 2>"],
  "export_control_flag": <true|false>,
  "supplier_diversion_flag": <true|false>,
  "key_quote": "<most significant direct quote showing risk language, or null>",
  "confidence": "<high|medium|low>"
}}

If no relevant signals are found, return signals as an empty array and both flags as false."""

_PORTFOLIO_BRIEF_PROMPT = """\
You are a DoD Industrial Base Policy analyst. Below is a financial resilience snapshot \
of a portfolio of defense-sector suppliers.

Write a concise 3-paragraph portfolio brief for a program manager or contracting officer \
who must prioritize oversight attention.

PORTFOLIO SNAPSHOT:
{portfolio_text}

Paragraph 1 — PORTFOLIO HEALTH: Summarize the overall risk distribution. Call out the \
highest-risk suppliers by name and their primary risk drivers.
Paragraph 2 — COMMON VULNERABILITIES: Identify themes shared across suppliers \
(financial pressures, supply chain signals, ownership concerns).
Paragraph 3 — MONITORING PRIORITIES: Recommend which 1-3 suppliers need immediate \
attention and why, in plain language a contracting officer can act on.

Write in clear, direct prose. No bullet points. No headers. Three paragraphs only."""


def _parse_json_from_response(text: str) -> dict | list:
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _client(api_key: Optional[str]) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY)


def extract_financials(
    company_name: str,
    filing_text: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Call Claude to extract structured financial data from 10-K/10-Q text.
    Returns a dict with keys matching the extraction prompt schema.
    Raises AnalystError on Claude failure.
    """
    client = _client(api_key)
    prompt = _EXTRACTION_PROMPT.format(
        company_name=company_name,
        filing_text=filing_text[:8_000],   # truncate to stay within token limits
    )
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        result = _parse_json_from_response(raw)
        if not isinstance(result, dict):
            raise AnalystError("Claude returned non-dict response")
        return result
    except AnalystError:
        raise
    except Exception as exc:
        raise AnalystError(f"Claude API error: {exc}") from exc


def flag_ownership_concerns(
    company_name: str,
    owners: list[dict],
    api_key: Optional[str] = None,
) -> list[dict]:
    """
    Call Claude to flag unusual or foreign-connected ownership.
    Returns a list of flagged owner dicts.
    Raises AnalystError on Claude failure.
    """
    if not owners:
        return []

    client = _client(api_key)
    owners_text = "\n".join(
        f"- {o.get('owner_name', 'Unknown')} ({o.get('pct_owned', 0):.1f}%)"
        + (f", country: {o['country']}" if o.get("country") else "")
        + (f", type: {o['owner_type']}" if o.get("owner_type") else "")
        for o in owners
    )
    prompt = _OWNERSHIP_FLAG_PROMPT.format(
        company_name=company_name,
        owners_list=owners_text,
    )
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        result = _parse_json_from_response(raw)
        if not isinstance(result, list):
            return []
        return result
    except AnalystError:
        raise
    except Exception as exc:
        raise AnalystError(f"Claude API error: {exc}") from exc


def extract_earnings_signals(
    company_name: str,
    transcript_text: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Call Claude to extract qualitative supply chain risk signals from an 8-K Exhibit 99.
    Returns dict with keys: signals, export_control_flag, supplier_diversion_flag,
    key_quote, confidence.
    Raises AnalystError on Claude failure.
    """
    client = _client(api_key)
    prompt = _EARNINGS_SIGNAL_PROMPT.format(
        company_name=company_name,
        transcript_text=transcript_text[:8_000],
    )
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        result = _parse_json_from_response(raw)
        if not isinstance(result, dict):
            raise AnalystError("Claude returned non-dict response for earnings signals")
        return result
    except AnalystError:
        raise
    except Exception as exc:
        raise AnalystError(f"Claude API error: {exc}") from exc


def generate_portfolio_brief(
    portfolio_data: list[dict],
    api_key: Optional[str] = None,
) -> str:
    """
    Call Claude to generate a portfolio-level risk brief across multiple suppliers.

    portfolio_data: list of dicts, each with keys:
        name, dib_category, sector, combined_risk_level, financial_risk_score,
        ownership_risk_score, distress_prob_1yr, distress_prob_3yr,
        cfius_flag_count, earnings_signals (list of signal strings)

    Returns plain text brief (3 paragraphs). Raises AnalystError on failure.
    """
    if not portfolio_data:
        return "No suppliers with completed assessments are currently tracked."

    lines = []
    for s in portfolio_data:
        signals_text = (
            "; ".join(s.get("earnings_signals", [])) if s.get("earnings_signals") else "None recorded"
        )
        lines.append(
            f"{s['name'].upper()} ({s.get('dib_category', 'Unknown')} | {s.get('sector', 'Unknown')})\n"
            f"  Financial Risk: {s.get('financial_risk_score', 'N/A')}/100 | "
            f"Ownership Risk: {s.get('ownership_risk_score', 'N/A')}/100 | "
            f"Combined: {s.get('combined_risk_level', 'N/A')}\n"
            f"  Monte Carlo P(Distress): {int((s.get('distress_prob_1yr') or 0) * 100)}% (1yr), "
            f"{int((s.get('distress_prob_3yr') or 0) * 100)}% (3yr)\n"
            f"  CFIUS flags: {s.get('cfius_flag_count', 0)}\n"
            f"  Earnings signals: {signals_text}"
        )
    portfolio_text = "\n\n".join(lines)

    client = _client(api_key)
    prompt = _PORTFOLIO_BRIEF_PROMPT.format(portfolio_text=portfolio_text)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        raise AnalystError(f"Claude API error: {exc}") from exc
