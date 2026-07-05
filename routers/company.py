"""routers/company.py — the entity-centric view. This is the actual
deliverable of the Arbor merger: search a company once, see its status
across every tool from one page, each card backed by a real query against
that tool's own tables via the shared Company.id foreign key.

Two routes:
  GET /            -- search box + recently-touched companies
  POST /search      -- read-only fuzzy lookup (shared.resolve_company.find_companies,
                       never resolve_or_create_company -- a search must never
                       create a company)
  GET /company/{id} -- the fan-out page: one card per tool, each either
                       showing that tool's real latest data for this
                       company or an honest "not yet analyzed" state with
                       a link to go analyze it.

Step 4 wired in the final two sources (Debt Exposure Monitor,
Pre-Acquisition Brief Generator) -- all five Arbor sources now have a
real card on this page.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from engines.cfius_screening_service import risk_score_of as cfius_risk_score_of
from models.brief import AcquisitionBrief
from models.cfius import Screening
from models.company import Company
from models.debt import DebtProfile
from models.dib import FinancialAssessment, Supplier
from models.ghosttrace import Trace
from shared.resolve_company import find_companies
from shared.templates import templates

router = APIRouter()


def _template(request: Request, name: str, ctx: dict) -> HTMLResponse:
    ctx.update({"app_title": "Arbor"})
    return templates.TemplateResponse(request, f"company/{name}", ctx)


def _recent_companies(db: Session, limit: int = 10) -> list[Company]:
    return db.query(Company).order_by(Company.created_at.desc()).limit(limit).all()


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return _template(request, "company_search.html", {
        "recent_companies": _recent_companies(db),
    })


@router.post("/search", response_class=HTMLResponse)
def search(request: Request, query: str = Form(...), db: Session = Depends(get_db)):
    query = query.strip()
    if not query:
        return RedirectResponse("/", status_code=303)

    matches = find_companies(db, query)
    if not matches:
        return _template(request, "company_search.html", {
            "recent_companies": _recent_companies(db),
            "search_error": f"No company matching '{query}' has been analyzed by any tool yet.",
            "query": query,
        })

    # A single strong (auto-merge-band) match skips disambiguation --
    # same UX rule GhostTrace's own /search uses for an exact ticker hit.
    best_company, best_score = matches[0]
    if len(matches) == 1 or best_score >= 90.0:
        return RedirectResponse(f"/company/{best_company.id}", status_code=303)

    return _template(request, "company_search.html", {
        "recent_companies": _recent_companies(db),
        "candidates": matches,
        "query": query,
    })


@router.get("/company/{company_id}", response_class=HTMLResponse)
def company_detail(request: Request, company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    traces = (
        db.query(Trace)
        .filter_by(company_id=company.id)
        .order_by(Trace.created_at.desc())
        .all()
    )
    screenings = (
        db.query(Screening)
        .filter_by(company_id=company.id)
        .order_by(Screening.created_at.desc())
        .all()
    )
    supplier = db.query(Supplier).filter_by(company_id=company.id).first()
    assessment = None
    if supplier is not None:
        assessment = (
            db.query(FinancialAssessment)
            .filter_by(supplier_id=supplier.id)
            .order_by(FinancialAssessment.id.desc())
            .first()
        )

    latest_screening = screenings[0] if screenings else None

    debt_profiles = (
        db.query(DebtProfile)
        .filter_by(company_id=company.id)
        .order_by(DebtProfile.created_at.desc())
        .all()
    )
    latest_debt_profile = debt_profiles[0] if debt_profiles else None
    latest_debt_risk = (
        json.loads(latest_debt_profile.risk_score_json)
        if latest_debt_profile and latest_debt_profile.risk_score_json
        else None
    )

    briefs = (
        db.query(AcquisitionBrief)
        .filter_by(company_id=company.id)
        .order_by(AcquisitionBrief.created_at.desc())
        .all()
    )
    latest_brief = briefs[0] if briefs else None

    return _template(request, "company_detail.html", {
        "company": company,
        "latest_trace": traces[0] if traces else None,
        "trace_count": len(traces),
        "latest_screening": latest_screening,
        "screening_count": len(screenings),
        "screening_risk": cfius_risk_score_of(latest_screening) if latest_screening else None,
        "supplier": supplier,
        "assessment": assessment,
        "latest_debt_profile": latest_debt_profile,
        "debt_profile_count": len(debt_profiles),
        "latest_debt_risk": latest_debt_risk,
        "latest_brief": latest_brief,
        "brief_count": len(briefs),
    })
