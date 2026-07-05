"""config.py — constants shared across every tool. No logic.

Arbor merges GhostTrace, CFIUS Screener, DIB Monitor, Pre-Acquisition Brief
Generator, and Debt Exposure Monitor. Per-tool thresholds/weights that
belong to a single tool's own engine (CFIUS's regulatory citations, DIB
Monitor's Monte Carlo params, GhostTrace's own risk-scoring weights, etc.)
live in `configs/<tool>.py` instead of here — found during porting that
flattening everything into one file would silently collide (GhostTrace's
and CFIUS's own configs both define `APP_TITLE` and `DEMO_BANNER` with
different values; a single shared name would let one tool's title clobber
another's at import time depending on order). This file holds only what
is genuinely used by more than one tool.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Database — one shared engine/Base for every tool's tables.
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./arbor.db")

# ---------------------------------------------------------------------------
# DEMO_MODE — reconciled to ONE implementation. GhostTrace's
# `.lower() in (...)` form is the one kept: Debt Exposure Monitor's exact
# `== "True"` string check silently evaluates DEMO_MODE=true/TRUE as False,
# and Pre-Acquisition Brief's config.DEMO_MODE was dead code entirely
# (superseded by its own CLI flag, never read). This is the single real
# implementation all five ported engines read from now.
# ---------------------------------------------------------------------------
DEMO_MODE = os.getenv("DEMO_MODE", "True").lower() in ("1", "true", "yes")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# SEC EDGAR — canonical client config (ghosttrace/edgar_client.py's values;
# debt_exposure_monitor's were already identical except EDGAR_USER_AGENT,
# which is updated here to name the merged tool).
# ---------------------------------------------------------------------------
EDGAR_USER_AGENT = "Arbor portfolio research tool (jak.potvin@gmail.com)"
EDGAR_RATE_LIMIT_PER_SEC = 8
EDGAR_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
MAX_DOC_CHARS = 30_000

# Two filing-selection strategies, one shared client (see shared/edgar_client.py):
# GhostTrace's ownership-filing strategy (13D/13G unlimited, latest-only 10-K/DEF 14A)...
OWNERSHIP_FORM_TYPES = ["SC 13D", "SC 13G", "10-K", "DEF 14A"]
OWNERSHIP_SINGLE_PER_FORM = {"10-K", "DEF 14A"}
MAX_FILINGS_PER_TRACE = 10

# ...and Debt Exposure Monitor's debt-filing strategy (capped-N per form type).
DEBT_RELEVANT_FORM_TYPES = ["10-K", "10-Q", "8-K"]
MAX_10K_10Q_PER_TRACE = 2
MAX_8K_PER_TRACE = 6

# ---------------------------------------------------------------------------
# Cross-tool entity resolution — reconciled from three drifted copies
# (ghosttrace, entity_graph/P71, debt_exposure_monitor). See
# shared/entity_resolver.py's module docstring for exactly what drifted and
# which fix was kept.
# ---------------------------------------------------------------------------
FUZZY_AUTO_MERGE_THRESHOLD = 90.0
FUZZY_ADJUDICATE_THRESHOLD = 75.0

# Read-only company search only (routers/company.py) -- below this, a
# "best match" is noise, not a real hit (SequenceMatcher finds some
# overlapping characters even between unrelated strings). Same role and
# same value as entity_graph's (P71) own MIN_QUERY_SCORE, carried over
# for the same reason: find_entity()-style search needs its own floor,
# separate from the merge/adjudicate bands used when a tool is actually
# writing data.
MIN_QUERY_SCORE = 40.0

NORMALIZE_SUFFIXES = [
    "inc", "inc.", "incorporated",
    "llc", "l.l.c.",
    "lp", "l.p.", "llp", "l.l.p.",
    "ltd", "ltd.", "limited",
    "corp", "corp.", "corporation",
    "co", "co.", "company",
    "plc", "sa", "s.a.", "ag", "gmbh", "nv", "n.v.", "bv", "b.v.",
    "holdings", "holding", "group",
    "na", "n.a.", "bank",
    # A FOURTH drifted copy, found while porting ofac_checker.py:
    # cfius_screener's own OFAC checker inlined a separate _normalize()
    # (deliberately, to avoid an entity_resolver dependency — its own
    # docstring says so) that additionally strips international corporate
    # forms neither ghosttrace's nor entity_graph's suffix list had. OFAC's
    # SDN list is full of non-US entities, so this coverage is real, not
    # decorative — folded in here rather than left behind as a fifth
    # almost-shared list.
    "pte", "pty", "jsc", "ooo", "pjsc", "sas", "spa",
]

# Curated subsidiary/DBA aliases carried over from entity_graph (P71) — a
# small, disclosed fix for cases fuzzy matching alone can't bridge (a
# subsidiary name sharing no normalized tokens with its parent's name).
# Extend this table as Arbor's own demo data surfaces new cases, same
# discipline as P71's own KNOWN_ALIASES comment.
KNOWN_ALIASES: dict[str, str] = {
    "ge power": "General Electric Company",
    "ge aviation": "General Electric Company",
    "ge capital": "General Electric Company",
}

# ---------------------------------------------------------------------------
# OFAC SDN screening — shared/ofac_checker.py, one copy used by both
# GhostTrace's and CFIUS Screener's routers. Both projects' own configs
# already used the identical URLs and threshold (90) independently, so this
# is consolidation, not a values change.
# ---------------------------------------------------------------------------
OFAC_SDN_CSV_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
OFAC_SDN_ALT_URL = "https://www.treasury.gov/ofac/downloads/alt.csv"
OFAC_MATCH_THRESHOLD = 90  # rapidfuzz token_sort_ratio
