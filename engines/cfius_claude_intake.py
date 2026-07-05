"""engines/cfius_claude_intake.py — ported from cfius_screener/claude_intake.py.

Claude Haiku parses plain-English deal descriptions. The caller (routers/
cfius.py) shows Claude's output on a confirmation screen before the engine
runs — Claude proposes, the human confirms. The engine never knows
whether facts arrived from this path or from the structured form.
"""
from __future__ import annotations

import json
import re
import textwrap

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_SYSTEM = textwrap.dedent("""\
    You are a CFIUS intake assistant. The user will paste a plain-English
    description of a proposed transaction. Extract the structured facts needed
    for a CFIUS Part 800 jurisdictional analysis.

    Return ONLY a JSON object with exactly these keys (no other text):

    {
      "us_business_name": "<name of the US target company>",
      "us_business_description": "<what the US business does, 1-2 sentences>",
      "acquirer_name": "<name of the foreign acquirer>",
      "acquirer_country": "<home country — ultimate ownership, not letterbox jurisdiction>",
      "foreign_govt_ownership_pct": <float 0-100, highest % any single foreign government owns of the acquirer>,
      "voting_interest_pct": <float 0-100, voting interest the acquirer will hold in the US business after closing>,
      "contractual_control_rights": <true/false, acquirer gets veto rights or board-majority appointment power>,
      "board_seat": <true/false, acquirer gets a board seat>,
      "board_observer": <true/false, acquirer gets a board observer seat>,
      "access_nonpublic_tech_info": <true/false, acquirer gets access to material non-public technical information>,
      "substantive_decision_role": <true/false, acquirer gets a role in substantive business decisions>,
      "produces_critical_tech": <true/false, US business produces export-controlled technologies (ITAR, EAR)>,
      "export_authorization_required": <true/false, exporting those technologies to the acquirer home country requires a US export authorization>,
      "critical_infrastructure": <true/false, US business owns or operates critical infrastructure>,
      "sensitive_personal_data": <true/false, US business collects sensitive personal data on >1 million people or any genetic data>,
      "confidence_notes": "<1-3 sentences on what you are confident about and where the description is ambiguous>"
    }

    Rules:
    - If a fact is not stated, default: numeric fields to 0.0, booleans to false.
    - Never invent facts. Uncertain? Use the default and note it in confidence_notes.
    - acquirer_country: full country name (e.g. "China", "Germany", "United Arab Emirates").
    - Sovereign wealth funds and state-owned enterprises: set foreign_govt_ownership_pct to 100.
    - Return JSON only. No markdown, no explanation outside the object.
""")

_REQUIRED_KEYS = [
    "us_business_name", "us_business_description",
    "acquirer_name", "acquirer_country",
    "foreign_govt_ownership_pct", "voting_interest_pct",
    "contractual_control_rights", "board_seat", "board_observer",
    "access_nonpublic_tech_info", "substantive_decision_role",
    "produces_critical_tech", "export_authorization_required",
    "critical_infrastructure", "sensitive_personal_data",
    "confidence_notes",
]


class IntakeError(Exception):
    pass


def parse_deal_description(description: str) -> dict:
    """Call Claude Haiku to extract TransactionFacts from plain English.

    Returns a dict whose keys match TransactionFacts fields plus
    'confidence_notes'. Raises IntakeError on API failure or bad output.
    """
    if not ANTHROPIC_API_KEY:
        raise IntakeError(
            "ANTHROPIC_API_KEY is not configured — cannot call Claude."
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": description}],
        )
    except IntakeError:
        raise
    except Exception as exc:
        raise IntakeError(f"Claude API error: {exc}") from exc

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntakeError(
            f"Claude returned non-JSON output: {raw[:200]}"
        ) from exc

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise IntakeError(f"Claude response missing fields: {missing}")

    return data
