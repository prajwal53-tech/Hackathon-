# Smart Bus Optimization Challenge

A 36-hour hackathon prototype: real-time bus simulation, rule-based scheduling, EWMA ridership forecasting, and a live dashboard with map, charts, and alerts.

## Features
- Realtime simulators: GPS bus movement + ticket events
- Scheduling engine: rule-based, uses EWMA forecasts to advance/delay stops
- Forecasting: lightweight EWMA per (route, stop)
- SSE stream + REST: `/sse`, `/static`, `/health`
- Dashboard: map (buses + stops), ridership chart, schedules table, alerts
- One-command dev run; minimal deps; works on Python 3.13

## Quick Start

Prereqs: Node 18+ and Python 3.10+ (tested on 3.13)

```bash
# From repository root
# 1) Create venv (we already vendored a script-free approach via virtualenv)
python3 -m pip install --user virtualenv --break-system-packages || true
~/.local/bin/virtualenv .venv
source .venv/bin/activate

# 2) Install backend deps
pip install -r backend/requirements.txt

# 3) Run backend
./scripts/dev_backend.sh
# Serves on http://localhost:8000

# 4) Install frontend deps & run
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
# Open http://localhost:5173
```

## API
- `GET /health` -> `{ ok: true }`
- `GET /static` -> `{ stops: Stop[], routes: Route[], schedule: Schedule[] }`
- `GET /sse` -> server-sent events: `ticket`, `buses`, `schedule_opt`

## Tech
- Backend: FastAPI, Uvicorn, SSE, structlog
- Frontend: Vite + React + TS, Recharts, Leaflet

## Notes
- Scheduling and forecasts are intentionally simple to keep the demo robust.
- You can extend the scheduler to use queue lengths, dwell times, and ML models.