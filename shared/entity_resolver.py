"""shared/entity_resolver.py — cross-tool fuzzy name matching.

Fifth deployment of the same fuzzy-match engine (GhostTrace -> tech-scanner
-> PatientFusion -> entity_graph/P71 -> here) — and the point where three
drifted copies get reconciled into one, instead of adding a sixth.

**What had actually drifted, found during the Arbor architecture review,
not assumed:**

- `ghosttrace/entity_resolver.py` and `entity_graph/entity_resolver.py`
  (P71 inherited it from GhostTrace) both strip corporate suffixes with a
  SINGLE pass: one `while` loop off the end, then one `for n in (3, 2)`
  check for multi-token suffixes, then stop. This works for
  "Harborview Capital Partners LP" but not for stacked suffixes.
- `debt_exposure_monitor/entity_resolver.py` fixed exactly that gap for its
  own lender-name use case (`normalize_name`'s docstring there: "JPMorgan
  Chase Bank, N.A." must lose BOTH "bank" and "n.a.", not just whichever
  the single pass hits first") by looping to a fixed point, and added
  "na"/"n.a."/"bank" to its own copy of `NORMALIZE_SUFFIXES` — but this fix
  was never backported to GhostTrace's or entity_graph's copies. Three
  projects, three different answers to "what does this function return
  today," despite two of them believing they were running "the same"
  logic.
- Separately, `debt_exposure_monitor/entity_resolver.py`'s `similarity()`
  only takes the max of two measures (direct ratio, token-sort ratio) —
  missing the token-set Jaccard measure `ghosttrace`/`entity_graph`'s
  version has, which is what catches partial-overlap matches word order
  alone doesn't fix.

**The reconciliation kept the better half of each:** the fixed-point
suffix-stripping loop (from debt_exposure_monitor, generalized — every
project's names get it now, not just lender names), the three-measure
similarity function (from ghosttrace/entity_graph), and `KNOWN_ALIASES` +
`resolve_known_alias()` (from entity_graph, the only one of the three that
had it — needed because fuzzy matching alone cannot bridge a subsidiary
name to its parent when the two share no normalized tokens at all, e.g.
"GE Power" vs "General Electric Company").

Three bands, unchanged from every prior deployment:
  similarity >= FUZZY_AUTO_MERGE_THRESHOLD  -> same entity
  similarity >= FUZZY_ADJUDICATE_THRESHOLD  -> ambiguous, ask before merging
  below                                     -> distinct entities
"""
from __future__ import annotations

from difflib import SequenceMatcher

from config import (
    FUZZY_ADJUDICATE_THRESHOLD,
    FUZZY_AUTO_MERGE_THRESHOLD,
    KNOWN_ALIASES,
    NORMALIZE_SUFFIXES,
)

_SUFFIX_SET = {s.replace(".", "") for s in NORMALIZE_SUFFIXES}
_KNOWN_ALIASES = {k.lower().strip(): v for k, v in KNOWN_ALIASES.items()}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, drop a leading 'the' and corporate
    suffixes -- to a FIXED POINT, so stacked suffixes ("Bank, N.A.") lose
    all of them, not just whichever a single pass happens to hit first."""
    cleaned = "".join(ch if ch.isalnum() or ch == " " else " " for ch in name.lower())
    tokens = cleaned.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]

    changed = True
    while changed and tokens:
        changed = False
        if tokens[-1] in _SUFFIX_SET:
            tokens = tokens[:-1]
            changed = True
            continue
        for n in (3, 2):
            if len(tokens) >= n and "".join(tokens[-n:]) in _SUFFIX_SET:
                tokens = tokens[:-n]
                changed = True
                break

    return " ".join(tokens)


def resolve_known_alias(name: str) -> str | None:
    """Look up a curated subsidiary/DBA alias (config.KNOWN_ALIASES).

    Returns the parent entity's canonical display name if `name`
    (normalized) is a known alias, else None. Callers should check this
    BEFORE fuzzy scoring -- see module docstring for why fuzzy matching
    alone isn't enough for these cases.
    """
    return _KNOWN_ALIASES.get(normalize_name(name))


def similarity(a: str, b: str) -> float:
    """0-100 similarity between two names.

    Max of three measures so word order and partial overlap don't defeat
    the match: direct ratio, token-sort ratio, and token-set Jaccard
    overlap.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    direct = SequenceMatcher(None, na, nb).ratio()
    ta, tb = na.split(), nb.split()
    token_sort = SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    sa, sb = set(ta), set(tb)
    token_set = len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0
    return max(direct, token_sort, token_set) * 100


class MatchBand:
    """Named result of comparing a name against a candidate -- avoids
    every caller re-deriving band membership from raw threshold
    comparisons."""

    AUTO_MERGE = "auto_merge"
    ADJUDICATE = "adjudicate"
    DISTINCT = "distinct"


def match_band(score: float) -> str:
    if score >= FUZZY_AUTO_MERGE_THRESHOLD:
        return MatchBand.AUTO_MERGE
    if score >= FUZZY_ADJUDICATE_THRESHOLD:
        return MatchBand.ADJUDICATE
    return MatchBand.DISTINCT
