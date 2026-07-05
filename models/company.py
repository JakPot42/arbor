"""models/company.py — the shared entity every tool's records hang off of.

This is the actual point of the merge: GhostTrace's Trace, CFIUS's
Screening, DIB Monitor's Supplier, and the (still-to-be-added)
Pre-Acquisition Brief / Debt Exposure tables each get a `company_id`
ForeignKey to a row here instead of writing their own free-text
company-name column and hoping it lines up with the other four. See
shared/resolve_company.py for how a row here actually gets created or
matched — this module is only the shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Company(Base):
    """The canonical cross-tool entity. `cik` is the strongest join key
    when present (only 3 of the 5 source projects ever populate one, and
    2 of those only on a live/non-demo lookup) — `canonical_name` plus
    fuzzy resolution is the fallback every entity ends up needing at least
    some of the time. See shared/entity_resolver.py for the resolution
    logic and shared/resolve_company.py for how these fields get set.
    """

    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("cik", name="uq_companies_cik"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(300), index=True)
    # Nullable + unique: SQLite (and standard SQL) permit multiple NULLs
    # under a unique constraint, so companies with no known CIK yet
    # (CFIUS screenings, Pre-Acquisition Brief targets before an EDGAR
    # lookup) don't collide with each other.
    cik: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    _aliases: Mapped[str | None] = mapped_column("aliases_json", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    @property
    def aliases(self) -> list[str]:
        return json.loads(self._aliases) if self._aliases else []

    @aliases.setter
    def aliases(self, val: list[str]) -> None:
        self._aliases = json.dumps(val)

    def __repr__(self) -> str:  # pragma: no cover — debugging convenience only
        return f"<Company id={self.id} canonical_name={self.canonical_name!r} cik={self.cik}>"
