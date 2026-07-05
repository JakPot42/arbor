"""configs/ghosttrace.py — GhostTrace's own domain constants, values
unchanged from ghosttrace/config.py. DEMO_MODE, ANTHROPIC_API_KEY,
CLAUDE_MODEL, DATABASE_URL, EDGAR_*, and the OFAC URLs/threshold now live
in the shared root config.py / shared/ofac_checker.py instead of here —
see that file's docstring for why.
"""
from __future__ import annotations

APP_TITLE = "GhostTrace — Hidden Ownership & Shell Company Tracer"
DEMO_BANNER = (
    "DEMO MODE — Harborview Capital Partners synthetic ownership network loaded. "
    "All entities fictional. No real intelligence."
)

# ---------------------------------------------------------------------------
# Claude call budgets
# ---------------------------------------------------------------------------
EXTRACTION_MAX_TOKENS = 1500
ADJUDICATION_MAX_TOKENS = 300
REPORT_MAX_TOKENS = 2000

# ---------------------------------------------------------------------------
# WITHIN-TRACE entity resolution thresholds — deliberately NOT the same as
# the shared cross-tool Company-resolution thresholds in root config.py
# (90/75). This is a genuinely different use case: consolidating multiple
# mentions of the same owner across filings WITHIN one ownership trace,
# tuned independently at 92/75 by the original GhostTrace build. Using
# shared/entity_resolver.py's normalize_name()/similarity() functions
# directly with these thresholds, not the shared match_band() (which reads
# the cross-tool 90/75 from root config.py).
# ---------------------------------------------------------------------------
FUZZY_AUTO_MERGE_THRESHOLD = 92
FUZZY_ADJUDICATE_THRESHOLD = 75

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------
SECRECY_JURISDICTIONS = [
    "Cayman Islands", "British Virgin Islands", "Bermuda", "Panama",
    "Cyprus", "Luxembourg", "Seychelles", "Marshall Islands",
    "Liechtenstein", "Isle of Man", "Jersey", "Guernsey",
    "Malta", "Belize", "Bahamas",
]

ADVERSARY_JURISDICTIONS = [
    "China", "PRC", "Russia", "Iran", "North Korea", "DPRK",
    "Belarus", "Venezuela",
]

RISK_WEIGHT_SECRECY_JURISDICTION = 30
RISK_WEIGHT_ADVERSARY_JURISDICTION = 40
RISK_WEIGHT_CIRCULAR_OWNERSHIP = 25
RISK_WEIGHT_CHAIN_DEPTH = 20
CHAIN_DEPTH_THRESHOLD = 3
RISK_WEIGHT_SHARED_AGENT = 15
RISK_WEIGHT_UNDISCLOSED_OWNER = 10
RISK_WEIGHT_OFAC_CANDIDATE = 35

RISK_LEVEL_HIGH = 60
RISK_LEVEL_MEDIUM = 30

# ---------------------------------------------------------------------------
# Deep Trace agentic loop
# ---------------------------------------------------------------------------
DEEP_TRACE_MAX_TOOL_CALLS = 5
DEEP_TRACE_MAX_TOKENS = 2000

# ---------------------------------------------------------------------------
# Semantic search (ChromaDB, hashed bag-of-words embedder)
# ---------------------------------------------------------------------------
EMBED_DIM = 512
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200
SEARCH_RESULTS_K = 8

GRAPH_OUTPUT_DIR = "static/ghosttrace/graphs"
