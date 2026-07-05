"""shared/edgar_client.py — SEC EDGAR HTTP layer, one copy for all five tools.

Ported from ghosttrace/edgar_client.py (the canonical source per the Arbor
architecture review — its rate limiter, ticker lookup, and HTML stripper
were already correct and already what debt_exposure_monitor's own copy was
adapted from). Pure data fetching: no Claude, no database. Fully testable
with mocked HTTP responses alone.

**The gap this file exists to close, found during the architecture review
and fixed here rather than deferred:** dib_monitor/dib_monitor/edgar_client.py
has NO rate limiter at all — it fires `urllib.request` calls with zero
throttling. SEC caps automated access at 10 req/s and IP-bans violators.
GhostTrace and Debt Exposure Monitor were already safe individually (each
has its own correctly-implemented, per-process rate limiter), but DIB
Monitor's un-throttled calls would have shared Arbor's single outbound IP
with two rate-limited clients once merged, defeating the whole point of a
process-global limiter. There is now exactly one EDGAR client in Arbor, and
it is rate-limited — the gap can't reappear because there's no second copy
left to have forgotten it.

**Filing selection is a shared, parameterized function, not two forks:**
GhostTrace's rule (keep every 13D/13G, but only the LATEST 10-K/DEF 14A —
an old subsidiary list is superseded, not additive) and Debt Exposure
Monitor's rule (cap 10-K/10-Q at N each, 8-K at M — footnotes are
cumulative, but new credit facilities/bond issuances are announced in 8-Ks
before showing up in the next periodic report) are both real, legitimately
different answers to "which filings matter for this question," not one
being a bug and the other the fix. `get_filings()` takes the strategy as
parameters; `get_ownership_filings()`/`get_debt_relevant_filings()` are the
two named callers preserving each project's exact original behavior.
"""
from __future__ import annotations

import threading
import time
from html.parser import HTMLParser

import httpx

from config import (
    DEBT_RELEVANT_FORM_TYPES,
    EDGAR_ARCHIVES_BASE,
    EDGAR_COMPANY_TICKERS_URL,
    EDGAR_RATE_LIMIT_PER_SEC,
    EDGAR_SUBMISSIONS_URL,
    EDGAR_USER_AGENT,
    MAX_10K_10Q_PER_TRACE,
    MAX_8K_PER_TRACE,
    MAX_DOC_CHARS,
    MAX_FILINGS_PER_TRACE,
    OWNERSHIP_FORM_TYPES,
    OWNERSHIP_SINGLE_PER_FORM,
)


class EdgarError(Exception):
    pass


# ---------------------------------------------------------------------------
# Rate limiting — the fix. Every _get() call goes through this, and there is
# only one _get() in all of Arbor.
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Process-wide rate limiter shared by every EDGAR call.

    The SEC's limit applies to our IP, not to any single code path — so the
    state (last request time) must be shared across concurrent request
    handlers, guarded by a lock. Sleeps only for the deficit since the last
    request, which is often zero when other work ran in between.
    """

    def __init__(self, max_per_second: float):
        self._min_interval = 1.0 / max_per_second
        self._lock = threading.Lock()
        self._last_request = 0.0

    def wait(self) -> None:
        with self._lock:
            # monotonic, not time.time(): wall clock can jump backwards
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()


_limiter = _RateLimiter(EDGAR_RATE_LIMIT_PER_SEC)

_HEADERS = {"User-Agent": EDGAR_USER_AGENT}


def throttle() -> None:
    """Public hook onto the one process-global rate limiter, for callers
    that need to hit EDGAR through their own request code instead of
    _get() (e.g. engines/dib_edgar_client.py, which has genuinely
    different needs — full-text-search CIK lookup, 8-K Exhibit 99
    extraction — that don't fit this module's own functions). This is the
    fix for the real gap found during the Arbor architecture review: DIB
    Monitor's original edgar_client.py fired every request with zero
    throttling. Call this before every outbound EDGAR request in any
    module, not just here."""
    _limiter.wait()


def _get(url: str) -> httpx.Response:
    _limiter.wait()
    try:
        resp = httpx.get(url, headers=_HEADERS, timeout=15.0, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise EdgarError(f"EDGAR request failed: {url} -- {exc}") from exc
    if resp.status_code != 200:
        raise EdgarError(f"EDGAR returned HTTP {resp.status_code} for {url}")
    return resp


# ---------------------------------------------------------------------------
# CIK lookup
# ---------------------------------------------------------------------------

# The ticker table is ~1 MB covering every listed registrant; cache it in
# memory and refresh daily. Only covers companies with tickers — private
# 13D filers won't resolve here, a documented limitation inherited from
# GhostTrace's v1.
_TICKER_CACHE: dict = {"fetched_at": 0.0, "rows": []}
_TICKER_CACHE_TTL_SECONDS = 24 * 3600


def _ticker_table() -> list[dict]:
    age = time.monotonic() - _TICKER_CACHE["fetched_at"]
    if not _TICKER_CACHE["rows"] or age > _TICKER_CACHE_TTL_SECONDS:
        data = _get(EDGAR_COMPANY_TICKERS_URL).json()
        # EDGAR serves this as {"0": {...}, "1": {...}} keyed by row number
        _TICKER_CACHE["rows"] = list(data.values())
        _TICKER_CACHE["fetched_at"] = time.monotonic()
    return _TICKER_CACHE["rows"]


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch == " ").strip()


def get_company_candidates(query: str, limit: int = 8) -> list[dict]:
    """Return ranked CIK candidates for a user-typed company name or ticker.

    Never silently picks one match: a confident report about the wrong
    company is worse than no report. Callers should show a disambiguation
    step when more than one candidate comes back.
    """
    q = _norm(query)
    if not q:
        return []
    rows = _ticker_table()
    exact_ticker = [r for r in rows if r["ticker"].lower() == query.strip().lower()]
    name_matches = [r for r in rows if q in _norm(r["title"])]

    seen: set[int] = set()
    out: list[dict] = []
    for r in exact_ticker + name_matches:
        cik = int(r["cik_str"])
        if cik in seen:
            continue
        seen.add(cik)
        out.append({"cik": cik, "ticker": r["ticker"], "name": r["title"]})
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Filing index — one parameterized function, two named strategies
# ---------------------------------------------------------------------------

def get_filings(
    cik: int,
    form_types: list[str],
    *,
    single_per_form: set[str] | None = None,
    max_per_form: dict[str, int] | None = None,
    max_total: int | None = None,
) -> list[dict]:
    """Newest filings matching `form_types`, filtered by whichever
    selection strategy the caller supplies:

    - `single_per_form`: keep only the MOST RECENT filing of these forms
      (an old subsidiary list / proxy statement is superseded, not
      additive). Forms not in this set are kept without a per-form cap.
    - `max_per_form`: keep up to N of each of these forms (recent 8-Ks
      each announce something new; footnotes in 10-Ks/10-Qs are
      cumulative but you still want more than just the latest one for a
      debt trend).
    - `max_total`: stop once this many filings have been kept, across all
      forms combined. None means no total cap (only the per-form rules
      apply).

    EDGAR's submissions JSON stores recent filings as parallel arrays —
    one array of forms, one of accession numbers, one of dates — where the
    same index across arrays describes one filing. zip() reassembles them.
    """
    data = _get(EDGAR_SUBMISSIONS_URL.format(cik=cik)).json()
    recent = data.get("filings", {}).get("recent", {})

    out: list[dict] = []
    seen_single_forms: set[str] = set()
    per_form_counts: dict[str, int] = {}

    for form, acc, doc, date in zip(
        recent.get("form", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("filingDate", []),
    ):
        if form not in form_types:
            continue
        if single_per_form and form in single_per_form:
            if form in seen_single_forms:
                continue
            seen_single_forms.add(form)
        elif max_per_form and form in max_per_form:
            count = per_form_counts.get(form, 0)
            if count >= max_per_form[form]:
                continue
            per_form_counts[form] = count + 1

        out.append({
            "form": form,
            "accession_number": acc,
            "primary_document": doc,
            "filing_date": date,
        })
        if max_total is not None and len(out) >= max_total:
            break

    return out


def get_ownership_filings(cik: int) -> list[dict]:
    """GhostTrace's original strategy: every 13D/13G (each names a
    different owner — all signal), only the latest 10-K/DEF 14A."""
    return get_filings(
        cik,
        OWNERSHIP_FORM_TYPES,
        single_per_form=OWNERSHIP_SINGLE_PER_FORM,
        max_total=MAX_FILINGS_PER_TRACE,
    )


def get_debt_relevant_filings(cik: int) -> list[dict]:
    """Debt Exposure Monitor's original strategy: cap 10-K/10-Q at
    MAX_10K_10Q_PER_TRACE each, 8-K at MAX_8K_PER_TRACE, no total cap."""
    return get_filings(
        cik,
        DEBT_RELEVANT_FORM_TYPES,
        max_per_form={
            "10-K": MAX_10K_10Q_PER_TRACE,
            "10-Q": MAX_10K_10Q_PER_TRACE,
            "8-K": MAX_8K_PER_TRACE,
        },
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def get_filing_documents(cik: int, accession_number: str) -> list[str]:
    """List the file names inside one filing's directory.

    Needed because a 10-K's subsidiary list (Exhibit 21) is a separate file
    from the primary document. Archive paths use the unpadded CIK and the
    accession number without dashes.
    """
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES_BASE}/{cik}/{acc}/index.json"
    data = _get(url).json()
    items = data.get("directory", {}).get("item", [])
    return [i["name"] for i in items]


def find_exhibit_21(document_names: list[str]) -> str | None:
    """Best-effort Exhibit 21 finder. Naming isn't standardized; this
    heuristic will occasionally miss — a documented limitation, surfaced to
    the user as 'subsidiary list not found' rather than hidden."""
    for name in document_names:
        lowered = name.lower()
        if ("ex21" in lowered or "ex-21" in lowered or "exhibit21" in lowered) \
                and lowered.endswith((".htm", ".html", ".txt")):
            return name
    return None


def fetch_document_text(cik: int, accession_number: str, document_name: str) -> str:
    """Fetch one document and return plain text, truncated to MAX_DOC_CHARS."""
    acc = accession_number.replace("-", "")
    url = f"{EDGAR_ARCHIVES_BASE}/{cik}/{acc}/{document_name}"
    raw = _get(url).text
    if document_name.lower().endswith((".htm", ".html")):
        raw = _strip_html(raw)
    return raw[:MAX_DOC_CHARS]


# ---------------------------------------------------------------------------
# HTML -> text (stdlib only; no BeautifulSoup dependency for one job)
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self._chunks)


def _strip_html(raw: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw)
    return parser.get_text()
