# AGENTS.md - Early Warning System

## Repository Layout

- `backend/`: FastAPI, SQLAlchemy, Alembic and pytest.
- `frontend/`: React, TypeScript, Vite and Vitest.
- Run language-specific commands from the corresponding directory.

## Backend Commands

- Install: `uv sync`
- Test: `uv run pytest`
- Single test: `uv run pytest tests/test_health.py::TestHealth::test_reports_healthy_when_database_is_reachable`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Type check: `uv run mypy`
- Migration: `uv run alembic upgrade head`
- Regenerate OpenAPI: `uv run python -m ews.api.openapi`

## Frontend Commands

- Install: `npm ci`
- Test: `npm test`
- Lint: `npm run lint`
- Type check: `npm run typecheck`
- Build: `npm run build`
- Regenerate API types: `npm run generate:api`

## Full Stack

- Start: `docker compose up --build` or `start.bat`
- Run monitoring cycle: `docker compose exec api python -m ews.cycles.service` or `run-cycle.bat`
- Stop: `docker compose down` or `stop.bat`

## Engineering Guidelines

- Keep domain decisions such as screening and lifecycle transitions pure and unit-tested.
- Use typed FastAPI schemas and generated frontend API types.
- Persist raw external payloads before deriving forecasts, signals or alerts.
- Use environment variables through `Settings`; never hardcode secrets.
- Log external-service and database failures with context; return user-safe errors.
- Keep migrations aligned with SQLAlchemy models.
- Mock external services in tests; tests must not access the network.
- Preserve the existing frontend visual language and accessibility behavior.
