# Arbor — Claude Code context

**SHIPPED — Phase 6, Cluster 1 of 6, live as of July 5, 2026.**
`https://arbor-vpa1.onrender.com` — GitHub: `JakPot42/arbor`.

Arbor merges GhostTrace, CFIUS Screener, DIB Monitor, Pre-Acquisition Brief
Generator, and Debt Exposure Monitor into one FastAPI app with one shared
`Company` entity every tool's records hang off of. First of six planned
Phase 6 cluster mergers. Architecture proposal: see
`C:\Users\JakPot\.claude\plans\wild-wibbling-wirth.md`.

## Deployment (step 5 — shipped)

Pushed to `JakPot42/arbor` (public), deployed to Render as
`srv-d94vip7aqgkc73ef9s00` (`arbor-vpa1.onrender.com`), and verified live
end-to-end before anything was decommissioned — same discipline as every
other verification pass in this build. `ghosttrace-aose`, `cfius-screener`,
and `dib-monitor`'s standalone Render services are now deleted;
`JakPot42/ghosttrace`, `JakPot42/cfius-screener`, and `JakPot42/dib-monitor`
GitHub repos are untouched and unarchived, exactly as required. The GitHub
profile README (`JakPot42/JakPot42`) now notes the merge on all three rows
with a link to Arbor, and Pre-Acquisition Brief and Debt Exposure Monitor
(previously CLI-only, no row at all for the latter) both got real entries
pointing to Arbor for the first time.

**Render's Hobby tier hard-caps at 25 services (confirmed directly via a
real 400 from the API, not assumed from memory) — this blocked deploying
Arbor as a clean 26th service while verifying against all three originals
still live.** Suspending a service to free the slot was tried first and
does NOT work — Render still counts suspended services against the cap
(confirmed by testing directly: the create call still 400'd after
suspending DIB Monitor). The actual resolution, confirmed with the user
first: delete DIB Monitor's Render service for real (not its GitHub repo)
to free one slot, deploy Arbor into it, verify Arbor's DIB Monitor coverage
specifically plus all other four tools over real HTTP before touching
anything else, then delete the other two once fully confirmed. DIB
Monitor's own live demo was offline for a few minutes before Arbor's
replacement was verified — a real, accepted tradeoff of the 25-slot cap,
not an oversight.

**Two real deploy-time bugs found via the actual Render build logs (never
guessed at):**
1. `ModuleNotFoundError: No module named 'slowapi'` on first boot — root
   `requirements.txt` had only ever listed the handful of packages step 1's
   shared plumbing needed (`fastapi`, `uvicorn`, `jinja2`, `sqlalchemy`,
   `httpx`, `anthropic`, `pytest`), never reconciled against everything
   steps 2-4's ported engines actually import. Fixed by rebuilding the file
   from a real grep of every top-level import across the whole codebase:
   added `chromadb`, `matplotlib`, `networkx`, `numpy`, `rapidfuzz`,
   `reportlab`, `requests`, `slowapi`, `python-multipart` (needed for every
   router's `Form(...)` parameters even though nothing imports it directly),
   and `pydantic` (a direct import in `jurisdiction_engine.py`, not just a
   FastAPI transitive dependency).
2. `RuntimeError: Directory '/opt/render/project/src/static/dib' does not
   exist` on the second boot — DIB Monitor's original project never had a
   static/ directory at all (its templates use inline styles, never a
   stylesheet link); `static/dib/` locally was an empty, never-git-tracked
   leftover (git doesn't track empty directories), so `main.py`'s
   `app.mount("/static/dib", ...)` pointed at a path that simply wasn't in
   the pushed repo. Removed the dead mount rather than adding a placeholder
   file just to keep an unused directory alive.

The second fix was verified with a targeted local smoke pass (DIB-related
tests) before pushing again, not a full regression run — the full suite
had already passed cleanly at the end of step 4, and neither fix touched
logic the rest of the suite exercises. Both are then re-verified live,
over real HTTP, after the successful deploy — including DIB Monitor's
dashboard, supplier detail, PDF export, earnings, and portfolio routes
specifically, since that tool's own standalone deployment was the one
sacrificed to make room.

## Build status

**Step 1 (shared plumbing) — complete.** `database.py`, `models/company.py`,
`shared/entity_resolver.py`, `shared/resolve_company.py`,
`shared/edgar_client.py`.

**Step 2 (port GhostTrace, CFIUS Screener, DIB Monitor onto the shared
plumbing) — complete.** All three apps run as one FastAPI process
(`main.py`), each under its own route prefix (`/ghosttrace`, `/cfius`,
`/dib`), sharing one DB, one EDGAR client, one OFAC checker, one entity
resolver.

**Step 3 (the `/company/{id}` entity-centric view) — complete, 340 tests
passing.** `routers/company.py`: `GET /` (search + recently-analyzed
list), `POST /search` (read-only fuzzy lookup — never
`resolve_or_create_company`, a search must never create a company),
`GET /company/{id}` (one page, three real cards: GhostTrace trace status,
CFIUS jurisdiction outcome, DIB Monitor combined risk — each a real query
against that tool's own table via `Company.id`, not a mock). This is the
actual deliverable of the merger. Verified end-to-end against real seed
data: booted the server, searched for real companies that exist in only
one tool's data and confirmed the other two cards honestly say "not yet
analyzed" rather than fabricating or omitting, searched an exact match
(direct redirect), a genuinely ambiguous query that matches two different
real companies (disambiguation list, correctly ranked), and a query
matching nothing (honest error, confirmed via a before/after row-count
check that it created no phantom Company row).

**Step 4 (wrap Debt Exposure Monitor and Pre-Acquisition Brief Generator
in net-new web layers) — complete, 642 tests passing.** Both were
CLI-only tools with zero persistence — `routers/debt.py` (prefix
`/debt`) and `routers/brief.py` (prefix `/brief`) are genuinely new web
layers, not ports, and `models/debt.py`/`models/brief.py` are net-new
SQLAlchemy tables these tools never had. All five Arbor sources are now
live in one process, and `routers/company.py`'s fan-out page shows all
five real cards. Verified end-to-end against real seed data: booted the
server, confirmed a debt-only company (Meridian Defense Systems) and a
brief-only company (Parsons Corporation) each show three honest "not yet
analyzed" cards plus their own real computed data (HIGH risk/75, MODERATE
overall tier respectively), and that both search and click-through links
resolve to the real underlying tool pages.

**A real, live-data-dependent test-isolation bug was found and fixed
during this step's own verification, not by luck.** `tests/test_cfius_m3.py`'s
OFAC tests reset `shared/ofac_checker.py`'s process-wide SDN cache
*before* injecting their own tiny mocked list, but never reset it
*after* — so whichever mocked test ran last in the full suite left that
fake list cached, and any later test needing the REAL live OFAC list
(engines/debt_seed_data.py's seeding, which screens Meridian Defense
Systems' demo lenders for real) silently got the stale fake list instead,
with no error raised — just a wrong risk score (MEDIUM instead of the
correct HIGH, since "VTB Bank" was never in the mocked test's tiny fake
list). First attempted fix (a blanket autouse fixture resetting the cache
before/after *every* test in the whole suite) was correct but far too
slow — it forced repeated real ~16MB BIS Consolidated Screening List
downloads throughout the run. Reverted that in favor of the actually
correct, narrowly-scoped fix: a module-scoped autouse fixture in
`test_cfius_m3.py` itself, since that file is where the leak originates.

## Architecture decisions (step 1)

**A real, portfolio-wide environment bug was found and fixed, not worked
around.** SQLAlchemy 2.0.36 cannot resolve `X | None` (or `Optional[X]`)
column annotations under Python 3.14 — a `TypeError` in
`de_stringify_union_elements` at class-definition time. This isn't
specific to Arbor's new code: `cfius_screener`'s own pre-existing
`models.py` fails identically when imported fresh on this machine (verified
directly, not assumed). There is no per-project virtualenv anywhere in
this portfolio — every project shares one global Python install — so this
silently blocked any SQLAlchemy model definition portfolio-wide on this
machine. Fixed by upgrading the shared install to `sqlalchemy==2.0.51`
(latest 2.0.x patch) and verified with a full regression pass: CFIUS
Screener (85 tests), GhostTrace (116 tests), and DIB Monitor (80 tests) all
still pass, unchanged, after the upgrade.

**`Company.cik` is nullable and unique.** SQLite (and standard SQL) permit
multiple NULLs under a unique constraint, so companies with no known CIK
yet don't collide with each other — this matters because only 3 of the 5
source projects ever populate a CIK, and 2 of those only outside demo mode.

**`entity_resolver.py` is a genuine reconciliation of three drifted
copies, not a pick between them.** GhostTrace's and entity_graph's (P71)
copies share the same single-pass suffix-stripping bug (documented in
`shared/entity_resolver.py`'s module docstring); Debt Exposure Monitor's
copy fixed that but only has a 2-measure `similarity()` (missing the
token-set Jaccard measure the other two have). The reconciled version
keeps the fixed-point stripping loop AND the 3-measure similarity AND
entity_graph's `KNOWN_ALIASES`/`resolve_known_alias()` (the only one of the
three that had it). Regression-tested directly against the real cases that
motivated each original fix: "Wells Fargo Bank, N.A." (stacked-suffix) and
"GE Power" -> "General Electric Company" (known-alias gap, plus a test
proving the real fuzzy score for that pair is actually below the
adjudicate threshold, not assumed to be).

**The adjudicate band's default is not to merge, with no adjudicator.**
Same rule GhostTrace's own entity-match Claude prompt states directly:
"When genuinely uncertain, answer false — a wrong merge is worse than a
missed merge." `resolve_or_create_company()` supports an optional
`adjudicator` callback (same signature as entity_graph's
`resolve_entities(..., adjudicator=...)`) for future use, but creates a new
`Company` row by default in the ambiguous band, surfacing the near-miss via
`CompanyResolution.adjudicate_candidate` rather than silently discarding it
— same "candidate, not confirmed" transparency as GhostTrace's OFAC
screening.

**The EDGAR rate-limiter gap is fixed by having only one client, not by
teaching DIB Monitor's client to rate-limit itself.** DIB Monitor's
original `edgar_client.py` had zero throttling. `shared/edgar_client.py` is
GhostTrace's client (rate limiter, ticker lookup, HTML stripper — already
correct) with filing selection generalized into one parameterized
`get_filings()` function; `get_ownership_filings()` and
`get_debt_relevant_filings()` are named wrappers that reproduce GhostTrace's
and Debt Exposure Monitor's original, different, both-legitimate selection
rules exactly (regression-tested against each project's real documented
behavior, including the exact filing sets from GhostTrace's own test
suite).

**A real test-isolation bug was found and fixed while testing the EDGAR
client, not by luck of test ordering.** `_TICKER_CACHE` is a deliberate
module-level singleton (one in-memory cache per process). Without a reset
fixture, an earlier test's cached rows leak into a later test expecting
freshly mocked data — caught because `test_respects_limit` failed only
when run after other tests, not in isolation. GhostTrace's own test suite
has the identical gap (grepped directly — no cache reset anywhere in its
`tests/test_edgar_client.py`); it just hasn't hit a test ordering that
exposes it. Fixed here with an autouse fixture, not copied forward as a
latent bug.

## Architecture decisions (step 2)

**Per-tool config namespaces, not one flat config.py.** Flattening
collided immediately: GhostTrace's and CFIUS's original configs both
define `APP_TITLE` and `DEMO_BANNER` with different values. Each tool's
own domain constants (unchanged values) now live in `configs/ghosttrace.py`
/ `configs/cfius.py` / `configs/dib.py`; only genuinely cross-tool constants
(DEMO_MODE, CLAUDE_MODEL, EDGAR_*, OFAC_*) stay in the root `config.py`.

**GhostTrace's within-trace entity resolution is genuinely distinct engine
logic, not just "generic fuzzy matching with different thresholds."** Its
`entity_resolver.py` has a real jurisdiction-conflict gate (two identically-
named entities in different jurisdictions must never auto-merge — the
classic shell pattern) that shared/entity_resolver.py has no reason to
know about. Ported as `engines/ghosttrace_entity_resolver.py`, keeping that
gate and GhostTrace's own independently-tuned 92/75 thresholds
(`configs/ghosttrace.py`) — but its old copy of `normalize_name()`/
`similarity()` was replaced with calls into the already-reconciled shared
versions, since porting forward a known bug the whole point of step 1 was
to fix would have defeated that work.

**A fourth drifted copy of the suffix list was found while porting
`ofac_checker.py`.** CFIUS's own version inlined a separate `_normalize()`
specifically to avoid an entity_resolver dependency, and in doing so added
international corporate-suffix coverage (`pte`, `pty`, `jsc`, `ooo`,
`pjsc`, `sas`, `spa`) neither GhostTrace's nor the reconciled list had.
OFAC's SDN list is full of non-US entities, so this coverage is real —
folded into `config.NORMALIZE_SUFFIXES` rather than left as a fifth
almost-shared list. `shared/ofac_checker.py` is now the one copy both
GhostTrace's and CFIUS's routers use.

**A real, pre-existing, self-documented bug in GhostTrace's live-trace
path was fixed during the port, not preserved.** The original
`run_trace()` called `get_filing_documents()` (returns `list[str]`) and
then indexed the result as `d["name"]` — a `TypeError` waiting to happen
on any live trace that reached that code path. GhostTrace's own CLAUDE.md
already documented this exact gap ("a pre-existing `d[\"name\"]` call that
would fail on live traces... `deep_trace.py` uses the correct `list[str]`
API"). Since this line had to be touched anyway for the
`get_target_filings` -> `get_ownership_filings` rename, fixed to match
`deep_trace.py`'s already-correct usage rather than knowingly porting a
known defect into new code.

**DIB Monitor's own EDGAR client kept its genuinely different
functionality (full-text-search CIK lookup, 8-K Exhibit 99 extraction) as
its own module (`engines/dib_edgar_client.py`), but now goes through the
one shared rate limiter.** `shared/edgar_client.py` gained a public
`throttle()` function specifically so other EDGAR-calling modules don't
need a second, redundant rate limiter — the fix for DIB Monitor's original
zero-throttling gap isn't "teach DIB's client to rate-limit itself
independently," it's "there is only one limiter in the whole app, and
everyone goes through it."

**DIB Monitor's CIK is a zero-padded string; Company.cik is an int.**
Preserved DIB's own field shape (matches its original data format)
rather than changing its model to match Company's — conversion happens at
the boundary (`routers/dib.py::_backfill_company_cik`), not by unifying
the two representations.

**`supplier_search()`'s duplicate check was upgraded, not just ported.**
The original used a naive `Supplier.name.ilike(f"%{name}%")` substring
match against DIB's own table — sloppy in both directions. Replaced with
`resolve_or_create_company()` + an exact `Supplier.company_id ==` lookup,
which is what the shared Company table exists for.

**Every route moved under a tool prefix** (`/ghosttrace`, `/cfius`,
`/dib`) — fixes two real, exact collisions found during the architecture
review: bare `/` (all three tools had their own dashboard there) and
`/api/stats` (CFIUS and DIB Monitor both used this literal path for
different response shapes).

**One shared `Jinja2Templates` instance** (`shared/templates.py`), anchored
to the file's own location rather than the process's working directory —
adopts CFIUS's already-correct pattern over GhostTrace's CWD-relative one
(`directory="templates"`, breaks if launched from the wrong directory) and
DIB Monitor's `str(__file__).replace("main.py", "templates")` string-
surgery hack. Each tool's templates live in their own subdirectory so
`cfius/index.html` and `dib/index.html` (same filename, same original
project) never collide.

**Every seed scenario resolves against the shared Company table before
storing its own tool-specific row** — GhostTrace's Harborview trace,
CFIUS's 3 demo screenings, and DIB's 2 demo suppliers. This is the actual,
running proof that cross-tool identity resolution works, not just a
function that exists and is never called.

## Architecture decisions (step 3)

**Search is read-only by construction, not by convention.**
`shared/resolve_company.py` gained `find_companies()` specifically because
`resolve_or_create_company()` — the function every tool's write path calls
— creates a row when nothing matches, which is exactly wrong for a search
box: typing a company nobody has analyzed yet must not silently create a
phantom `Company` row. `find_companies()` is a separate, genuinely
side-effect-free function (fuzzy-matches existing rows only, floored at
`MIN_QUERY_SCORE` so unrelated queries return nothing), not
`resolve_or_create_company()` called with a flag to suppress creation —
the two have different contracts and deserve different functions.
Regression-tested directly: `test_search_never_creates_a_company` asserts
a before/after row count.

**`MIN_QUERY_SCORE = 40.0`, carried over from entity_graph's (P71) own
constant of the same name and same purpose** — `find_entity()`-style
search needs its own noise floor, separate from the merge/adjudicate bands
used when a tool is actually resolving-and-writing. Not reinvented; the
existing precedent already solved this exact problem.

**A real bug was found the same way step 2's bugs were — by actually
booting the server, not just running unit tests first.** The first pass
returned `jinja2.exceptions.TemplateNotFound: company_search.html` on
`GET /` — the templates live in `templates/company/`, but the router's
`_template()` helper didn't prepend that subdirectory (every other
router's `_template()` does this for its own tool). Fixed by making
`routers/company.py`'s helper consistent with the others, then re-verified
over real HTTP before writing it up here or moving on to tests.

**The three cards are honest about what's missing, not just what's
present.** A company known only to DIB Monitor shows real "not yet traced"
/ "not yet screened" text for GhostTrace/CFIUS, each linking to that
tool's own entry point — never a blank space where a card silently isn't
rendered, and never fabricated placeholder data. Verified against real
seed data for both directions (a DIB-only company, a GhostTrace-only
company), not just asserted as a design principle.

**Pre-Acquisition Brief Generator and Debt Exposure Monitor got one
explicit disclosure line at the bottom of the page** ("not yet wired into
Arbor") through the end of step 3, rather than being silently absent —
the page never implied completeness it didn't have. Removed once step 4
wired both in for real.

## Architecture decisions (step 4)

**Both tools' original in-memory dataclasses were kept as their own
`engines/{debt,brief}_models.py` module, separate from the new
SQLAlchemy persistence models (`models/debt.py`, `models/brief.py`).**
Neither original CLI tool had ANY persistence — `SupplierDebtProfile`/
`AcquisitionBrief` existed only for the duration of one process
invocation. Rather than rewriting every ported engine function
(`risk_engine.py`, `pipeline.py`, `brief_engine.py`, all four brief
clients) to work off SQLAlchemy rows or raw dicts, the original
dataclasses stay exactly as they were as the pipeline's in-memory working
shape, and the router does one conversion step (dataclass -> JSON columns)
at the point a run actually gets persisted. Same separation
GhostTrace/CFIUS/DIB already have between their engine layer and their
DB layer — applied here from day one instead of retrofitted.

**One table each, not one table per nested dataclass.** The Arbor
architecture proposal's module map sketch called for tables "mirroring
the existing dataclass shapes 1:1" (plural) — read literally that could
mean 9 new tables for Pre-Acquisition Brief alone (PatentRecord,
IPPortfolio, LitigationCase, LitigationProfile, RegulatoryFlag,
RegulatoryExposure, ContractAward, ContractProfile, AcquisitionBrief).
Used the same JSON-blob-under-one-row convention CFIUS's
`Screening.findings_json` and DIB's `EarningsSignal.signals_json`
already established for point-in-time nested report data instead —
`DebtProfile` and `AcquisitionBrief` are each one table, with nested
lists (lenders, screening hits, patents, cases, flags, awards) as JSON
columns. Consistent with the rest of Arbor, and this data doesn't need
independent relational identity (nobody queries "all patents across every
brief," only "this brief's patents").

**Debt Exposure Monitor needed no new EDGAR client at all.**
`shared/edgar_client.py`'s `get_debt_relevant_filings()` strategy (built
in step 1) is a direct, exact reproduction of Debt Exposure Monitor's own
original filing-selection rule — `engines/debt_pipeline.py` just calls
the shared client's existing functions
(`get_company_candidates`/`get_debt_relevant_filings`/`fetch_document_text`),
same as `shared/ofac_checker.py` needed no new copy either. Only BIS
screening (`engines/debt_bis_checker.py`) and the foreign-state-lender
list (`engines/debt_foreign_state_lender_checker.py`) were genuinely new
to Arbor.

**Pre-Acquisition Brief's EDGAR client stayed its own module** (a
different use case — EFTS full-text search by company name, not a
CIK-keyed submissions lookup) **but now throttles through the one shared
rate limiter**, `shared.edgar_client.throttle()` — the same fix already
applied to `engines/dib_edgar_client.py` in step 2, extended to the third
and last EDGAR-calling module in Arbor. The original's deeper live-mode
bug (it re-issues the EFTS search URL as its "document fetch" instead of
pulling real filing text, so live mode always returns
`government_revenue_pct: 0.0`/`flags: []`) was NOT fixed — that's a
separate, more invasive piece of work than what this step's architecture
review flagged, and is disclosed directly in
`engines/brief_edgar_client.py`'s own docstring rather than silently
carried forward or silently expanded into a bigger rewrite than asked for.

**Two real, small drift bugs fixed in `engines/brief_claude_generator.py`,
flagged during the original architecture review, not newly discovered:**
the model string was hardcoded (`"claude-haiku-4-5-20251001"`) instead of
importing `config.CLAUDE_MODEL`, and the API key was read via
`os.getenv("ANTHROPIC_API_KEY", "")` directly instead of the shared
`config.ANTHROPIC_API_KEY` every other Claude call site in Arbor uses.
Both fixed to match the rest of the portfolio; no other logic touched.

**Debt Exposure Monitor's Claude-narrative module was renamed
`engines/debt_risk_brief.py`, not `debt_brief.py`** — the original file
was literally named `brief.py`, and Arbor now has an entirely separate
tool called Pre-Acquisition *Brief* Generator with its own `brief_*.py`
engine modules. Keeping the original name would have made every file
listing and every "which brief are we talking about" conversation
ambiguous for no reason.

## Module map

| File | Purpose |
|---|---|
| `config.py` | Cross-tool constants only — no logic |
| `configs/{ghosttrace,cfius,dib,debt,brief}.py` | Each tool's own domain constants, unchanged values |
| `database.py` | One `Base`/engine/`get_db` for every tool's tables |
| `models/company.py` | The shared cross-tool entity |
| `models/{ghosttrace,cfius,dib}.py` | Ported models, `company_id` FK added to each |
| `models/{debt,brief}.py` | New: SQLAlchemy persistence neither tool ever had, one table each, JSON blobs for nested data |
| `shared/entity_resolver.py` | Reconciled fuzzy name matching (4 drifted copies found and merged) |
| `shared/resolve_company.py` | Live `resolve_or_create_company()` + read-only `find_companies()` |
| `shared/edgar_client.py` | One rate-limited EDGAR client, two filing-selection strategies, public `throttle()` |
| `shared/ofac_checker.py` | One OFAC SDN screening module for GhostTrace + CFIUS |
| `shared/rate_limit.py` | One slowapi `Limiter`, shared by `main.py` and `routers/cfius.py` |
| `shared/templates.py` | One `Jinja2Templates` instance, anchored to file location |
| `engines/*.py` | Genuinely-distinct per-tool logic (jurisdiction tree, Deep Trace, Monte Carlo, risk scorers, Claude-calling modules, seed data) |
| `engines/debt_*.py` | Ported Debt Exposure Monitor engine (BIS/foreign-state checkers, HHI risk scoring, lender dedup, pipeline, `debt_risk_brief.py` narrative — renamed from `brief.py` to avoid confusion with the other Brief tool) |
| `engines/brief_*.py` | Ported Pre-Acquisition Brief engine (4 data clients, aggregation, Claude generator — 2 real drift bugs fixed) |
| `routers/{ghosttrace,cfius,dib}.py` | HTTP glue, one router per tool, prefixed |
| `routers/{debt,brief}.py` | New: net-new web layers for the two CLI-only tools, prefixed `/debt` and `/brief` |
| `routers/company.py` | The entity-centric view — search + `/company/{id}` fan-out, now all five real cards |
| `templates/{ghosttrace,cfius,dib}/*.html` | Ported templates, links/extends rewritten to prefixed routes |
| `templates/{debt,brief}/*.html` | New: dashboard + detail pages, extend Arbor's own shared shell |
| `templates/company/*.html` | Search page + fan-out detail page (5 cards) |
| `templates/base.html` | Arbor's own shared shell (not any one tool's) |
| `static/shared/css/app.css` | Arbor's own home/company-view stylesheet |
| `main.py` | Mounts all six routers, one lifespan seeding all five tools |

## Known gaps (not forgotten)

- `resolve_or_create_company()`'s `adjudicator` parameter still has no
  caller anywhere in Arbor — every ambiguous-band match creates a new row.
  Correct/safe default, not a bug, but worth knowing.
- Pre-Acquisition Brief Generator's live-mode regulatory-exposure signal
  is still weak (re-issues its EFTS search URL as a "document fetch"
  rather than pulling real filing text) — disclosed in
  `engines/brief_edgar_client.py`'s docstring, not fixed in step 4, since
  fixing the real extraction logic is separate, more invasive work than
  what this step's architecture review scoped.
- **`ANTHROPIC_API_KEY` is not actually set on the live Render service**,
  despite being told it was — checked directly via the Render API
  (env-vars list shows only `DEMO_MODE` and `PYTHON_VERSION`), not assumed.
  Doesn't block anything verified so far (DEMO_MODE=True covers every
  route this build's own verification exercised), but any live-mode Claude
  call (CFIUS intake, DIB analyze, live debt screen, live brief generate)
  will fail with a real `TypeError` until this is actually set. Flagged
  directly rather than silently trusted.

## Test suite

642 tests, all passing. Run with `py -m pytest` from this directory —
expect several minutes, since seeding/screening tests make real (not
mocked) calls to OFAC, BIS, and the SEC EDGAR ticker table, same as the
original standalone tools' own suites did. Includes full ported test
suites from all five source projects (test logic unchanged — only import
paths, route prefixes, and the specific real adaptations noted in each
step's architecture-decisions section above) plus Arbor's own
shared-plumbing and router-level tests. Some originals' tests were
consolidated where an earlier step already built equivalent shared-module
coverage (e.g. `shared/edgar_client.py`'s tests already cover GhostTrace's
and Debt Exposure Monitor's original client behavior one-for-one under
their new names) rather than duplicated.
