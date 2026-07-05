"""
engines/dib_seed_data.py — ported from
dib_monitor/dib_monitor/seed_data.py. Two fictional defense suppliers: one
HIGH risk, one LOW risk. All companies, names, and financial figures are
fictional.

**One addition from the original:** each supplier resolves against the
shared Company table via resolve_or_create_company() before being stored.
"""
from __future__ import annotations
import json
from sqlalchemy.orm import Session

from models.dib import EarningsSignal, FinancialAssessment, OwnershipRecord, Supplier
from shared.resolve_company import resolve_or_create_company


def load_seed_data(db: Session) -> None:
    if db.query(Supplier).first():
        return  # idempotent

    # ── Supplier 1: Arrowhead Defense Systems (HIGH financial + ownership risk) ──
    resolution1 = resolve_or_create_company(db, "Arrowhead Defense Systems", ticker="ADS")
    s1 = Supplier(
        company_id=resolution1.company.id,
        name="Arrowhead Defense Systems",
        ticker="ADS",
        cik=None,
        sector="Defense Electronics",
        dib_category="Tier 1 Subcontractor",
        is_demo=True,
    )
    db.add(s1)
    db.flush()

    a1 = FinancialAssessment(
        supplier_id=s1.id,
        filing_type="10-K",
        filing_period="FY2025",
        revenue_mm=847.0,
        total_debt_mm=1200.0,
        cash_mm=89.0,
        ebitda_mm=145.0,
        debt_service_annual_mm=180.0,
        debt_to_ebitda=8.3,
        covenant_summary=(
            "Net leverage ratio must not exceed 9.0x as defined in the 2022 Term Loan "
            "Agreement. Current net leverage of 8.3x provides limited headroom. "
            "Additional covenant: interest coverage ratio must exceed 2.0x (currently 1.8x — "
            "NEAR BREACH). Lender consent required for any dividend payments exceeding $25M."
        ),
        going_concern_flag=False,
        going_concern_quote=None,
        near_term_maturity_mm=400.0,
        near_term_maturity_date="March 2027",
        claude_summary=(
            "Arrowhead carries significant leverage at 8.3x Debt/EBITDA, approaching "
            "covenant limits. The $400M senior note maturity in March 2027 is a near-term "
            "refinancing risk given current credit market conditions. Interest coverage is "
            "at 1.8x against a 2.0x covenant floor. Revenue has declined 6% over two years "
            "driven by program delays in the NEXRAD-II radar modernization contract. "
            "Management guidance acknowledges refinancing risk but does not characterize it "
            "as a going concern. Key program wins needed in H1 2026 to stabilize trajectory."
        ),
        extraction_confidence="demo",
        distress_prob_1yr=0.12,
        distress_prob_2yr=0.28,
        distress_prob_3yr=0.41,
        financial_risk_score=72,
        financial_risk_level="HIGH",
        ownership_risk_score=65,
        ownership_risk_level="HIGH",
        combined_risk_score=69,
        combined_risk_level="HIGH",
    )
    db.add(a1)
    db.flush()

    # Ownership records for Arrowhead
    owners1 = [
        OwnershipRecord(
            supplier_id=s1.id, assessment_id=a1.id, quarter="Q1-2026",
            owner_name="Bering Alpha Fund LP",
            owner_type="Hedge Fund",
            pct_owned=7.2, country="Cayman Islands",
            cfius_flag=True,
            flag_reason=(
                "Fund registered in Cayman Islands with opaque LP structure. "
                "Ultimate beneficial owner not publicly disclosed. "
                "Fund manager has historic ties to entities flagged by OFAC. "
                "CFIUS concern: foreign-connected ownership in defense electronics supplier."
            ),
            risk_level="HIGH",
        ),
        OwnershipRecord(
            supplier_id=s1.id, assessment_id=a1.id, quarter="Q1-2026",
            owner_name="Vanguard Group Inc",
            owner_type="Institution",
            pct_owned=12.8, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
        OwnershipRecord(
            supplier_id=s1.id, assessment_id=a1.id, quarter="Q1-2026",
            owner_name="BlackRock Inc",
            owner_type="Institution",
            pct_owned=9.4, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
        OwnershipRecord(
            supplier_id=s1.id, assessment_id=a1.id, quarter="Q1-2026",
            owner_name="State Street Corp",
            owner_type="Institution",
            pct_owned=4.1, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
    ]
    for o in owners1:
        db.add(o)

    # ── Supplier 2: Meridian Propulsion Corp (LOW financial + ownership risk) ──
    resolution2 = resolve_or_create_company(db, "Meridian Propulsion Corp", ticker="MRPC")
    s2 = Supplier(
        company_id=resolution2.company.id,
        name="Meridian Propulsion Corp",
        ticker="MRPC",
        cik=None,
        sector="Aerospace Propulsion",
        dib_category="Critical Sole-Source Supplier",
        is_demo=True,
    )
    db.add(s2)
    db.flush()

    a2 = FinancialAssessment(
        supplier_id=s2.id,
        filing_type="10-K",
        filing_period="FY2025",
        revenue_mm=312.0,
        total_debt_mm=245.0,
        cash_mm=67.0,
        ebitda_mm=71.0,
        debt_service_annual_mm=28.0,
        debt_to_ebitda=3.4,
        covenant_summary=(
            "Revolving credit facility requires total net leverage below 4.5x "
            "(currently 3.4x — comfortable headroom). No maintenance financial covenants "
            "on the senior notes. No dividend restrictions triggered."
        ),
        going_concern_flag=False,
        going_concern_quote=None,
        near_term_maturity_mm=None,
        near_term_maturity_date=None,
        claude_summary=(
            "Meridian demonstrates solid financial health with 3.4x leverage, strong "
            "interest coverage of 9.1x, and $67M cash providing meaningful liquidity. "
            "As the sole-source supplier for Stage-2 propulsion assemblies on the "
            "Precision Strike Missile (PrSM) program, revenue is largely contracted "
            "through FY2028. No near-term debt maturities; the revolving facility "
            "matures in 2029. Management has guided 6–8% EBITDA growth for FY2026 "
            "supported by production ramp on PrSM Block II. Financial risk is LOW."
        ),
        extraction_confidence="demo",
        distress_prob_1yr=0.02,
        distress_prob_2yr=0.05,
        distress_prob_3yr=0.09,
        financial_risk_score=14,
        financial_risk_level="LOW",
        ownership_risk_score=0,
        ownership_risk_level="LOW",
        combined_risk_score=8,
        combined_risk_level="LOW",
    )
    db.add(a2)
    db.flush()

    owners2 = [
        OwnershipRecord(
            supplier_id=s2.id, assessment_id=a2.id, quarter="Q1-2026",
            owner_name="Vanguard Group Inc",
            owner_type="Institution",
            pct_owned=14.2, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
        OwnershipRecord(
            supplier_id=s2.id, assessment_id=a2.id, quarter="Q1-2026",
            owner_name="BlackRock Inc",
            owner_type="Institution",
            pct_owned=11.8, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
        OwnershipRecord(
            supplier_id=s2.id, assessment_id=a2.id, quarter="Q1-2026",
            owner_name="T. Rowe Price Group",
            owner_type="Institution",
            pct_owned=7.4, country="United States",
            cfius_flag=False, flag_reason=None, risk_level="LOW",
        ),
    ]
    for o in owners2:
        db.add(o)

    # ── Earnings signal for Arrowhead (Q4 2025 earnings call, 8-K Exhibit 99.1) ──
    arrowhead_signals = [
        "Actively diversifying semiconductor sourcing away from PRC-based Tier-1 suppliers "
        "following October 2025 BIS export control expansion on advanced logic chips",
        "Expects $18–22M incremental sourcing cost in FY2026 from qualified domestic and "
        "allied-nation alternate suppliers (Japan, South Korea)",
        "NEXRAD-II radar program delay attributed in part to restricted component availability "
        "— management expects resolution by Q3 2026 after domestic qualification completes",
        "CEO: 'We are no longer comfortable with a single-country concentration for advanced "
        "processing components on any defense-critical program'",
    ]
    es1 = EarningsSignal(
        supplier_id=s1.id,
        filing_date="2026-01-28",
        accession_number="0001234567-26-000128",
        signals_json=json.dumps(arrowhead_signals),
        export_control_flag=True,
        supplier_diversion_flag=True,
        key_quote=(
            "We are no longer comfortable with a single-country concentration for advanced "
            "processing components on any defense-critical program. The BIS October rule "
            "was the forcing function we needed to accelerate our domestic qualification roadmap."
        ),
        claude_brief=(
            "Arrowhead's Q4 2025 earnings call disclosed material supply chain restructuring "
            "driven by BIS export control expansion. Management confirmed active diversion away "
            "from PRC-based semiconductor suppliers, projecting $18–22M in incremental FY2026 "
            "sourcing costs while domestic and allied-nation alternates complete qualification. "
            "The NEXRAD-II program delay — already a financial risk factor — is now confirmed as "
            "partly supply-chain-driven, a forward-looking signal absent from the FY2025 10-K "
            "which cites only 'program schedule risk.' This language represents a meaningful "
            "escalation in disclosed exposure and warrants close monitoring through Q3 2026."
        ),
        extraction_confidence="demo",
    )
    db.add(es1)

    db.commit()
