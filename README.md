# Arbor

**Arbor is a due-diligence platform that screens a company for supply-chain, foreign-investment, and financial risk from one place.** You search for a company once and Arbor pulls together five kinds of checks on it — hidden ownership and sanctions exposure, foreign-investment (CFIUS) review triggers, financial-distress signals, who is lending it money, and a pre-acquisition intelligence brief — into a single entity view instead of five disconnected tools.

**Live demo:** https://arbor-vpa1.onrender.com

The demo runs on seeded example data and needs no login, no API key, and no setup to click through.

---

## What it does

Type a company name into the search box and Arbor shows one page for that company with a card from each of its five analysis modules. If a module hasn't analyzed the company yet, it says so honestly rather than showing a blank or inventing data. The five modules are:

| Module | Question it answers | How |
|---|---|---|
| **GhostTrace** (`/ghosttrace`) | Who actually owns and controls this company, and does any owner appear on a sanctions list? | Reads SEC EDGAR filings, resolves name variants with fuzzy matching, screens owners against the OFAC SDN list, and runs a bounded AI "deep trace" to follow ownership chains |
| **CFIUS Screener** (`/cfius`) | Would a proposed foreign investment in this company trigger a mandatory U.S. national-security review? | Applies the 31 CFR Part 800 decision tree, produces a cited findings trail and a risk scorecard, and can generate a screening memo as a PDF |
| **DIB Monitor** (`/dib`) | How financially healthy is this defense supplier, and what's the probability it hits distress? | Extracts covenant and going-concern language from SEC 10-Ks, runs a Monte Carlo distress simulation, and tracks earnings-call risk signals |
| **Debt Exposure Monitor** (`/debt`) | Who is *funding* this supplier, and are any lenders sanctioned or state-controlled? | Pulls lender identities from SEC debt disclosures and screens them against OFAC, BIS, and a curated foreign-state-lender list |
| **Pre-Acquisition Brief** (`/brief`) | Before we pursue this target, what does its IP, litigation, and contract history look like? | Assembles USPTO patents, CourtListener litigation, SEC filings, and federal contract history into a scored due-diligence brief |

The connecting idea is the **shared company record**. All five modules write to one database keyed on a single company entity, and Arbor resolves company-name variants (e.g. "Acme Corp." vs "Acme Corporation") to the same record at the moment data is saved. So an ownership flag from one module and a debt-lender flag from another line up on the same company page automatically.

## Design principles

Arbor follows the same discipline throughout:

- **The AI extracts and drafts; deterministic rules decide.** Claude reads unstructured filings and turns them into structured facts and plain-language narratives. It never makes a legal determination, a compliance certification, or a risk score — those come from auditable, deterministic code citing a specific regulation or data source.
- **A human confirms before anything consequential.** Where a workflow parses free text into structured facts (for example, the CFIUS deal-intake step), it proposes the facts for a person to confirm before the engine runs on them.
- **Demo mode by default.** Every module works with no API key against seeded example data, so the demo is reliable and reproducible. Live data sources and live AI calls are opt-in.
- **Sources are cited and limitations are stated.** Findings link back to the filing or list they came from, and each module is explicit about what it does not do.

## Tech stack

- **Backend:** FastAPI, one shared SQLite database via SQLAlchemy 2.0
- **AI:** Anthropic Claude (extraction and narrative synthesis only)
- **Data sources:** SEC EDGAR, OFAC SDN, BIS/Consolidated Screening List, USPTO, CourtListener, USASpending
- **Analysis:** NetworkX (ownership graphs), rapidfuzz (entity resolution), NumPy (Monte Carlo), ReportLab (PDF export)
- **Frontend:** Jinja2 templates, air-gap-safe CSS (no external CDNs)

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open http://localhost:8000. The database auto-seeds with example companies on startup, so every module has data to explore immediately.

To enable live AI analysis, set `ANTHROPIC_API_KEY` and `DEMO_MODE=False`. Live external data sources (EDGAR, OFAC, etc.) are fetched on demand and rate-limited.

```bash
pytest        # run the test suite
```

## Scope and honest limitations

Arbor does not render legal advice or an official CFIUS determination, it does not guarantee completeness of any sanctions or ownership screen, and its regulatory parameters should be independently verified before any real-world use. Every module surfaces checkable evidence for a human analyst to interpret — it does not substitute for one.

## About

Arbor combines five independent analysis tools — GhostTrace, CFIUS Screener, DIB Monitor, Debt Exposure Monitor, and the Pre-Acquisition Brief generator — into one platform with a shared company record. It's part of a portfolio of national-security and defense-compliance software, and is a demonstration of an integrated due-diligence workflow rather than a certified commercial compliance product.
