"""routers/cfius.py — CFIUS Screener, ported from cfius_screener/main.py.

Every route moves under prefix="/cfius" (fixes the real route collisions
found during the architecture review: bare `/` and `/api/stats` both
collided with GhostTrace's and DIB Monitor's own root-level routes).
Templates render from the shared templates/ root under a `cfius/`
subdirectory. The engine layer is unchanged — this file is glue between
HTTP and engines.cfius_*, exactly as the original main.py was glue between
HTTP and its own jurisdiction_engine/screening_service.

**One addition from the original, not just a port:** screen_submit() and
intake_confirm() both call resolve_or_create_company() on the US business
name before run_and_store() — CFIUS's schema never had a cross-tool join
key before this.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from configs.cfius import (
    APP_TITLE,
    CRITICAL_INFRASTRUCTURE_EXAMPLES,
    DECLARATION_ASSESSMENT_DAYS,
    DEMO_BANNER,
    NOTICE_INVESTIGATION_DAYS,
    NOTICE_REVIEW_DAYS,
    SENSITIVE_DATA_CATEGORIES,
    VERIFICATION_DISCLAIMER,
)
from config import DEMO_MODE
from database import get_db
from engines.cfius_claude_intake import IntakeError, parse_deal_description
from engines.cfius_claude_memo import MemoError, draft_memo
from engines.cfius_pdf_export import render_memo_pdf
from engines.jurisdiction_engine import TransactionFacts
from engines.cfius_screening_service import (
    findings_of,
    mandatory_reasons_of,
    ofac_hits_of,
    risk_score_of,
    run_and_store,
    tid_categories_of,
)
from models.cfius import Screening
from shared.ofac_checker import screen_entities
from shared.rate_limit import limiter
from shared.resolve_company import resolve_or_create_company
from shared.templates import templates

router = APIRouter(prefix="/cfius")

OUTCOME_LABELS = {
    "NOT_COVERED": "Not a covered transaction",
    "COVERED_VOLUNTARY": "Covered — voluntary filing available",
    "MANDATORY_DECLARATION": "Mandatory declaration required",
}


def _template(request: Request, name: str, ctx: dict) -> HTMLResponse:
    ctx.update({
        "app_title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "demo_banner": DEMO_BANNER,
        "disclaimer": VERIFICATION_DISCLAIMER,
        "outcome_labels": OUTCOME_LABELS,
    })
    return templates.TemplateResponse(request, f"cfius/{name}", ctx)


def _facts_from_form(
    us_business_name: str,
    us_business_description: str,
    acquirer_name: str,
    acquirer_country: str,
    foreign_govt_ownership_pct: float,
    voting_interest_pct: float,
    contractual_control_rights: Optional[str],
    board_seat: Optional[str],
    board_observer: Optional[str],
    access_nonpublic_tech_info: Optional[str],
    substantive_decision_role: Optional[str],
    produces_critical_tech: Optional[str],
    export_authorization_required: Optional[str],
    critical_infrastructure: Optional[str],
    sensitive_personal_data: Optional[str],
) -> TransactionFacts:
    us_business_name = us_business_name.strip()
    acquirer_name = acquirer_name.strip()
    acquirer_country = acquirer_country.strip()
    if not (us_business_name and acquirer_name and acquirer_country):
        raise HTTPException(status_code=422, detail="Names and country are required.")

    return TransactionFacts(
        us_business_name=us_business_name,
        us_business_description=us_business_description.strip(),
        acquirer_name=acquirer_name,
        acquirer_country=acquirer_country,
        foreign_govt_ownership_pct=foreign_govt_ownership_pct,
        voting_interest_pct=voting_interest_pct,
        contractual_control_rights=contractual_control_rights is not None,
        board_seat=board_seat is not None,
        board_observer=board_observer is not None,
        access_nonpublic_tech_info=access_nonpublic_tech_info is not None,
        substantive_decision_role=substantive_decision_role is not None,
        produces_critical_tech=produces_critical_tech is not None,
        export_authorization_required=export_authorization_required is not None,
        critical_infrastructure=critical_infrastructure is not None,
        sensitive_personal_data=sensitive_personal_data is not None,
    )


# ---------------------------------------------------------------------------
# Dashboard — recent screenings
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    screenings = (
        db.query(Screening).order_by(Screening.created_at.desc()).limit(25).all()
    )
    return _template(request, "index.html", {"screenings": screenings})


# ---------------------------------------------------------------------------
# New screening — structured fact form
# ---------------------------------------------------------------------------

@router.get("/screen", response_class=HTMLResponse)
def screen_form(request: Request):
    return _template(request, "screen_form.html", {
        "infra_examples": CRITICAL_INFRASTRUCTURE_EXAMPLES,
        "data_categories": SENSITIVE_DATA_CATEGORIES,
    })


@router.post("/screen", response_class=HTMLResponse)
def screen_submit(
    request: Request,
    db: Session = Depends(get_db),
    us_business_name: str = Form(...),
    us_business_description: str = Form(""),
    acquirer_name: str = Form(...),
    acquirer_country: str = Form(...),
    foreign_govt_ownership_pct: float = Form(0.0),
    voting_interest_pct: float = Form(0.0),
    contractual_control_rights: Optional[str] = Form(None),
    board_seat: Optional[str] = Form(None),
    board_observer: Optional[str] = Form(None),
    access_nonpublic_tech_info: Optional[str] = Form(None),
    substantive_decision_role: Optional[str] = Form(None),
    produces_critical_tech: Optional[str] = Form(None),
    export_authorization_required: Optional[str] = Form(None),
    critical_infrastructure: Optional[str] = Form(None),
    sensitive_personal_data: Optional[str] = Form(None),
):
    facts = _facts_from_form(
        us_business_name, us_business_description, acquirer_name, acquirer_country,
        foreign_govt_ownership_pct, voting_interest_pct, contractual_control_rights,
        board_seat, board_observer, access_nonpublic_tech_info, substantive_decision_role,
        produces_critical_tech, export_authorization_required, critical_infrastructure,
        sensitive_personal_data,
    )
    resolution = resolve_or_create_company(db, facts.us_business_name)
    row = run_and_store(db, facts, company_id=resolution.company.id)
    return RedirectResponse(f"/cfius/screening/{row.id}", status_code=303)


# ---------------------------------------------------------------------------
# Screening result — determination + findings trail
# ---------------------------------------------------------------------------

@router.get("/screening/{screening_id}", response_class=HTMLResponse)
def screening_detail(
    request: Request,
    screening_id: int,
    db: Session = Depends(get_db),
    memo_error: str = Query(default=""),
    ofac_error: str = Query(default=""),
):
    row = db.get(Screening, screening_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Screening not found.")
    return _template(request, "result.html", {
        "s": row,
        "findings": findings_of(row),
        "tid_categories": tid_categories_of(row),
        "mandatory_reasons": mandatory_reasons_of(row),
        "risk_score": risk_score_of(row),
        "ofac_hits": ofac_hits_of(row),
        "declaration_days": DECLARATION_ASSESSMENT_DAYS,
        "review_days": NOTICE_REVIEW_DAYS,
        "investigation_days": NOTICE_INVESTIGATION_DAYS,
        "memo_error": memo_error,
        "ofac_error": ofac_error,
    })


# ---------------------------------------------------------------------------
# Intake — plain-English description → Claude parse → human confirm → engine
# ---------------------------------------------------------------------------

@router.get("/intake", response_class=HTMLResponse)
def intake_form(request: Request):
    return _template(request, "intake_form.html", {})


_MAX_INTAKE_CHARS = 5_000

@router.post("/intake", response_class=HTMLResponse)
@limiter.limit("10/minute")
def intake_parse(
    request: Request,
    description: str = Form(...),
):
    """Claude parses the description. Renders confirm screen — nothing is stored."""
    description = description.strip()
    if len(description) > _MAX_INTAKE_CHARS:
        return _template(request, "intake_form.html", {
            "error": f"Description too long ({len(description):,} chars). Maximum is {_MAX_INTAKE_CHARS:,} characters.",
            "description": description[:200],
        })
    try:
        proposed = parse_deal_description(description)
    except IntakeError as exc:
        return _template(request, "intake_form.html", {
            "error": str(exc),
            "description": description,
        })
    return _template(request, "intake_confirm.html", {
        "proposed": proposed,
        "description": description,
        "infra_examples": CRITICAL_INFRASTRUCTURE_EXAMPLES,
        "data_categories": SENSITIVE_DATA_CATEGORIES,
    })


@router.post("/intake/confirm", response_class=HTMLResponse)
def intake_confirm(
    request: Request,
    db: Session = Depends(get_db),
    intake_description: str = Form(""),
    us_business_name: str = Form(...),
    us_business_description: str = Form(""),
    acquirer_name: str = Form(...),
    acquirer_country: str = Form(...),
    foreign_govt_ownership_pct: float = Form(0.0),
    voting_interest_pct: float = Form(0.0),
    contractual_control_rights: Optional[str] = Form(None),
    board_seat: Optional[str] = Form(None),
    board_observer: Optional[str] = Form(None),
    access_nonpublic_tech_info: Optional[str] = Form(None),
    substantive_decision_role: Optional[str] = Form(None),
    produces_critical_tech: Optional[str] = Form(None),
    export_authorization_required: Optional[str] = Form(None),
    critical_infrastructure: Optional[str] = Form(None),
    sensitive_personal_data: Optional[str] = Form(None),
):
    """User has confirmed (or adjusted) Claude's proposed facts. Run the engine."""
    facts = _facts_from_form(
        us_business_name, us_business_description, acquirer_name, acquirer_country,
        foreign_govt_ownership_pct, voting_interest_pct, contractual_control_rights,
        board_seat, board_observer, access_nonpublic_tech_info, substantive_decision_role,
        produces_critical_tech, export_authorization_required, critical_infrastructure,
        sensitive_personal_data,
    )
    resolution = resolve_or_create_company(db, facts.us_business_name)
    row = run_and_store(
        db, facts, intake_description=intake_description, company_id=resolution.company.id,
    )
    return RedirectResponse(f"/cfius/screening/{row.id}", status_code=303)


# ---------------------------------------------------------------------------
# Memo — generate via Claude, download as PDF
# ---------------------------------------------------------------------------

@router.post("/screening/{screening_id}/memo")
def generate_memo(screening_id: int, db: Session = Depends(get_db)):
    row = db.get(Screening, screening_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Screening not found.")
    try:
        row.memo_text = draft_memo(row)
        db.commit()
    except MemoError:
        return RedirectResponse(
            f"/cfius/screening/{screening_id}?memo_error=1", status_code=303
        )
    return RedirectResponse(f"/cfius/screening/{screening_id}", status_code=303)


@router.get("/screening/{screening_id}/memo.pdf")
def memo_pdf(screening_id: int, db: Session = Depends(get_db)):
    row = db.get(Screening, screening_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Screening not found.")
    if not row.memo_text:
        raise HTTPException(status_code=404, detail="No memo generated yet.")
    pdf_bytes = render_memo_pdf(row, row.memo_text)
    filename = f"cfius_memo_{screening_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# OFAC SDN screening — on-demand, acquirer name only
# ---------------------------------------------------------------------------

@router.post("/screening/{screening_id}/ofac-screen")
def ofac_screen(screening_id: int, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    import json

    row = db.get(Screening, screening_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Screening not found.")
    try:
        hits = screen_entities([row.acquirer_name])
        row.ofac_hits_json = json.dumps([h._asdict() for h in hits])
        row.ofac_checked_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        return RedirectResponse(
            f"/cfius/screening/{screening_id}?ofac_error=1", status_code=303
        )
    return RedirectResponse(f"/cfius/screening/{screening_id}", status_code=303)


# ---------------------------------------------------------------------------
# JSON health/stats
# ---------------------------------------------------------------------------

@router.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    total = db.query(Screening).count()
    by_outcome = {
        outcome: db.query(Screening).filter(Screening.outcome == outcome).count()
        for outcome in OUTCOME_LABELS
    }
    return JSONResponse({"status": "ok", "screenings": total, "by_outcome": by_outcome})
