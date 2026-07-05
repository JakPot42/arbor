"""engines/debt_claude_lender_extractor.py — Claude reads debt-disclosure
filing text and extracts structured lender/counterparty records. Ported
from debt_exposure_monitor/claude_lender_extractor.py.

"Claude extracts, rules decide" -- the doctrine used throughout this
portfolio. Claude never scores risk or decides whether a lender is
concerning; it only pulls names, roles, and instrument types out of
unstructured filing prose. engines/debt_risk_engine.py (deterministic)
and the OFAC/BIS/foreign-state-lender checkers (deterministic fuzzy
matching) make every actual determination.
"""
from __future__ import annotations

import json

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from engines.debt_models import LenderRecord

_SYSTEM_PROMPT = """\
You extract lender and counterparty identities from SEC filing text \
about debt instruments (credit facilities, bond issuances, term loans, \
syndicated loans). For each distinct lender, underwriter, administrative \
agent, or bond trustee named in the text, output one JSON object.

Rules:
1. Only extract entities the text actually names. Do not infer a lender \
that isn't named (e.g. "a syndicate of banks" with no names given yields \
NO record).
2. "evidence_quote" must be a short, real excerpt from the provided text \
that names this entity -- not a paraphrase.
3. "instrument_type" must be one of: credit_facility, bond, term_loan, \
syndicated_loan, other.
4. "role" must be one of: administrative_agent, lender, underwriter, \
trustee, unspecified.
5. Output strict JSON: a list of objects with keys lender_name, \
instrument_type, role, amount_text (the dollar amount/terms mentioned \
near this lender, or "" if none), evidence_quote. No prose outside the \
JSON array.
"""


class ExtractionError(Exception):
    pass


def _claude_extract(filing_text: str, source_label: str) -> list[LenderRecord]:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": filing_text}],
        )
        data = json.loads(msg.content[0].text.strip())
        return [
            LenderRecord(
                lender_name=item.get("lender_name", ""),
                canonical_name=item.get("lender_name", ""),
                instrument_type=item.get("instrument_type", "other"),
                role=item.get("role", "unspecified"),
                amount_text=item.get("amount_text", ""),
                evidence_quote=item.get("evidence_quote", ""),
                source_filing=source_label,
            )
            for item in data
            if item.get("lender_name")
        ]
    except Exception as exc:
        # Same doctrine as every Claude call site in this portfolio: catch
        # Exception (the SDK raises TypeError on a missing key, not
        # anthropic.APIError). Extraction failure returns no records
        # rather than crashing the trace -- an empty result is visibly
        # different from "no lenders disclosed" in the brief's output.
        raise ExtractionError(f"Claude extraction failed for {source_label}: {exc}") from exc


def extract_lenders(filing_text: str, source_label: str) -> list[LenderRecord]:
    return _claude_extract(filing_text, source_label)
