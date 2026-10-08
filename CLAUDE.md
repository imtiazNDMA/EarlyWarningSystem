# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Flask dashboard for district-level weather forecasting and bilingual (English/Urdu) early-warning alerts across Pakistan (NDMA/NEOC). Weather comes from Open-Meteo, alerts are written by a local LLM through Ollama, and everything is cached in SQLite and rendered onto a server-side Folium map.

## Commands

The project is managed with **uv** (`pyproject.toml` + `uv.lock`); there is no `requirements.txt`. Python must be >=3.10,<3.13 (`.python-version` pins 3.12).

```bash
uv sync                                # install runtime + dev dependencies
uv run python app.py                   # dev server on http://localhost:5001

uv run pytest tests/ -v                # all tests
uv run pytest tests/test_endpoints.py::TestFlaskEndpoints::test_index_get -v   # single test
uv run pytest tests/ -v --cov=. --cov-report=term                              # as CI runs it

uv run ruff check .                    # lint (CI gate)
uv run ruff format --check .           # format check (CI gate); drop --check to apply
```

- `config.py` calls `Config.validate()` at import time and raises if `MAPBOX_TOKEN` is unset. Anything that imports `app`, `config`, or a service — including the tests — needs a `.env` (copy `.env.example`) or `MAPBOX_TOKEN` in the environment. A dummy value is enough for tests.
- Run everything from the repo root: `weather.db`, `app.log`, and `static/boundary/district.geojson` are opened by relative path.
- Most tests are not isolated from the database: they import the real `app`, which calls `database.init_db()` and reads/writes `weather.db` in the working directory. `tests/test_alert_generation.py` shows the isolated pattern (temporary `DB_FILE`). Patch service methods on the class, not on the singletons in `extensions.py`.
- Linting is ruff only (line length 88, rule set in `pyproject.toml`, including bandit `S` rules and McCabe complexity 10). The flake8/black/bandit commands and the 100-char limit in `AGENTS.md` are outdated.
- `app.py` is the entry point. The dev server binds to `HOST` (default `127.0.0.1`); set `HOST=0.0.0.0` to expose it on the network.

## New backend (`backend/`)

The Flask app is being replaced by a FastAPI service, built alongside it in `backend/` until it reaches parity (plan in `ai.md`, tickets on GitHub). It is a separate uv project with its own `pyproject.toml`, lockfile and virtualenv; run its commands from `backend/`.

```bash
docker compose up -d db                # Postgres 16 on host port 5434 (override with EWS_DB_PORT)
docker compose up --build              # database + API on http://localhost:8000 (EWS_API_PORT)

cd backend
uv sync
uv run pytest                          # needs the db container running
uv run pytest tests/test_health.py::TestHealth::test_reports_healthy_when_database_is_reachable
uv run ruff check . && uv run ruff format --check .
uv run mypy                            # strict
uv export --frozen --no-dev --no-emit-project -o requirements-audit.txt && uvx pip-audit -r requirements-audit.txt --disable-pip --require-hashes   # dependency audit (CI gate)
uv run alembic upgrade head            # apply migrations to EWS_DATABASE_URL
uv run alembic revision -m "message"   # new migration
```

- Settings are `EWS_`-prefixed environment variables read by `ews.core.settings.Settings`; every field has a development default, so nothing fails at import.
- `ews.api.app.create_app(settings)` is the application factory. The engine is created in the lifespan, so tests that do not start the app must override `ews.api.dependencies.get_session`.
- Tests create a uniquely named database per run, apply the migrations, and drop it afterwards. The `db_session` fixture wraps each test in a transaction that is rolled back, and the `client` fixture routes requests through that same session, so committed data never leaks between tests. Point `EWS_TEST_ADMIN_DATABASE_URL` at another server if needed.
- The container applies migrations and loads the district registry before starting uvicorn.
- **District registry.** `backend/data/source/` holds the inputs: the coordinate table, the boundary GeoJSON, and `boundary_overrides.json` for districts the two files spell differently. `uv run python -m ews.districts.build` regenerates the packaged registry and boundary file (`src/ews/districts/data/`) and `data/district_mismatch_report.md`; never edit those three by hand, and a test fails if they are stale. A district is attached to a polygon only by exact name or an explicit override. `python -m ews.districts.registry` upserts the registry into the database. District `id` is a slug of the name and is the stable key everything else should use.

The sections below describe the legacy Flask app.

## Architecture

### Wiring

`app.py` configures logging and CORS, calls `database.init_db()`, and registers two blueprints:

- `routes/main_routes.py` — pages and map HTML (`/`, `/refresh_map/<days>`, `/get_districts/<province>`)
- `routes/api_routes.py` — JSON API (forecast, alerts, generation, `/purge_cache`, `/health`)

Routes do not construct services. `extensions.py` holds the module-level singletons (`weather_service`, `alert_service`, `map_service`) and routes import them from there. `services/database.py` is a module of plain functions rather than a class; services and `utils/formatting.py` call it directly.

`models.py` contains `PROVINCES` (province -> district -> `(lat, lon)`), the source of truth for which provinces and districts exist. District keys are mostly upper-case with their own spellings (`"MUZAFARGARH"`, `"Shaheed BENAZIRABAD"`), and they are used verbatim as database keys, LLM prompt labels, and API path segments. `utils/validation.py` keeps a separate hard-coded `ALLOWED_PROVINCES` set that has to be updated alongside `PROVINCES`.

### Generation flow

The dashboard's generate button posts to `/generate_forecast_and_alerts`, which runs synchronously:

1. `WeatherService.get_bulk_weather_data(..., cache_time=0)` fetches Open-Meteo daily data per district in a thread pool and stores the raw JSON response.
2. `utils.formatting.create_weather_dataframe` turns each district's `daily` block into a DataFrame with display column names (`"Max Temp (°C)"`, `"Weather Code"`, ...). `AlertService.generate_alert` reads these column names when building the prompt.
3. `AlertService.generate_alert` makes **one** LLM call per province covering all requested districts and asks for a JSON object keyed by exact district name plus a `"Region's Summary"` key, each mapping to `{"english": ..., "urdu": ...}`.
4. `parse_district_alerts` strips code fences and extracts the JSON; `save_district_alerts` stores each entry as a JSON string in the `alerts` table (`"Region's Summary"` is saved as if it were a district).

`/generate_alerts` does the same work in a daemon thread via `utils/background.py` and returns a `task_id`, but no endpoint exposes task status or results.

Alert readers (`AlertService.get_alert`, `/get_all_alerts`, the map popups) accept both the JSON form and legacy plain-text alerts, wrapping plain text as `{"english": text, "urdu": ""}`. Keep `ensure_ascii=False` when serialising alerts so Urdu is stored readably.

### Caching (`weather.db`)

Two tables, both with an `expires_at` set to now + `CACHE_TIME` on write, and all reads filter on it:

- `alerts`, primary key `(province, district, forecast_days)`.
- `weather_cache`, keyed by a string `cache_key`, holding two different payload shapes:
  - `weather_{days}_{province}_{sanitize_filename(district)}` — raw Open-Meteo JSON. `WeatherService` writes this key and `MapService` rebuilds the same string to read it, so the format must change in both places together.
  - `forecast_{province}_{district}_{days}`, `alerts_{province}_{days}_{district}`, `combined_{province}_{days}_{district}` — DataFrames serialised as JSON records by `create_weather_dataframe`.

`get_bulk_weather_data` additionally compares the row's age against its `cache_time` argument; the generation endpoints pass `cache_time=0` to force a refetch. `/get_forecast` only reads the cache and never fetches.

`database.purge_cache_db` deletes alerts and the `forecast_`/`alerts_` DataFrame keys. It does not delete raw `weather_` or `combined_` entries.

Most functions in `services/database.py` catch every exception and return `None`, `0`, or `{}`. A database failure therefore looks like a cache miss to callers; check `app.log` when data seems to be missing.

### Map rendering

`MapService.create_map` builds the whole Folium map server-side and returns HTML. `/` embeds it in `templates/index.html`, and `/refresh_map` returns a fresh copy as JSON for the frontend to swap in. Each call loads weather and alerts for every district with two batch queries (`get_raw_weather_cache_batch`, `get_alerts_batch`).

District polygons come from `static/boundary/district.geojson`, whose names differ from `models.py` (`Dera_Ghazi_Khan` vs `DERA GHAZI KHAN`). `MapService._district_aliases` maps between them; a district added or renamed in `PROVINCES` needs an alias entry if its GeoJSON name is not an exact match. The path constants in `constants.py` are not used — the only thing imported from `constants.py` is `WEATHER_CODE_DESCRIPTIONS`.

### Frontend

`templates/index.html` is the single live template, with its JavaScript inline. It calls `/get_districts`, `/refresh_map`, `/get_forecast`, `/get_alert`, `/get_all_alerts`, `/generate_forecast_and_alerts`, and `/purge_cache`.

## Configuration

Loaded from `.env` by `config.py`: `MAPBOX_TOKEN` (required), `OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_MODEL` (code default `llama3.1`; the README mentions `qwen3-coder:latest`), `SECRET_KEY`, `CACHE_TIME` (seconds, default 43200), `API_TIMEOUT` (default 120), `BASE_URL` (Open-Meteo), `TIMEZONE` (default `Asia/Karachi`), `HOST` (dev server bind address, default `127.0.0.1`), `CORS_ORIGINS` (comma-separated, default `*`), `MAX_DISTRICTS_PER_REQUEST` (default 100), `LOG_LEVEL`, `LOG_FILE`.

## Conventions

- Type hints on function parameters and return values; docstrings describing purpose, args, and returns.
- Tests use pytest with class-based organisation and mock external services (Open-Meteo, Ollama).
- API responses go through `jsonify()`; request input is checked with the helpers in `utils/validation.py` before use.
- Settings are read through `Config`, not `os.getenv` at call sites.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues in `imtiazNDMA/EarlyWarningSystem`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage labels are used unchanged (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
