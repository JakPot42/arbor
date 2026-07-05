"""main.py — Arbor: GhostTrace + CFIUS Screener + DIB Monitor + Debt
Exposure Monitor + Pre-Acquisition Brief Generator, merged. All five
Arbor sources are now wired in.

Phase 6 (Merger #1). Step 2 ported the three existing FastAPI apps onto
shared plumbing (database.py, models/company.py, shared/resolve_company.py,
shared/edgar_client.py) — see each router/model/engine module's own
docstring for the real conflicts fixed along the way (route collisions,
DIB Monitor's missing rate limiter and ForeignKeys, the entity_resolver.py
drift, template-path fragility). Step 3 built the entity-centric
`/company/{id}` view (routers/company.py) against those three.

Step 4 (this step) wraps the two CLI-only tools -- Debt Exposure Monitor
(routers/debt.py) and Pre-Acquisition Brief Generator (routers/brief.py)
-- in net-new web layers, and both now get real Company-backed
persistence (models/debt.py, models/brief.py) they never had before.
`routers/company.py`'s fan-out page now shows all five real cards.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from configs.ghosttrace import GRAPH_OUTPUT_DIR
from database import SessionLocal, init_db
from engines.brief_seed_data import load_seed_data as load_brief_seed_data
from engines.cfius_seed_data import load_seed_data as load_cfius_seed_data
from engines.debt_seed_data import load_seed_data as load_debt_seed_data
from engines.dib_seed_data import load_seed_data as load_dib_seed_data
from engines.ghosttrace_seed_data import load_seed_data as load_ghosttrace_seed_data
from engines.ghosttrace_vector_store import reindex_from_db
from routers import brief as brief_router
from routers import cfius as cfius_router
from routers import company as company_router
from routers import debt as debt_router
from routers import dib as dib_router
from routers import ghosttrace as ghosttrace_router
from shared.rate_limit import limiter

_HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    os.makedirs(GRAPH_OUTPUT_DIR, exist_ok=True)

    db = SessionLocal()
    try:
        # Each tool's seed data is idempotent and independent -- one
        # tool's seeding failure must not block the others.
        for load_seed in (
            load_ghosttrace_seed_data,
            load_cfius_seed_data,
            load_dib_seed_data,
            load_debt_seed_data,
            load_brief_seed_data,
        ):
            try:
                load_seed(db)
            except Exception:
                pass

        # Rebuild GhostTrace's in-memory search index from the Filing
        # table. Wrapped so a search-layer failure can never take down
        # the whole app (same guard the original had).
        try:
            reindex_from_db(db)
        except Exception:
            pass
    finally:
        db.close()
    yield


app = FastAPI(title="Arbor", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static/cfius", StaticFiles(directory=_HERE / "static" / "cfius"), name="cfius_static")
app.mount("/static/ghosttrace", StaticFiles(directory=_HERE / "static" / "ghosttrace"), name="ghosttrace_static")
app.mount("/static/dib", StaticFiles(directory=_HERE / "static" / "dib"), name="dib_static")
app.mount("/static/shared", StaticFiles(directory=_HERE / "static" / "shared"), name="shared_static")

app.include_router(company_router.router)
app.include_router(ghosttrace_router.router)
app.include_router(cfius_router.router)
app.include_router(dib_router.router)
app.include_router(debt_router.router)
app.include_router(brief_router.router)
