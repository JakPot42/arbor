"""engines/debt_entity_resolver.py — lender-name fuzzy deduplication.

debt_exposure_monitor/entity_resolver.py's own `normalize_name()`/
`similarity()` were the ORIGINAL source of the fixed-point suffix-
stripping fix now reconciled into shared/entity_resolver.py (see that
module's docstring) -- so unlike ghosttrace_entity_resolver.py (which had
genuinely distinct jurisdiction-conflict logic worth keeping alongside a
delegation to the shared fix), there is nothing left here that isn't
already in shared/entity_resolver.py. Only `dedupe_lenders()` survives as
its own function: collapsing name variants WITHIN one profile's disclosed
lender list is a different operation than resolving a name against the
cross-tool Company table, and deserves its own threshold
(configs.debt.LENDER_DEDUPE_THRESHOLD) tuned for that use case.
"""
from __future__ import annotations

from configs.debt import LENDER_DEDUPE_THRESHOLD
from shared.entity_resolver import similarity


def dedupe_lenders(names: list[str]) -> dict[str, str]:
    """Collapses name variants into a canonical form (the first-seen
    spelling). Returns a map of every input name to its canonical form.

    Unlike resolve_or_create_company() (which needs an adjudicator for the
    ambiguous band because a wrong merge blends two real companies'
    identities), lender-name variants in a single filing set are almost
    always the same institution spelled two ways -- a straight
    high-confidence threshold is the right tradeoff here.
    """
    canonical_names: list[str] = []
    result: dict[str, str] = {}
    for name in names:
        best_match = None
        best_score = 0.0
        for canonical in canonical_names:
            score = similarity(name, canonical)
            if score > best_score:
                best_score = score
                best_match = canonical
        if best_match is not None and best_score >= LENDER_DEDUPE_THRESHOLD:
            result[name] = best_match
        else:
            canonical_names.append(name)
            result[name] = name
    return result
