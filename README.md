# Automated Property Lead Intelligence System

Backend pipeline that scans online property sources (Facebook Marketplace, Zameen, OLX,
Graana, FB Groups, Instagram), extracts structured lead data with an LLM, deduplicates,
scores, and routes qualified leads to agents, with a light dashboard on top.

See `IMPLEMENTATION_PLAN.md` for the full stack decision, concrete component choices, and
phased build order.

## Stack

- **Backend / pipeline:** Python (FastAPI) + Celery + Redis
- **Data:** PostgreSQL + pgvector
- **Scraping:** Apify (primary)
- **LLM extraction:** Claude Haiku 4.5 (escalates to Sonnet 4.6 on low confidence)
- **Dashboard:** React (Vite) — added in Phase 1b

## Layout

```
app/
  config.py         # pydantic-settings, all secrets/config
  db/               # engine, session, models (Phase 1a)
  sources/          # Apify-backed source adapters
  extraction/       # LLM structured extraction
  pipeline/         # filter -> extract -> dedup -> score -> notify
  api/              # FastAPI read routes for dashboard
  notifications/    # pluggable Notifier channels
tests/
dashboard/          # React/Vite SPA (Phase 1b)
docker-compose.yml  # local Postgres(pgvector) + Redis
requirements.txt
.env.example        # copy to .env and fill in
```

## Local setup

```bash
# 1. Infra
docker compose up -d

# 2. Python env
python -m venv .venv
# Windows: .venv\Scripts\activate   |  Unix: source .venv/bin/activate
pip install -r requirements.txt

# 3. Secrets
cp .env.example .env   # then fill in APIFY_TOKEN and ANTHROPIC_API_KEY
```

Feature build (Phase 1a onward) begins after scaffolding. Nothing runs end-to-end yet.
