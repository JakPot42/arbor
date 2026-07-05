"""configs/debt.py — Debt Exposure Monitor's own domain constants,
unchanged values from debt_exposure_monitor/config.py. EDGAR/OFAC/
NORMALIZE_SUFFIXES/CLAUDE_MODEL/ANTHROPIC_API_KEY are cross-tool and stay
in root config.py; everything here is debt-specific.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# FINRA TRACE — no unauthenticated public API for issuer-level bond
# transaction history exists (Historical Data Agreement or member access
# required). See engines/debt_trace_client.py for the honest-unavailable
# result this produces instead of fabricating data.
# ---------------------------------------------------------------------------
TRACE_DATA_AGREEMENT_REQUIRED = True

# Lender-name fuzzy dedupe (separate from the cross-tool Company-resolution
# thresholds in root config.py -- this collapses name variants WITHIN one
# profile's disclosed lender list, not across companies).
LENDER_DEDUPE_THRESHOLD = 88

# ---------------------------------------------------------------------------
# BIS screening — the Commerce Department's Bureau of Industry and Security
# lists (Entity List, Denied Persons List, Unverified List, Military End
# User List), filtered from the International Trade Administration's
# Consolidated Screening List (a single public CSV covering eleven
# Commerce/State/Treasury export-control and sanctions lists).
# ---------------------------------------------------------------------------
CSL_CSV_URL = "https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv"
BIS_SOURCE_MARKERS = [
    "Bureau of Industry and Security",
]
BIS_MATCH_THRESHOLD = 90

# ---------------------------------------------------------------------------
# Foreign state-connected lenders — a curated, cited list of financial
# institutions majority state-owned/controlled by a nation on
# HIGH_RISK_COUNTRIES. A DIFFERENT signal than OFAC/BIS: most of these are
# NOT sanctioned (China is not comprehensively sanctioned the way
# Russia/Iran/North Korea are), so a Chinese state policy bank becoming a
# defense supplier's lender produces zero OFAC/BIS hits but is still a
# real financial-exposure fact.
# ---------------------------------------------------------------------------
HIGH_RISK_COUNTRIES = {
    "China", "PRC", "People's Republic of China", "Russia", "Iran",
    "North Korea", "DPRK", "Belarus", "Venezuela",
}

FOREIGN_STATE_LENDERS: list[dict] = [
    {
        "name": "China Development Bank",
        "country": "China",
        "basis": "Policy bank wholly owned by the State Council of the PRC.",
        "citation": "China Development Bank Corporation 2023 Annual Report, "
                     "\"Shareholder Structure\" (Ministry of Finance + Central "
                     "Huijin Investment + National Council for Social "
                     "Security Fund -- 100% state ownership).",
    },
    {
        "name": "Export-Import Bank of China",
        "country": "China",
        "basis": "Policy bank wholly owned by the State Council of the PRC.",
        "citation": "Export-Import Bank of China, \"About Us -- Corporate "
                     "Governance\" (state-funded policy financial institution "
                     "directly under the State Council).",
    },
    {
        "name": "Bank of China",
        "country": "China",
        "basis": "Majority state-owned; one of China's \"Big Four\" state "
                  "commercial banks, controlled via Central Huijin Investment.",
        "citation": "Bank of China Limited 2023 Annual Report, \"Substantial "
                     "Shareholders\" (Central Huijin Investment Ltd., a PRC "
                     "sovereign entity, majority shareholder).",
    },
    {
        "name": "Industrial and Commercial Bank of China",
        "country": "China",
        "basis": "Majority state-owned; one of China's \"Big Four\" state "
                  "commercial banks, controlled via Central Huijin Investment.",
        "citation": "ICBC 2023 Annual Report, \"Shareholder Structure\" "
                     "(Central Huijin Investment Ltd. majority shareholder).",
    },
    {
        "name": "China Construction Bank",
        "country": "China",
        "basis": "Majority state-owned; one of China's \"Big Four\" state "
                  "commercial banks, controlled via Central Huijin Investment.",
        "citation": "China Construction Bank 2023 Annual Report, \"Substantial "
                     "Shareholders\" (Central Huijin Investment Ltd. majority "
                     "shareholder).",
    },
    {
        "name": "Agricultural Bank of China",
        "country": "China",
        "basis": "Majority state-owned; one of China's \"Big Four\" state "
                  "commercial banks, controlled via Central Huijin Investment.",
        "citation": "Agricultural Bank of China 2023 Annual Report, "
                     "\"Substantial Shareholders\" (Central Huijin Investment "
                     "Ltd. majority shareholder).",
    },
    {
        "name": "VTB Bank",
        "country": "Russia",
        "basis": "Majority owned by the Russian Federation (Federal Agency "
                  "for State Property Management).",
        "citation": "VTB Bank PJSC ownership disclosure, Russian Federation "
                     "as controlling shareholder (also OFAC SDN-designated "
                     "since Feb 2022 -- see OFAC screening).",
    },
    {
        "name": "Sberbank",
        "country": "Russia",
        "basis": "Majority owned by Russia's National Wealth Fund.",
        "citation": "Sberbank of Russia PJSC ownership disclosure, National "
                     "Wealth Fund of the Russian Federation as controlling "
                     "shareholder (also OFAC SDN-designated since Feb 2022 "
                     "-- see OFAC screening).",
    },
    {
        "name": "Bank Melli Iran",
        "country": "Iran",
        "basis": "Wholly state-owned, Iran's largest commercial bank.",
        "citation": "U.S. Treasury OFAC designation history (also OFAC "
                     "SDN-designated -- see OFAC screening).",
    },
    {
        "name": "Foreign Trade Bank",
        "country": "North Korea",
        "basis": "State bank of the DPRK, primary foreign-exchange bank.",
        "citation": "U.S. Treasury OFAC designation history (also OFAC "
                     "SDN-designated -- see OFAC screening).",
    },
]
FOREIGN_STATE_LENDER_MATCH_THRESHOLD = 88

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------
RISK_WEIGHT_OFAC_HIT = 35
RISK_WEIGHT_BIS_HIT = 35
RISK_WEIGHT_FOREIGN_STATE_LENDER = 20
RISK_WEIGHT_HIGH_CONCENTRATION = 15

CONCENTRATION_HHI_HIGH = 5000
CONCENTRATION_HHI_MODERATE = 2500

RISK_TIERS = [
    (25, "LOW"),
    (50, "MEDIUM"),
    (75, "HIGH"),
]
RISK_TIER_DEFAULT = "CRITICAL"
