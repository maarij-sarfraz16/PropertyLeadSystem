# Automated Property Lead Intelligence System — Implementation Plan

## Context

Building the system described in `Real_Estate_Lead_Automation_Proposal.docx`. Goal: a
backend pipeline that continuously scans online property sources (Facebook Marketplace,
Zameen, OLX, Graana, FB Groups, Instagram), extracts structured lead data with LLM,
deduplicates, scores, and routes qualified leads to agents within minutes — with a light
dashboard on top. Replaces slow walk-in/referral lead flow with a 24/7 "radar."

The project root is `C:\A-WORK\mRealEstate` (build directly here, no nested app subfolder).
Currently empty except the proposal doc. Greenfield.

**User decisions (this session):**
- Hosting: **local dev only for now** — build to run via Docker Compose on the dev machine;
  defer prod hosting. Keep it cloud-portable.
- First notification channel: **dashboard first**, expand to Slack/WhatsApp/CRM later.

---

## Stack Decision

**Pick: Python (FastAPI) backend + React (Vite) dashboard + PostgreSQL + Redis + Celery.**

This system is ~80% backend data pipeline, ~20% dashboard. The decision follows the work,
not language preference.

| Option | Verdict | Why |
|---|---|---|
| **Python FastAPI + React SPA** | **CHOSEN** | Python owns the pipeline: mature libs for image perceptual hashing (`imagehash`/Pillow), embeddings (`sentence-transformers`), dedup (pandas), scheduling/retry/rate-limit (Celery+Redis), Playwright, and clean LLM SDKs. FastAPI = typed async API. React/Vite = enough for a light dashboard (no SSR needed). |
| Next.js full-stack | Rejected | API routes are request-scoped; long-running scheduled scrapers and worker queues fight the serverless model. You end up bolting on a separate worker process anyway — at which point the split stack is unavoidable, so make the worker Python where the data ecosystem lives. |
| MERN | Rejected | Node lacks first-class image hashing and ML tooling; you would shell out to Python for dedup/embeddings regardless. Mongo is a poor fit for relational leads needing unique constraints, price/geo indexes, and vector similarity. |

**Why Postgres over Mongo:** leads are relational (canonical lead ↔ many source posts),
dedup needs unique constraints + geo/price indexes, and `pgvector` gives embedding similarity
search in-DB — no separate vector store.

---

## Concrete Decisions

### 1. Scraping provider — **Apify (primary)**, ScraperAPI (cost-optimization, later)
- **Apify** for anti-bot-heavy sources (FB Marketplace, Groups, Instagram): pre-built Actors
  return structured JSON, handle proxy rotation + CAPTCHA + dynamic content internally. Matches
  the proposal's core principle: don't build anti-bot evasion in-house. Apify MCP is already
  available in this environment for Actor discovery/testing.
- **ScraperAPI + custom parsers** deferred to Scale phase for high-volume structured portals
  (Zameen/Graana/OLX have stable HTML) to cut per-listing cost. Pilot uses Apify only for speed.

### 2. NLP/LLM extraction — runs in the **Celery worker**, model **Gemini 2.5 Flash**
- Provider-agnostic extraction layer (`app/extraction`) so the model can be swapped without
  touching the pipeline. Gemini chosen for the pilot: **free tier** via Google AI Studio lets us
  validate extraction accuracy at zero cost, Flash is cheap at scale, and it handles
  Urdu/Roman-Urdu listings well. Claude Haiku/Sonnet remain drop-in alternatives.
- Two-stage in the pipeline (never in the dashboard):
  1. **Cheap pre-filter** (keyword/regex) drops obvious non-listings before spending tokens.
  2. **Gemini 2.5 Flash** structured extraction via **`response_schema` (strict JSON)**
     (location, price, area, bedrooms, contact phone, seller intent, seller type).
  3. **Confidence gate** → low-confidence posts escalate to **Gemini 2.5 Pro**.
- Free-tier caveats: rate limits (low RPM/daily cap — fine for pilot, throttle or go paid at
  scale) and free-tier requests may be used by Google for training (data is public listings,
  low sensitivity; flag for legal sign-off). Dedup embeddings use a local
  `sentence-transformers` model (offline, deterministic), not the LLM.

### 3. Deduplication — **multi-signal, phone-first**
- **Hard key:** normalized `contact_phone` (E.164). Exact match = same seller/listing across
  platforms → instant dedupe. Strongest signal, cheapest.
- **Soft match:** candidate block = same geo bucket + price within ±5%, then confirm by
  **either** perceptual image hash (`pHash`, Hamming distance ≤ ~10) **or** text embedding
  cosine ≥ ~0.85 (title+description via `all-MiniLM` in pgvector).
- Store one **canonical lead** linked to many **source posts** (`lead_sources` join). Update
  `last_seen_at` on re-sightings rather than creating a new lead.

### 4. Scheduler / queue — **Celery + Redis (+ Celery Beat)**
- Beat schedules periodic per-source scan tasks; Redis is broker + result backend + hot dedup
  cache + rate-limit token buckets. Separate worker queues per source so one blocked/slow
  source can't stall others. Built-in retries + exponential backoff on 429/blocks.

### 5. Data store & schema — **PostgreSQL + pgvector**
Core tables:
- `sources` — id, name, type, config JSONB, scan_interval, enabled
- `raw_posts` — id, source_id, external_id, url, raw_json, scraped_at; unique(source_id, external_id)
- `leads` (canonical) — id, intent (buy/sell/rent/wanted), location_text, geo(lat/lng),
  area_value/unit, price, currency, bedrooms, seller_type (owner/agent), contact_phone (E.164),
  contact_name, description, first_seen_at, last_seen_at, status, score,
  embedding `vector`, primary_photo_phash
- `lead_sources` — lead_id ↔ raw_post_id (many source posts per canonical lead)
- `photos` — id, lead_id, url, phash
- `notifications` — id, lead_id, channel, sent_at, status, agent_id
- `agents` / `users`
> **Schema-forward note:** the `leads` schema captures phone + photos + description **from
> Phase 1**, even though dedup/scoring arrive in Phase 2 — avoids migration churn later.

### 6. Notification layer — pluggable `Notifier` interface
- Abstract `Notifier` with channel adapters. **Dashboard first** (user choice): qualified leads
  land in a reviewable dashboard list. Then add **Slack** (incoming webhook, trivial), then
  **WhatsApp** (Twilio WhatsApp for fast start → migrate to Meta Cloud API at scale), plus a
  **generic outbound webhook** so any CRM (HubSpot/Zoho/Make/Zapier) can subscribe without
  custom code. Notifications are deduped so a lead pings once.

### 7. Secrets & rate-limit / rotation
- **Secrets:** `.env` (git-ignored) loaded/validated via `pydantic-settings`; no keys in code.
  Formalize a secrets manager (Doppler / cloud secrets) when prod hosting is chosen.
- **Rate limits:** per-source token bucket in Redis + Celery `rate_limit` + jitter + exponential
  backoff on 429/blocks; per-source concurrency caps.
- **Rotation:** Apify residential proxies handle rotation for anti-bot sources internally;
  ScraperAPI rotating proxies for the later custom-parser path. Per-source **circuit breaker** —
  if block-rate spikes, back that source off automatically.

---

## Implementation Phases (vertical slices, mapped Pilot → Automation → Scale)

Each phase is independently runnable and testable and ends in a working slice. Ordered to
validate the biggest unknown (extraction accuracy) earliest, before investing in infra.

### Phase 1a — Prove extraction (one-shot, no scheduler) — *Pilot*
Thinnest end-to-end: `python -m app.scan --source zameen` fetches one source via Apify →
Gemini structured extraction → writes `leads` rows to Postgres → prints a table.
- **Deliverable:** real structured leads from real posts, viewable via CLI/query.
- **Test:** run manually, eyeball extraction accuracy on ~50 posts. This de-risks the LLM
  schema before any queue/dashboard work.
- **Includes:** Docker Compose (Postgres+Redis), settings/secrets, Apify client, the full
  `leads` schema, Gemini extraction with `response_schema` JSON.
- **Status (2026-07-29): BUILT.** DB + schema + adapter (with offline fixtures) + Gemini
  extractor + `scan` CLI done. Offline-verified: 9 unit tests pass, lint clean, Postgres
  initialized (7 tables, pgvector). Live extraction run pending a free `GEMINI_API_KEY`.

### Phase 1b — Schedule it + minimal dashboard — *Pilot*
Wrap 1a in **Celery Beat** (periodic scans) + a **Source adapter interface** (one source now,
config-driven so adding sources later is config, not code) + a minimal **React/Vite dashboard**
listing leads (read-only table, manual review). Expand to a 2nd source (FB Marketplace).
- **Deliverable:** a running radar for 1–2 sources; agents review extracted leads in a browser.
- **Test:** start stack, watch scheduled scans populate the dashboard; manually validate accuracy.
- **Maps to proposal Phase 1** (monitor FB Marketplace + Zameen, manual review).

### Phase 2a — Filter + dedup + scoring — *Automation*
Add pipeline stages, each unit-testable in isolation:
- **Pre-filter classifier** (keyword/regex) drops non-listings before LLM (cost control).
- **Dedup engine** — phone-first + geo/price block + pHash/embedding confirm; canonical lead
  + `lead_sources`. Fixture-based unit tests.
- **Scoring engine** — deterministic function of freshness, price fit vs target areas, area
  match, seller type (owner > agent). Pure function → unit-testable. Dashboard shows score
  + dedup groupings; still human-reviewed.
- **Test:** feed duplicate/near-duplicate fixtures → one canonical lead; scoring ranks correctly.

### Phase 2b — Notifications + multi-source — *Automation*
Gate notifications on score threshold (dedup runs **before** notify so no double-pings). Ship
`Notifier` with **Slack** + **generic webhook** adapters (dashboard already exists from 1b);
scaffold WhatsApp (Twilio). Expand source configs to 4–5 sources.
- **Deliverable:** a genuinely new qualified post flows scrape → filter → extract → dedup →
  score → notify, end to end, across 4–5 sources.
- **Test:** inject a fresh high-score fixture → agent receives one Slack/webhook alert.
- **Maps to proposal Phase 2** (NLP filtering, scoring, notifications, 4–5 sources).

### Phase 3 — Scale — *Scale (ongoing)*
- Full **management dashboard**: leads/day, per-source performance, per-area breakdown,
  conversion tracking; **agent assignment + lead status workflow**.
- **CRM webhook** integration; **A/B source performance** metrics.
- **Cost/robustness hardening:** swap high-volume portals to ScraperAPI+custom parser, add a
  local embedding pre-classifier to cut LLM spend, per-source circuit breakers, proxy-rotation
  hardening, formal secrets manager, multi-city source configs. WhatsApp → Meta Cloud API.
- **Maps to proposal Phase 3.**

---

## Self-Critique (build order tightened)

- **Split original Phase 1** into 1a (one-shot extraction) + 1b (scheduler+dashboard). Reason:
  extraction accuracy is the biggest unknown and the whole system's value depends on it —
  validate it with a manual run *before* building Celery/dashboard infra around it.
- **Schema-forward leads table in Phase 1.** Dedup (phone/phash) and scoring (seller_type,
  price, freshness) need fields that must be captured at extraction time. Designing the full
  `leads` schema in Phase 1 avoids painful migrations in Phase 2.
- **Dedup strictly before scoring/notify.** Scoring or notifying duplicates wastes agent time
  and double-contacts owners. Order inside Phase 2: filter → extract → dedup → score → notify.
  This ordering was verified, not assumed.
- **Source adapter interface lands in 1b** (with one source) so Phase 2's multi-source
  expansion is config, not a rewrite.
- **Secrets hygiene from day 1** (`.env` + pydantic-settings), manager formalized only when
  prod hosting is chosen — matches the "local dev for now" decision without leaving keys in code.
- **Cost controls staged:** cheap keyword pre-filter in 2a; heavier local-embedding classifier
  and ScraperAPI custom parsers deferred to Phase 3 where volume justifies the effort.

---

## Verification (per phase)

- **1a:** `docker compose up -d db`, run `python -m app.scan --source zameen`, query `leads`;
  manual accuracy check on a sample.
- **1b:** `docker compose up`; confirm Beat triggers scans and dashboard table fills; add 2nd source.
- **2a:** `pytest` on dedup + scoring fixtures (duplicates collapse to one lead; scores ordered
  correctly); dashboard shows dedup groups + scores.
- **2b:** inject fresh high-score fixture → exactly one Slack/webhook alert; verify 4–5 sources
  ingest.
- **3:** dashboard analytics reconcile with DB counts; CRM webhook receives payloads; A/B and
  cost-optimization metrics tracked.
