"""models/ghosttrace.py — ported from ghosttrace/models.py, unchanged
shape, plus Trace.company_id -> Company. Every other field, property, and
relationship is identical to the original.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Filing(Base):
    """Fetched filing documents. Doubles as the EDGAR cache: the orchestrator
    checks here before hitting the network, and reports cite rows from here."""

    __tablename__ = "ghosttrace_filings"
    __table_args__ = (UniqueConstraint("accession_number", "document_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    accession_number: Mapped[str] = mapped_column(String(30))
    document_name: Mapped[str] = mapped_column(String(200))
    form: Mapped[str] = mapped_column(String(20))
    filing_date: Mapped[str] = mapped_column(String(10))
    text: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    @property
    def edgar_url(self) -> str:
        acc = self.accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{acc}/{self.document_name}"


class Trace(Base):
    __tablename__ = "ghosttrace_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NEW: links this trace to the shared cross-tool Company row. Nullable
    # during the port -- resolve_or_create_company() is called by the
    # router (routers/ghosttrace.py), not here, so a Trace built directly
    # (e.g. in a test) can exist without one.
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(300))
    cik: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null for seed data
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(10), default="LOW")  # HIGH | MEDIUM | LOW
    _findings: Mapped[str | None] = mapped_column("findings_json", Text, nullable=True)

    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    _key_findings: Mapped[str | None] = mapped_column("key_findings_json", Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph_image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)

    ofac_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    _ofac_hits_json: Mapped[str | None] = mapped_column("ofac_hits_json", Text, nullable=True)

    deep_trace_ran_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    _deep_trace_json: Mapped[str | None] = mapped_column("deep_trace_json", Text, nullable=True)

    entities: Mapped[list["Entity"]] = relationship(
        "Entity", back_populates="trace", cascade="all, delete-orphan"
    )
    links: Mapped[list["OwnershipLink"]] = relationship(
        "OwnershipLink", back_populates="trace", cascade="all, delete-orphan"
    )

    @property
    def findings(self) -> list[dict]:
        return json.loads(self._findings) if self._findings else []

    @findings.setter
    def findings(self, val: list[dict]) -> None:
        self._findings = json.dumps(val)

    @property
    def key_findings(self) -> list[str]:
        return json.loads(self._key_findings) if self._key_findings else []

    @key_findings.setter
    def key_findings(self, val: list[str]) -> None:
        self._key_findings = json.dumps(val)

    @property
    def ofac_hits(self) -> list[dict]:
        return json.loads(self._ofac_hits_json) if self._ofac_hits_json else []

    @ofac_hits.setter
    def ofac_hits(self, val: list[dict]) -> None:
        self._ofac_hits_json = json.dumps(val)

    @property
    def deep_trace(self) -> dict | None:
        return json.loads(self._deep_trace_json) if self._deep_trace_json else None

    @deep_trace.setter
    def deep_trace(self, val: dict) -> None:
        self._deep_trace_json = json.dumps(val)

    @property
    def risk_badge_class(self) -> str:
        return {"HIGH": "badge-red", "MEDIUM": "badge-yellow", "LOW": "badge-green"}.get(
            self.risk_level, "badge-green"
        )


class Entity(Base):
    __tablename__ = "ghosttrace_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[int] = mapped_column(Integer, ForeignKey("ghosttrace_traces.id"))
    canonical_name: Mapped[str] = mapped_column(String(300))
    entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jurisdiction_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    is_focal: Mapped[bool] = mapped_column(Boolean, default=False)
    _aliases: Mapped[str | None] = mapped_column("aliases_json", Text, nullable=True)
    _sources: Mapped[str | None] = mapped_column("sources_json", Text, nullable=True)

    trace: Mapped[Trace] = relationship("Trace", back_populates="entities")

    @property
    def aliases(self) -> list[str]:
        return json.loads(self._aliases) if self._aliases else []

    @aliases.setter
    def aliases(self, val: list[str]) -> None:
        self._aliases = json.dumps(val)

    @property
    def sources(self) -> list[str]:
        return json.loads(self._sources) if self._sources else []

    @sources.setter
    def sources(self, val: list[str]) -> None:
        self._sources = json.dumps(val)

    @property
    def category_badge_class(self) -> str:
        return {"adversary": "badge-red", "secrecy": "badge-yellow"}.get(
            self.jurisdiction_category or "", "badge-gray"
        )


class OwnershipLink(Base):
    __tablename__ = "ghosttrace_ownership_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trace_id: Mapped[int] = mapped_column(Integer, ForeignKey("ghosttrace_traces.id"))
    owner_name: Mapped[str] = mapped_column(String(300))
    owned_name: Mapped[str] = mapped_column(String(300))
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_accession: Mapped[str | None] = mapped_column(String(30), nullable=True)

    trace: Mapped[Trace] = relationship("Trace", back_populates="links")
