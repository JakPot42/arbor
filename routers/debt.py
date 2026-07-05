"""routers/debt.py — Debt Exposure Monitor, wrapped in a web layer for the
first time. The original was CLI-only (Click); this is net-new work, not
a port, per step 4 of the Arbor build sequence.

Every route lives under prefix="/debt". A single POST /debt/screen runs
the whole pipeline (EDGAR fetch -> Claude extraction -> dedupe -> OFAC/
BIS/foreign-state screening -> risk score -> brief) in one action and
persists one DebtProfile row -- matching the original CLI's own `screen`
command, which did all of this in a single invocation with no separate
confirmation step (unlike CFIUS's intake/confirm flow, there's no
user-supplied fact here that needs a human check before rules run; every
fact comes from a public filing or a deterministic checker).
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from engines.debt_pipeline import AmbiguousCompanyError, CompanyNotFoundError, build_profile
from engines.debt_risk_brief import generate_brief
from engines.debt_risk_engine import score_debt_profile
from engines.debt_screening import screen_lenders
from models.debt import DebtProfile
from shared.resolve_company import resolve_or_create_company
from shared.templates import templates

router = APIRouter(prefix="/debt")


def _dashboard_rows(db: Session) -> list[dict]:
    profiles = db.query(DebtProfile).order_by(DebtProfile.created_at.desc()).all()
    return [
        {"profile": p, "risk": json.loads(p.risk_score_json) if p.risk_score_json else None}
        for p in profiles
    ]


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "debt/index.html", {
        "rows": _dashboard_rows(db),
    })


@router.post("/screen", response_class=HTMLResponse)
def screen(request: Request, company_query: str = Form(...), db: Session = Depends(get_db)):
    try:
        profile = build_profile(company_query)
    except CompanyNotFoundError as exc:
        return templates.TemplateResponse(request, "debt/index.html", {
            "rows": _dashboard_rows(db),
            "screen_error": str(exc),
        })
    except AmbiguousCompanyError as exc:
        return templates.TemplateResponse(request, "debt/index.html", {
            "rows": _dashboard_rows(db),
            "screen_error": str(exc),
            "candidates": exc.candidates,
        })

    risk = score_debt_profile(profile)
    brief_text = generate_brief(profile, risk)

    resolution = resolve_or_create_company(db, profile.company_name, cik=profile.cik)

    row = DebtProfile(
        company_id=resolution.company.id,
        company_name=profile.company_name,
        cik=profile.cik,
        lenders_json=json.dumps([l.__dict__ for l in profile.lenders]),
        screening_hits_json=json.dumps([h.__dict__ for h in profile.screening_hits]),
        trace_available=profile.trace_available,
        trace_note=profile.trace_note,
        risk_score_json=json.dumps(risk),
        brief_text=brief_text,
        is_demo=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return RedirectResponse(f"/debt/profile/{row.id}", status_code=303)


@router.get("/profile/{profile_id}", response_class=HTMLResponse)
def profile_detail(request: Request, profile_id: int, db: Session = Depends(get_db)):
    row = db.get(DebtProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Debt profile not found")

    return templates.TemplateResponse(request, "debt/profile.html", {
        "profile": row,
        "lenders": json.loads(row.lenders_json),
        "screening_hits": json.loads(row.screening_hits_json),
        "risk": json.loads(row.risk_score_json) if row.risk_score_json else None,
    })


@router.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    profiles = db.query(DebtProfile).all()
    return {
        "status": "ok",
        "profiles": len(profiles),
        "demo_mode": any(p.is_demo for p in profiles),
    }
