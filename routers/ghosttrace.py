"""routers/ghosttrace.py — GhostTrace, ported from ghosttrace/main.py.

Every route moves under prefix="/ghosttrace" (fixes the route collision:
bare `/` collided with CFIUS's and DIB Monitor's own root routes).

**One real, pre-existing bug fixed during this port, not preserved
verbatim:** the original `run_trace()`'s live-fetch path called
`get_filing_documents()` (which returns `list[str]` of filenames) and then
indexed the result as `d["name"]` / `docs[0]["name"]` — a `TypeError`
waiting to happen the first time a live trace actually reached that code
path. This was a KNOWN, self-documented issue in ghosttrace's own
CLAUDE.md ("Known limitations": "`get_filing_documents()` returns
`list[str]`... The `main.py` orchestrator has a pre-existing `d["name"]`
call that would fail on live traces... `deep_trace.py` uses the correct
`list[str]` API."). deep_trace.py (engines/deep_trace.py, already ported)
demonstrates the correct usage right next to this bug. Since this exact
line had to be touched anyway (get_target_filings -> get_ownership_filings
rename), fixed here rather than knowingly porting a self-documented defect
into new code.

**One addition from the original:** run_trace() resolves the company
against the shared Company table via resolve_or_create_company(name,
cik=cik) — GhostTrace already has the exact EDGAR CIK at this point, the
strongest possible join key.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from configs.ghosttrace import (
    APP_TITLE,
    DEEP_TRACE_MAX_TOOL_CALLS,
    DEMO_BANNER,
    GRAPH_OUTPUT_DIR,
    RISK_WEIGHT_OFAC_CANDIDATE,
)
from config import DEMO_MODE
from database import get_db
from engines.deep_trace import run_deep_trace
from engines.ghosttrace_claude_extractor import ExtractorError, extract_entities, generate_risk_report
from engines.ghosttrace_entity_resolver import resolve_entities, rewrite_links
from engines.ghosttrace_graph_builder import build_graph_png
from engines.ghosttrace_risk_engine import assess, jurisdiction_category
from engines.ghosttrace_seed_data import load_seed_data
from engines.ghosttrace_vector_store import get_store
from models.ghosttrace import Entity, Filing, OwnershipLink, Trace
from shared.edgar_client import (
    fetch_document_text,
    find_exhibit_21,
    get_company_candidates,
    get_filing_documents,
    get_ownership_filings,
)
from shared.entity_resolver import normalize_name
from shared.ofac_checker import screen_entities as ofac_screen
from shared.resolve_company import resolve_or_create_company
from shared.templates import templates

router = APIRouter(prefix="/ghosttrace")


def _template(request: Request, name: str, ctx: dict) -> HTMLResponse:
    ctx.update({"app_title": APP_TITLE, "demo_mode": DEMO_MODE, "demo_banner": DEMO_BANNER})
    return templates.TemplateResponse(request, f"ghosttrace/{name}", ctx)


# ---------------------------------------------------------------------------
# Home — company search
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    recent = db.query(Trace).order_by(Trace.created_at.desc()).limit(10).all()
    return _template(request, "index.html", {"recent_traces": recent})


# ---------------------------------------------------------------------------
# Company search — returns candidate list or redirects directly
# ---------------------------------------------------------------------------

@router.post("/search", response_class=HTMLResponse)
def search(request: Request, query: str = Form(...), db: Session = Depends(get_db)):
    query = query.strip()
    if not query:
        return RedirectResponse("/ghosttrace/", status_code=303)
    candidates = get_company_candidates(query)
    if not candidates:
        return _template(request, "index.html", {
            "recent_traces": db.query(Trace).order_by(Trace.created_at.desc()).limit(10).all(),
            "search_error": f"No SEC registrants found for '{query}'.",
            "query": query,
        })
    # Exact ticker match → skip disambiguation
    exact = next((c for c in candidates if c.get("ticker", "").upper() == query.upper()), None)
    if exact and len(candidates) == 1:
        return RedirectResponse(f"/ghosttrace/trace?cik={exact['cik']}&name={exact['name']}", status_code=303)
    return _template(request, "index.html", {
        "recent_traces": db.query(Trace).order_by(Trace.created_at.desc()).limit(10).all(),
        "candidates": candidates,
        "query": query,
    })


# ---------------------------------------------------------------------------
# Live trace — fetch EDGAR filings, extract, score, store
# ---------------------------------------------------------------------------

@router.get("/trace", response_class=HTMLResponse)
def run_trace(
    request: Request,
    cik: int,
    name: str,
    db: Session = Depends(get_db),
):
    # Check for existing non-demo trace for this CIK
    existing = db.query(Trace).filter_by(cik=cik, is_demo=False).order_by(
        Trace.created_at.desc()
    ).first()
    if existing:
        return RedirectResponse(f"/ghosttrace/trace/{existing.id}", status_code=303)

    filings = get_ownership_filings(cik)
    if not filings:
        return _template(request, "index.html", {
            "recent_traces": db.query(Trace).order_by(Trace.created_at.desc()).limit(10).all(),
            "search_error": f"No relevant SEC filings found for '{name}' (CIK {cik}).",
            "query": name,
        })

    # Fetch and extract from each filing
    raw_entities: list[dict] = []
    raw_links: list[dict] = []

    for filing in filings:
        acc = filing["accession_number"]
        form = filing["form"]
        date = filing["filing_date"]

        doc_names = get_filing_documents(cik, acc)
        # For 10-K, prefer Exhibit 21; for others, take the first substantive doc.
        # doc_names is list[str] -- indexed directly, not as dicts (see module
        # docstring: this is the fixed version of a known pre-existing bug).
        if form == "10-K":
            doc_name = find_exhibit_21(doc_names)
            if not doc_name and doc_names:
                doc_name = doc_names[0]
        else:
            doc_name = doc_names[0] if doc_names else None

        if not doc_name:
            continue

        # Filing cache: SQLite first, EDGAR only on a miss. Fetched documents
        # are stored (citations need them anyway) and indexed for search.
        cached = db.query(Filing).filter_by(
            accession_number=acc, document_name=doc_name
        ).first()
        if cached:
            text = cached.text
        else:
            text = fetch_document_text(cik, acc, doc_name)
            if text:
                db.add(Filing(
                    cik=cik, accession_number=acc, document_name=doc_name,
                    form=form, filing_date=date, text=text,
                ))
                db.commit()
                try:
                    get_store().add_filing(
                        accession_number=acc, document_name=doc_name,
                        form=form, filing_date=date, cik=cik, text=text,
                    )
                except Exception:
                    pass
        if not text:
            continue

        try:
            extracted = extract_entities(text, form, date)
        except ExtractorError:
            continue

        for e in extracted.get("entities", []):
            e["sources"] = [acc]
            raw_entities.append(e)
        for link in extracted.get("relationships", []):
            link["source"] = acc
            raw_links.append(link)

    if not raw_entities:
        return _template(request, "index.html", {
            "recent_traces": db.query(Trace).order_by(Trace.created_at.desc()).limit(10).all(),
            "search_error": f"Could not extract ownership data for '{name}'. Filings may be in an unsupported format.",
            "query": name,
        })

    # Resolve entity name variants, rewire links
    def _adjudicator(a: str, b: str) -> bool:
        from engines.ghosttrace_claude_extractor import adjudicate_match
        try:
            return adjudicate_match(a, b)["same_entity"]
        except ExtractorError:
            return False

    resolved, alias_map = resolve_entities(raw_entities, adjudicator=_adjudicator)
    links = rewrite_links(raw_links, alias_map)

    # Score
    result = assess(resolved, links, name)

    # OFAC SDN screening — runs after structural scoring; adds candidate findings
    ofac_hits: list[dict] = []
    ofac_checked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        entity_names = [e["canonical_name"] for e in resolved]
        raw_hits = ofac_screen(entity_names)
        for hit in raw_hits:
            ofac_hits.append(hit._asdict())
            result["findings"].append({
                "rule": "ofac_candidate",
                "detail": (
                    f"{hit.entity_name} ≈ SDN '{hit.sdn_name}' "
                    f"({hit.score}% match, program: {hit.sdn_program or 'unknown'}) "
                    "— verification required"
                ),
                "weight": RISK_WEIGHT_OFAC_CANDIDATE,
            })
        if raw_hits:
            result["score"] = min(100, sum(f["weight"] for f in result["findings"]))
            from configs.ghosttrace import RISK_LEVEL_HIGH, RISK_LEVEL_MEDIUM
            result["level"] = (
                "HIGH" if result["score"] >= RISK_LEVEL_HIGH
                else "MEDIUM" if result["score"] >= RISK_LEVEL_MEDIUM
                else "LOW"
            )
    except Exception:
        pass  # OFAC check is non-blocking — never fails a trace

    # Generate narrative report
    try:
        report = generate_risk_report(
            name, result["score"], result["level"], result["findings"],
            resolved, links,
        )
    except ExtractorError:
        report = {
            "headline": f"Risk assessment for {name} — {result['level']}",
            "summary": "Report narrative unavailable (API error).",
            "key_findings": [f['detail'] for f in result['findings']],
            "full_text": "",
        }

    # Resolve against the shared Company table -- CIK is the strongest join
    # key GhostTrace has, and it's already in hand at this point.
    resolution = resolve_or_create_company(db, name, cik=cik)

    # Persist
    trace = Trace(
        company_id=resolution.company.id,
        company_name=name,
        cik=cik,
        is_demo=False,
        risk_score=result["score"],
        risk_level=result["level"],
        headline=report["headline"],
        summary=report["summary"],
        full_text=report["full_text"],
        ofac_checked_at=ofac_checked_at,
    )
    trace.findings = result["findings"]
    trace.key_findings = report["key_findings"]
    trace.ofac_hits = ofac_hits
    db.add(trace)
    db.flush()

    for e in resolved:
        ent = Entity(
            trace_id=trace.id,
            canonical_name=e["canonical_name"],
            entity_type=e.get("entity_type"),
            jurisdiction=e.get("jurisdiction"),
            jurisdiction_category=jurisdiction_category(e.get("jurisdiction")),
            address=e.get("address"),
            is_focal=(normalize_name(e["canonical_name"]) == normalize_name(name)),
        )
        ent.aliases = e.get("aliases", [])
        ent.sources = e.get("sources", [])
        db.add(ent)

    for link in links:
        db.add(OwnershipLink(
            trace_id=trace.id,
            owner_name=link["owner"],
            owned_name=link["owned"],
            ownership_pct=link.get("ownership_pct"),
            evidence_quote=link.get("evidence_quote"),
            source_accession=link.get("source"),
        ))

    try:
        path = os.path.join(GRAPH_OUTPUT_DIR, f"trace_{trace.id}.png")
        build_graph_png(resolved, links, name, path)
        trace.graph_image_path = "/" + path.replace(os.sep, "/")
    except Exception:
        pass

    db.commit()
    return RedirectResponse(f"/ghosttrace/trace/{trace.id}", status_code=303)


# ---------------------------------------------------------------------------
# Trace detail page
# ---------------------------------------------------------------------------

@router.get("/trace/{trace_id}", response_class=HTMLResponse)
def trace_detail(request: Request, trace_id: int, db: Session = Depends(get_db)):
    trace = db.query(Trace).filter_by(id=trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return _template(request, "trace_detail.html", {
        "trace": trace,
        "deep_trace_max_calls": DEEP_TRACE_MAX_TOOL_CALLS,
    })


# ---------------------------------------------------------------------------
# Deep Trace — bounded agentic loop on an existing trace
# ---------------------------------------------------------------------------

@router.post("/trace/{trace_id}/deep-trace", response_class=HTMLResponse)
def run_deep_trace_route(
    request: Request,
    trace_id: int,
    db: Session = Depends(get_db),
):
    trace = db.query(Trace).filter_by(id=trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    if trace.is_demo:
        raise HTTPException(status_code=400, detail="Deep Trace is not available for demo traces")

    entities_for_dt = [
        {
            "canonical_name": e.canonical_name,
            "entity_type": e.entity_type,
            "jurisdiction": e.jurisdiction,
        }
        for e in trace.entities
    ]
    links_for_dt = [
        {
            "owner": l.owner_name,
            "owned": l.owned_name,
            "ownership_pct": l.ownership_pct,
        }
        for l in trace.links
    ]

    result = run_deep_trace(
        company_name=trace.company_name,
        entities=entities_for_dt,
        links=links_for_dt,
        risk_score=trace.risk_score,
        risk_level=trace.risk_level,
        findings=trace.findings,
        db=db,
    )

    trace.deep_trace = result
    trace.deep_trace_ran_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return RedirectResponse(f"/ghosttrace/trace/{trace_id}", status_code=303)


# ---------------------------------------------------------------------------
# Filing search — semantic search across all cached filing text
# ---------------------------------------------------------------------------

@router.get("/filings", response_class=HTMLResponse)
def filing_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    results = []
    error = None
    if q.strip():
        try:
            results = get_store().search(q)
        except Exception:
            error = "Search index unavailable."
    indexed = db.query(Filing).count()
    return _template(request, "filings.html", {
        "query": q,
        "results": results,
        "indexed_filings": indexed,
        "search_error": error,
    })


# ---------------------------------------------------------------------------
# Seed / health routes
# ---------------------------------------------------------------------------

@router.get("/seed")
def seed(db: Session = Depends(get_db)):
    result = load_seed_data(db)
    trace = db.query(Trace).filter_by(company_name="Harborview Capital Partners LP").first()
    if trace:
        return RedirectResponse(f"/ghosttrace/trace/{trace.id}", status_code=303)
    return JSONResponse(result)


@router.get("/api/health")
def health(db: Session = Depends(get_db)):
    trace_count = db.query(Trace).count()
    entity_count = db.query(Entity).count()
    filing_count = db.query(Filing).count()
    try:
        indexed_chunks = get_store().count()
    except Exception:
        indexed_chunks = 0
    return {"status": "ok", "traces": trace_count, "entities": entity_count,
            "filings": filing_count, "indexed_chunks": indexed_chunks,
            "demo_mode": DEMO_MODE}
