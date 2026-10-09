# CLAUDE.md

Guidance for working in this repository.

## System Layout

The application has one active stack:

- `backend/`: Python 3.12 FastAPI API, SQLAlchemy models, Alembic migrations and tests.
- `frontend/`: React 19, TypeScript, Vite, TanStack Query and MapLibre.
- `docker-compose.yml`: PostgreSQL, API and nginx-served frontend.
- `ai.md`: long-term product and architecture plan.

There is no root Python application. Run Python tooling from `backend/` and Node
tooling from `frontend/`.

## Commands

Full stack from the repository root:

```bash
docker compose up --build
docker compose down
docker compose exec api python -m ews.cycles.service
```

Windows helpers provide the same flows: `start.bat`, `stop.bat`, `run-cycle.bat`.

Backend:

```bash
cd backend
uv sync
uv run pytest
uv run pytest tests/test_alerts_api.py::TestListAlerts::test_lists_newest_first
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run alembic upgrade head
uv run python -m ews.api.openapi
```

Frontend:

```bash
cd frontend
npm ci
npm test
npm run lint
npm run typecheck
npm run build
npm run generate:api
```

## Backend Conventions

- Settings are `EWS_`-prefixed and defined in `ews.core.settings.Settings`. Defaults
  support local development; `EWS_ADMIN_TOKEN` enables HTTP cycle triggering.
- `ews.api.app.create_app(settings)` is the application factory. Engines are created
  in lifespan context; tests override the session dependency.
- Tests create an isolated PostgreSQL database, apply every migration and roll back
  each test. They never contact live external services.
- `ews.llm.gateway.LLMGateway` owns all model access. Callers pass a Pydantic type to
  `complete()` and get a validated object plus the `LLMCall` record of what served it.
  Provider defaults live in `PROVIDER_DEFAULTS`; `EWS_LLM_PROVIDER` selects LM Studio
  or Groq. Tests script the provider with `httpx.MockTransport` and never call a model.
- Source clients return typed records and raise `SourceError`. Raw payloads are saved
  as `source_snapshots` before use so alerts can cite immutable evidence.
- Monitoring cycles are transactional. Failed source ingestion rolls back snapshots,
  signals and alert lifecycle changes while preserving the failed run record.
- A cycle is a LangGraph graph built per run in `ews.cycles.service`: ingest, screen,
  analyse, apply lifecycle. Graph state holds only progress counts; working data stays
  on the run's `_Cycle` object because it lives in the run's transaction. A `draft`
  node runs between analyse and apply when the analyst upheld a signal.
- `ews.analyst` judges the most severe signals with a bounded tool loop and submits a
  `HazardAssessment` through a tool call. Alerts follow the assessment. If the model is
  unavailable, errors, or runs out of steps or time, the rule-based alert stands. Tests
  script the model with the `model` fixture, which has no model loaded by default.
- `ews.drafting` words the alerts the analyst assessed. `verifier.verify` is pure and is
  the only gate before publication: every number and date must be in the evidence, and
  no other hazard or severity may be named. A draft that still fails after the allowed
  revisions is stored with status `held` and never becomes active; a model failure
  falls back to rule wording. The lifecycle is split into `plan_lifecycle` and
  `apply_plan` so only alerts that will be written are drafted.
- `ews.drafting.urdu` puts every alert about to be published into Urdu, rule-worded
  ones included, in a `write_urdu` node after `draft`. `verifier.verify_urdu` is pure
  and checks the Urdu against the English, not the evidence: the same dates and
  numbers, the hazard and severity in the terms of `ews.drafting.glossary`, no
  transliterated weather word and no Latin-script word. Urdu that fails, or a model
  that is unavailable, never holds an alert: it is published in English alone.
- Each run keeps an ordered event log in `run_events`. `RunRecorder` commits every
  event through a session of its own, so the log outlives a rolled-back run and is
  readable while the run is in progress; `GET /api/runs/{id}/events` streams it as
  Server-Sent Events. Under the test fixtures those sessions share the test's
  connection, so a rollback there also undoes events; only
  `TestEventsOutliveARollback` uses real commits, and it deletes its own rows.
- Screening and lifecycle decisions are pure logic. Thresholds are loaded from
  `ews/screening/data/thresholds.yaml`.
- Alerts are append-only. Lifecycle changes end old records and create replacements;
  historical records are never overwritten or deleted. A held alert replaces nothing
  and leaves the current one active.
- District source inputs live in `backend/data/source/`. Run
  `uv run python -m ews.districts.build` after changing them; generated registry files
  and the mismatch report must remain current.
- After changing API routes or schemas, run `uv run python -m ews.api.openapi`, then
  `npm run generate:api` in `frontend/`. CI checks both committed outputs.

## Frontend Conventions

- API types are generated in `src/api/schema.d.ts`; do not hand-write API payload
  interfaces. Export convenient aliases from `src/api/client.ts`.
- The browser always calls `/api`; Vite and nginx proxy requests to the backend.
- MapLibre district hover, selection and active-alert severity use feature state keyed
  by `feature_id`. Layers sit below base-map labels.
- Tailwind 4 theme tokens and shared typography/panel classes live in `src/index.css`.
  Yellow, orange and red are reserved for alert severity.
- MapLibre is not unit-tested under jsdom. Test pure helpers and components, then run
  a browser smoke test for map behavior.
- Forecast charts are hand-written SVG and retain a table representation of the same
  values for accessibility.

## Configuration

Compose reads `.env` at the repository root. Important values are
`EWS_ADMIN_TOKEN`, `EWS_DB_PORT`, `EWS_API_PORT` and `EWS_WEB_PORT`. Backend settings
also include `EWS_DATABASE_URL`, `EWS_LOG_LEVEL`, source timeout, forecast horizon,
freshness window, batch size and the `EWS_LLM_*` model settings; see
`backend/src/ews/core/settings.py`.

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `imtiazNDMA/EarlyWarningSystem`, managed
with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repository root, created
lazily when terms or decisions are resolved. See `docs/agents/domain.md`.

### Skill routing

`.claude/skills/` holds 16 skills vendored from mattpocock/skills, pinned and
adapted to this stack; see `.claude/skills/VENDORED.md`. The upstream plugin is
disabled in `.claude/settings.json`, so these are the only copies.

**Vendored wins.** Where a vendored skill and another plugin cover the same
ground, use the vendored one: `tdd` for test-first work, `diagnosing-bugs` for
anything broken or slow, `code-review` for reviewing changes, `codebase-design`
for interface and seam decisions, `research` for gathering facts.

Planned work runs `to-spec` → `to-tickets` → `implement` against GitHub issues.
`grilling` stress-tests a design that already exists.
