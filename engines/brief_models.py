"""engines/brief_models.py — Pre-Acquisition Brief Generator's original
in-memory dataclasses (acquisition_brief/models.py), ported verbatim.
This is the pipeline's working shape; models/brief.py (SQLAlchemy) is
what a completed run gets persisted into.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PatentRecord:
    patent_id: str
    title: str
    filing_date: str
    grant_date: str
    cpc_classes: list[str]
    forward_citations: int


@dataclass
class IPPortfolio:
    company: str
    total_patents: int
    recent_patents: int         # last RECENT_YEARS
    patent_velocity: float      # patents/year, recent period
    baseline_velocity: float    # patents/year, baseline period
    velocity_change_pct: float  # (recent - baseline) / baseline * 100
    top_domains: list[str]      # human-readable CPC category labels
    avg_citations: float
    strength_tier: str          # STRONG / MODERATE / WEAK / MINIMAL
    patents: list[PatentRecord] = field(default_factory=list)


@dataclass
class LitigationCase:
    case_id: str
    case_name: str
    court: str
    filed_date: str
    status: str     # ACTIVE / CLOSED / SETTLED / PENDING
    case_type: str  # IP_DISPUTE / CONTRACT / EMPLOYMENT / REGULATORY / SECURITIES
    summary: str


@dataclass
class LitigationProfile:
    company: str
    total_cases: int
    active_cases: int
    ip_disputes: int
    regulatory_actions: int
    settled_last_3yr: int
    risk_tier: str  # CRITICAL / ELEVATED / NORMAL / CLEAR
    cases: list[LitigationCase] = field(default_factory=list)


@dataclass
class RegulatoryFlag:
    flag_type: str   # MATERIAL_WEAKNESS / GOING_CONCERN / EXPORT_CONTROL / CONTRACT_DEPENDENCY / SEC_COMMENT
    severity: str    # HIGH / MEDIUM / LOW / INFORMATIONAL
    description: str
    filing_period: str
    excerpt: str


@dataclass
class RegulatoryExposure:
    company: str
    ticker: str
    material_weakness: bool
    going_concern: bool
    export_control_mentions: int
    government_revenue_pct: float
    flags: list[RegulatoryFlag] = field(default_factory=list)
    exposure_tier: str = "LOW"


@dataclass
class ContractAward:
    award_id: str
    awarding_agency: str
    value_usd: float
    award_date: str
    description: str
    naics_code: str


@dataclass
class ContractProfile:
    company: str
    total_awards: int
    total_value_usd: float
    agency_breakdown: dict[str, float]   # agency -> cumulative dollars
    primary_agency: str
    primary_agency_pct: float
    recent_awards: int                   # last 2 calendar years
    naics_top: list[str]
    dependency_tier: str  # HIGH_DEPENDENCY / MODERATE / DIVERSIFIED
    awards: list[ContractAward] = field(default_factory=list)


@dataclass
class AcquisitionBrief:
    company: str
    ticker: str
    prepared_date: str
    ip_portfolio: IPPortfolio
    litigation_profile: LitigationProfile
    regulatory_exposure: RegulatoryExposure
    contract_profile: ContractProfile
    overall_risk_tier: str       # CLEAN / LOW / MODERATE / HIGH / CRITICAL
    diligence_questions: list[str]
    executive_summary: str
    full_text: str
