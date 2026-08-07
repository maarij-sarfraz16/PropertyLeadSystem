# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Automated real estate lead pipeline. A background worker polls Zameen.com search pages on an
interval, extracts structured lead fields (price, area, bedrooms, location, contact, owner-vs-agent)
with an LLM, deduplicates against existing leads, scores each 0-100 for agent actionability, and
streams new leads to a React dashboard in realtime. Also matches new leads against saved searches
and raises in-app alerts. Runs from a single process: the scan worker is owned by the FastAPI
lifespan, so `uvicorn app.api.main:app` starts API + scanner + realtime together. No separate
scheduler. `README.md` and `IMPLEMENTATION_PLAN.md` have the long-form detail.

## Stack (and why)

- **Python 3.11 + FastAPI** — async API and the lifespan hook that owns the worker; one process, no scheduler service.
- **PostgreSQL + pgvector** — relational lead store; pgvector column reserved for Phase 2 embedding dedup.
- **SQLAlchemy 2.0 (sync ORM)** — pipeline is synchronous by design; worker runs it in a thread.
- **httpx** — fetches Zameen search pages; no headless browser needed (data is in an embedded JSON blob).
- **Gemini (`gemini-flash-latest`) via google-genai** — LLM extraction on free tier; provider-agnostic layer with a heuristic fallback.
- **Redis** — provisioned (compose + config) for future rate-limit buckets / cross-process fan-out; not yet wired.
- **React 19 + Vite + TanStack Query + Tailwind v4 + react-router 7** — realtime SPA; lint is oxlint, not ESLint.
- **pydantic-settings** — all config from `.env`, single place to swap in a secrets manager.

## Folder map

```
app/
  config.py            # pydantic-settings; every knob + env var, no hardcoded secrets
  logging_config.py    # structured event logging (scan.started, lead.saved, ...)
  serializers.py       # Lead -> dashboard JSON, shared by API and worker (one contract)
  leads_query.py       # apply_filters(): the SQL leads-list + saved-search matching both use
  scan.py              # CLI entry: one cycle / --dry-run / --watch
  seed_demo.py         # offline demo rows, no API key
  db/                  # models.py, session.py, init_db.py (idempotent + additive migrations), cleanup.py
  sources/             # base.py (SourceAdapter), zameen_web.py (live scraper), zameen.py (adapter), apify.py
  extraction/          # base.py, gemini.py, heuristic.py (fallback), service.py (pick + merge + resilience), schema.py
  pipeline/            # ingest.py (the cycle), dedup.py, scoring.py, classify.py, urls.py, normalize.py, validation.py, photos.py
  notifications/       # criteria.py, matching.py (saved-search alerts)
  realtime/            # broker.py (in-process pub/sub)
  worker/              # scanner.py (the background loop, backoff, lifespan-managed)
  api/                 # main.py (routes + lifespan), leads.py, saved_searches.py, notifications.py, agents.py, realtime.py (WS/SSE)
tests/                 # pytest; async broker tests marked asyncio
dashboard/             # React/Vite SPA (live app)
dashboard_app_tmp/     # stale scratch copy — ignore
```

## How to run

Backend (repo root, venv active):
- `docker compose up -d` — Postgres (pgvector) + Redis
- `uvicorn app.api.main:app --reload` — whole system (API + scanner + realtime). The lifespan runs `init_db` on boot (create tables, apply additive migrations, backfill facets, seed source — all idempotent), so no separate DB step is needed.
- `python -m app.db.init_db` — run the same bootstrap manually (diagnostics; the server already does this on startup)
- `python -m app.db.init_db --refresh-facets` — recompute derived `city`/`property_type` after editing `pipeline/classify.py`
- `python -m app.scan --source zameen` — one manual cycle (diagnostics)
- `python -m app.scan --dry-run` — fetch + extract + print, no DB write
- `python -m app.scan --watch` — worker standalone (set `SCAN_ENABLED=false` on the API)
- `python -m app.seed_demo` — offline demo data
- `pytest` — full suite; `pytest tests/test_dedup.py::test_name` — single test
- `ruff check .` / `ruff format .` — lint / format (line length 100)

Dashboard (`dashboard/`):
- `npm install && npm run dev` — http://localhost:5173
- `npm run build` — `tsc -b && vite build`; `dashboard/dist` is auto-served by FastAPI at `/dashboard`
- `npm run lint` — oxlint

Health check the automation: `curl localhost:8000/api/scan/status`.

## Architecture decisions and constraints

**One pipeline, two callers.** `app/pipeline/ingest.py::run_scan_cycle` is the entire cycle and is
synchronous + framework-free: the worker runs it in a thread, the CLI calls it directly. Do not
fork a second implementation. Cost ordering is deliberate: the two cheap filters (publish-time
watermark, already-ingested id check) run *before* the LLM, so a typical 30s cycle makes zero LLM
calls.

**Scraping provider + rate rules.** Source is Zameen's own server-rendered search payload
(`app/sources/zameen_web.py`), read from the `window.state` JSON blob (`algolia.content.hits`) —
no token, no headless browser, breaks less than DOM scraping. Rules to keep:
- Identify as an ordinary browser (`_HEADERS` UA), poll at a modest configurable cadence (`SCAN_INTERVAL_SECONDS`, min 5s). Do not add evasion, proxy rotation, or aggressive concurrency — this is polite polling, not scraping around a block.
- One request per configured search path per cycle; append `?sort=newest` so the first page is enough. Posts are interleaved round-robin across paths so prolific categories don't starve the others.
- A failed path is logged and skipped; the cycle only fails if every path fails.
- The watermark (`scan_state.last_posted_at`) advances only from a real listing publish time, never the run clock — otherwise an offline/fixture cycle would skip live listings.

**LLM/NLP extraction.** Runs in `app/extraction/` per new listing, orchestrated by
`service.py`. Default model Gemini `gemini-flash-latest` (`EXTRACTION_MODEL`). Source facts from
Zameen (price/area/bedrooms/location/contact) are authoritative and override the model; the model
only fills gaps the portal omits (intent nuance, owner-vs-agent, summary). On any LLM error/quota
failure it degrades to the heuristic extractor (`EXTRACTION_FALLBACK_ENABLED`) so lead production
never stops. Service is a process-wide singleton (Gemini client holds sockets).

**Dedup** (`app/pipeline/dedup.py`), three layers cheapest-first: (1) already-ingested query on
`raw_posts(source_id, external_id)` before extraction; (2) content key `sha256(phone|price|area|bedrooms)`
so a repost under a new ad id collapses onto the existing lead; (3) DB `UNIQUE(leads.dedup_key)` as
the concurrency backstop — the losing racer catches `IntegrityError` and counts a duplicate. Same
"let the DB reject the second writer" pattern guards alerts (`UNIQUE(saved_search_id, lead_id)`).

**Lead scoring** lives in `app/pipeline/scoring.py::score_lead` — transparent additive 0-100
(base 50, +weights for reachable contact, direct owner, clear intent, data completeness, extraction
confidence). Computed at ingest so the realtime feed is sortable immediately.

**Notifications.** Saved searches are persisted `LeadFilters`; `app/notifications/matching.py`
tests them with the *same* `apply_filters` SQL the leads list uses (one query per search over the
cycle's new ids, not per lead) so an alert never disagrees with the list it links to. Only the
**dashboard/in-app** channel is implemented (rows + realtime push). Slack / WhatsApp / webhook are
enum placeholders in the `Notification.channel` model, not built. Throttled by
`ALERTS_MAX_PER_SEARCH_PER_HOUR` and `ALERTS_MAX_PER_CYCLE`.

**Realtime** (`app/realtime/broker.py`) is in-process pub/sub over `/ws/leads` (WS) and
`/api/stream` (SSE). Bounded per-subscriber queue drops oldest events on lag; cleanup in `finally`.

**Derived columns.** `leads.city` and `leads.property_type` are computed at ingest
(`pipeline/classify.py`) and persisted so the list filters/facets/paginates in SQL. Re-run
`init_db --refresh-facets` after changing classify rules.

**Dashboard auth is client-side only** (`dashboard/src/lib/auth.tsx`, localStorage). No backend
auth exists. `Role` types (admin/analyst/agent) are defined but `App.tsx` wires only admin routes.

## Env vars (names only; see `.env.example`)

`DATABASE_URL`, `REDIS_URL`, `APIFY_TOKEN`, `GEMINI_API_KEY`, `EXTRACTION_MODEL`,
`ESCALATION_MODEL`, `EXTRACTION_CONFIDENCE_THRESHOLD`, `EXTRACTION_ENABLED`,
`EXTRACTION_FALLBACK_ENABLED`, `SCAN_ENABLED`, `SCAN_INTERVAL_SECONDS`,
`SCAN_STARTUP_DELAY_SECONDS`, `SCAN_SOURCES`, `SCAN_PAGE_SIZE`, `SCAN_BACKFILL_LIMIT`,
`SCAN_MAX_NEW_PER_CYCLE`, `SCAN_ERROR_BACKOFF_SECONDS`, `SCAN_ERROR_BACKOFF_MAX_SECONDS`,
`ZAMEEN_BASE_URL`, `ZAMEEN_SEARCH_PATHS`, `ZAMEEN_REQUEST_TIMEOUT_SECONDS`, `ALERTS_ENABLED`,
`ALERTS_MAX_PER_SEARCH_PER_HOUR`, `ALERTS_MAX_PER_CYCLE`, `REALTIME_QUEUE_SIZE`,
`REALTIME_HEARTBEAT_SECONDS`, `LOG_LEVEL`, `LOG_JSON`, `CORS_ALLOW_ORIGINS`.

Only `DATABASE_URL` is required; `GEMINI_API_KEY` unlocks LLM extraction (heuristic runs without it).

## Conventions

- **Config**: every knob and secret goes through `app/config.py` (pydantic-settings). Never hardcode a value or read `os.environ` directly.
- **Logging**: structured events with context fields (`log.info("lead.saved", extra={...})`), not free-text. `LOG_JSON=true` for NDJSON.
- **Error handling**: per-listing failures are caught, logged, and skipped (one bad ad must not abort a cycle); fetch-level failures raise so the worker applies jittered exponential backoff. Notification/matching code never raises into the cycle.
- **File naming**: lowercase `snake_case.py` modules; one concern per pipeline module.
- **Adding a source**: implement a `SourceAdapter` in `app/sources/`, then register it in `ADAPTERS` in `app/pipeline/ingest.py`. Facts the source states authoritatively go in the adapter's `facts` dict (they override the LLM). Nothing else changes.
- **The dashboard contract** is `app/serializers.py` + `main.py::build_dashboard_payload`; every number is a real aggregate. Do not invent metrics or fake percentages.

## Do not

- Do not scrape behind logins, paywalls, or captchas; do not add proxy rotation or request-rate evasion. Stay on the public search payload at a polite cadence.
- Do not substitute a homepage/search/fallback URL for a missing ad link. A URL is stored only if `app/pipeline/urls.py` confirms it identifies one advertisement; otherwise store NULL ("Unavailable").
- Do not commit secrets or `.env`; do not hardcode API keys or connection strings — route through `config.py`.
- Do not advance the scan watermark from wall-clock time.
- Do not reimplement lead-filter predicates in Python; reuse `apply_filters` so list and alerts stay identical.
- Do not construct a Gemini client per cycle; use the `get_extraction_service()` singleton.
