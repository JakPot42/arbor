"""engines/cfius_seed_data.py — ported from cfius_screener/seed_data.py.

Fictional demo transactions, loaded on every startup. Every name is
obviously fictional. The three scenarios exercise the three main branches
of the decision tree — including one where the answer is "no filing
required," because a screener that only ever says YES is not credible:

1. MANDATORY (both prongs)  — Chinese-state-backed fund takes 30% + board
   seat in an export-controlled photonics maker.
2. COVERED BUT VOLUNTARY    — Canadian pension fund buys 100% of a non-TID
   logistics-software company (excepted investor).
3. MANDATORY (substantial-interest prong only) — UAE sovereign wealth fund
   takes 28% non-controlling + board observer in a genetic-testing company.

**One addition from the original:** each scenario now also resolves its
`us_business_name` against the shared Company table via
`resolve_or_create_company()` before storing the Screening — the seed data
is Arbor's first real exercise of the cross-tool entity link, not just
GhostTrace/CFIUS running side by side with no shared identity.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from engines.cfius_screening_service import run_and_store
from engines.jurisdiction_engine import TransactionFacts
from models.cfius import Screening
from shared.resolve_company import resolve_or_create_company

_SEED_SCENARIOS = [
    TransactionFacts(
        us_business_name="Meridian Photonics Corporation",
        us_business_description=(
            "Tempe, Arizona manufacturer of semiconductor inspection optics "
            "and EUV metrology components. Several product lines are "
            "controlled under the EAR (Commerce Control List Category 3) and "
            "require a license for export to China."
        ),
        acquirer_name="Golden Harbor Capital Pte. Ltd.",
        acquirer_country="China",
        foreign_govt_ownership_pct=51.0,
        voting_interest_pct=30.0,
        contractual_control_rights=False,
        board_seat=True,
        access_nonpublic_tech_info=True,
        produces_critical_tech=True,
        export_authorization_required=True,
    ),
    TransactionFacts(
        us_business_name="TrueNorth Logistics Software LLC",
        us_business_description=(
            "Columbus, Ohio SaaS provider of commercial freight scheduling "
            "and warehouse management software. No government customers, no "
            "export-controlled technology, no sensitive personal data."
        ),
        acquirer_name="Laurentide Pension Investment Board",
        acquirer_country="Canada",
        foreign_govt_ownership_pct=0.0,
        voting_interest_pct=100.0,
    ),
    TransactionFacts(
        us_business_name="HelixPrint Genomics Inc.",
        us_business_description=(
            "San Diego direct-to-consumer genetic testing company holding "
            "genetic test results and identifiable health data on roughly "
            "2.1 million US customers."
        ),
        acquirer_name="Al Dhafra Strategic Investments PJSC",
        acquirer_country="United Arab Emirates",
        foreign_govt_ownership_pct=100.0,
        voting_interest_pct=28.0,
        board_observer=True,
        sensitive_personal_data=True,
    ),
]


def load_seed_data(db: Session) -> None:
    """Idempotent: seeds only when no demo screenings exist."""
    if db.query(Screening).filter(Screening.is_demo.is_(True)).count() > 0:
        return
    for facts in _SEED_SCENARIOS:
        resolution = resolve_or_create_company(db, facts.us_business_name)
        run_and_store(db, facts, is_demo=True, company_id=resolution.company.id)
