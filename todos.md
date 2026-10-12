# todos.md — Agentic Extremely-Early Warning System: Implementation Plan

**Baseline reviewed:** branch `fresh-plan` @ `d81d1b5` + uncommitted working tree, 2026-10-05
**Verified at review time:** `pytest tests` → 81 passed (Python 3.12, no network, no LLM)
**Relationship to `path.md`:** `path.md` remains the rationale and decisions log (D1–D6 are carried forward unchanged). Its Phase 0 is complete. This file is the execution checklist and widens the scope in three directions `path.md` deliberately left out: **lead time** (beyond 7 days), **autonomy** (the system runs itself instead of waiting for a button click), and **dissemination**. Where the two disagree, see "Decisions needed" below.

---

## 0. How to read this file

- Tasks are `- [ ]` with a stable ID (`P3-07`). Tick them in place; do not renumber.
- Every phase has an **exit gate**. A phase is not done until its gate is met, regardless of how many boxes are ticked.
- `GATE` tasks block everything after them in the phase. `HUMAN` tasks need a named person, not an engineer's judgement.
- Size: **S** ≤ 1 day · **M** 2–4 days · **L** 1–2 weeks (one senior engineer).

---

## 1. Decisions needed from you

The plan below proceeds on the **default** in each row. Changing one changes the phases listed.

| # | Decision | Default assumed | Affects |
|---|---|---|---|
| Q1 | What does "extremely early" mean operationally? | **Maximum lead time across tiers**: nowcast (0–6 h) → short range (6–72 h) → medium range (3–10 d) → extended outlook (10–16 d, ensemble to ~35 d) → seasonal outlook. Each tier has its own product type and confidence ceiling. | Phase 2, 3 |
| Q2 | Port from `feature/agentic-platform-foundation` or rebuild? That branch (worktree `G:/AIProjects/earlyWarnings-agentic`) already has `hazards/`, `ingestion/ensemble.py`, `domain/`, and ~960 lines of hazard-engine tests. `path.md` 8.7 says salvage, not re-adopt. | **Salvage selectively**: port the pure hazard rules, ensemble ingestion and their tests; do not port the Mongo/Postgres repository layer. | Phase 2, 3 |
| Q3 | Database: stay on SQLite or move to Postgres/PostGIS? | **SQLite + migration runner now**, behind a repository interface; move to Postgres at Phase 10 only if multi-worker or spatial queries require it. | Phase 1, 4, 10 |
| Q4 | May the system ever publish without a human? | **No.** D3 stands: everything is born `draft`; a duty officer issues it. Autonomy covers monitoring, analysis, drafting and escalation — not publication. | Phase 4, 6, 9 |
| Q5 | Is dissemination (SMS / WhatsApp / email / CAP feed) in scope? `path.md` Part 8 excluded it. | **In scope as Phase 9**, sandbox-first, behind the approval gate. | Phase 9 |
| Q6 | Local LLM only, or is a hosted model allowed for some roles? | **Local only** (LM Studio, `qwen/qwen3.8-27b`) per D6. Tool-calling ability of that model is unproven — see `P5-01`. | Phase 5 |
| Q7 | Who is the domain reviewer (D2) and the duty-officer group (D3)? | Unnamed. `HUMAN` tasks cannot close without them. | Phase 3, 7, 11 |

---

## 2. Current-state review

### 2.1 What the system is today

```
Browser (templates/index.html, ~1,265 lines, inline JS)
   │  POST /generate_forecast_and_alerts   (user clicks a button)
   ▼
routes/api_routes.py ──► WeatherService ──► Open-Meteo (9 daily vars, 1 point per district, ≤7 days)
        │                      └──► SQLite weather_cache
        ├──► AlertService ──► one ChatOpenAI call per province ──► JSON string
        │                      └──► SQLite alerts  (INSERT OR REPLACE, 12 h expiry)
        └──► MapService ──► Folium HTML (markers coloured by precipitation only)
```

| Dimension | State |
|---|---|
| Shape | Flask monolith, two blueprints, three import-time singletons in `extensions.py`, no app factory |
| Coverage | 155 districts across 8 province-level units, one lat/lon each (`models.PROVINCES`) |
| Trigger | Entirely request-driven. Nothing happens unless someone clicks. No scheduler, no worker |
| Intelligence | One prompt in, one JSON blob out. No tools, no planning, no verification, no memory |
| Hazard logic | None in the alert path. An undocumented second set of thresholds lives in the map layer |
| Persistence | Two cache tables. No history: an alert is overwritten on regeneration and deleted after 12 h |
| Tests | 81 passing; no golden weather cases, no LLM-output evaluation |
| Ops | No auth, no rate limiting, no container, no migrations, no metrics |

### 2.2 Findings (verified in code during this review)

Severity: **S1** unsafe or wrong now · **S2** will fail in operation · **S3** debt

| # | Sev | Finding | Evidence |
|---|---|---|---|
| R-01 | S1 | The LLM is the only thing deciding whether a hazard exists, and it is shown only date, high, low, rain total and a WMO code description. Gusts, precipitation probability, snowfall and UV are fetched and then dropped before the prompt. | `services/alert_service.py:131-150` |
| R-02 | S1 | District blocks are concatenated with no separator, so the last forecast line of one district runs straight into `District: <next>`. This invites cross-district mixing, which the prompt then forbids in prose. | `services/alert_service.py:152,164` |
| R-03 | S1 | Map geography is substituted: Layyah is drawn as Dera Ghazi Khan, Bajaur as Mansehra, Lehri as Lasbela, Kachhi as Nasirabad. A warning system must not paint a hazard on the wrong district. | `services/map_service.py:30-76` |
| R-04 | S1 | Stored XSS surface: LLM-generated text and district names are interpolated into `innerHTML`. | `templates/index.html:1016-1020`, `1066-1067` |
| R-05 | S1 | All write endpoints are unauthenticated, including cache purge and LLM generation; CORS defaults to `*`; `FLASK_DEBUG` defaults to `True`. | `routes/api_routes.py:224,325,426`; `config.py:22,54` |
| R-06 | S2 | Mixed clocks. `expires_at` is written from local `datetime.now()` but compared against SQLite `CURRENT_TIMESTAMP` (UTC); cache age is computed as local-now minus a UTC `created_at`. Expiry and freshness are both off by the machine's UTC offset. | `services/database.py:192,236`; `services/weather_service.py:92` |
| R-07 | S2 | No alert history. Primary key is `(province, district, forecast_days)` with `INSERT OR REPLACE`, preceded by an explicit purge. Nothing can be audited, compared or verified after the fact. | `services/database.py:82-90,240`; `routes/api_routes.py:298` |
| R-08 | S2 | Persistence failures are swallowed: `save_alert` logs a warning and returns, and the endpoint still reports success. | `services/database.py:248-250` |
| R-09 | S2 | A second, hardcoded hazard rule set decides which markers blink (rain > 20 mm, precip chance > 90 %, gust > 50 km/h, snow > 5 cm, UV > 10). It is unrelated to the advisory text, so map and text can disagree. Marker colour uses precipitation alone. | `services/map_service.py:643-685` |
| R-10 | S2 | One coordinate represents a whole district. For large mountain districts (Chitral, Kohistan, Skardu) a single point cannot represent valley-scale rain, snow or flash-flood risk. | `models.py` |
| R-11 | S2 | Worst-case generation holds an HTTP worker for ~27 minutes: 3 decorator attempts × 3 client attempts × 180 s timeout, synchronously inside the request. | `services/alert_service.py:105`; `config.py:45-46` |
| R-12 | S2 | Forecast horizon is capped at 7 days in constants and validation. | `constants.py:15`; `utils/validation.py:41-47` |
| R-13 | S2 | Every generation refetches with `cache_time=0`, one HTTP call per district, and the cache key includes `forecast_days`, so 3-day and 7-day views fetch and store the same data separately. | `routes/api_routes.py:260,362`; `services/weather_service.py:81` |
| R-14 | S2 | `/health` performs two live outbound HTTP calls and a file write on every hit, and does not check the database. | `utils/health_check.py` |
| R-15 | S2 | CI triggers on `main` and `develop`; the repository's branches are `main`, `dev`, `staging`. Pushes to `dev` are not tested. | `.github/workflows/ci.yml:5,7` |
| R-16 | S3 | Phase 0 work (29 modified/deleted files) is uncommitted on `fresh-plan`. | `git status` |
| R-17 | S3 | `Config.validate()` runs at import and requires `MAPBOX_TOKEN`; services are constructed at import. Nothing can be injected or swapped in tests without patching modules. | `config.py:81`; `extensions.py` |
| R-18 | S3 | `constants.DISTRICT_BOUNDARY_FILE` points to a file that does not exist; two of three boundary files appear unused. | `constants.py:20`; `static/boundary/` |
| R-19 | S3 | Docs drift: `AGENTS.md` and `CLAUDE.md` still prescribe `flake8`/`black`; the repo uses `ruff`. Root is cluttered with tracked artefacts (`ruff_final.json`, `ruff_modern_errors.txt`, `pytest_collection_error.txt`, `coverage.xml`). | repo root |
| R-20 | S3 | Two Urdu hazard names proposed in `path.md` §3.1 look wrong and need a native-speaker check before they reach a glossary: hail (`گرگے`; the usual term is `ژالہ باری`) and dust storm (`ڈھول بھڑ`; usually `گرد آلود آندھی`). | `path.md` §3.1 |

### 2.3 Gap to "agentic" and to "extremely early"

| Capability | Needed | Today |
|---|---|---|
| Runs without a human trigger; notices new model runs | yes | no |
| Typed tools the model may call | yes | none |
| Deterministic hazard detection with evidence | yes | none |
| Multi-step plan → act → observe → verify → repair | yes | single call |
| Durable, resumable workflow state | yes | none |
| Memory of what was issued and what happened | yes | overwritten |
| Human approval and audit trail | yes | none |
| Lead time beyond 7 days; probabilistic outlooks | yes | 7-day deterministic |
| Precursor signals (river discharge, soil moisture, snowpack, upstream rain) | yes | none |
| Forecast verification feeding back into thresholds | yes | none |
| Works when the LLM is down | yes | returns 503 |

---

## 3. Target architecture

### 3.1 Governing principles

1. **Code decides, the model explains.** Hazard existence, severity, area, timing and confidence come from deterministic rules over data. The LLM plans investigations, reconciles sources, narrates, translates and answers questions. It may *propose* an escalation; it can never create or raise one on its own.
2. **Every claim has evidence.** No hazard without at least one evidence row; no sentence in an advisory naming a hazard the detector did not produce.
3. **Lead time trades against confidence, and the product says so.** Far-horizon signals are published as outlooks with probabilities, never as warnings.
4. **Nothing is published without a human** (D3 / Q4).
5. **Degrade, don't fail.** LLM down → templated advisory. Provider down → stale data, flagged as stale. Never a blank screen during an event.
6. **Everything is replayable.** Each advisory records data-run IDs, rule version, prompt version, model and tool-call log.

### 3.2 Lead-time tiers

| Tier | Horizon | Data | Product | Max severity |
|---|---|---|---|---|
| T0 Nowcast | 0–6 h | 15-minutely model fields, observations, lightning, satellite (if obtainable) | Immediate alert | severe |
| T1 Short range | 6–72 h | Hourly deterministic + convective indices, multi-model | Warning | severe |
| T2 Medium range | 3–10 d | Daily + ensemble spread | Watch | warning |
| T3 Extended | 10–16 d (ensemble to ~35 d) | Ensemble probabilities, anomalies vs climatology | Outlook | advisory |
| T4 Seasonal | weeks–months | Seasonal ensembles, river/snow/soil state | Seasonal outlook (monsoon, heat season, GLOF season, drought) | outlook only |

### 3.3 Planes

```
┌─ DATA PLANE ────────────────────────────────────────────────────────────────┐
│ provider adapters → immutable forecast runs → normalisation + quality flags  │
│ (Open-Meteo forecast / ensemble / flood / air-quality / archive; official     │
│  bulletins; observations)                                                     │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌─ DETECTION PLANE (no LLM) ──────────────────────────────────────────────────┐
│ rules per hazard × tier → HazardFinding{severity, confidence, window,        │
│ evidence[]} → compound hazards → corroboration                                │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌─ AGENT PLANE ───────────────────────────────────────────────────────────────┐
│ Sentinel (schedule/trigger) → Supervisor graph:                               │
│   triage → investigate (tools) → corroborate → draft EN/UR → verify → repair  │
│   → deterministic fallback                                                    │
│ Operator copilot (read-only tools) for duty-officer questions                 │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌─ GOVERNANCE PLANE ──────────────────────────────────────────────────────────┐
│ warning events + versions, draft → approved → issued → updated → expired,     │
│ escalation/suppression, append-only audit, human review queue                 │
└───────────────┬──────────────────────────────────────────────────────────────┘
                ▼
┌─ DELIVERY + FEEDBACK ───────────────────────────────────────────────────────┐
│ dashboard, API v2, CAP feed, channels (sandbox first) → delivery receipts     │
│ post-event verification → POD/FAR/CSI → threshold calibration                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.4 Agent roles (one graph, bounded; not free-roaming agents)

| Role | Kind | Does | May not |
|---|---|---|---|
| Sentinel | code | Detects new model runs, schedules cycles, opens investigations on threshold crossings or source disagreement | call the LLM |
| Triage | code + LLM | Ranks districts, picks which need full investigation within a token/time budget | change findings |
| Investigator | LLM with tools | Pulls extra data when findings are ambiguous (ensemble, upstream catchment, prior issuance, official bulletins) and records what it checked | invent data; raise severity |
| Corroborator | code | Adjusts confidence from model agreement and source consistency | — |
| Communicator | LLM | Writes meteorological overview, hazard narrative, impacts, actions in English and Urdu | add hazards, numbers or dates |
| Verifier | code | Schema, claim ⊆ evidence, number/date parity EN↔UR, glossary compliance | be skipped |
| Fallback renderer | code | Templated bilingual advisory from findings | — |
| Copilot | LLM with read-only tools | Answers "why was this flagged?", "what changed since the last run?" | write anything |

### 3.5 Target layout

```
app.py (factory)  worker.py (scheduler + agent runs)
domain/      forecast.py hazard.py warning.py            # typed contracts
ingestion/   providers/{open_meteo,flood,air_quality,archive}.py  coordinator.py  quality.py
hazards/     thresholds.yaml  engine.py confidence.py onset.py compound.py  rules/*.py
agent/       tools.py graph.py verifier.py fallback.py provider.py copilot.py
warnings/    lifecycle.py escalation.py repository.py
delivery/    cap.py channels/*.py outbox.py
prompts/     <task>/vN.md           i18n/glossary.yaml
migrations/  NNN_*.sql              evals/ cases/ run.py report.py
docs/        hazards.md evaluation.md runbook.md adr/
```

---

## 4. Phases

Dependency order: `0 → 1 → 2 → 3 → 4 → 5 → 6`, with `7` starting after 4, `8` after 3, `9` after 6+7, `10` alongside 6–9, `11` last.

---

### Phase 0 — Lock the baseline · S

**Goal:** the verified-green state is committed and CI actually runs on it.

- [ ] `P0-01` Commit the current working tree on `fresh-plan` in logical commits (LLM runtime switch, dead-code removal, test fixes, docs). (R-16)
- [ ] `P0-02` Fix CI branch triggers to the branches that exist (`main`, `dev`, `staging`). (R-15)
- [ ] `P0-03` Add a separator between district blocks in the prompt and a test asserting each block starts on its own line. (R-02)
- [ ] `P0-04` Remove tracked artefacts from the repo and add them to `.gitignore`: `ruff_final.json`, `ruff_modern_errors.txt`, `pytest_collection_error.txt`, `coverage.xml`, `.coverage`, `htmlcov/`, `app.log`, `waitress.*.log`. (R-19)
- [ ] `P0-05` Align `AGENTS.md` and `CLAUDE.md` with `ruff`; delete the stray XML tail at `AGENTS.md:29-30`. (R-19)
- [ ] `P0-06` Remove or fix `constants.DISTRICT_BOUNDARY_FILE`; delete boundary files nothing loads. (R-18)
- [ ] `P0-07` Record in `path.md` Appendix A that `todos.md` is the execution checklist, plus the answers to Q1–Q7.

**Exit gate:** clean `git status`; CI green on a push to `dev`; 81+ tests passing.

---

### Phase 1 — Safety and structural foundations · M

**Goal:** remove the hazards that become dangerous once the system acts on its own, and create the seams later phases plug into.

**Structure**
- [ ] `P1-01` Application factory `create_app(config)`; move service construction out of import time; `Config.validate()` called by the factory, not on import. (R-17)
- [ ] `P1-02` `wsgi.py` entry point; `python app.py` stays as the dev runner with debug off by default. (R-05)
- [ ] `P1-03` Migration runner: ordered `migrations/NNN_*.sql`, `schema_migrations` table, runs at startup and from a CLI; `001` reproduces today's two tables exactly.
- [ ] `P1-04` Repository interface over `services/database.py` so storage can change without touching services (Q3).
- [ ] `P1-05` All timestamps UTC, timezone-aware, ISO-8601 in storage; convert to `Asia/Karachi` only at presentation. Regression test that fails on a non-UTC host. (R-06)
- [ ] `P1-06` Persistence errors propagate: a failed save fails the request with a structured error. (R-08)
- [ ] `P1-07` Uniform error envelope `{"error": {"code", "message", "request_id"}}` and request-ID middleware.

**Security minimum**
- [ ] `P1-08` Role-based auth for every non-GET route: `viewer`, `forecaster`, `duty_officer`, `admin`; service tokens for the worker. (R-05)
- [ ] `P1-09` Rate limiting on generation and purge endpoints; `429` with `Retry-After`.
- [ ] `P1-10` CORS deny-by-default; startup refuses `*`, default `SECRET_KEY`, or debug when `FLASK_ENV=production`.
- [ ] `P1-11` Frontend escaping: replace every `innerHTML` that carries model output or names with `textContent`/DOM construction; escape in `MapService._build_popup_html`; add a CSP header. (R-04)
- [ ] `P1-12` XSS regression test: an alert containing `<img src=x onerror=…>` renders inert in panel and popup.

**Geography**
- [ ] `P1-13` Remove every alias that maps a district onto a different district's polygon; a district with no geometry is listed as "no boundary available", not drawn elsewhere. (R-03)
- [ ] `P1-14` `HUMAN` Obtain an authoritative district boundary file (current administrative units, including merged KP districts and Karachi divisions) and reconcile it with `models.PROVINCES`; record source and date.
- [ ] `P1-15` Stable district IDs (not display names) as keys across DB, API and GeoJSON; names become labels.
- [ ] `P1-16` Delete `_is_critical_weather_alert` and `_get_marker_color` thresholds from the map layer behind a flag; they are replaced by findings in Phase 3. (R-09)

**Exit gate:** unauthenticated write → 401; XSS test passes; no district is rendered on another district's polygon; migrations run from an empty DB and from the existing `weather.db`; suite green on a UTC and a UTC+5 host.

---

### Phase 2 — Data plane for long lead time · L

**Goal:** the detector gets enough variables, enough horizon, enough spatial resolution and enough provenance to justify a warning.

**Availability first**
- [ ] `P2-01` `GATE` `scripts/probe_variables.py`: for ~8 representative points (coast, plains, desert, Karakoram valley, Kashmir, Quetta plateau) and each candidate model, record which hourly/daily/15-minutely/ensemble/flood/air-quality variables actually return data and to what horizon. Output `docs/variable_availability.md`. No rule may depend on a variable this document does not show as available.
- [ ] `P2-02` Confirm provider terms, rate limits and whether a commercial/self-hosted Open-Meteo tier is required at 155 districts × multi-point × hourly cadence; record the request budget.

**Ingestion**
- [ ] `P2-03` Typed provider adapter interface; port `ingestion/open_meteo.py` and `ingestion/ensemble.py` from the agentic branch if Q2 = salvage.
- [ ] `P2-04` Batch requests (multiple coordinates per call) instead of one call per district; bounded concurrency with backoff. (R-13)
- [ ] `P2-05` Immutable `forecast_runs` table: provider, model, run time, fetched-at, horizon, payload hash. Replaces the "cache" concept; cache keys stop including `forecast_days`. (R-07, R-13)
- [ ] `P2-06` Variable groups declared once (`ingestion/variables.py`): daily, hourly (CAPE, CIN, lifted index, gusts, visibility, humidity, dew point, freezing level, precipitation type, wet-bulb, soil moisture, snow depth), 15-minutely for T0.
- [ ] `P2-07` Horizon raised to 16 days deterministic; `MAX_FORECAST_DAYS` and validation updated; UI selector follows. (R-12)
- [ ] `P2-08` Ensemble ingestion for T2–T3: member spread and exceedance probabilities per threshold, stored as derived fields, not raw members.
- [ ] `P2-09` Seasonal/sub-seasonal ingestion for T4 (monthly anomalies of temperature and precipitation).
- [ ] `P2-10` River-discharge ingestion (flood API) for points on the Indus, Jhelum, Chenab, Ravi, Sutlej, Kabul and Swat, including upstream points outside Pakistan.
- [ ] `P2-11` Air-quality ingestion (PM2.5/PM10, dust) for smog and dust hazards.

**Spatial resolution**
- [ ] `P2-12` Multi-point sampling per district: a sampling set generated from the boundary polygon (grid or population-weighted), with elevation recorded per point. District value = worst-case and area-fraction, both kept. (R-10)
- [ ] `P2-13` Static exposure layer per district: population, major settlements, river adjacency, steep-terrain fraction, glacial-lake presence. Source and date recorded.

**Quality and context**
- [ ] `P2-14` Normalisation module: units, nulls, scalar-vs-list, timezone, one canonical in-memory `DistrictForecast` type.
- [ ] `P2-15` Quality flags per run: freshness, completeness, stale-fallback-used; surfaced to the detector and the UI.
- [ ] `P2-16` Climatology builder `scripts/build_climatology.py`: per sampling point and calendar month, percentiles (P50/P75/P90/P95/P99) of Tmax, Tmin, daily precipitation from the historical archive; stored as a versioned artefact.
- [ ] `P2-17` `HUMAN` Official-source connectors, scoped with NDMA/PMD: which bulletins (PMD forecasts, Flood Forecasting Division, cyclone advisories) may be ingested, in what format, under what agreement. Until agreed, stub the adapter.
- [ ] `P2-18` Observation ingestion for T0 and for verification (station observations or reanalysis as a stand-in); record the limitation if only reanalysis is available.

**Exit gate:** a `DistrictForecast` for any district carries hourly convective fields, 16-day daily fields, ensemble exceedance probabilities and quality flags; identical inputs replay to identical normalised output; fetch for all 155 districts stays inside the request budget from `P2-02` and its p95 latency is recorded.

---

### Phase 3 — Deterministic hazard engine · L

**Goal:** typed, evidence-backed findings from pure functions. No LLM is imported anywhere under `hazards/`.

- [ ] `P3-01` `domain/hazard.py`: `Severity` (advisory/watch/warning/severe), `Confidence`, `Tier`, `Evidence{variable, value, operator, threshold, unit, source_run, valid_time}`, `HazardFinding{hazard_id, tier, severity, confidence, onset, peak, end, area_fraction, evidence[], rule_id, rule_version}`.
- [ ] `P3-02` `hazards/thresholds.yaml`: every number in one versioned table with per-region overrides and a `status: needs-review | approved` field. No literals in rule code (lint check).
- [ ] `P3-03` If Q2 = salvage, port `hazards/{heat,rain,snow,visibility,wind,compound,lead_time}.py` and `tests/test_hazard_engine.py` from the agentic branch; reconcile with the contracts above.
- [ ] `P3-04` Rules, short range (T0–T1): heavy rain, flash flood (intensity + terrain + antecedent soil moisture), thunderstorm, hail, strong wind, dense fog, snowfall, extreme UV.
- [ ] `P3-05` Rules, temperature: heatwave and cold wave using climatology percentiles with absolute fallbacks; humid-heat via wet-bulb; warm-night flag.
- [ ] `P3-06` Rules, hydrological: riverine flood from discharge vs return-period thresholds, with upstream-to-downstream travel-time lead.
- [ ] `P3-07` Rules, mountain: glacial-lake outburst and snowmelt-flood precursors (sustained high freezing level + heat anomaly + rain-on-snow), landslide proxy (rain accumulation × slope). Issued as low-confidence "monitor" until validated.
- [ ] `P3-08` Rules, slow-onset: drought (precipitation deficit vs climatology), smog and dust (air-quality + stagnation), tropical cyclone proximity for the Sindh/Balochistan coast.
- [ ] `P3-09` Rules, far horizon (T2–T4): probability-of-exceedance outlooks from ensembles; severity capped per §3.2.
- [ ] `P3-10` `onset.py`: onset/peak/end from the hourly series (first to last threshold crossing), not daily buckets.
- [ ] `P3-11` `confidence.py`: signal count, model agreement, lead time and data quality → confidence; `low` confidence can never carry `warning` or above.
- [ ] `P3-12` `compound.py`: compound and cascading hazards (heat + drought, rain on saturated soil, rain-on-snow, storm + high tide).
- [ ] `P3-13` `engine.py`: run rules, merge overlapping findings of the same hazard, rank by severity → confidence → onset, attach exposure.
- [ ] `P3-14` Fixtures `tests/fixtures/forecast/*.json`: clear day, hail day, extreme rain, heatwave, fog morning, river crest, far-horizon ensemble signal, missing-data day.
- [ ] `P3-15` Invariant tests: every finding has ≥ 1 evidence row; severity/confidence/tier caps hold; findings round-trip through JSON; same input + same rule version → byte-identical output.
- [ ] `P3-16` Map marker colour and blinking driven by max finding severity; legend added. Removes the last of R-09.
- [ ] `P3-17` `docs/hazards.md`: each rule, threshold, rationale and reference.
- [ ] `P3-18` `HUMAN` Domain reviewer signs off thresholds one by one (D2) and maps the severity ladder to official PMD/NDMA product levels (D4). Engineering does not flip `needs-review`.

**Exit gate:** engine runs with the LLM server switched off; clear-day fixture yields zero findings; hail and extreme-rain fixtures yield findings with ≥ 2 evidence rows and correct onset; `hazards/` has no import of `langchain` or `agent`.

---

### Phase 4 — Warning lifecycle, persistence and API v2 · M

**Goal:** an alert becomes a versioned, auditable event with a lifecycle, and the existing UI keeps working throughout.

- [ ] `P4-01` `domain/warning.py`: `WarningEvent` (district, hazard, window) with immutable `WarningVersion`s; states `draft → approved → issued → updated → cancelled | expired`.
- [ ] `P4-02` Migrations: `warning_events`, `warning_versions`, `advisories`, `audit_log` (append-only), `workflow_runs`.
- [ ] `P4-03` Advisory v2 schema (Pydantic) per `path.md` §2.3, plus `tier`, `data_run_ids`, `verification_results`.
- [ ] `P4-04` Escalation logic against *issued* events only: new / unchanged (suppress) / escalated / de-escalated / expired. Drafts never suppress an issued event.
- [ ] `P4-05` Idempotency: the same event window upserts a new version, never a duplicate event.
- [ ] `P4-06` API v2: `GET /api/v2/hazards`, `GET /api/v2/advisories`, `POST /api/v2/advisories/<id>/approve|reject|cancel` (role-gated, audited with who/when/why), `GET /api/v2/events/<id>/history`.
- [ ] `P4-07` Legacy routes read v2 and project to `{"english", "urdu"}`; they serve **issued** content only.
- [ ] `P4-08` Retention policy for forecast runs and warning history; nothing with status `issued` is ever deleted.
- [ ] `P4-09` Tests: lifecycle transition matrix (legal and illegal), escalation matrix, v2 → v1 projection, audit completeness.

**Exit gate:** a generated advisory is `draft` and invisible on public/legacy routes until approved; re-running the same window produces a new version, not a new event; every state change has an audit row naming a user.

---

### Phase 5 — Agent runtime · L

**Goal:** a bounded, auditable tool-using graph that investigates, drafts, verifies and repairs, with a deterministic fallback.

- [ ] `P5-01` `GATE` Model capability probe against the local model: tool-calling reliability, structured-output reliability, Urdu quality, latency and context limit at realistic prompt sizes. Result decides native tool calls vs. constrained JSON for the graph, and whether Q6 must be reopened.
- [ ] `P5-02` `agent/provider.py`: provider protocol, timeouts, circuit breaker, one retry policy (replaces the stacked retries of R-11).
- [ ] `P5-03` `agent/tools.py`: typed tool registry with Pydantic in/out — `get_forecast`, `detect_hazards`, `get_ensemble_agreement`, `get_climatology`, `get_river_state`, `get_exposure`, `get_prior_issuance`, `get_official_bulletins`, `lookup_glossary`, `validate_advisory`. Every tool is callable in tests with no LLM. All tools are read-only except `submit_draft`.
- [ ] `P5-04` `agent/graph.py`: fixed graph `triage → investigate → corroborate → draft → verify → repair (≤ 2) → submit_draft | fallback`, with per-node step, token and wall-clock budgets. State checkpointed to SQLite so a run can resume.
- [ ] `P5-05` Triage node: rank districts by finding score; full narrative for flagged districts, one-line summary for quiet ones.
- [ ] `P5-06` Investigator node: bounded tool loop for ambiguous cases (model disagreement, borderline thresholds, conflict with an official bulletin). Output is an *investigation note* with the tools called and what they returned; it may recommend a confidence change for human review, never apply one.
- [ ] `P5-07` Communicator: per-district generation (not one call per province) with the full enriched frame and findings; province and national roll-ups built from district outputs. (R-01, R-02)
- [ ] `P5-08` Prompts as versioned files under `prompts/`; `prompt_version` stamped on every advisory.
- [ ] `P5-09` `i18n/glossary.yaml`: hazard names, severity words, action phrases, EN↔UR, used by renderer and verifier. `HUMAN` native-speaker review of every term, starting with the two flagged in R-20.
- [ ] `P5-10` `agent/verifier.py` (hard gate): schema; every hazard named in text exists in findings; every number and date in text matches evidence within tolerance; EN and UR carry the same numbers, dates and severity; glossary compliance; no hazard language at a severity above the finding.
- [ ] `P5-11` Repair: structured errors `[{path, code, expected, actual}]` fed back; two failures → fallback.
- [ ] `P5-12` `agent/fallback.py`: templated bilingual advisory from findings + glossary, zero LLM calls.
- [ ] `P5-13` Prompt-injection hardening: text from official bulletins and any external source is passed as quoted data, never as instructions; test with an adversarial bulletin.
- [ ] `P5-14` Run log persisted per advisory: node timings, tool calls with arguments and result hashes, token counts, verifier results.
- [ ] `P5-15` Graph tests with a scripted fake LLM: happy path, invalid JSON → repair, invented hazard → reject, verifier fails twice → fallback, provider timeout → fallback, budget exhausted → fallback.
- [ ] `P5-16` Retire the legacy `AlertService.generate_alert` path once the UI reads v2.

**Exit gate:** the hail fixture yields a valid advisory with overview + hazard block in both languages; a fixture where the model invents a hazard is rejected by the verifier; with the LLM server stopped, a valid advisory is still produced; every advisory is traceable to data runs, rule version, prompt version, model and tool log.

---

### Phase 6 — Autonomy: sentinel, scheduling, memory · M

**Goal:** the system watches continuously and opens its own investigations. This is the phase after which "agentic" is an accurate description.

- [ ] `P6-01` `worker.py`: separate process from the web app, single-instance lock, graceful shutdown.
- [ ] `P6-02` Run discovery: poll provider metadata for new model runs; trigger ingestion on arrival rather than on a fixed clock.
- [ ] `P6-03` Cadence by tier: T0 every 15–30 min for districts with an active finding; T1 hourly; T2–T3 on each new run; T4 weekly.
- [ ] `P6-04` Durable `workflow_runs`: status, trigger, inputs, step checkpoints, error, retry count; resumable after a crash; dead-letter state after bounded retries.
- [ ] `P6-05` Adaptive focus: a district with a finding, a rising trend or model disagreement gets tighter cadence and multi-model corroboration automatically; quiet districts stay cheap.
- [ ] `P6-06` Trend detection across consecutive runs: a signal that strengthens over three runs at long lead is raised as an early outlook even below the warning threshold. This is the core of "extremely early".
- [ ] `P6-07` Change-driven drafting: a new draft only when findings change materially (escalation logic from `P4-04`); otherwise a logged no-op.
- [ ] `P6-08` Operational memory: per district and hazard — prior issuances, outcomes, false alarms, reviewer rejection reasons — exposed to triage and investigator through tools.
- [ ] `P6-09` Duty-officer notification when a draft at `warning` or above is waiting, with escalation if unacknowledged within a configured time.
- [ ] `P6-10` Kill switch and safe mode: one flag stops all autonomous runs; safe mode runs detection only, with no LLM.
- [ ] `P6-11` Simulation/replay mode: run the whole loop against archived forecast runs for a past date without touching live state.
- [ ] `P6-12` Tests: crash mid-run and resume; duplicate trigger is idempotent; kill switch halts within one cycle; replay of a past event reproduces the same findings.

**Agentic exit gate:** with no human action for 48 hours in staging, the system ingests every new run, produces findings, opens investigations where warranted, queues verified drafts for review, and survives a worker restart and an LLM outage without losing or duplicating work.

---

### Phase 7 — Operator console and public UI · L (can start after Phase 4)

**Goal:** hazards are scannable, reviewable and explainable; the 1,265-line template is broken up.

- [ ] `P7-01` Split `templates/index.html` into static JS/CSS modules; no inline scripts (required by the CSP from `P1-11`).
- [ ] `P7-02` Advisory v2 renderer: overview, then hazard cards with severity, confidence, tier, onset/peak/end, expandable evidence ("gust 78 km/h ≥ 70").
- [ ] `P7-03` Map: polygon fill by max severity, tier toggle (now / 3-day / 10-day / outlook), legend, per-district timeline strip across the full horizon.
- [ ] `P7-04` Review queue for duty officers: drafts by severity, side-by-side English/Urdu, evidence and investigation note, diff against the last issued version, approve / edit / reject with reason.
- [ ] `P7-05` Edits by a reviewer are re-run through the verifier before issue; overrides are allowed but recorded.
- [ ] `P7-06` Event history view: versions, who approved, what changed, outcome once verified.
- [ ] `P7-07` Copilot panel: read-only tool access, answers cite findings and data runs, refuses to state a hazard not in findings.
- [ ] `P7-08` Data-quality and staleness indicators on every panel; explicit "degraded: templated advisory" badge when the fallback was used.
- [ ] `P7-09` System status page: last successful run per provider, worker heartbeat, queue depth, LLM status.
- [ ] `P7-10` Urdu RTL layout, mobile layout, accessibility (severity never by colour alone, keyboard navigation, `aria-live` for new warnings).
- [ ] `P7-11` Remove the typing animation from warning content.
- [ ] `P7-12` Browser tests: review flow end to end, XSS inertness, RTL rendering, legacy view parity.

**Exit gate:** a duty officer can take a draft from queue to issued without leaving the console and can see why each hazard was raised; nothing unapproved is visible to a `viewer`.

---

### Phase 8 — Evaluation and verification loop · L (can start after Phase 3)

**Goal:** quality is measured, regressions are blocked, and thresholds improve from outcomes.

- [ ] `P8-01` Case set `evals/cases/`: ≥ 15 synthetic fixtures, ≥ 15 historical Pakistani events replayed from archive data (e.g. 2022 monsoon floods, 2010 floods, recent heatwaves, pre-monsoon hail, winter fog, a GLOF event, an Arabian Sea cyclone), ≥ 15 clear-negative periods.
- [ ] `P8-02` `HUMAN` Ground-truth annotation per case: district, hazard, severity, window, source of truth.
- [ ] `P8-03` Detector metrics per hazard and tier: POD, FAR, CSI, severity accuracy, onset error, **achieved lead time** (hours between first outlook/watch/warning and onset).
- [ ] `P8-04` Language metrics: schema validity, hallucinated-hazard rate (target 0), EN↔UR number parity, glossary compliance, run-to-run disagreement over 3 runs.
- [ ] `P8-05` Cost and latency per cycle: tokens, wall-clock p50/p95, provider calls.
- [ ] `P8-06` `evals/run.py` + `evals/report.py`; fast subset on every PR, full set nightly; CI fails on regression beyond tolerance.
- [ ] `P8-07` Baseline recorded before any threshold or prompt tuning.
- [ ] `P8-08` Live verification job: after each event window closes, compare issued warnings with observations and write outcomes to operational memory (`P6-08`).
- [ ] `P8-09` Calibration loop: outcomes propose threshold changes as a reviewable diff to `thresholds.yaml`; `HUMAN` domain reviewer approves; rule version bumps.
- [ ] `P8-10` Bilingual human review protocol: sampled advisories scored on accuracy, clarity, actionability, Urdu quality; documented in `docs/evaluation.md`.
- [ ] `P8-11` Model/prompt change gate: no model or prompt version reaches production without a full eval run and a recorded comparison.

**Exit gate:** baseline and current metrics committed; hallucinated-hazard rate is 0 across the suite; CSI floors per hazard agreed with the domain reviewer and met or explicitly waived in writing; lead-time distribution reported per tier.

---

### Phase 9 — Dissemination · M (after Phases 6 and 7; scope per Q5)

**Goal:** issued warnings reach people through reliable channels, with receipts. Nothing here fires before approval.

- [ ] `P9-01` CAP 1.2 serialisation of issued warnings (urgency, severity, certainty, area polygon, effective/expires, bilingual `info` blocks); schema-validated.
- [ ] `P9-02` Public CAP/Atom feed and read-only public API for issued warnings.
- [ ] `P9-03` Outbox pattern: delivery jobs written in the same transaction as the `issued` transition; worker delivers with retries and idempotency keys.
- [ ] `P9-04` Channel adapters behind one interface, each starting in sandbox mode: email, SMS gateway, WhatsApp Business, webhook for partner systems.
- [ ] `P9-05` `HUMAN` Agreements for each real channel (sender IDs, telecom/PTA requirements, recipient lists, PDMA/DDMA contacts per district).
- [ ] `P9-06` Recipient targeting by district and role; subscription management; message templates per channel length limit, both languages.
- [ ] `P9-07` Update and cancellation messages reference the original warning; expiry sends an all-clear where policy requires.
- [ ] `P9-08` Delivery receipts and failure dashboard; alert the duty officer on delivery failure for `warning` and above.
- [ ] `P9-09` Tests: no delivery without `issued`; duplicate trigger sends once; cancellation reaches everyone the original reached.

**Exit gate:** in sandbox, an approved warning produces a valid CAP document and exactly one message per recipient per channel, with receipts; a draft produces none.

---

### Phase 10 — Production hardening and operations · M (alongside Phases 6–9)

- [ ] `P10-01` Dockerfile (multi-stage, non-root) for web and worker; compose file with volumes for DB and artefacts.
- [ ] `P10-02` Production WSGI server config; worker count decision documented against the storage choice (Q3). If more than one web worker or spatial queries are needed, migrate to Postgres/PostGIS here.
- [ ] `P10-03` Structured JSON logs with request and run IDs across web, worker and agent tool calls.
- [ ] `P10-04` Metrics endpoint: request latency, provider calls and failures, LLM calls/tokens/errors, findings by hazard and severity, verifier failures, fallback count, queue depth, draft age.
- [ ] `P10-05` Health split: `/health/live` (no I/O) and `/health/ready` (DB + cached dependency checks, short TTL). (R-14)
- [ ] `P10-06` Alerting on the system itself: no successful ingestion in N hours, worker heartbeat lost, draft at `warning`+ unreviewed past its limit, fallback rate above threshold.
- [ ] `P10-07` Backups with a tested restore; documented recovery time and data-loss objectives.
- [ ] `P10-08` Secrets out of `.env` files in deployment; rotate anything that has ever been committed or shared; secret scanning in CI.
- [ ] `P10-09` CI: lint, format, tests, migration test, eval fast subset, container build, dependency audit; `uv.lock` enforced.
- [ ] `P10-10` Load test: full national cycle (155 districts, all tiers) within the cadence budget; LLM outage and provider outage drills.
- [ ] `P10-11` Redundancy plan for the single LLM host and the single weather provider (second model source at minimum for T1).
- [ ] `P10-12` Security review: authz matrix test per route and role, dependency audit, threat model for prompt injection and for a compromised operator account.

**Exit gate:** `docker compose up` gives a working, authenticated system; outage drills pass with degraded-but-valid output; restore from backup demonstrated.

---

### Phase 11 — Rollout and handover · M

- [ ] `P11-01` Shadow mode: system runs live, drafts are reviewed but nothing is issued; compare against official PMD/NDMA products for at least one full weather regime.
- [ ] `P11-02` `HUMAN` Shadow-mode review with the domain reviewer; thresholds adjusted via `P8-09`.
- [ ] `P11-03` Staged exposure: internal → NEOC duty officers → provincial authorities → public feed.
- [ ] `P11-04` Duty-officer training on the review console, overrides, kill switch and degraded modes.
- [ ] `P11-05` `docs/runbook.md`: deploy, rollback, outage behaviour, threshold-override procedure, incident triage.
- [ ] `P11-06` ADRs: deterministic detection; bounded graph over free-form agents; storage choice; human approval gate; lead-time tiers and severity caps.
- [ ] `P11-07` README, `CLAUDE.md`, `AGENTS.md` rewritten to match the shipped system.
- [ ] `P11-08` Post-launch review after the first real event: lead time achieved, misses, false alarms, reviewer workload.

**Exit gate:** programme definition of done (§7) met.

---

## 5. Milestones

| Milestone | Phases | What you can demonstrate |
|---|---|---|
| M1 Safe baseline | 0, 1 | Authenticated, XSS-safe dashboard with correct geography; no behaviour change otherwise |
| M2 Deterministic decision support | 2, 3 | 16-day, evidence-backed hazard findings on the map with no LLM involved |
| M3 Governed advisories | 4, 5, 7 (review queue) | Verified bilingual drafts with evidence, approved by a duty officer, full audit trail |
| M4 Agentic | 6 | 48-hour unattended run meeting the agentic exit gate |
| M5 Trusted | 8 | Published POD/FAR/CSI and lead-time numbers on historical events |
| M6 Operational | 9, 10, 11 | Shadow mode, then staged live issuance with dissemination |

Suggested first slice (one hazard end to end before widening): heavy rain for Punjab — `P2-01`, `P2-03..06`, `P3-01..02`, heavy-rain rule from `P3-04`, `P3-10..11`, `P4-01..03`, `P5-12` (fallback renderer first, LLM second), `P7-02`.

---

## 6. Risks

| # | Risk | Mitigation |
|---|---|---|
| K1 | Model invents or inflates a hazard | Verifier hard gate (`P5-10`), 0 % hallucination metric in CI (`P8-04`), human approval |
| K2 | False alarms at long lead erode trust | Tier severity caps (§3.2), probability wording for outlooks, calibration loop (`P8-09`) |
| K3 | Local model cannot do reliable tool calls or good Urdu | Capability probe gates the design (`P5-01`); graph works with constrained JSON; fallback renderer |
| K4 | Variables or horizons unavailable from the provider | Availability probe gates rules (`P2-01`) |
| K5 | Single provider / single LLM host | `P10-11`; stale-data and fallback modes |
| K6 | Thresholds not accepted by forecasters | Domain reviewer owns sign-off (`P3-18`); shadow mode (`P11-01`) |
| K7 | Wrong geography on a warning | Authoritative boundaries and stable IDs (`P1-13..15`) |
| K8 | Free-form agents make output irreproducible | Fixed graph with budgets, versioned prompts and rules, replay mode (`P6-11`) |
| K9 | Request volume or cost at national scale | Budget from `P2-02`, batching (`P2-04`), adaptive focus (`P6-05`) |
| K10 | Scope: eleven phases is a large programme | Milestones are independently valuable; first slice proves the spine on one hazard |
| K11 | Unnamed human owners block `HUMAN` tasks | Q7 must be answered before Phase 3 closes |

---

## 7. Programme definition of done

- [ ] Every S1/S2 finding in §2.2 is closed with a regression test.
- [ ] Hazard detection runs with zero LLM involvement and every finding carries evidence.
- [ ] Advisories exist at all five lead-time tiers with the severity caps enforced in code.
- [ ] The system runs unattended, resumes after failure, and can be stopped with one switch.
- [ ] No advisory names a hazard, number or date not present in its evidence (test-enforced).
- [ ] LLM outage and provider outage both yield valid, clearly-labelled degraded output.
- [ ] Nothing reaches the public without a recorded human approval.
- [ ] POD, FAR, CSI and achieved lead time are published per hazard on historical events and tracked in CI.
- [ ] Issued warnings are delivered as CAP and through at least one real channel with receipts.
- [ ] Auth, rate limiting, metrics, backups, runbook and ADRs are in place; CI is green on all checks.

---

## 8. Out of scope

- Running our own numerical weather model or training a forecasting model.
- Seismic, public-health and security hazards.
- Automatic publication without human approval.
- Replacing the Folium map stack (revisit only if `P7-03` cannot be met with it).
