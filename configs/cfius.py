"""configs/cfius.py — CFIUS Screener's own domain constants, values
unchanged from cfius_screener/config.py. DEMO_MODE, ANTHROPIC_API_KEY,
CLAUDE_MODEL, DATABASE_URL, and the OFAC URLs/threshold now live in the
shared root config.py / shared/ofac_checker.py instead of here.

VERIFICATION NOTICE (carried over unchanged): every threshold, list, and
citation below was encoded from the public text of 31 CFR Part 800 as best
understood. None of it has been verified by a CFIUS practitioner or
export-control counsel. This is a portfolio screening aid, not legal
advice.
"""
from __future__ import annotations

APP_TITLE = "CFIUS Screener — Foreign Investment Transaction Screening"
DEMO_BANNER = (
    "DEMO MODE — All transactions, companies, and investors are fictional. "
    "Screening output is a portfolio demonstration, not legal advice."
)

# ---------------------------------------------------------------------------
# Jurisdiction thresholds — 31 CFR Part 800
# ---------------------------------------------------------------------------
CONTROL_MAJORITY_PCT = 50.0
SUBSTANTIAL_INTEREST_GOVT_PCT = 49.0
SUBSTANTIAL_INTEREST_ACQUISITION_PCT = 25.0

EXCEPTED_FOREIGN_STATES = (
    "Australia",
    "Canada",
    "New Zealand",
    "United Kingdom",
)

SENSITIVE_DATA_INDIVIDUALS_THRESHOLD = 1_000_000

SENSITIVE_DATA_CATEGORIES = (
    "Financial distress or hardship data",
    "Consumer report data",
    "Health insurance / long-term care / professional liability application data",
    "Physical, mental, or psychological health condition data",
    "Non-public electronic communications (email, messaging, chat)",
    "Geolocation data",
    "Biometric enrollment data",
    "Government ID or security clearance status data",
    "Security clearance or government employment application data",
    "Genetic test results (qualifies at ANY volume)",
)

CRITICAL_INFRASTRUCTURE_EXAMPLES = (
    "Internet protocol networks / internet exchange points",
    "Telecommunications backbone or submarine cable systems",
    "Industrial control systems for critical manufacturing",
    "Electric power generation, transmission, or distribution serving military installations",
    "Crude oil storage or LNG import/export terminals",
    "Financial market utilities / interbank clearing",
    "Rail lines and airports designated as strategic",
    "Public water systems serving large populations",
    "Manufacturing of items on defense-critical supply lists",
)

DECLARATION_ASSESSMENT_DAYS = 30
NOTICE_REVIEW_DAYS = 45
NOTICE_INVESTIGATION_DAYS = 45

CITATIONS = {
    "foreign_person": "31 CFR § 800.224",
    "us_business": "31 CFR § 800.252",
    "control": "31 CFR § 800.208",
    "covered_control_transaction": "31 CFR § 800.210",
    "covered_investment": "31 CFR § 800.211",
    "tid_us_business": "31 CFR § 800.248",
    "critical_technologies": "31 CFR § 800.215",
    "critical_infrastructure": "Appendix A to 31 CFR Part 800",
    "sensitive_personal_data": "31 CFR § 800.241",
    "substantial_interest": "31 CFR § 800.244",
    "excepted_foreign_state": "31 CFR § 800.218",
    "excepted_investor": "31 CFR § 800.219",
    "mandatory_declaration": "31 CFR § 800.401",
    "declaration_timeline": "31 CFR Part 800, Subpart D",
    "notice_timeline": "31 CFR Part 800, Subpart E",
}

VERIFICATION_DISCLAIMER = (
    "All regulatory parameters and citations encoded from the public text of "
    "31 CFR Part 800 and NOT verified by counsel. Screening aid only — not "
    "legal advice. Real CFIUS determinations require a qualified attorney."
)

# ---------------------------------------------------------------------------
# National security risk scoring (TVC — Threat/Vulnerability/Consequence)
# ---------------------------------------------------------------------------
RISK_HIGH_RISK_COUNTRIES = (
    "China", "Prc",
    "Russia",
    "Iran",
    "North Korea", "Dprk",
    "Belarus",
    "Venezuela",
    "Cuba",
    "Syria",
)

RISK_SOE_THRESHOLD = 49.0

RISK_WEIGHT_HIGH_RISK_COUNTRY = 30
RISK_WEIGHT_SOE_ACQUIRER = 20

RISK_WEIGHT_CRITICAL_TECH = 20
RISK_WEIGHT_EXPORT_AUTH = 15
RISK_WEIGHT_CRITICAL_INFRA = 20
RISK_WEIGHT_SENSITIVE_DATA = 15
RISK_WEIGHT_CONTROL_ACQUIRED = 10
RISK_WEIGHT_BOARD_ACCESS = 8
RISK_WEIGHT_TECH_INFO_ACCESS = 8
RISK_WEIGHT_DECISION_ROLE = 6

RISK_WEIGHT_TID_CLASSIFICATION = 15
RISK_WEIGHT_MANDATORY_FILING = 10
RISK_WEIGHT_TECH_TRANSFER = 15
RISK_WEIGHT_INFRA_DISRUPTION = 15
RISK_WEIGHT_DATA_EXPLOITATION = 10

RISK_TIER_CRITICAL = 75
RISK_TIER_HIGH = 50
RISK_TIER_MEDIUM = 25
