# AI Property Intelligence Dashboard

Premium, interactive frontend command center for Pakistan real estate lead intelligence.

## Stack

- React + TypeScript + Vite
- Tailwind CSS (v4)
- Framer Motion
- Lucide React
- TanStack Query

## Features

- Dark premium AI SaaS aesthetic with glassmorphism and gradients
- Animated KPI stat cards
- Live intelligence feed, updated over a WebSocket (no polling, no refresh)
- AI lead scoring panel
- Source monitoring cards
- Extraction pipeline visualization
- Searchable, filterable, sortable, paginated lead table
- CSV export
- Lead details slide-in drawer
- AI insights cards
- Notification center

## Run

```bash
cd dashboard
npm install
npm run dev
```

Open:

- http://localhost:5173

## Build

```bash
cd dashboard
npm run build
npm run preview
```

## Notes

- All data comes from the live backend (`/api/dashboard/overview`, `/api/leads`); there is no
  mock data. Start the backend first or the dashboard renders empty states.
- New leads arrive over `/ws/leads` and are written straight into the query cache, so the
  table updates without a refetch. Polling remains only as a 2-minute fallback.
- There are deliberately no charts. The aggregates that backed them were mostly constant or
  permanently zero, so the charting layer and its `recharts` dependency were removed — this
  roughly halved the production bundle (835kB → 439kB).
