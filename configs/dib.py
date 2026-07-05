"""configs/dib.py — DIB Monitor's own domain constants, values unchanged
from dib_monitor/dib_monitor/config.py. DEMO_MODE, ANTHROPIC_API_KEY,
CLAUDE_MODEL, DATABASE_URL, and EDGAR_USER_AGENT now live in the shared
root config.py instead of here.
"""
from __future__ import annotations

APP_TITLE = "DIB Financial Resilience Monitor"
APP_VERSION = "1.0.0"

CLAUDE_MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Monte Carlo parameters
# ---------------------------------------------------------------------------
MC_N_PATHS = 10_000
MC_SEED = 42

# ---------------------------------------------------------------------------
# Risk score thresholds
# ---------------------------------------------------------------------------
RISK_THRESHOLDS = {
    "CRITICAL": 75,
    "HIGH": 50,
    "MEDIUM": 25,
    "LOW": 0,
}

# Financial score weights (out of 100)
LEVERAGE_WEIGHT = 30
DISTRESS_WEIGHT_1YR = 25
DISTRESS_WEIGHT_3YR = 15
GOING_CONCERN_WEIGHT = 20
MATURITY_WEIGHT = 10

# Ownership score weights (per flagged owner, additive)
CFIUS_OWNER_WEIGHT = 30
FOREIGN_GOV_OWNER_WEIGHT = 25
HIGH_RISK_COUNTRY_WEIGHT = 15
CONCENTRATION_WEIGHT_25PCT = 20
CONCENTRATION_WEIGHT_10PCT = 10
CONCENTRATION_WEIGHT_5PCT = 5

HIGH_RISK_COUNTRIES = {
    "China", "PRC", "Russia", "Iran", "North Korea", "DPRK",
    "Belarus", "Venezuela", "Cuba", "Syria",
}

DIB_CATEGORIES = [
    "Prime Contractor",
    "Tier 1 Subcontractor",
    "Tier 2 Subcontractor",
    "Critical Sole-Source Supplier",
    "Foreign-Owned Supplier",
]
