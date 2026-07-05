"""engines/brief_seed_data.py — demo data for Parsons Corporation (NYSE:
PSN), a mid-size defense IT/cyber contractor. Ported verbatim from
acquisition_brief/seed_data.py.

`load_seed_data(db)` is net-new (the original CLI had no persistence --
`main.py demo` ran the four-source pipeline fresh every invocation and
printed to the terminal): runs the same pipeline in demo mode, resolves
Parsons Corporation against the shared Company table, and persists one
AcquisitionBrief row, idempotently.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from database import Base  # noqa: F401 -- ensures models import order doesn't matter
from models.brief import AcquisitionBrief
from shared.resolve_company import resolve_or_create_company

DEMO_COMPANY = "Parsons Corporation"
DEMO_TICKER = "PSN"

# ---------------------------------------------------------------------------
# USPTO — 26 sample patent records
# Baseline period 2019-2022 (4yr): 16 patents (4.0/yr)
# Recent period 2023-2025 (3yr): 10 patents (3.3/yr) -> -17% velocity change
# Top domains: Network Security, Computing Systems, Radar/Remote Sensing
# Avg citations: ~4.5  Strength tier: MODERATE (26 >= IP_MODERATE_MIN=25)
# ---------------------------------------------------------------------------
DEMO_PATENTS: list[dict] = [
    {
        "patent_id": "US11,489,835",
        "title": "Zero-Trust Architecture for Multi-Domain Defense Networks",
        "filing_date": "2022-02-08",
        "grant_date": "2022-11-01",
        "cpc_classes": ["H04L63/08", "H04L63/10", "G06F21/60"],
        "forward_citations": 9,
    },
    {
        "patent_id": "US11,356,491",
        "title": "Automated CMMC Compliance Verification System",
        "filing_date": "2021-09-14",
        "grant_date": "2022-06-07",
        "cpc_classes": ["G06F21/57", "G06Q10/06"],
        "forward_citations": 6,
    },
    {
        "patent_id": "US11,611,883",
        "title": "Real-Time Anomaly Detection in Satellite Communications",
        "filing_date": "2022-05-20",
        "grant_date": "2023-03-21",
        "cpc_classes": ["H04L63/14", "H04B7/185"],
        "forward_citations": 4,
    },
    {
        "patent_id": "US11,250,172",
        "title": "Adaptive SIGINT Collection and Processing Framework",
        "filing_date": "2020-11-30",
        "grant_date": "2022-02-15",
        "cpc_classes": ["G01S7/021", "H04K3/00"],
        "forward_citations": 5,
    },
    {
        "patent_id": "US11,782,447",
        "title": "Autonomous UAS Geofencing Enforcement with Cryptographic Proof",
        "filing_date": "2022-08-12",
        "grant_date": "2023-10-10",
        "cpc_classes": ["B64C39/02", "G06F21/64", "G01S19/13"],
        "forward_citations": 3,
    },
    {
        "patent_id": "US10,958,666",
        "title": "Supply Chain Provenance Tracking for Critical Electronic Components",
        "filing_date": "2019-06-18",
        "grant_date": "2021-03-23",
        "cpc_classes": ["G06Q10/0831", "H04L9/32"],
        "forward_citations": 7,
    },
    {
        "patent_id": "US11,042,884",
        "title": "Federated Machine Learning for Cross-Agency Threat Intelligence",
        "filing_date": "2020-03-09",
        "grant_date": "2021-06-22",
        "cpc_classes": ["G06N20/00", "H04L63/04"],
        "forward_citations": 12,
    },
    {
        "patent_id": "US11,860,007",
        "title": "Passive Radar Signal Classification Using Deep Residual Networks",
        "filing_date": "2023-01-25",
        "grant_date": "2024-01-02",
        "cpc_classes": ["G01S7/40", "G06N3/04"],
        "forward_citations": 2,
    },
    {
        "patent_id": "US11,705,026",
        "title": "Cryptographically Sealed Audit Trail for Classified Information Systems",
        "filing_date": "2022-10-04",
        "grant_date": "2023-07-18",
        "cpc_classes": ["G06F21/64", "H04L9/32"],
        "forward_citations": 5,
    },
    {
        "patent_id": "US10,715,552",
        "title": "Multi-Layer Intrusion Detection for Operational Technology Networks",
        "filing_date": "2018-11-14",
        "grant_date": "2020-07-14",
        "cpc_classes": ["H04L63/14", "G05B23/02"],
        "forward_citations": 8,
    },
    {
        "patent_id": "US10,834,117",
        "title": "Attribute-Based Access Control for Classified Cloud Environments",
        "filing_date": "2019-02-26",
        "grant_date": "2020-11-10",
        "cpc_classes": ["H04L63/10", "G06F21/62"],
        "forward_citations": 6,
    },
    {
        "patent_id": "US11,924,235",
        "title": "AI-Driven Predictive Maintenance for Critical Infrastructure Sensors",
        "filing_date": "2023-06-07",
        "grant_date": "2024-03-05",
        "cpc_classes": ["G06N3/08", "G06F11/07"],
        "forward_citations": 1,
    },
    {
        "patent_id": "US11,157,613",
        "title": "Secure Multi-Party Computation for Joint Intelligence Analysis",
        "filing_date": "2020-07-22",
        "grant_date": "2021-10-26",
        "cpc_classes": ["H04L9/08", "G06F21/60"],
        "forward_citations": 4,
    },
    {
        "patent_id": "US10,637,881",
        "title": "Dynamic Security Posture Assessment for DoD Information Systems",
        "filing_date": "2018-04-03",
        "grant_date": "2020-04-28",
        "cpc_classes": ["G06F21/57", "H04L63/20"],
        "forward_citations": 3,
    },
    {
        "patent_id": "US11,996,082",
        "title": "Quantum-Resistant Key Exchange Protocol for Tactical Networks",
        "filing_date": "2023-09-11",
        "grant_date": "2024-05-28",
        "cpc_classes": ["H04L9/08", "H04L63/06"],
        "forward_citations": 0,
    },
    {
        "patent_id": "US11,509,489",
        "title": "Automated Threat Hunting in Industrial Control System Environments",
        "filing_date": "2021-12-01",
        "grant_date": "2022-11-22",
        "cpc_classes": ["H04L63/14", "G05B23/02"],
        "forward_citations": 4,
    },
    {
        "patent_id": "US11,095,687",
        "title": "Software-Defined Perimeter for Remote Cleared Workforce Access",
        "filing_date": "2020-05-14",
        "grant_date": "2021-08-17",
        "cpc_classes": ["H04L63/02", "H04L63/08"],
        "forward_citations": 7,
    },
    {
        "patent_id": "US11,388,219",
        "title": "Scalable Security Operations Center Workflow Automation Platform",
        "filing_date": "2021-06-28",
        "grant_date": "2022-07-12",
        "cpc_classes": ["H04L63/14", "G06F9/451"],
        "forward_citations": 3,
    },
    {
        "patent_id": "US12,001,445",
        "title": "Adversarial Machine Learning Detection for Autonomous Defense Systems",
        "filing_date": "2023-11-14",
        "grant_date": "2024-09-03",
        "cpc_classes": ["G06N20/00", "G06F21/57"],
        "forward_citations": 0,
    },
    {
        "patent_id": "US11,812,330",
        "title": "Cross-Domain Solution for Classified-to-Unclassified Data Transfer",
        "filing_date": "2023-02-22",
        "grant_date": "2023-11-07",
        "cpc_classes": ["H04L63/02", "G06F21/60", "H04L9/32"],
        "forward_citations": 2,
    },
    {
        "patent_id": "US11,620,485",
        "title": "Automated Vulnerability Triage Using Behavioral Signatures",
        "filing_date": "2022-06-05",
        "grant_date": "2023-04-11",
        "cpc_classes": ["H04L63/14", "G06N3/08"],
        "forward_citations": 5,
    },
    {
        "patent_id": "US10,892,910",
        "title": "Tactical Edge Computing Node with Secure Enclaves",
        "filing_date": "2019-08-07",
        "grant_date": "2021-01-12",
        "cpc_classes": ["G06F21/72", "H04L63/04"],
        "forward_citations": 4,
    },
    {
        "patent_id": "US11,115,436",
        "title": "Insider Threat Detection via Graph-Based User Behavior Analytics",
        "filing_date": "2020-01-17",
        "grant_date": "2021-09-07",
        "cpc_classes": ["H04L63/14", "G06Q10/10"],
        "forward_citations": 6,
    },
    {
        "patent_id": "US11,956,274",
        "title": "Digital Twin Framework for Critical Infrastructure Cyber Resilience",
        "filing_date": "2023-04-18",
        "grant_date": "2024-02-13",
        "cpc_classes": ["G06F30/20", "H04L63/14"],
        "forward_citations": 1,
    },
    {
        "patent_id": "US10,778,459",
        "title": "Secure Software-Defined Radio for Tactical Communications",
        "filing_date": "2019-03-28",
        "grant_date": "2020-09-15",
        "cpc_classes": ["H04B1/38", "H04L63/06"],
        "forward_citations": 5,
    },
    {
        "patent_id": "US11,451,563",
        "title": "Adaptive Access Control Policy Engine for Multi-Cloud Defense Environments",
        "filing_date": "2021-04-06",
        "grant_date": "2022-09-20",
        "cpc_classes": ["H04L63/10", "G06F21/62"],
        "forward_citations": 3,
    },
]

# ---------------------------------------------------------------------------
# CourtListener — 4 litigation cases
# ---------------------------------------------------------------------------
DEMO_CASES: list[dict] = [
    {
        "case_id": "cl-9841023",
        "case_name": "Vargas et al. v. Parsons Corporation",
        "court": "U.S. District Court, C.D. California",
        "filed_date": "2023-04-17",
        "status": "ACTIVE",
        "case_type": "EMPLOYMENT",
        "summary": (
            "Class action alleging violations of California Labor Code SS 226, 510, "
            "and PAGA: unpaid overtime, missed meal periods, and failure to provide "
            "accurate wage statements for approximately 1,200 salaried-exempt "
            "classified-facility employees. Plaintiffs seek back wages, statutory "
            "penalties, and injunctive relief. Class certification briefing pending."
        ),
    },
    {
        "case_id": "cl-10297461",
        "case_name": "Axiom Technical Services LLC v. Parsons Federal Services Inc.",
        "court": "U.S. District Court, E.D. Virginia",
        "filed_date": "2024-01-09",
        "status": "ACTIVE",
        "case_type": "CONTRACT",
        "summary": (
            "Subcontractor claims breach of a $14.2M task order for cybersecurity "
            "engineering support on a classified DoD program. Axiom alleges Parsons "
            "wrongfully terminated for convenience after incorporating Axiom's "
            "proprietary methodology into a follow-on prime contract. Parsons has "
            "counterclaimed for defective deliverables. Discovery ongoing."
        ),
    },
    {
        "case_id": "cl-7602214",
        "case_name": "In re Parsons Corporation Securities Litigation",
        "court": "U.S. District Court, D. Maryland",
        "filed_date": "2021-08-03",
        "status": "SETTLED",
        "case_type": "SECURITIES",
        "summary": (
            "Securities class action alleging that Parsons made materially misleading "
            "statements regarding contract backlog and program execution on a federal "
            "IT modernization effort. Settled in February 2023 for $18.5M with no "
            "admission of liability. Settlement funded by D&O insurance. Case closed."
        ),
    },
    {
        "case_id": "cl-6891047",
        "case_name": "Parsons Government Services Inc. v. Centinel Defense Systems LLC",
        "court": "U.S. District Court, D. Delaware",
        "filed_date": "2020-11-22",
        "status": "CLOSED",
        "case_type": "IP_DISPUTE",
        "summary": (
            "Parsons brought suit alleging infringement of US 10,637,881 (Dynamic "
            "Security Posture Assessment). Centinel cross-claimed invalidity. "
            "Case settled in June 2021 with a cross-licensing agreement; terms "
            "undisclosed. No damages awarded. Patent confirmed valid."
        ),
    },
]

# ---------------------------------------------------------------------------
# SEC EDGAR — regulatory exposure profile
# ---------------------------------------------------------------------------
DEMO_REGULATORY_DATA: dict = {
    "material_weakness": False,
    "going_concern": False,
    "export_control_mentions": 8,
    "government_revenue_pct": 0.80,
    "flags": [
        {
            "flag_type": "EXPORT_CONTROL",
            "severity": "MEDIUM",
            "description": "ITAR and EAR compliance obligations cited as material risk factor",
            "filing_period": "FY2024",
            "excerpt": (
                "We are subject to various U.S. export control laws and regulations, "
                "including the International Traffic in Arms Regulations (ITAR) and the "
                "Export Administration Regulations (EAR). Failure to comply with these "
                "requirements could result in civil and criminal penalties, loss of export "
                "privileges, and suspension or debarment from government contracting."
            ),
        },
        {
            "flag_type": "CONTRACT_DEPENDENCY",
            "severity": "LOW",
            "description": "~80% revenue from U.S. federal government contracts -- standard for DIB",
            "filing_period": "FY2024",
            "excerpt": (
                "Approximately 80% of our revenues are derived from contracts with the "
                "U.S. federal government. Reductions in government spending, continuing "
                "resolutions, and sequestration events could materially impact our revenues "
                "and operating results."
            ),
        },
        {
            "flag_type": "SEC_COMMENT",
            "severity": "INFORMATIONAL",
            "description": "SEC staff comment on revenue recognition for long-term cost-plus contracts",
            "filing_period": "FY2023",
            "excerpt": (
                "The staff requested additional disclosure regarding the Company's application "
                "of ASC 606 to performance obligations on cost-plus-fixed-fee contracts, "
                "specifically the determination of standalone selling prices for engineering "
                "labor categories. The Company responded with enhanced footnote disclosure "
                "and the comment was resolved without restatement."
            ),
        },
    ],
}

# ---------------------------------------------------------------------------
# USASpending — 15 representative contract awards
# ---------------------------------------------------------------------------
DEMO_AWARDS: list[dict] = [
    {
        "award_id": "FA8750-23-C-0042",
        "awarding_agency": "Department of Defense",
        "value_usd": 287_400_000,
        "award_date": "2023-03-14",
        "description": "Cybersecurity Operations Center (CSOC) enterprise services for AFCYBER",
        "naics_code": "541512",
    },
    {
        "award_id": "FA8750-24-C-0015",
        "awarding_agency": "Department of Defense",
        "value_usd": 143_800_000,
        "award_date": "2024-01-22",
        "description": "C4ISR systems integration and sustainment, multiple COCOM",
        "naics_code": "541519",
    },
    {
        "award_id": "W91CRB-22-C-0078",
        "awarding_agency": "Department of Defense",
        "value_usd": 98_000_000,
        "award_date": "2022-09-30",
        "description": "Missile defense program systems engineering and integration support",
        "naics_code": "541330",
    },
    {
        "award_id": "W91CRB-24-C-0011",
        "awarding_agency": "Department of Defense",
        "value_usd": 211_500_000,
        "award_date": "2024-04-05",
        "description": "Integrated Air and Missile Defense (IAMD) technical support",
        "naics_code": "541330",
    },
    {
        "award_id": "HQ0034-23-D-0003",
        "awarding_agency": "Department of Defense",
        "value_usd": 72_000_000,
        "award_date": "2023-07-11",
        "description": "Space systems software development and sustainment",
        "naics_code": "541512",
    },
    {
        "award_id": "70RDND22C00000012",
        "awarding_agency": "Department of Homeland Security",
        "value_usd": 185_200_000,
        "award_date": "2022-10-01",
        "description": "Border security technology deployment and maintenance, CBP",
        "naics_code": "541519",
    },
    {
        "award_id": "70RDND23C00000034",
        "awarding_agency": "Department of Homeland Security",
        "value_usd": 94_700_000,
        "award_date": "2023-09-28",
        "description": "TSA aviation security IT operations and modernization",
        "naics_code": "541512",
    },
    {
        "award_id": "70RSAT24C00000007",
        "awarding_agency": "Department of Homeland Security",
        "value_usd": 67_500_000,
        "award_date": "2024-02-14",
        "description": "CISA National Cybersecurity Protection System (NCPS) engineering",
        "naics_code": "541330",
    },
    {
        "award_id": "2024-H-SZ-0003",
        "awarding_agency": "Intelligence Community",
        "value_usd": 134_000_000,
        "award_date": "2024-03-18",
        "description": "All-source intelligence analysis platform development (classified)",
        "naics_code": "541519",
    },
    {
        "award_id": "2022-H-SZ-0017",
        "awarding_agency": "Intelligence Community",
        "value_usd": 88_600_000,
        "award_date": "2022-11-07",
        "description": "Geospatial intelligence data processing and exploitation",
        "naics_code": "541512",
    },
    {
        "award_id": "GS-00F-0034X",
        "awarding_agency": "General Services Administration",
        "value_usd": 52_300_000,
        "award_date": "2023-05-02",
        "description": "Cloud security architecture and FedRAMP advisory services",
        "naics_code": "541519",
    },
    {
        "award_id": "19AQMM22C00193",
        "awarding_agency": "Department of State",
        "value_usd": 38_900_000,
        "award_date": "2022-08-15",
        "description": "Diplomatic security communications infrastructure modernization",
        "naics_code": "541330",
    },
    {
        "award_id": "VA118-23-C-0089",
        "awarding_agency": "Department of Veterans Affairs",
        "value_usd": 29_400_000,
        "award_date": "2023-11-01",
        "description": "VA electronic health record integration and cybersecurity support",
        "naics_code": "541512",
    },
    {
        "award_id": "DE-AC52-24PSC0041",
        "awarding_agency": "Department of Energy",
        "value_usd": 44_100_000,
        "award_date": "2024-05-10",
        "description": "Nuclear facility cyber resilience assessment and remediation",
        "naics_code": "541330",
    },
    {
        "award_id": "N00039-23-C-0092",
        "awarding_agency": "Department of Defense",
        "value_usd": 61_800_000,
        "award_date": "2023-12-19",
        "description": "Naval tactical communications network security modernization",
        "naics_code": "541512",
    },
]

# ---------------------------------------------------------------------------
# Pre-baked acquisition brief
# ---------------------------------------------------------------------------
DEMO_BRIEF = """PRE-ACQUISITION INTELLIGENCE BRIEF
RESTRICTED -- ATTORNEY-CLIENT PRIVILEGED

TO:      Acquisition Committee
FROM:    Intelligence Analysis Unit
RE:      Target Company Assessment -- Parsons Corporation (NYSE: PSN)
DATE:    June 24, 2026

------------------------------------------------------------------------

I. EXECUTIVE SUMMARY

Parsons Corporation presents a MODERATE overall acquisition risk profile with no
disqualifying red flags. The company is a well-established defense IT and critical
infrastructure integrator with approximately $4.5B in annual revenue and an ~80%
government revenue concentration. The IP portfolio is MODERATE (58 patents, stable
velocity), litigation exposure is NORMAL (2 active cases, neither IP-related), and
regulatory exposure is MODERATE primarily due to standard ITAR/EAR obligations and
high government contract dependency. Government contract analysis reveals MODERATE
concentration in DoD (52%), which is sector-typical and does not represent an unusual
dependency risk for a defense-oriented acquirer. Seven diligence questions are
recommended for legal counsel review.

------------------------------------------------------------------------

II. IP PORTFOLIO ASSESSMENT -- MODERATE

Parsons holds 58 granted patents with 18 issued in the recent three-year period
(2022-2024), representing a patent velocity of 6.0 per year versus a baseline rate
of 7.0 per year (2018-2021) -- a 14% deceleration. This deceleration is not alarming
and may reflect a shift toward classified/unpublished innovations, which are inherently
excluded from public patent counts and are common in defense IT. The portfolio
concentrates in Network Security (H04L, 28%), Computing Systems (G06F, 22%), and
Radar/Remote Sensing (G01S, 17%), consistent with the company's C4ISR and
cybersecurity program footprint.

Average forward citation count is 4.2, indicating moderate external validation. The
highest-cited patent (US11,042,884 -- Federated Machine Learning for Cross-Agency
Threat Intelligence, 12 forward citations) addresses a strategically relevant
capability gap. Three patents filed in 2023-2024 have zero forward citations, which
is expected given their recency.

One closed IP dispute (Parsons v. Centinel Defense, D. Delaware 2020-2021) resulted
in a cross-licensing agreement confirming the validity of US 10,637,881. No patents
are currently under inter partes review (IPR) challenge.

DILIGENCE NOTE: The filing velocity deceleration warrants inquiry into whether key
IP is now generated in classified programs and therefore not captured in public patent
filings. Acquirer should request a complete trade secret register as part of technical
due diligence.

------------------------------------------------------------------------

III. LITIGATION RISK PROFILE -- NORMAL

Parsons has four identified cases in the CourtListener federal docket database,
consistent with the expected litigation profile of a $4B+ federal contractor.

Active cases (2):
  -- Vargas et al. v. Parsons (C.D. Cal. 2023): California labor code class action
    for approximately 1,200 employees. Class certification pending. Financial exposure
    estimated at $8-22M based on comparable PAGA settlements. This is a common
    California employer risk and not a strategic concern.

  -- Axiom Technical Services v. Parsons Federal Services (E.D. Va. 2024): $14.2M
    subcontractor breach and misappropriation claim. The proprietary methodology
    allegation warrants close review -- if Axiom's claims have merit, there could be
    follow-on IP infringement exposure on the downstream prime contract.

Resolved cases (2):
  -- In re Parsons Securities Litigation (D. Md., settled Feb. 2023, $18.5M): Funded
    by D&O insurance; no admission of liability. The underlying allegations regarding
    backlog disclosure practices are resolved and should not affect current forecasting.
  -- Parsons v. Centinel (D. Del., closed June 2021): Cross-licensing resolution.
    No current IP exposure.

There are no regulatory enforcement actions, FCPA investigations, False Claims Act
(FCA) suits, or debarment proceedings identified in the public record.

------------------------------------------------------------------------

IV. REGULATORY EXPOSURE -- MODERATE

No material weaknesses or going-concern qualifications appear in Parsons' SEC filings
for FY2022-FY2024. The company received an unqualified audit opinion each year.

Three regulatory flags are noted:

1. EXPORT CONTROL (MEDIUM): Eight ITAR/EAR references appear in the FY2024 10-K risk
   factors, consistent with a company operating classified and controlled programs.
   These are disclosure obligations, not evidence of past violations. However, acquirer
   should request Parsons' ITAR registration history, any State Department consent
   agreements, and the most recent DTSA commodity jurisdiction determinations for
   key program deliverables.

2. CONTRACT DEPENDENCY (LOW): ~80% federal government revenue concentration is
   disclosed explicitly. For a defense-oriented acquirer, this is sector-standard
   and not a risk amplifier -- it would be a concern only if the acquirer's existing
   portfolio is already highly concentrated in the same agency accounts.

3. SEC STAFF COMMENT (INFORMATIONAL): A resolved 2023 comment regarding ASC 606
   revenue recognition on cost-plus contracts. No restatement required. This signals
   that Parsons' long-duration contract accounting warrants normal acquirer scrutiny
   but does not indicate a disclosure failure.

------------------------------------------------------------------------

V. GOVERNMENT CONTRACT DEPENDENCY PROFILE -- MODERATE

Analysis of 15 representative federal contract awards totaling $1.61B identifies
the following agency distribution:

  Department of Defense:        52% ($874M)  -- MODERATE concentration
  Department of Homeland Security: 22% ($347M)
  Intelligence Community:       14% ($223M)
  Other Agencies (GSA/State/VA/DOE): 12% ($165M)

The DoD share at 52% is below the HIGH_DEPENDENCY threshold (60%) and reflects
appropriate diversification across DHS and the IC. The CISA/NCPS engagement and
nuclear facility work at DOE indicate an intentional strategy to distribute risk
across national security customers beyond DoD.

Recent contract activity (2024 awards: $356M of the identified $1.61B, approximately
22%) suggests a healthy pipeline replenishment rate. The IAMD ($211.5M) and CSOC
($287.4M) contracts represent flagship program wins with multi-year revenue visibility.

Key agency relationships: AFCYBER, Army Space and Missile Defense Command, CBP, CISA,
NRO/NGA (implied by classified IC awards), and naval tactical communications.

------------------------------------------------------------------------

VI. RECOMMENDED DILIGENCE QUESTIONS FOR COUNSEL

1. IP -- Classified program trade secret register: What proprietary methodologies,
   algorithms, and source code are embedded in classified program deliverables that
   would not appear in public patent filings? Request a complete trade secret register
   with government ownership/rights-in-data determinations under FAR 52.227-14.

2. Litigation -- Axiom Technical Services methodology claim: Obtain the full complaint
   and Axiom's expert disclosures to assess whether the "proprietary methodology"
   allegation overlaps with any patent-pending Parsons innovations or with deliverables
   under the current prime contract that would pass to the acquirer.

3. Export Control -- ITAR registration and consent agreements: Confirm current DDTC
   registration status, any past voluntary disclosures, and whether any Parsons
   facilities are operating under consent agreements or special licensing conditions
   that would require prior State Department approval of the proposed acquisition.

4. IP velocity deceleration: Request management's explanation for the 14% decline
   in public patent filing velocity from baseline. Determine whether the cause is
   (a) migration to trade secrets and SBIR/classified program IP, (b) workforce
   attrition in the innovation pipeline, or (c) a deliberate portfolio rationalization.

5. Contract -- CMMC certification status: For each active DoD contract requiring
   CMMC Level 2 or Level 3 certification, confirm whether Parsons has achieved C3PAO
   assessment, and whether any contracts contain re-assessment triggers upon change
   of ownership that could create a gap risk during the acquisition transition period.

6. Litigation -- FCA exposure: The subcontractor dispute (Axiom) and prior securities
   case both involved allegations about program delivery. Request all active qui tam
   investigations or government audit findings (DCAA/DCMA) not yet in the public
   record.

7. Regulatory -- Government revenue concentration: For the top 10 contracts by value,
   confirm option exercise history and remaining ceiling. Assess whether any single
   program represents >15% of total annual revenue, which would require specific
   retention risk analysis in the integration plan.
"""


def load_seed_data(db: Session) -> None:
    if db.query(AcquisitionBrief).filter_by(is_demo=True).first():
        return  # idempotent

    from engines.brief_uspto_client import fetch_patents, build_ip_portfolio
    from engines.brief_courtlistener_client import fetch_cases, build_litigation_profile
    from engines.brief_edgar_client import fetch_regulatory_data, build_regulatory_exposure
    from engines.brief_contracts_client import fetch_awards, build_contract_profile
    from engines.brief_engine import build_brief
    from engines.brief_claude_generator import generate_brief

    patents = fetch_patents(DEMO_COMPANY, demo_mode=True)
    cases = fetch_cases(DEMO_COMPANY, demo_mode=True)
    reg_raw = fetch_regulatory_data(DEMO_COMPANY, DEMO_TICKER, demo_mode=True)
    awards = fetch_awards(DEMO_COMPANY, demo_mode=True)

    ip = build_ip_portfolio(DEMO_COMPANY, patents)
    lit = build_litigation_profile(DEMO_COMPANY, cases)
    reg = build_regulatory_exposure(DEMO_COMPANY, DEMO_TICKER, reg_raw)
    cont = build_contract_profile(DEMO_COMPANY, awards)

    full_text, questions, summary = generate_brief(
        DEMO_COMPANY, DEMO_TICKER, ip, lit, reg, cont, demo_mode=True,
    )
    brief = build_brief(DEMO_COMPANY, DEMO_TICKER, ip, lit, reg, cont, full_text, questions, summary)

    resolution = resolve_or_create_company(db, DEMO_COMPANY, ticker=DEMO_TICKER)

    db.add(AcquisitionBrief(
        company_id=resolution.company.id,
        company_name=brief.company,
        ticker=brief.ticker,
        prepared_date=brief.prepared_date,
        ip_json=json.dumps(_ip_to_dict(brief.ip_portfolio)),
        litigation_json=json.dumps(_lit_to_dict(brief.litigation_profile)),
        regulatory_json=json.dumps(_reg_to_dict(brief.regulatory_exposure)),
        contract_json=json.dumps(_cont_to_dict(brief.contract_profile)),
        overall_risk_tier=brief.overall_risk_tier,
        diligence_questions_json=json.dumps(brief.diligence_questions),
        executive_summary=brief.executive_summary,
        full_text=brief.full_text,
        is_demo=True,
    ))
    db.commit()


def _ip_to_dict(ip) -> dict:
    d = ip.__dict__.copy()
    d["patents"] = [p.__dict__ for p in ip.patents]
    return d


def _lit_to_dict(lit) -> dict:
    d = lit.__dict__.copy()
    d["cases"] = [c.__dict__ for c in lit.cases]
    return d


def _reg_to_dict(reg) -> dict:
    d = reg.__dict__.copy()
    d["flags"] = [f.__dict__ for f in reg.flags]
    return d


def _cont_to_dict(cont) -> dict:
    d = cont.__dict__.copy()
    d["awards"] = [a.__dict__ for a in cont.awards]
    return d
