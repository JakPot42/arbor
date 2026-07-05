"""routers/brief.py — Pre-Acquisition Brief Generator, wrapped in a web
layer for the first time. The original was CLI-only (Click); this is
net-new work, not a port, per step 4 of the Arbor build sequence.

Every route lives under prefix="/brief". POST /brief/generate runs the
four-source pipeline (USPTO, CourtListener, EDGAR regulatory, USASpending)
in demo mode by default -- the live path's known EDGAR limitation (see
engines/brief_edgar_client.py's docstring) means live mode is offered but
not the default action, same caution the Arbor architecture review
flagged for both untested-live-path tools in this step.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from database import get_db
from engines.brief_contracts_client import build_contract_profile, fetch_awards
from engines.brief_courtlistener_client import build_litigation_profile, fetch_cases
from engines.brief_claude_generator import generate_brief
from engines.brief_edgar_client import build_regulatory_exposure, fetch_regulatory_data
from engines.brief_engine import build_brief
from engines.brief_uspto_client import build_ip_portfolio, fetch_patents
from models.brief import AcquisitionBrief
from shared.resolve_company import resolve_or_create_company
from shared.templates import templates

router = APIRouter(prefix="/brief")


def _run_pipeline(company: str, ticker: str, demo: bool):
    patents = fetch_patents(company, demo_mode=demo)
    cases = fetch_cases(company, demo_mode=demo)
    reg_raw = fetch_regulatory_data(company, ticker, demo_mode=demo)
    awards = fetch_awards(company, demo_mode=demo)

    ip = build_ip_portfolio(company, patents)
    lit = build_litigation_profile(company, cases)
    reg = build_regulatory_exposure(company, ticker, reg_raw)
    cont = build_contract_profile(company, awards)

    full_text, questions, summary = generate_brief(
        company, ticker, ip, lit, reg, cont, demo_mode=demo,
    )
    return build_brief(company, ticker, ip, lit, reg, cont, full_text, questions, summary)


def _to_dict(obj) -> dict:
    d = obj.__dict__.copy()
    for key, val in list(d.items()):
        if isinstance(val, list) and val and hasattr(val[0], "__dict__"):
            d[key] = [item.__dict__ for item in val]
    return d


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    briefs = db.query(AcquisitionBrief).order_by(AcquisitionBrief.created_at.desc()).all()
    return templates.TemplateResponse(request, "brief/index.html", {
        "briefs": briefs,
    })


@router.post("/generate", response_class=HTMLResponse)
def generate(
    request: Request,
    company: str = Form(...),
    ticker: str = Form(""),
    demo: bool = Form(True),
    db: Session = Depends(get_db),
):
    result = _run_pipeline(company, ticker, demo)

    resolution = resolve_or_create_company(db, result.company, ticker=ticker or None)

    row = AcquisitionBrief(
        company_id=resolution.company.id,
        company_name=result.company,
        ticker=result.ticker,
        prepared_date=result.prepared_date,
        ip_json=json.dumps(_to_dict(result.ip_portfolio)),
        litigation_json=json.dumps(_to_dict(result.litigation_profile)),
        regulatory_json=json.dumps(_to_dict(result.regulatory_exposure)),
        contract_json=json.dumps(_to_dict(result.contract_profile)),
        overall_risk_tier=result.overall_risk_tier,
        diligence_questions_json=json.dumps(result.diligence_questions),
        executive_summary=result.executive_summary,
        full_text=result.full_text,
        is_demo=demo,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return RedirectResponse(f"/brief/{row.id}", status_code=303)


@router.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    briefs = db.query(AcquisitionBrief).all()
    return {
        "status": "ok",
        "briefs": len(briefs),
        "demo_mode": any(b.is_demo for b in briefs),
    }


@router.get("/{brief_id}", response_class=HTMLResponse)
def brief_detail(request: Request, brief_id: int, db: Session = Depends(get_db)):
    row = db.get(AcquisitionBrief, brief_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Brief not found")

    return templates.TemplateResponse(request, "brief/detail.html", {
        "brief": row,
        "ip": json.loads(row.ip_json),
        "litigation": json.loads(row.litigation_json),
        "regulatory": json.loads(row.regulatory_json),
        "contract": json.loads(row.contract_json),
        "diligence_questions": json.loads(row.diligence_questions_json),
    })
