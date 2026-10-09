# Pakistan Early Warning System

District-level weather monitoring and lifecycle-managed hazard alerts for Pakistan.
The platform fetches Open-Meteo forecasts, screens them against configurable
thresholds, preserves the evidence behind every alert, and presents current and
historical alerts on an interactive map.

## Stack

- **API:** FastAPI, SQLAlchemy and Alembic under `backend/`
- **Database:** PostgreSQL 16
- **Web:** React 19, TypeScript, Vite and MapLibre under `frontend/`
- **Operations:** Docker Compose, with Windows helpers at `start.bat`, `stop.bat`
  and `run-cycle.bat`

## Run Locally

Docker Desktop is the only prerequisite for the complete stack.

```powershell
copy .env.example .env
start.bat
```

The dashboard opens at <http://localhost:5173>. The API is available at
<http://localhost:8000>, including interactive documentation at `/docs`.

To run a monitoring cycle over every registered district:

```powershell
run-cycle.bat
```

Stop the services without deleting PostgreSQL data:

```powershell
stop.bat
```

The equivalent cross-platform commands are:

```bash
docker compose up --build
docker compose exec api python -m ews.cycles.service
docker compose down
```

## Configuration

All settings are optional for local development.

| Variable | Purpose | Default |
| --- | --- | --- |
| `EWS_ADMIN_TOKEN` | Enables `POST /api/runs`; sent as `X-Admin-Token` | unset |
| `EWS_DB_PORT` | PostgreSQL host port | `5434` |
| `EWS_API_PORT` | API host port | `8000` |
| `EWS_WEB_PORT` | Dashboard host port | `5173` |
| `EWS_LOG_LEVEL` | API logging level | `INFO` |
| `EWS_FORECAST_DAYS` | Forecast horizon | `7` |
| `EWS_AIR_QUALITY_FORECAST_DAYS` | Air-quality horizon, capped to complete CAMS days | `5` |
| `EWS_FORECAST_MAX_AGE_SECONDS` | Stored-forecast freshness window | `10800` |
| `EWS_FORECAST_BATCH_SIZE` | Districts fetched per Open-Meteo request | `50` |
| `EWS_LLM_PROVIDER` | Language model provider: `lm_studio` or `groq` | `lm_studio` |
| `EWS_LLM_BASE_URL` | Chat-completions base URL | `http://localhost:1234/v1` for LM Studio, `https://api.groq.com/openai/v1` for Groq |
| `EWS_LLM_MODEL` | Model to call | whichever model LM Studio has loaded; `openai/gpt-oss-120b` on Groq |
| `EWS_LLM_API_KEY` | Provider key; required for Groq, where the API refuses to start without it | unset |
| `EWS_LLM_TEMPERATURE` | Sampling temperature | `0.2` |
| `EWS_LLM_TIMEOUT_SECONDS` | Budget for one model request, including rate-limit waits | `120` |
| `EWS_LLM_MAX_CONCURRENCY` | Model requests in flight at once | `1` for LM Studio, `2` for Groq |

Under Docker Compose, LM Studio running on the host is reached with
`EWS_LLM_BASE_URL=http://host.docker.internal:1234/v1`. `GET /api/health` reports
whether the configured model is available; a missing model does not make the API
unhealthy.

Backend-only settings such as `EWS_DATABASE_URL` use development defaults and can
be overridden when running the API outside Docker.

## Development

### Backend

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
docker compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run uvicorn ews.api.app:app --reload
```

### Frontend

Node.js 24 is used in CI.

```bash
cd frontend
npm ci
npm test
npm run lint
npm run typecheck
npm run build
npm run dev
```

When an API schema changes, regenerate both committed schemas:

```bash
cd backend
uv run python -m ews.api.openapi
cd ../frontend
npm run generate:api
```

## Architecture

Monitoring cycles fetch and persist source snapshots before screening daily values
against `backend/src/ews/screening/data/thresholds.yaml`. Signals issue, supersede,
cancel or expire append-only alert records. Every alert retains the source snapshot
and forecast values that justified it. The React client uses the generated OpenAPI
types to display forecasts, active alerts, evidence and alert history.

Source registry inputs live in `backend/data/source/`. Generated registry assets in
`backend/src/ews/districts/data/` must be rebuilt with:

```bash
cd backend
uv run python -m ews.districts.build
```

## License

Confidential - NEOC Internal Use Only.
