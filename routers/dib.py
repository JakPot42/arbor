"""routers/dib.py — DIB Monitor, ported from
dib_monitor/dib_monitor/main.py.

Every route moves under prefix="/dib" (fixes the real, exact route
collision found during the architecture review: DIB Monitor's own
`/api/stats` was byte-for-byte the same path CFIUS Screener already used
for a completely different response shape).

**Two real changes from the original, not just a port:**

1. `supplier_search()`'s duplicate check used to be a naive
   `Supplier.name.ilike(f"%{name}%")` substring match against DIB's own
   table — sloppy in both directions (misses real name variants, can
   false-match an unrelated supplier whose name happens to contain the
   search string as a substring). Replaced with
   `resolve_or_create_company()` + a precise `Supplier.company_id ==`
   lookup, which is what the shared Company table exists for.
2. Every place that discovers or backfills a CIK
   (`supplier_analyze`/`supplier_analyze_earnings`) now also backfills it
   onto the Company row via `resolve_or_create_company`, not just onto
   DIB's own `Supplier.cik`. DIB stores CIK as a zero-padded STRING
   (`models.dib.Supplier.cik`, matching the original); `Company.cik` is an
   int — converted at the boundary, not by changing either model's shape.
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from configs.dib import APP_TITLE
from config import ANTHROPIC_API_KEY, DEMO_MODE
from database import get_db
from engines.dib_claude_analyst import (
    AnalystError,
    extract_earnings_signals,
    extract_financials,
    generate_portfolio_brief,
)
from engines.dib_edgar_client import fetch_latest_10k_text, fetch_latest_8k_exhibit99, search_company_cik
from engines.dib_pdf_export import generate_resilience_pdf
from engines.dib_risk_engine import compute_combined_risk, compute_financial_risk, compute_ownership_risk
from engines.monte_carlo import run_gbm_distress
from models.dib import EarningsSignal, FinancialAssessment, OwnershipRecord, Supplier
from shared.resolve_company import resolve_or_create_company
from shared.templates import templates

router = APIRouter(prefix="/dib")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_latest_assessment(db: Session, supplier_id: int) -> Optional[FinancialAssessment]:
    return (
        db.query(FinancialAssessment)
        .filter(FinancialAssessment.supplier_id == supplier_id)
        .order_by(FinancialAssessment.id.desc())
        .first()
    )


def _get_owners(db: Session, assessment_id: int) -> list[OwnershipRecord]:
    return (
        db.query(OwnershipRecord)
        .filter(OwnershipRecord.assessment_id == assessment_id)
        .all()
    )


def _risk_color(level: str) -> str:
    return {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e74c3c", "CRITICAL": "#8e44ad"}.get(
        level or "", "#95a5a6"
    )


def _get_latest_earnings_signal(db: Session, supplier_id: int) -> Optional[EarningsSignal]:
    return (
        db.query(EarningsSignal)
        .filter(EarningsSignal.supplier_id == supplier_id)
        .order_by(EarningsSignal.id.desc())
        .first()
    )


def _backfill_company_cik(db: Session, supplier: Supplier, cik: str) -> None:
    """Push a newly-discovered CIK onto the shared Company row too, not
    just DIB's own Supplier.cik. Converts DIB's zero-padded string CIK to
    the int Company.cik expects."""
    if not supplier.company_id:
        return
    resolve_or_create_company(db, supplier.name, cik=int(cik), ticker=supplier.ticker)


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    suppliers = db.query(Supplier).order_by(Supplier.id).all()
    supplier_rows = []
    for s in suppliers:
        a = _get_latest_assessment(db, s.id)
        supplier_rows.append({
            "supplier": s,
            "assessment": a,
            "risk_color": _risk_color(a.combined_risk_level if a else None),
        })
    return templates.TemplateResponse(request, "dib/index.html", {
        "title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "supplier_rows": supplier_rows,
    })


_MAX_COMPANY_NAME_CHARS = 200

@router.post("/supplier/search")
def supplier_search(
    request: Request,
    company_name: str = Form(...),
    dib_category: str = Form("Tier 1 Subcontractor"),
    db: Session = Depends(get_db),
):
    name = company_name.strip()
    if not name:
        return RedirectResponse("/dib/", status_code=303)
    if len(name) > _MAX_COMPANY_NAME_CHARS:
        raise HTTPException(status_code=422, detail=f"Company name too long. Maximum {_MAX_COMPANY_NAME_CHARS} characters.")

    resolution = resolve_or_create_company(db, name)
    existing = db.query(Supplier).filter(Supplier.company_id == resolution.company.id).first()
    if existing:
        return RedirectResponse(f"/dib/supplier/{existing.id}", status_code=303)

    supplier = Supplier(company_id=resolution.company.id, name=name, dib_category=dib_category)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return RedirectResponse(f"/dib/supplier/{supplier.id}", status_code=303)


@router.get("/supplier/{supplier_id}", response_class=HTMLResponse)
def supplier_detail(request: Request, supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return HTMLResponse("Supplier not found.", status_code=404)

    assessment = _get_latest_assessment(db, supplier_id)
    owners = _get_owners(db, assessment.id) if assessment else []

    return templates.TemplateResponse(request, "dib/supplier.html", {
        "title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "supplier": supplier,
        "assessment": assessment,
        "owners": owners,
        "risk_color": _risk_color(assessment.combined_risk_level if assessment else None),
        "fin_risk_color": _risk_color(assessment.financial_risk_level if assessment else None),
        "own_risk_color": _risk_color(assessment.ownership_risk_level if assessment else None),
        "error": None,
    })


@router.post("/supplier/{supplier_id}/analyze")
def supplier_analyze(
    request: Request,
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return HTMLResponse("Supplier not found.", status_code=404)

    api_key = ANTHROPIC_API_KEY or None
    error_msg = None

    if DEMO_MODE and supplier.is_demo:
        # Demo suppliers already have pre-seeded assessments — skip live analysis
        return RedirectResponse(f"/dib/supplier/{supplier_id}", status_code=303)

    # Live analysis: EDGAR → Claude → Monte Carlo
    filing_text = None
    cik = supplier.cik
    if not cik:
        cik = search_company_cik(supplier.name)
        if cik:
            supplier.cik = cik
            db.commit()
            _backfill_company_cik(db, supplier, cik)

    if cik:
        filing_text = fetch_latest_10k_text(cik)

    extracted: dict = {}
    if filing_text and api_key:
        try:
            extracted = extract_financials(supplier.name, filing_text, api_key)
        except AnalystError as exc:
            error_msg = f"Claude extraction failed: {exc}"
    elif not api_key:
        error_msg = "ANTHROPIC_API_KEY not set — cannot run live analysis."
    elif not filing_text:
        error_msg = "Could not retrieve filing from SEC EDGAR."

    if error_msg:
        assessment_obj = _get_latest_assessment(db, supplier_id)
        owners = _get_owners(db, assessment_obj.id) if assessment_obj else []
        return templates.TemplateResponse(request, "dib/supplier.html", {
            "title": APP_TITLE,
            "demo_mode": DEMO_MODE,
            "supplier": supplier,
            "assessment": assessment_obj,
            "owners": owners,
            "risk_color": _risk_color(assessment_obj.combined_risk_level if assessment_obj else None),
            "fin_risk_color": _risk_color(assessment_obj.financial_risk_level if assessment_obj else None),
            "own_risk_color": _risk_color(assessment_obj.ownership_risk_level if assessment_obj else None),
            "error": error_msg,
        }, status_code=200)

    # Build assessment from extracted data
    ebitda = extracted.get("ebitda_mm")
    total_debt = extracted.get("total_debt_mm")
    debt_service = extracted.get("debt_service_annual_mm")
    near_term = extracted.get("near_term_maturity_mm")

    debt_to_ebitda = (total_debt / ebitda) if (ebitda and total_debt and ebitda > 0) else None

    # Monte Carlo
    mc = {}
    if ebitda and debt_service:
        mc = run_gbm_distress(
            current_ebitda_mm=ebitda,
            debt_service_annual_mm=debt_service,
        )

    # Risk scoring
    fin_score, fin_level = compute_financial_risk(
        debt_to_ebitda=debt_to_ebitda,
        distress_prob_1yr=mc.get("prob_1yr", 0),
        distress_prob_3yr=mc.get("prob_3yr", 0),
        going_concern_flag=extracted.get("going_concern_flag", False),
        near_term_maturity_mm=near_term,
    )
    own_score, own_level = compute_ownership_risk([])
    comb_score, comb_level = compute_combined_risk(fin_score, own_score)

    assessment = FinancialAssessment(
        supplier_id=supplier_id,
        filing_type="10-K",
        filing_period="Live",
        assessed_at=datetime.utcnow(),
        revenue_mm=extracted.get("revenue_mm"),
        total_debt_mm=total_debt,
        cash_mm=extracted.get("cash_mm"),
        ebitda_mm=ebitda,
        debt_service_annual_mm=debt_service,
        debt_to_ebitda=debt_to_ebitda,
        covenant_summary=extracted.get("covenant_summary"),
        going_concern_flag=extracted.get("going_concern_flag", False),
        going_concern_quote=extracted.get("going_concern_quote"),
        near_term_maturity_mm=near_term,
        near_term_maturity_date=extracted.get("near_term_maturity_date"),
        extraction_confidence=extracted.get("confidence", "low"),
        distress_prob_1yr=mc.get("prob_1yr"),
        distress_prob_2yr=mc.get("prob_2yr"),
        distress_prob_3yr=mc.get("prob_3yr"),
        financial_risk_score=fin_score,
        financial_risk_level=fin_level,
        ownership_risk_score=own_score,
        ownership_risk_level=own_level,
        combined_risk_score=comb_score,
        combined_risk_level=comb_level,
        claude_summary=None,
    )
    db.add(assessment)
    db.commit()

    return RedirectResponse(f"/dib/supplier/{supplier_id}", status_code=303)


@router.get("/supplier/{supplier_id}/report.pdf")
def supplier_pdf(supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return Response("Supplier not found.", status_code=404)

    assessment = _get_latest_assessment(db, supplier_id)
    if not assessment:
        return Response("No assessment found for this supplier.", status_code=404)

    owners = _get_owners(db, assessment.id)

    supplier_dict = {
        "name": supplier.name,
        "dib_category": supplier.dib_category,
        "sector": supplier.sector,
    }
    assessment_dict = {
        "assessed_at": str(assessment.assessed_at or datetime.utcnow()),
        "filing_period": assessment.filing_period,
        "revenue_mm": assessment.revenue_mm,
        "total_debt_mm": assessment.total_debt_mm,
        "cash_mm": assessment.cash_mm,
        "ebitda_mm": assessment.ebitda_mm,
        "debt_service_annual_mm": assessment.debt_service_annual_mm,
        "debt_to_ebitda": assessment.debt_to_ebitda,
        "covenant_summary": assessment.covenant_summary,
        "going_concern_flag": assessment.going_concern_flag,
        "going_concern_quote": assessment.going_concern_quote,
        "near_term_maturity_mm": assessment.near_term_maturity_mm,
        "near_term_maturity_date": assessment.near_term_maturity_date,
        "distress_prob_1yr": assessment.distress_prob_1yr or 0,
        "distress_prob_2yr": assessment.distress_prob_2yr or 0,
        "distress_prob_3yr": assessment.distress_prob_3yr or 0,
        "financial_risk_score": assessment.financial_risk_score,
        "financial_risk_level": assessment.financial_risk_level,
        "ownership_risk_score": assessment.ownership_risk_score,
        "ownership_risk_level": assessment.ownership_risk_level,
        "combined_risk_score": assessment.combined_risk_score,
        "combined_risk_level": assessment.combined_risk_level,
    }
    owners_list = [
        {
            "owner_name": o.owner_name,
            "pct_owned": o.pct_owned,
            "country": o.country,
            "cfius_flag": o.cfius_flag,
            "flag_reason": o.flag_reason,
        }
        for o in owners
    ]

    pdf_bytes = generate_resilience_pdf(supplier_dict, assessment_dict, owners_list, DEMO_MODE)
    filename = f"DIB_Resilience_{supplier.name.replace(' ', '_')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    return {
        "suppliers": db.query(Supplier).count(),
        "assessments": db.query(FinancialAssessment).count(),
        "high_risk": db.query(FinancialAssessment).filter(
            FinancialAssessment.combined_risk_level.in_(["HIGH", "CRITICAL"])
        ).count(),
        "cfius_flags": db.query(OwnershipRecord).filter(OwnershipRecord.cfius_flag.is_(True)).count(),
        "earnings_signals": db.query(EarningsSignal).count(),
        "demo_mode": DEMO_MODE,
    }


# ── Earnings signal routes ────────────────────────────────────────────────────

@router.get("/supplier/{supplier_id}/earnings", response_class=HTMLResponse)
def supplier_earnings(request: Request, supplier_id: int, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return HTMLResponse("Supplier not found.", status_code=404)

    signal = _get_latest_earnings_signal(db, supplier_id)
    signals_list = []
    if signal and signal.signals_json:
        import json
        try:
            signals_list = json.loads(signal.signals_json)
        except Exception:
            signals_list = []

    return templates.TemplateResponse(request, "dib/earnings.html", {
        "title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "supplier": supplier,
        "signal": signal,
        "signals_list": signals_list,
        "error": None,
    })


@router.post("/supplier/{supplier_id}/analyze-earnings")
def supplier_analyze_earnings(
    request: Request,
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        return HTMLResponse("Supplier not found.", status_code=404)

    if DEMO_MODE and supplier.is_demo:
        return RedirectResponse(f"/dib/supplier/{supplier_id}/earnings", status_code=303)

    api_key = ANTHROPIC_API_KEY or None
    error_msg = None

    # Fetch 8-K Exhibit 99 from EDGAR
    cik = supplier.cik
    if not cik:
        cik = search_company_cik(supplier.name)
        if cik:
            supplier.cik = cik
            db.commit()
            _backfill_company_cik(db, supplier, cik)

    exhibit_data = None
    if cik:
        exhibit_data = fetch_latest_8k_exhibit99(cik)

    extracted: dict = {}
    if exhibit_data and api_key:
        try:
            extracted = extract_earnings_signals(supplier.name, exhibit_data["text"], api_key)
        except AnalystError as exc:
            error_msg = f"Claude extraction failed: {exc}"
    elif not api_key:
        error_msg = "ANTHROPIC_API_KEY not set — cannot run live analysis."
    elif not exhibit_data:
        error_msg = "Could not retrieve 8-K Exhibit 99 from SEC EDGAR."

    if error_msg:
        signal = _get_latest_earnings_signal(db, supplier_id)
        signals_list = []
        if signal and signal.signals_json:
            import json
            try:
                signals_list = json.loads(signal.signals_json)
            except Exception:
                pass
        return templates.TemplateResponse(request, "dib/earnings.html", {
            "title": APP_TITLE,
            "demo_mode": DEMO_MODE,
            "supplier": supplier,
            "signal": signal,
            "signals_list": signals_list,
            "error": error_msg,
        }, status_code=200)

    import json
    new_signal = EarningsSignal(
        supplier_id=supplier_id,
        filing_date=exhibit_data.get("filed_date"),
        accession_number=exhibit_data.get("accession"),
        signals_json=json.dumps(extracted.get("signals", [])),
        export_control_flag=extracted.get("export_control_flag", False),
        supplier_diversion_flag=extracted.get("supplier_diversion_flag", False),
        key_quote=extracted.get("key_quote"),
        claude_brief=None,
        extraction_confidence=extracted.get("confidence", "low"),
    )
    db.add(new_signal)
    db.commit()

    return RedirectResponse(f"/dib/supplier/{supplier_id}/earnings", status_code=303)


# ── Portfolio routes ──────────────────────────────────────────────────────────

def _build_portfolio_rows(db: Session) -> list[dict]:
    """Build data rows for all tracked suppliers with assessments."""
    suppliers = db.query(Supplier).order_by(Supplier.id).all()
    rows = []
    for s in suppliers:
        assessment = _get_latest_assessment(db, s.id)
        signal = _get_latest_earnings_signal(db, s.id)

        cfius_count = 0
        if assessment:
            cfius_count = (
                db.query(OwnershipRecord)
                .filter(
                    OwnershipRecord.assessment_id == assessment.id,
                    OwnershipRecord.cfius_flag.is_(True),
                )
                .count()
            )

        earnings_signals = []
        if signal and signal.signals_json:
            import json
            try:
                earnings_signals = json.loads(signal.signals_json)
            except Exception:
                pass

        rows.append({
            "supplier": s,
            "assessment": assessment,
            "signal": signal,
            "cfius_count": cfius_count,
            "earnings_signals": earnings_signals,
            "risk_color": _risk_color(assessment.combined_risk_level if assessment else None),
        })
    return rows


@router.get("/portfolio", response_class=HTMLResponse)
def portfolio_view(request: Request, db: Session = Depends(get_db)):
    rows = _build_portfolio_rows(db)
    total = len(rows)
    assessed = sum(1 for r in rows if r["assessment"])
    high_critical = sum(
        1 for r in rows
        if r["assessment"] and r["assessment"].combined_risk_level in ("HIGH", "CRITICAL")
    )
    cfius_total = sum(r["cfius_count"] for r in rows)
    earnings_total = sum(1 for r in rows if r["signal"])

    return templates.TemplateResponse(request, "dib/portfolio.html", {
        "title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "rows": rows,
        "total": total,
        "assessed": assessed,
        "high_critical": high_critical,
        "cfius_total": cfius_total,
        "earnings_total": earnings_total,
        "brief": None,
        "error": None,
    })


@router.post("/portfolio/brief", response_class=HTMLResponse)
def portfolio_brief(request: Request, db: Session = Depends(get_db)):
    rows = _build_portfolio_rows(db)
    total = len(rows)
    assessed = sum(1 for r in rows if r["assessment"])
    high_critical = sum(
        1 for r in rows
        if r["assessment"] and r["assessment"].combined_risk_level in ("HIGH", "CRITICAL")
    )
    cfius_total = sum(r["cfius_count"] for r in rows)
    earnings_total = sum(1 for r in rows if r["signal"])

    api_key = ANTHROPIC_API_KEY or None
    brief = None
    error_msg = None

    if not api_key:
        error_msg = "ANTHROPIC_API_KEY not set — cannot generate portfolio brief."
    else:
        assessed_rows = [r for r in rows if r["assessment"]]
        portfolio_data = [
            {
                "name": r["supplier"].name,
                "dib_category": r["supplier"].dib_category,
                "sector": r["supplier"].sector,
                "combined_risk_level": r["assessment"].combined_risk_level,
                "financial_risk_score": r["assessment"].financial_risk_score,
                "ownership_risk_score": r["assessment"].ownership_risk_score,
                "distress_prob_1yr": r["assessment"].distress_prob_1yr,
                "distress_prob_3yr": r["assessment"].distress_prob_3yr,
                "cfius_flag_count": r["cfius_count"],
                "earnings_signals": r["earnings_signals"],
            }
            for r in assessed_rows
        ]
        try:
            brief = generate_portfolio_brief(portfolio_data, api_key)
        except AnalystError as exc:
            error_msg = f"Claude failed to generate portfolio brief: {exc}"

    return templates.TemplateResponse(request, "dib/portfolio.html", {
        "title": APP_TITLE,
        "demo_mode": DEMO_MODE,
        "rows": rows,
        "total": total,
        "assessed": assessed,
        "high_critical": high_critical,
        "cfius_total": cfius_total,
        "earnings_total": earnings_total,
        "brief": brief,
        "error": error_msg,
    })
