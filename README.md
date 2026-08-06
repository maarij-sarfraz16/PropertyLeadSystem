# Automated Property Lead Intelligence System

Continuously monitors online property sources, extracts structured lead data with an LLM,
deduplicates, scores, and streams new leads to a live dashboard — with a working deep link to
the original advertisement on every lead.

The system is **fully automated**. Start the backend and leads appear on the dashboard by
themselves, within seconds of being published. No manual scan command is involved.

```
New property published on Zameen
        ↓  background worker, every SCAN_INTERVAL_SECONDS
Automatic detection (publish-time watermark)
        ↓
Scraping (search payload → structured fields + canonical ad URL)
        ↓
AI extraction (Gemini, with a rule-based fallback)
        ↓
Deduplication (already-seen → content key → UNIQUE constraint)
        ↓
PostgreSQL
        ↓
Realtime push (WebSocket, SSE fallback)
        ↓
Dashboard updates without a refresh
        ↓
User clicks the lead → the original Zameen advertisement opens
```

## Stack

- **Backend / pipeline:** Python, FastAPI, asyncio background worker
- **Data:** PostgreSQL + pgvector
- **Scraping:** Zameen's own server-rendered search payload (no token); Apify optional per source
- **LLM extraction:** Gemini (`gemini-flash-latest`), provider-agnostic, with a deterministic fallback extractor
- **Realtime:** WebSocket `/ws/leads`, Server-Sent Events `/api/stream`
- **Dashboard:** React (Vite) + TanStack Query

## Quick start

```bash
# 1. Infra (Postgres + Redis)
docker compose up -d

# 2. Python env
python -m venv .venv
# Windows: .venv\Scripts\activate   |  Unix: source .venv/bin/activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env        # optional: add GEMINI_API_KEY for LLM extraction

# 4. Database (idempotent; also applies additive migrations)
python -m app.db.init_db

# 5. Run everything — API + scanner + realtime, one process
python -m uvicorn app.api.main:app --reload

# 6. Dashboard
cd dashboard && npm install && npm run dev
```

Open http://localhost:5173. New listings appear on their own; no refresh, no CLI command.

Verify the automation is alive:

```bash
curl localhost:8000/api/scan/status
```

## How it works

### Automatic detection

`app/worker/scanner.py` runs a loop inside the API process, started by the FastAPI lifespan.
Each cycle runs in a worker thread (`asyncio.to_thread`), so scraping and LLM calls never
block request handling.

Newly published listings are identified by a **watermark**: `scan_state.last_posted_at` holds
the newest publish time already ingested, and the Zameen search payload reports each ad's
`createdAt`. A cycle only considers listings published after the watermark, so re-scanning the
same page costs one HTTP request and zero LLM calls.

Failures are survivable: a failed cycle is logged, recorded on the source's scan state, and
retried with jittered exponential backoff (`SCAN_ERROR_BACKOFF_SECONDS` → `..._MAX_SECONDS`).
The loop only stops on shutdown, which is graceful — the interval sleep is interruptible, and
the in-flight cycle gets a bounded window to finish.

### Realtime updates

`app/realtime/broker.py` is an in-process pub/sub. The worker publishes `lead.created`,
`scan.completed` and `dashboard.updated`; every connected client receives them over
`/ws/leads` (WebSocket) or `/api/stream` (SSE).

Each subscriber has a bounded queue — a lagging client drops its oldest events instead of
growing the server's memory. Subscriptions are released in a `finally` block, so every
dropped connection is cleaned up.

On the client, `dashboard/src/hooks/useLeadStream.ts` writes each pushed lead straight into
the TanStack Query cache, so the table updates instantly; `dashboard.updated` invalidates the
aggregate query so the metric tiles follow. Reconnects use a capped backoff, and two failed
WebSocket attempts switch the client to SSE. Polling remains only as a 2-minute safety net.

### Deduplication

Three layers, cheapest first (`app/pipeline/dedup.py`):

1. **Already ingested** — one batched query per cycle against `raw_posts (source_id, external_id)`.
   This runs *before* extraction, so duplicates never reach the LLM.
2. **Content key** — `sha256(phone | price | area | bedrooms)`, so the same property reposted
   under a new ad id, or seen on two search paths, collapses onto one lead. A duplicate links
   its raw post to the existing lead and refreshes `last_seen_at`.
3. **UNIQUE constraint** on `leads.dedup_key` — concurrent cycles cannot race a duplicate in;
   the loser catches `IntegrityError` and records a duplicate.

### Original listing URLs

The old behaviour sent users to the Zameen homepage, which renders "Ad not found". Three
causes, all fixed:

- Demo/fixture rows carried hand-written zameen.com paths for ads that never existed. Fixture
  URLs now point at `example.com` so they can never be mistaken for real ads, and
  `python -m app.db.cleanup --demo --apply` removes the old rows.
- The scraper never captured a real URL. It now reads the listing `slug` from the search
  payload and builds the canonical `https://www.zameen.com/Property/<slug>.html`.
- Nothing validated URLs. `app/pipeline/urls.py` accepts a URL only if it identifies a single
  advertisement; a homepage, search page or blog URL is rejected. **A missing URL is stored as
  NULL and rendered "Unavailable" — it is never replaced with a fallback page.**

The URL is stored on `raw_posts.url` exactly as scraped and denormalized to `leads.listing_url`,
so the dashboard renders it without a join.

### Logging

Structured events (`app/logging_config.py`), each with context fields:
`scan.started`, `scan.fetched`, `listing.new`, `listing.duplicate`, `extraction.completed`,
`lead.saved`, `dashboard.updated`, `scan.error`, `scan.retry_scheduled`, `worker.started`,
`worker.stopped`. Set `LOG_JSON=true` for newline-delimited JSON.

## Configuring the scan interval

`SCAN_INTERVAL_SECONDS` in `.env` (default 30; minimum 5):

```bash
SCAN_INTERVAL_SECONDS=10    # development: near-instant feedback
SCAN_INTERVAL_SECONDS=300   # production: kinder to the source
```

Related knobs: `SCAN_PAGE_SIZE`, `SCAN_MAX_NEW_PER_CYCLE` (caps LLM spend per cycle),
`SCAN_BACKFILL_LIMIT`, `SCAN_SOURCES`, `ZAMEEN_SEARCH_PATHS` (add cities/categories),
`SCAN_ENABLED`. All documented in `.env.example`.

To run scanning as its own process instead of inside the API, set `SCAN_ENABLED=false` on the
API and run `python -m app.scan --watch`.

## Commands

| Command | Purpose |
| --- | --- |
| `uvicorn app.api.main:app` | **The whole system**: API + scanner + realtime |
| `python -m app.db.init_db` | Create tables, apply migrations, seed the source |
| `python -m app.scan --source zameen` | One manual cycle (diagnostics) |
| `python -m app.scan --dry-run` | Fetch + extract + print, no DB write — checks listing URLs |
| `python -m app.scan --watch` | Run the worker standalone |
| `python -m app.seed_demo` | Offline demo rows, no API key needed |
| `python -m app.db.cleanup --demo --dead-links` | Find leads that cannot be opened (dry run) |
| `pytest` | Test suite |

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/leads` | Filtered, sorted, paginated leads — see below |
| `GET /api/leads/facets` | Distinct filter values and ranges across the whole table |
| `GET /api/leads/{id}` | Lead detail: description, gallery, AI fields, raw metadata |
| `PATCH /api/leads/{id}/status` | Move a lead to `new` / `reviewed` / `assigned` / `archived` |
| `GET /api/dashboard/overview` | Metric tiles, feed, insights, sources — all from real aggregates |
| `GET /api/scan/status` | Worker state, per-source watermarks, realtime stats |
| `GET /api/metrics`, `/api/health` | Counters and health |
| `WS /ws/leads` | Realtime event stream |
| `GET /api/stream` | Same stream over SSE |

### Browsing leads

`GET /api/leads` filters, sorts and pages **in SQL**, so every query runs against the full lead
history rather than a recently-fetched window, and `total` is the real match count.

| Param | Notes |
| --- | --- |
| `search` | Title, description, location, city, property type, contact |
| `city`, `source`, `sellerType`, `propertyType`, `status` | Repeatable (`?city=A&city=B`) or comma-joined; case-insensitive |
| `minScore`, `maxScore`, `minPrice`, `maxPrice` | Inclusive bounds |
| `dateFrom`, `dateTo` | ISO instant or `YYYY-MM-DD`, filtered on `first_seen_at`. A bare date means the whole UTC day |
| `sort` | `newest` (default), `oldest`, `price_high`, `price_low`, `score_high`, `score_low` |
| `page`, `pageSize` | 1-based; `pageSize` max 200 |

Response: `{ items, total, page, pageSize, totalPages, hasMore }`.

`leads.city` and `leads.property_type` are derived at ingest (`app/pipeline/classify.py`) so they
can be filtered on. After changing those rules, reclassify existing rows with:

```bash
python -m app.db.init_db --refresh-facets
```

## Layout

```
app/
  config.py           # pydantic-settings; every knob, no hardcoded secrets
  logging_config.py   # structured logging
  serializers.py      # Lead -> dashboard JSON, shared by API and worker
  db/                 # models, session, init/migrations, cleanup
  sources/            # zameen_web.py (live scraper), zameen.py (adapter), apify.py
  extraction/         # gemini.py, heuristic.py (fallback), service.py (merge + resilience)
  pipeline/           # ingest.py (the cycle), dedup.py, scoring.py, urls.py, normalize.py
  realtime/           # broker.py (pub/sub)
  worker/             # scanner.py (background loop)
  api/                # main.py (routes + lifespan), realtime.py (WS/SSE)
tests/
dashboard/            # React/Vite SPA
```

See `IMPLEMENTATION_PLAN.md` for the original stack decisions and phased build order.
