"""
engines/jurisdiction_engine.py — the deterministic CFIUS decision tree.

Ported verbatim from cfius_screener/jurisdiction_engine.py — zero logic
changes, only the config import path (now configs.cfius instead of the
standalone project's own config.py). This module is pure functions over
structured input: no database, no web, no Claude. Given the facts of a
transaction, it walks the jurisdictional tests of 31 CFR Part 800 in order
and returns a Determination whose findings trail shows every step, its
answer, and the regulation that drives it.

WHY deterministic: whether a CFIUS filing is legally MANDATORY is a question
of law with civil penalties (up to the value of the transaction) for getting
it wrong. A language model must never make that call. Claude's jobs are
upstream (engines/cfius_claude_intake.py — turning a plain-English deal
description into the structured facts this engine consumes) and downstream
(engines/cfius_claude_memo.py — writing the memo narrative ABOUT these
conclusions). The conclusions themselves come from here, the same answer
every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field

from configs.cfius import (
    CITATIONS,
    CONTROL_MAJORITY_PCT,
    EXCEPTED_FOREIGN_STATES,
    SUBSTANTIAL_INTEREST_ACQUISITION_PCT,
    SUBSTANTIAL_INTEREST_GOVT_PCT,
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

class TransactionFacts(BaseModel):
    """The structured facts the decision tree runs on.

    In Milestone 1 a human fills these in directly on the screening form.
    In Milestone 2 Claude proposes them from a plain-English deal description
    and a human confirms them — but the engine never knows the difference.
    """

    us_business_name: str
    us_business_description: str = ""
    acquirer_name: str
    # Home country of the acquirer (ultimate ownership, not letterbox).
    acquirer_country: str
    # Highest voting interest any single foreign government holds in the
    # acquirer (e.g. a sovereign wealth fund is typically ~100).
    foreign_govt_ownership_pct: float = Field(0.0, ge=0.0, le=100.0)
    # Voting interest the acquirer obtains in the US business.
    voting_interest_pct: float = Field(0.0, ge=0.0, le=100.0)

    # Control below the majority line: veto rights over key decisions, the
    # power to appoint a board majority, etc. (§ 800.208 control indicators).
    contractual_control_rights: bool = False

    # Covered-investment access rights (§ 800.211).
    board_seat: bool = False
    board_observer: bool = False
    access_nonpublic_tech_info: bool = False
    substantive_decision_role: bool = False

    # TID classification facts (§ 800.248).
    produces_critical_tech: bool = False
    # Would exporting those critical technologies to the acquirer's home
    # country require a US regulatory authorization (ITAR/EAR license)?
    export_authorization_required: bool = False
    critical_infrastructure: bool = False
    sensitive_personal_data: bool = False

    is_us_business: bool = True


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

class Outcome(str, Enum):
    NOT_COVERED = "NOT_COVERED"                      # CFIUS has no jurisdiction
    COVERED_VOLUNTARY = "COVERED_VOLUNTARY"          # jurisdiction, filing optional
    MANDATORY_DECLARATION = "MANDATORY_DECLARATION"  # filing required by law


@dataclass
class Finding:
    """One node of the decision tree, rendered as a row in the audit trail."""

    step: str          # short machine id, e.g. "control_test"
    question: str      # the legal question, in plain English
    answer: str        # what the facts showed
    determination: str # the legal consequence of that answer
    citation: str      # the regulation that makes it so


@dataclass
class Determination:
    outcome: Outcome
    is_tid: bool = False
    tid_categories: list[str] = field(default_factory=list)
    # "control", "covered_investment", or None when not covered.
    covered_basis: str | None = None
    excepted_investor: bool = False
    mandatory_reasons: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# The decision tree
# ---------------------------------------------------------------------------

def determine_jurisdiction(facts: TransactionFacts) -> Determination:
    """Walk the Part 800 tests in order and return the full audit trail.

    Even when an early test ends the analysis (e.g. the acquirer isn't
    foreign), the findings up to that point are returned — the trail is the
    product, not just the verdict.
    """
    d = Determination(outcome=Outcome.NOT_COVERED)

    # --- Step 1: foreign person -------------------------------------------
    is_foreign = facts.acquirer_country.strip().lower() not in (
        "united states", "usa", "us", "united states of america",
    )
    d.findings.append(Finding(
        step="foreign_person",
        question="Is the acquirer a foreign person?",
        answer=f"{facts.acquirer_name} — home country {facts.acquirer_country}.",
        determination=(
            "Foreign person — CFIUS analysis continues." if is_foreign
            else "Not a foreign person — CFIUS has no jurisdiction over this transaction."
        ),
        citation=CITATIONS["foreign_person"],
    ))
    if not is_foreign:
        return d

    # --- Step 2: US business ----------------------------------------------
    d.findings.append(Finding(
        step="us_business",
        question="Is the target a US business?",
        answer=f"{facts.us_business_name} — "
               + ("engaged in interstate commerce in the United States."
                  if facts.is_us_business else "not a US business as described."),
        determination=(
            "US business — CFIUS analysis continues." if facts.is_us_business
            else "Not a US business — CFIUS has no jurisdiction over this transaction."
        ),
        citation=CITATIONS["us_business"],
    ))
    if not facts.is_us_business:
        return d

    # --- Step 3: TID classification ---------------------------------------
    # Determined before the control test because BOTH the covered-investment
    # test (step 5) and the substantial-interest mandatory prong (step 7a)
    # depend on it.
    if facts.produces_critical_tech:
        d.tid_categories.append("Critical technologies")
    if facts.critical_infrastructure:
        d.tid_categories.append("Critical infrastructure")
    if facts.sensitive_personal_data:
        d.tid_categories.append("Sensitive personal data")
    d.is_tid = bool(d.tid_categories)
    d.findings.append(Finding(
        step="tid_classification",
        question="Is the target a TID US business (critical Technology, "
                 "critical Infrastructure, or sensitive personal Data)?",
        answer=(
            "Yes — " + ", ".join(d.tid_categories) + "." if d.is_tid
            else "No TID category applies as described."
        ),
        determination=(
            "TID US business — covered-investment jurisdiction and "
            "mandatory-declaration tests can apply." if d.is_tid
            else "Not a TID US business — only the control test can create "
                 "jurisdiction, and no mandatory declaration can apply."
        ),
        citation=CITATIONS["tid_us_business"],
    ))

    # --- Step 4 (interleaved): excepted investor ---------------------------
    # Evaluated before the covered-investment test because excepted investors
    # are carved out of that test entirely. SIMPLIFICATION: country-of-origin
    # check only — the real § 800.219 test examines the investor's own
    # ownership chain. The UI states this.
    d.excepted_investor = (
        facts.acquirer_country.strip().title() in EXCEPTED_FOREIGN_STATES
    )
    d.findings.append(Finding(
        step="excepted_investor",
        question="Does the acquirer qualify as an excepted investor?",
        answer=f"Home country {facts.acquirer_country} is "
               + ("an excepted foreign state (Australia, Canada, New Zealand, "
                  "United Kingdom)." if d.excepted_investor
                  else "not an excepted foreign state."),
        determination=(
            "May qualify as an excepted investor — exempt from "
            "covered-investment jurisdiction and from mandatory declarations. "
            "Covered CONTROL transactions remain reviewable. "
            "(Simplified test — full § 800.219 criteria require counsel.)"
            if d.excepted_investor
            else "Not an excepted investor — all jurisdictional and mandatory "
                 "tests apply."
        ),
        citation=CITATIONS["excepted_investor"],
    ))

    # --- Step 5: control test ----------------------------------------------
    acquires_control = (
        facts.voting_interest_pct >= CONTROL_MAJORITY_PCT
        or facts.contractual_control_rights
    )
    if acquires_control:
        basis_bits = []
        if facts.voting_interest_pct >= CONTROL_MAJORITY_PCT:
            basis_bits.append(
                f"{facts.voting_interest_pct:g}% voting interest (majority)"
            )
        if facts.contractual_control_rights:
            basis_bits.append("contractual control rights")
        answer = "Yes — " + " and ".join(basis_bits) + "."
    else:
        answer = (f"No — {facts.voting_interest_pct:g}% voting interest, "
                  "no contractual control rights.")
    d.findings.append(Finding(
        step="control_test",
        question="Does the transaction give the foreign person control of "
                 "the US business?",
        answer=answer,
        determination=(
            "Covered control transaction — CFIUS jurisdiction attaches. "
            "(Excepted-investor status does not remove control "
            "jurisdiction.)" if acquires_control
            else "No control — checking covered-investment jurisdiction next."
        ),
        citation=CITATIONS["covered_control_transaction"] if acquires_control
                 else CITATIONS["control"],
    ))

    # --- Step 6: covered investment (only if not control) -------------------
    if acquires_control:
        d.covered_basis = "control"
    else:
        access_rights = []
        if facts.board_seat:
            access_rights.append("board seat")
        if facts.board_observer:
            access_rights.append("board observer seat")
        if facts.access_nonpublic_tech_info:
            access_rights.append("access to material non-public technical information")
        if facts.substantive_decision_role:
            access_rights.append("involvement in substantive decision-making")

        is_covered_investment = (
            d.is_tid and bool(access_rights) and not d.excepted_investor
        )
        if is_covered_investment:
            answer = ("Yes — TID US business plus "
                      + ", ".join(access_rights) + ".")
            determination = ("Covered investment — CFIUS jurisdiction "
                             "attaches without control.")
        elif d.excepted_investor and d.is_tid and access_rights:
            answer = ("Target is TID and the investor receives "
                      + ", ".join(access_rights)
                      + ", but the investor is excepted.")
            determination = ("Excepted investors are carved out of "
                             "covered-investment jurisdiction.")
        elif not d.is_tid:
            answer = "Target is not a TID US business."
            determination = ("Covered-investment jurisdiction only applies "
                             "to TID US businesses.")
        elif not access_rights:
            answer = ("No board seat, observer seat, technical-information "
                      "access, or decision-making role.")
            determination = ("A non-controlling investment without access "
                             "rights is not a covered investment.")
        else:  # pragma: no cover — branches above are exhaustive
            answer = "Not a covered investment."
            determination = "No covered-investment jurisdiction."
        d.findings.append(Finding(
            step="covered_investment",
            question="Is this a covered (non-controlling) investment in a "
                     "TID US business?",
            answer=answer,
            determination=determination,
            citation=CITATIONS["covered_investment"],
        ))
        if is_covered_investment:
            d.covered_basis = "covered_investment"

    # --- Step 7: jurisdiction verdict ---------------------------------------
    if d.covered_basis is None:
        d.findings.append(Finding(
            step="jurisdiction_verdict",
            question="Does CFIUS have jurisdiction over this transaction?",
            answer="Neither a covered control transaction nor a covered investment.",
            determination="NOT A COVERED TRANSACTION — no CFIUS filing "
                          "available or required.",
            citation=CITATIONS["covered_control_transaction"],
        ))
        return d

    d.outcome = Outcome.COVERED_VOLUNTARY

    # --- Step 8a: mandatory declaration — substantial interest --------------
    if not d.excepted_investor:
        govt_prong = (
            facts.foreign_govt_ownership_pct >= SUBSTANTIAL_INTEREST_GOVT_PCT
        )
        acq_prong = (
            facts.voting_interest_pct >= SUBSTANTIAL_INTEREST_ACQUISITION_PCT
        )
        triggered = govt_prong and acq_prong and d.is_tid
        d.findings.append(Finding(
            step="mandatory_substantial_interest",
            question="Mandatory declaration — substantial interest: does a "
                     f"foreign government hold ≥{SUBSTANTIAL_INTEREST_GOVT_PCT:g}% "
                     f"of the acquirer AND does the acquirer obtain "
                     f"≥{SUBSTANTIAL_INTEREST_ACQUISITION_PCT:g}% of a TID US "
                     "business?",
            answer=(f"Foreign government interest in acquirer: "
                    f"{facts.foreign_govt_ownership_pct:g}%. Voting interest "
                    f"acquired: {facts.voting_interest_pct:g}%. TID business: "
                    f"{'yes' if d.is_tid else 'no'}."),
            determination=(
                "MANDATORY DECLARATION REQUIRED — substantial-interest test met."
                if triggered else
                "Substantial-interest test not met — no mandatory filing on "
                "this prong."
            ),
            citation=f"{CITATIONS['mandatory_declaration']}; "
                     f"{CITATIONS['substantial_interest']}",
        ))
        if triggered:
            d.mandatory_reasons.append("substantial_interest")

        # --- Step 8b: mandatory declaration — critical technology -----------
        ct_triggered = (
            facts.produces_critical_tech and facts.export_authorization_required
        )
        d.findings.append(Finding(
            step="mandatory_critical_tech",
            question="Mandatory declaration — critical technology: does the "
                     "US business produce critical technologies that would "
                     "require a US export authorization for the acquirer's "
                     "home country?",
            answer=(
                "Produces critical technologies: "
                f"{'yes' if facts.produces_critical_tech else 'no'}. "
                "Export authorization required for "
                f"{facts.acquirer_country}: "
                f"{'yes' if facts.export_authorization_required else 'no'}."
            ),
            determination=(
                "MANDATORY DECLARATION REQUIRED — critical-technology test met."
                if ct_triggered else
                "Critical-technology test not met — no mandatory filing on "
                "this prong."
            ),
            citation=f"{CITATIONS['mandatory_declaration']}; "
                     f"{CITATIONS['critical_technologies']}",
        ))
        if ct_triggered:
            d.mandatory_reasons.append("critical_technology")
    else:
        d.findings.append(Finding(
            step="mandatory_exemption",
            question="Do the mandatory declaration requirements apply?",
            answer="The acquirer is an excepted investor.",
            determination="Excepted investors are exempt from both mandatory "
                          "declaration prongs. Any filing would be voluntary.",
            citation=CITATIONS["excepted_investor"],
        ))

    if d.mandatory_reasons:
        d.outcome = Outcome.MANDATORY_DECLARATION

    return d
