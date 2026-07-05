"""engines/cfius_claude_memo.py — ported from cfius_screener/claude_memo.py.

Claude Haiku drafts the screening memorandum narrative. Claude writes
ABOUT the engine's conclusions — it never makes its own legal
determinations. The deterministic findings trail drives the memo; Claude
translates it into plain English for a business audience.
"""
from __future__ import annotations

import json
import textwrap

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from engines.cfius_screening_service import findings_of, mandatory_reasons_of, tid_categories_of
from models.cfius import Screening

_SYSTEM = textwrap.dedent("""\
    You are a CFIUS compliance analyst drafting the narrative section of a
    transaction screening memorandum. You will receive the structured output of
    a deterministic Part 800 jurisdictional analysis as JSON — the outcome,
    TID categories, mandatory-declaration reasons, excepted-investor status,
    and the full step-by-step findings trail.

    Write a professional, plain-English memorandum narrative (4-6 paragraphs):

    1. Opening: state the deal parties, what is being acquired, and the
       jurisdictional outcome in one clear sentence.
    2. Explain which tests led to that outcome — cite the specific regulations
       from the findings trail. Be precise about what triggered (or didn't).
    3. If a mandatory declaration was triggered: name the prong(s) and explain
       the filing timeline (declaration assessment period).
    4. If excepted-investor status was found: explain what that means and,
       critically, its limit — it does NOT remove jurisdiction over covered
       control transactions.
    5. Recommend concrete next steps (engage CFIUS counsel, prepare filing,
       conduct voluntary filing risk analysis, etc.).

    RULES:
    - You write ABOUT the engine's conclusions. Do not make your own legal
      determinations or add analysis beyond what the findings support.
    - Cite regulations exactly as they appear in the findings (e.g.
      "31 CFR § 800.401").
    - Plain English throughout — a business executive, not a lawyer, is the
      primary reader.
    - Flowing paragraphs only — no headers, no bullet points.
    - End with this exact disclaimer paragraph:
      "This memorandum is a draft narrative prepared by an AI assistant for
      informational purposes only. It does not constitute legal advice. All
      CFIUS determinations require review by qualified counsel."
""")


class MemoError(Exception):
    pass


def draft_memo(row: Screening) -> str:
    """Draft a screening memorandum narrative for the given Screening row.

    Raises MemoError on API failure.
    """
    if not ANTHROPIC_API_KEY:
        raise MemoError(
            "ANTHROPIC_API_KEY is not configured — cannot call Claude."
        )

    context = json.dumps({
        "us_business_name": row.us_business_name,
        "us_business_description": row.us_business_description,
        "acquirer_name": row.acquirer_name,
        "acquirer_country": row.acquirer_country,
        "voting_interest_pct": row.voting_interest_pct,
        "foreign_govt_ownership_pct": row.foreign_govt_ownership_pct,
        "outcome": row.outcome,
        "covered_basis": row.covered_basis,
        "is_tid": row.is_tid,
        "tid_categories": tid_categories_of(row),
        "excepted_investor": row.excepted_investor,
        "mandatory_reasons": mandatory_reasons_of(row),
        "findings": findings_of(row),
    }, indent=2)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": context}],
        )
    except MemoError:
        raise
    except Exception as exc:
        raise MemoError(f"Claude API error: {exc}") from exc

    return msg.content[0].text.strip()
