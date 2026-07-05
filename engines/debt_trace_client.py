"""engines/debt_trace_client.py — FINRA TRACE bond secondary-market data.
Ported from debt_exposure_monitor/trace_client.py.

Researched before building (per the original spec's "where available"
hedge): FINRA does not offer an unauthenticated public API for
issuer-level TRACE transaction history. Detailed corporate-bond TRACE
data requires either FINRA member access or a Historical Data Agreement
(fee-based), per FINRA's own "TRACE Data & Licensing" page. FINRA does
publish aggregate market statistics without authentication, but that's
market-wide, not issuer-specific -- useless for "who is lending to this
one defense supplier."

Rather than silently return an empty list (which would look identical to
"we checked and found nothing") or fabricate data, this module returns an
explicit, labeled "unavailable" result so the brief can say so plainly.
"""
from __future__ import annotations

from dataclasses import dataclass

from configs.debt import TRACE_DATA_AGREEMENT_REQUIRED


@dataclass
class TraceResult:
    available: bool
    reason: str
    bond_records: list[dict]


def fetch_bond_activity(cik: int | None) -> TraceResult:
    if TRACE_DATA_AGREEMENT_REQUIRED:
        return TraceResult(
            available=False,
            reason=(
                "FINRA TRACE issuer-level bond transaction data requires a "
                "Historical Data Agreement with FINRA (fee-based) or FINRA "
                "member access -- there is no unauthenticated public API "
                "for this. This brief's bond-issuance signal comes from SEC "
                "EDGAR 10-K/10-Q footnote disclosures and 8-K Item 1.01/2.03 "
                "filings instead."
            ),
            bond_records=[],
        )
    return TraceResult(available=True, reason="", bond_records=[])
