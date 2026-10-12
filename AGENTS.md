# AGENTS.md - Early Warnings Weather Dashboard

Flask weather-forecast + AI-alert dashboard for Pakistan. Local LLM (LM Studio) for alert generation, Open-Meteo for weather data, SQLite for caching.

## Commands

All commands use `uv` (see `pyproject.toml` + CI).

```bash
uv sync --all-extras --dev          # install deps
uv run python app.py                # run app (port 5001)
uv run pytest tests/ -v             # run all tests
uv run pytest tests/test_endpoints.py::TestFlaskEndpoints::test_index_get -v  # single test
uv run ruff check .                 # lint
uv run ruff format --check .        # format check
uv run ruff format .                # auto-format
uv run safety check                 # security scan
```

CI order: `ruff check` → `ruff format --check` → `safety check` → `pytest --cov`.

## Architecture

- `app.py` — Flask app, registers blueprints, initializes DB. Dev entrypoint (port 5001).
- `extensions.py` — service singletons (`weather_service`, `alert_service`, `map_service`). Imported by routes.
- `routes/` — Flask blueprints: `main_bp` (dashboard, map refresh), `api_bp` (forecast, alerts, health).
- `services/` — business logic: `weather_service`, `alert_service`, `map_service`, `database` (SQLite).
- `utils/` — helpers: `validation`, `formatting`, `retry`, `health_check`, `performance`.
- `models.py` — `PROVINCES` dict: province → district → (lat, lon).
- `config.py` — `Config` class, env-var driven. **Calls `Config.validate()` at import time** (requires `MAPBOX_TOKEN`).
- `constants.py` — map/weather thresholds, error messages, WMO weather codes.

## Gotchas

- **`services/` and `utils/` have no `__init__.py`** — they work as PEP 420 namespace packages. `routes/` and `tests/` do have `__init__.py`. Don't add one to `services/` or `utils/` unless you have a reason.
- **`config.py` validates at import**: importing `config` without `MAPBOX_TOKEN` set raises `ValueError`. Tests must set env vars (CI writes a `.env` with test values before running pytest).
- **Ruff, not flake8/black**: lint + format are both ruff. Config in `pyproject.toml` `[tool.ruff]`. Line length 100, target py310.
- **Per-file ruff ignores** in `pyproject.toml`: `alert_service.py` (E501 — LLM prompt text), `map_service.py` (E501, C901 — inline HTML/JS), `weather_service.py` (C901), `api_routes.py` (C901). Don't "fix" these without understanding why.
- **No type checker** is configured despite the CI job name mentioning "Type Check".
- **LLM is local** (LM Studio at `http://127.0.0.1:1234/v1` by default), not a cloud API. `LLM_API_KEY` is a dummy (`lm-studio`) to satisfy the OpenAI client.

## Environment

Required env vars (see `.env.example`): `MAPBOX_TOKEN`, `LLM_BASE_URL`, `LLM_MODEL`, `SECRET_KEY`. Optional: `CACHE_TIME`, `API_TIMEOUT`, `LOG_LEVEL`, `LOG_FILE`, `CORS_ORIGINS`.
