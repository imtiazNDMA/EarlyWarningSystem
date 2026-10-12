# path.md — Path to a Production-Ready Agentic Early Warning System

**Repo baseline:** `fresh-plan` @ `c1c8d42` (pre-`todos.md`, pre-agentic-platform, pre-MongoDB)
**Scope of this document:** critical review of the current system → target agentic architecture → phased implementation plan with per-step checklists.
**Primary goal:** extract *disaster/hazard* signals (hailstorm, flash flood, heatwave, …) from forecast data with **tools**, and compose them into the existing bilingual advisory **alongside the meteorological overview**.

---

## Part 1 — Critical Review (as-is)

### 1.1 What the system actually is

| Dimension | Current state |
|---|---|
| Shape | Single Flask monolith, 3 service singletons in `extensions.py`, 1,261-line `templates/index.html` with inline JS |
| Coverage | 155 districts / 8 province-level units (`models.PROVINCES`) |
| Data | Open-Meteo only, **9 daily variables**, parallel fetch (15 workers), SQLite cache |
| Intelligence | One-shot `ChatOpenAI` (LM Studio, `qwen/qwen3.8-27b`) prompt → JSON string → `json.loads` → SQLite |
| Hazards | **None.** The only disaster signal is the literal string of WMO codes 95/96/99 |
| Persistence | SQLite `weather.db`, 2 tables (`weather_cache`, `alerts`), WAL commented out |
| Tests | 52 collected, 50 pass, 2 fail (both pre-existing) |
| Deploy | None — no Dockerfile, no compose, no migrations, no `requirements.txt` |
| Security | No auth, no rate limit, `CORS *`, raw exception text returned to clients |

### 1.2 Findings

Severity: **S1** = broken/unsafe now · **S2** = will bite in production · **S3** = hygiene/debt

| # | Sev | Finding | Evidence |
|---|---|---|---|
| F-01 | S1 | **Core prompt crashes at runtime.** `NameError: forecast_days` — the variable is used in an f-string but is never in scope. `generate_alert()` signature is `(self, province, forecasts)`. Retries 3× then raises → alert generation is *always* broken. | `services/alert_service.py:87`, `:136-137`, `:215-216`, `:223`, `:233` |
| F-02 | S1 | **`weather_data` unbound.** The fetch is indented *inside* the `else`, so the no-districts path hits `NameError` before returning. | `routes/api_routes.py:181-196` |
| F-03 | S1 | **The LLM never sees wind, gusts, precipitation chance, snowfall, or UV.** The day-summary builder emits only Date / High / Low / Rain / WMO description — the other 6 columns in the DataFrame are silently dropped. Hail is visible only as the text `"Thunderstorm with heavy hail"` *if* code 99 happens to be the day's dominant code. | `services/alert_service.py:99-121` vs `utils/formatting.py` |
| F-04 | S1 | **No hazard model exists.** No taxonomy, no severity levels, no onset/validity window, no confidence, no evidence. A warning system cannot cite *which variable* triggered a warning. | `constants.py`, `services/alert_service.py` |
| F-05 | S2 | **False test coverage.** `tests/test_parsing.py` defines its **own local copy** of `parse_district_alerts` and asserts nothing (only `print`). It never imports `AlertService`. Always green. | `tests/test_parsing.py` |
| F-06 | S2 | **Health test patches the wrong target.** Test patches `utils.health_check.get_health_status`; `routes/api_routes.py:12` imported the name at module load, so the patch is inert → real Ollama call → 503. | `tests/test_endpoints.py:27`, `routes/api_routes.py:12` |
| F-07 | S2 | **SQLite WAL disabled** while writes come from Flask threads *and* a `ThreadPoolExecutor` — `database is locked` under concurrency is a matter of time. | `services/database.py:27` (commented out) |
| F-08 | S2 | **Exception text leaked to clients** — `str(ex)` in a 503 body. Also two bare `except:` clauses swallow `KeyboardInterrupt` and hide root causes. | `routes/api_routes.py:396`, `:135`; `services/map_service.py:350` |
| F-09 | S2 | **`/generate_alerts` returns a `task_id` nobody polls.** The only UI path is the *synchronous* `/generate_forecast_and_alerts`. `utils/background.py` and `BackgroundTaskManager` are effectively dead code. | `routes/api_routes.py:294-305`; `templates/index.html:1183` |
| F-10 | S2 | **No structured output enforcement.** Parse = find first `{` and last `}`. No schema validation, no retry-on-invalid, no claim-vs-evidence check. An LLM that hallucinates a hazard is stored verbatim as an official advisory. | `services/alert_service.py:39-84` |
| F-11 | S2 | **No evaluation harness.** Zero golden cases, zero metrics. We cannot answer "did the new prompt make alerts better or worse?" — the central risk of any LLM feature. | `tests/` |
| F-12 | S2 | **Production gaps:** no auth, no rate limiting, `CORS_ORIGINS=*`, no `/metrics`, health check performs 2 live outbound HTTP calls *per request* with no cache, secrets in `.env` (incl. a Groq key irrelevant to this baseline). | `config.py`, `utils/health_check.py` |
| F-13 | S3 | **Docs drift.** README says `qwen3-coder:latest`, `config.py` says `llama3.1`, `.env.example` says `llama3.1`, `CLAUDE.md` points at a root-level `database.py`, `AGENTS.md` documents `pip install -r requirements.txt` (file does not exist). `pyproject.toml` pins `<3.13`; runtime is 3.14. | `README.md:86,118`, `config.py:29`, `pyproject.toml:7` |
| F-14 | S3 | **Frontend debt.** `index copy.html` + `index.backup.html` shipped alongside `index.html`; `loadAllAlerts()` fetches and discards the result; alert rendering is string-concatenated `innerHTML` (XSS surface if an LLM ever emits markup). | `templates/`, `index.html:1074-1084` |
| F-15 | S3 | **Glossary hardcoded in the prompt** (~45 lines) — no versioning, no shared source of truth, duplicated between system and human messages. | `services/alert_service.py:160-210` |
| F-16 | S3 | `main.py` is a `print("Hello")` stub; `loadAllAlerts` and `/generate_forecast` paths are partially unreachable. | `main.py` |

### 1.3 The agentic gap

The current pipeline is **prompt-in, text-out**. Measured against what an agentic EWS needs:

| Capability | Required | Present? |
|---|---|---|
| Typed tools the agent can call | ✅ | ❌ none |
| Deterministic hazard extraction (code, not LLM) | ✅ | ❌ |
| Multi-step plan → act → observe → verify | ✅ | ❌ single invoke |
| Evidence / citation per hazard | ✅ mandatory for warnings | ❌ |
| Structured output schema + validation | ✅ | ❌ |
| Self-repair on invalid output | ✅ | ❌ |
| Ensemble / multi-model corroboration | ✅ | ❌ single model |
| Graceful degradation (rules-only if LLM down) | ✅ | ❌ raises → 503 |
| Memory of prior issuance (re-alert suppression) | ✅ | ❌ overwrite only |
| Evaluation & regression harness | ✅ | ❌ |

**Design stance for this plan:**

> **The LLM must never be the thing that decides a hazard exists.** Detection is deterministic code over measured/thresholded fields. The LLM's job is *narration, translation, prioritisation and roll-up* — and a validator re-checks every claim it writes against the evidence the detector produced. That is the only posture defensible for a system whose output may trigger an NDMA/PMD warning.

---

## Part 2 — Target Architecture (to-be)

### 2.1 Pipeline

```
                 ┌──────────────────────────────────────────────────────────┐
  Open-Meteo ──► │ 1. INGEST   weather_service (enriched vars + ensemble)   │
  (+ optional    └───────────────┬──────────────────────────────────────────┘
   Flood/Soil APIs)             │ raw JSON, cached in weather_cache
                                 ▼
                 ┌──────────────────────────────────────────────────────────┐
                 │ 2. DETECT   hazard engine  (pure functions, no LLM)      │
                 │    rules → HazardFinding[] with evidence[] + confidence  │
                 └───────────────┬──────────────────────────────────────────┘
                                 │ typed findings
                                 ▼
                 ┌──────────────────────────────────────────────────────────┐
                 │ 3. ORCHESTRATE  agent loop (bounded, typed, auditable)   │
                 │    plan → tools → render → verify → repair → publish     │
                 └───────────────┬──────────────────────────────────────────┘
                                 │ Advisory v2 (met_overview + hazards[])
                                 ▼
                 ┌──────────────────────────────────────────────────────────┐
                 │ 4. PERSIST   advisories / hazard_events / issuance_log   │
                 └───────────────┬──────────────────────────────────────────┘
                                 ▼
                 ┌──────────────────────────────────────────────────────────┐
                 │ 5. SERVE + RENDER  API v2, map markers, hazard chips, UI │
                 └──────────────────────────────────────────────────────────┘
```

### 2.2 Tool surface (what the agent may call)

All tools are plain Python functions with Pydantic in/out contracts. Exposed to the model via tool-calling; callable directly by tests without an LLM.

| Tool | Purpose | Deterministic? |
|---|---|---|
| `get_forecast(province, district, days, models?)` | Enriched raw forecast (daily + hourly + ensemble) | ✅ |
| `detect_hazards(district, forecast, climatology?)` | → `HazardFinding[]` | ✅ |
| `get_climatology(district, doy)` | Percentile baselines for heat/cold/precip | ✅ |
| `corroborate(finding, models)` | Ensemble agreement → confidence adjust | ✅ |
| `get_exposure(district)` | Static population/asset context (optional) | ✅ |
| `draft_advisory(findings, tone, langs)` | LLM narration (EN + UR) | ❌ LLM |
| `validate_advisory(advisory, findings)` | Schema + **claim⊆evidence** + glossary check | ✅ |
| `lookup_glossary(term)` | Shared EN↔UR term store | ✅ |
| `get_prior_issuance(district, hazard_id)` | Suppression / escalation diff | ✅ |

### 2.3 Advisory v2 schema (the contract)

```jsonc
{
  "schema_version": "2.0",
  "province": "PUNJAB",
  "forecast_days": 3,
  "issued_at": "2026-09-28T12:00:00+05:00",
  "rule_version": "1.0.0",
  "prompt_version": "2.0.0",
  "model": "qwen/qwen3.8-27b",
  "met_overview": { "english": "…", "urdu": "…" },
  "districts": [
    {
      "district": "Lahore",
      "met_overview": { "english": "…", "urdu": "…" },
      "hazards": [
        {
          "hazard_id": "hailstorm",
          "name": { "english": "Hailstorm", "urdu": "گرگے" },
          "severity": "warning",          // advisory|watch|warning|severe
          "confidence": "high",           // high|medium|low
          "onset": "2026-09-30T15:00:00+05:00",
          "duration_h": 4,
          "peak_period": { "start": "…", "end": "…" },
          "evidence": [
            { "variable": "weather_code", "value": 99, "operator": "==", "threshold": 99, "unit": "code", "source": "open-meteo:daily" },
            { "variable": "cape_max",     "value": 3150, "operator": ">=", "threshold": 2500, "unit": "J/kg", "source": "open-meteo:hourly" }
          ],
          "narrative": { "english": "…", "urdu": "…" },
          "impacts":  { "english": ["…"], "urdu": ["…"] },
          "actions":  { "english": ["…"], "urdu": ["…"] }
        }
      ]
    }
  ],
  "province_summary": { "english": "…", "urdu": "…" }
}
```

**Invariant (enforced by `validate_advisory`):** every hazard in `hazards[]` must have `len(evidence) >= 1` and every hazard *mentioned* in `narrative`/`met_overview` must exist in `hazards[]`. Zero tolerance — this is the hallucination firewall.

---

## Part 3 — Hazard Taxonomy & Detection Rules

### 3.1 Taxonomy (v1 — meteorological, extractable from Open-Meteo alone)

| `hazard_id` | EN / UR | Primary signals | Starting thresholds | Severity ladder |
|---|---|---|---|---|
| `hailstorm` | Hailstorm / **گرگے** | `weather_code` ∈ {96,99}; `cape_max`; updraft; deep-layer shear; `lightning_potential` | code 96→watch, 99→warning; CAPE ≥2500 watch, ≥3500 warning; combined ≥2 signals→severe | advisory → watch → warning → severe |
| `thunderstorm` | Thunderstorm / **گرج چمک** | `weather_code` = 95; `thunderstorm_probability`; `lightning_density` | prob ≥50% watch, ≥70% warning | as above |
| `heavy_rain` | Heavy rain / **تیز بارش** | `precipitation_sum`, hourly `precipitation`, `minutely_15` | ≥20 mm/24h watch · ≥40 mm/24h warning · ≥65 mm/24h severe | as above |
| `flash_flood` | Flash flood / **سیلاب** | ≥30 mm/6h **or** ≥8 mm/h, on saturated/urban proxy, steep-terrain flag | threshold-triggered; requires `heavy_rain` co-finding | watch → warning → severe |
| `heatwave` | Heatwave / **گرمی کی لہر** | `temperature_2m_max`, `apparent_temperature_max`, local percentile, `tmin_night` | Tmax ≥45 °C **or** ≥local P90 for ≥3 consecutive days; apparent ≥48 severe; night Tmin ≥30 → separate "warm night" note | advisory → watch → warning |
| `cold_wave` | Cold wave / **سردی کی لہر** | `temperature_2m_min`, apparent/wind-chill | Tmin ≤5 °C watch · ≤0 °C warning · ≤−5 °C severe (calibrate per region) | as above |
| `snowfall` | Snowfall / **برفباری** | `snowfall_sum`, `freezing_level_height` | ≥5 cm/24h watch · ≥10 cm warning | advisory → watch → warning |
| `fog` | Dense fog / **گھنا دھند** | `visibility`, `relative_humidity_2m` | vis ≤1000 m watch · ≤200 m or (≤500 m + RH≥95%) warning | advisory → watch → warning |
| `strong_wind` | Strong wind / **تیز ہوا** | `wind_gusts_10m_max`, `wind_speed_10m_max` | gust ≥50 km/h watch · ≥70 warning · ≥90 severe | as above |
| `dust_storm` | Dust storm / **ڈھول بھڑ** | gust ≥40 + vis ≤2 km + RH ≤30% + no precip (proxy) | **low confidence by design** — issue as "monitor" until validated | advisory only in v1 |
| `uv_extreme` | Extreme UV / **شدید UV** | `uv_index_max` | ≥11 warning · ≥8 advisory | advisory → warning |
| `flood_riverine` | Riverine flood / **دریائی سیلاب** | *(Phase 6, optional)* Open-Meteo Flood API `river_discharge` | Needs gauge/return-period data | deferred |
| `landslide` / `avalanche` | Landslide / Avalanche | *(Phase 6, optional)* rainfall+slope+snowpack | Needs DEM / soil layers | deferred |

**Severity → product colour:** `advisory`=yellow, `watch`=orange, `warning`=red, `severe`=deep red/magenta. `confidence=low` never renders as `warning` or above — it degrades to "monitor".

### 3.2 Confidence rule (deterministic, documented)

| Confidence | Rule |
|---|---|
| **high** | ≥2 independent signals over threshold **AND** (if ensemble on) ≥2/3 models agree |
| **medium** | 1 strong primary signal (e.g. `weather_code == 99`) **or** ≥2 marginal signals |
| **low** | 1 weak/proxy signal, or model disagreement → **never** issued ≥ `warning` |

### 3.3 Data enrichment required (Phase 1)

Today: 9 daily variables. Add:

- **Daily:** `rain_sum`, `showers_sum`, `precipitation_hours`, `wind_direction_10m_dominant`, `apparent_temperature_max/min`, `temperature_2m_mean`
- **Hourly:** `cape`, `convective_inhibition`, `lifted_index`, `k_index`, `precipitation`, `wind_gusts_10m`, `visibility`, `relative_humidity_2m`, `dew_point_2m`, `uv_index`, `lightning_potential`, `lightning_density`, `updraft`, `precipitation_type`, `freezing_level_height`, `wet_bulb_temperature_2m`, `snowfall`
- **15-minutely (short-range only):** `precipitation`, `wind_gusts_10m`, `cape`, `lightning_potential` — for flash-flood/onset timing
- **Ensemble:** `models=` parameter (`best_match` + e.g. `ecmwf_ifs025`, `gfs_seamless`, `icon_seamless`) for corroboration
- **Climatology:** Open-Meteo Historical API → per-district monthly percentiles for heat/cold/precip, precomputed offline

> ⚠️ Several of these are **model-dependent** (not every model returns `k_index` / `lightning_*` / `updraft`). Step 1.3 below is a hard gate: verify per-variable availability before wiring thresholds.

---

## Part 4 — Phased Implementation Plan

**Conventions:** every phase has goals, deliverables, an ordered checklist, tests, and acceptance criteria. Nothing is "done" until its checkboxes and acceptance criteria are met.
**Ordering rationale:** fix what's broken → enrich data → detect deterministically → re-shape the contract → make it agentic → prove it works → harden → ship.

---

### Phase 0 — Stabilise the baseline
**Goal:** a green, honest, non-crashing system before any new capability.
**Effort:** ~1–2 days · **Blocks:** everything

**Checklist**

- [x] **0.1** Fix F-01: pass `forecast_days` into `generate_alert()` (derive from `df.shape[0]` if callers won't supply it) and fix every `{forecast_days}` interpolation in `services/alert_service.py:136,137,215,216,223,233`
- [x] **0.2** Fix F-02: de-indent the `weather_data = ...` call in `routes/api_routes.py:188` so both branches compute it
- [x] **0.3** Fix F-06: patch `routes.api_routes.get_health_status` in `tests/test_endpoints.py:27`
- [x] **0.4** Replace F-05: delete the self-contained copy in `tests/test_parsing.py`; import `AlertService.parse_district_alerts` and write real `assert`s (valid JSON, fenced JSON, prose-wrapped JSON, legacy string, garbage → `{}`
- [x] **0.5** Fix F-07: enable WAL (`PRAGMA journal_mode=WAL`) + `busy_timeout` in `services/database.py:18-32`
- [x] **0.6** Fix F-08: replace both bare `except:` with `except Exception:`; remove `str(ex)` from the 503 body — log it, return a correlation id
- [x] **0.7** *(D1: DELETE)* Remove the dead background-task path — delete `utils/background.py`, drop the `task_id` branch of `POST /generate_alerts` in `routes/api_routes.py:294-305`, and remove `BackgroundTaskManager` imports/usages. The pipeline stays synchronous like the only UI path already expects. Add a test asserting `/generate_alerts` has no `task_id` key.
- [x] **0.8** Fix F-13: single source of truth for model id (config + `.env.example` + README + CLAUDE.md); align `pyproject.toml` `requires-python` with the runtime; add `requirements.txt` *or* correct `AGENTS.md`
- [x] **0.9** Delete `templates/index copy.html` and `templates/index.backup.html`; remove the dead `loadAllAlerts()` call body or make it actually render
- [x] **0.10** Make `loadAllAlerts()`/health checks deterministic in tests (no live outbound HTTP)
- [x] **0.11** Delete or wire up the `main.py` stub
- [x] **0.12** `ruff check .` + `ruff format --check .` clean; `bandit -r .` reviewed
- [x] **0.13** Switch the LLM runtime: drop Ollama/`llama3.1`; `services/alert_service.py` now uses `langchain_openai.ChatOpenAI` against an OpenAI-compatible server (`LLM_BASE_URL`, `LLM_MODEL`); `utils/health_check.py` probes `GET {base}/models` (key `llm_status`); `AlertService.clean_llm_response` strips Qwen3 thinking blocks and ``` fences before `json.loads`; deps `langchain-ollama` -> `langchain-openai`; README/CLAUDE.md/.env.example/CI updated. Live smoke-tested against LM Studio.

**Tests**
- `pytest tests/ -v` → **all green, 0 skipped**
- New: `test_generate_alert_prompt_contains_forecast_days` (guards F-01 from regressing)
- New: `test_generate_forecast_no_districts` (guards F-02)
- New: `test_health_endpoint_does_not_call_network`
- New: `test_init_uses_configured_openai_endpoint` + `TestCleanLLMResponse` (guards the LM Studio / langchain-openai switch)

**Acceptance criteria**
- [x] Full suite green with no network and no LLM running
- [x] `/generate_forecast` works with an empty district list
- [x] `/generate_alerts` returns parseable output for a mocked LLM
- [x] No S1 findings remain open

---

### Phase 1 — Enrich the data layer
**Goal:** give the detector the fields it needs; nothing else changes for users.
**Effort:** ~2–3 days · **Blocks:** Phase 2

**Checklist**

- [ ] **1.1** Add `hazard_fields.py` (or `config.HAZARD_*` groups) declaring daily/hourly/minutely variable lists — one place, imported by `WeatherService`
- [ ] **1.2** Extend `WeatherService.get_bulk_weather_data()` request params with daily + hourly (+ `minutely_15` for ≤2 days) groups
- [ ] **1.3** **GATE — availability probe:** script `scripts/probe_variables.py` hitting Open-Meteo for 6 representative coordinates × `models=` candidates; emit `docs/variable_availability.md`. *Do not proceed until reviewed.*
- [ ] **1.4** Decide ensemble policy: `off` (default, cheapest) / `corroborate` (2 extra models on hazard-flagged districts only) — config flag `ENSEMBLE_MODE`
- [ ] **1.5** Extend `create_weather_dataframe()` (or add `create_hazard_frame()`) — **keep the existing column names byte-identical**, add new columns alongside
- [ ] **1.6** Version the cache key (`weather_v2_…`) so stale 9-variable payloads aren't read as new-format
- [ ] **1.7** Bump `weather_cache` payload size expectations; re-check SQLite write latency with WAL from Phase 0
- [ ] **1.8** Offline climatology builder: `scripts/build_climatology.py` → `static/climatology/{district}.parquet` (P50/P75/P90/P95 Tmax/Tmin/precip by month), committed or built in CI
- [ ] **1.9** Unit tests for each variable group's request construction and response normalisation (scalar-vs-list, missing keys)

**Tests**
- `test_weather_service.py`: request params include each new group; missing optional variables degrade gracefully
- Normalisation tests: scalar `daily` values, `null` entries, absent `minutely_15`

**Acceptance criteria**
- [ ] A raw payload for any district contains CAPE + gusts + visibility + precipitation_type
- [ ] Old cached rows cannot be misread as new-format (version key)
- [ ] Probe doc reviewed and thresholds in Phase 2 adjusted to real availability
- [ ] p95 fetch latency for 36 districts documented (baseline vs enriched)

---

### Phase 2 — Deterministic hazard detection engine ("the tools")
**Goal:** pure, testable, LLM-free code that turns a forecast into typed hazard findings with evidence.
**Effort:** ~4–6 days · **Blocks:** Phase 3, Phase 4

**Checklist**

- [ ] **2.1** Create `hazards/` package: `types.py` (`Severity`, `Confidence`, `Evidence`, `HazardFinding` as Pydantic models), `taxonomy.py` (ids, EN/UR names, colour tokens)
- [ ] **2.2** `rules/` — one module per hazard (`hailstorm.py`, `heavy_rain.py`, `heatwave.py`, …), each exposing `detect(fc: DistrictForecast, ctx: DetectContext) -> list[HazardFinding]`
- [ ] **2.3** `thresholds.py` — all numbers in ONE data table (YAML or Python dict) with `version`, per-region overrides, and `severity` mapping. **No magic numbers in rule code.**
- [ ] **2.4** `hailstorm` rule: WMO 96/99 direct + CAPE bands + shear/freezing-level corroboration; produce evidence for every trigger
- [ ] **2.5** `heavy_rain` + `flash_flood` rules (24h bands and 6h/1h short-circuit from minutely)
- [ ] **2.6** `heatwave` / `cold_wave` rules using climatology percentiles **with** absolute fallbacks when climatology is missing
- [ ] **2.7** `strong_wind`, `snowfall`, `fog`, `thunderstorm`, `uv_extreme`, `dust_storm`(proxy) rules
- [ ] **2.8** `engine.py`: run all rules, dedupe/merge (same hazard overlapping windows → one finding with combined evidence), order by severity→confidence→onset
- [ ] **2.9** `confidence.py`: implement §3.2 including ensemble agreement adjustment
- [ ] **2.10** `onset.py`: compute onset/peak/duration from the hourly series (first crossing → last crossing), not from daily buckets
- [ ] **2.11** Exposure/context helper stub (`get_exposure`) returning `None` safely so the agent contract is stable
- [ ] **2.12** Golden-fixture harness: `tests/fixtures/forecast/*.json` (at least: plain day, hail day, extreme rain, heatwave, fog morning, no-hazard) + `tests/test_rules_*.py` asserting exact findings, severities and evidence entries
- [ ] **2.13** Property/invariant tests: `severity ≥ warning ⇒ confidence ≠ low`; `len(evidence) ≥ 1` always; findings are JSON-round-trippable
- [ ] **2.14** Write `docs/hazards.md` — human-readable spec of every rule, threshold, and its rationale/calibration source (PMD/NDMA/WMO reference). *(D2)* Every threshold carries `status: needs-review`; the **domain reviewer** signs off per-threshold — engineering may not mark one `approved`. Gate for Phase 8.

**Tests**
- ≥40 rule unit tests across 6 fixtures
- Snapshot test: full engine output for the hail fixture matches a committed JSON snapshot
- Threshold table version is asserted equal to `rule_version` in outputs

**Acceptance criteria**
- [ ] `detect_hazards()` runs with **no LLM available**
- [ ] Hail fixture produces a `hailstorm` finding with ≥2 evidence rows and correct onset
- [ ] Clean fixture produces **zero** findings (false-alarm guard)
- [ ] Every finding round-trips through JSON and validates
- [ ] `docs/hazards.md` merged and reviewed by a domain reviewer

---

### Phase 3 — Advisory schema v2 + persistence + API
**Goal:** the alert becomes a *structured document* that can carry hazards, while the UI keeps working.
**Effort:** ~3–4 days · **Blocks:** Phase 4, 5

**Checklist**

- [ ] **3.1** `advisory.py`: Pydantic models mirroring §2.3, with `schema_version`, `met_overview`, `districts[].hazards[]`, `province_summary`
- [ ] **3.2** Backward-compat shim: `AdvisoryV2.to_legacy_v1()` → `{"english":…, "urdu":…}` so existing `/get_alert` and the UI don't break during migration
- [ ] **3.3** DB migration — new tables (keep `alerts` reading as legacy):
  ```sql
  CREATE TABLE IF NOT EXISTS advisories (
    id INTEGER PRIMARY KEY,
    province TEXT NOT NULL, forecast_days INTEGER NOT NULL,
    schema_version TEXT NOT NULL, payload TEXT NOT NULL,
    rule_version TEXT NOT NULL, prompt_version TEXT NOT NULL,
    model TEXT, issued_at TIMESTAMP NOT NULL, valid_from TIMESTAMP, valid_to TIMESTAMP,
    status TEXT DEFAULT 'draft',                 -- draft|approved|published  (D3)
    approved_by TEXT, approved_at TIMESTAMP,
    UNIQUE(province, forecast_days, valid_from)
  );
  CREATE TABLE IF NOT EXISTS hazard_events (
    id INTEGER PRIMARY KEY,
    province TEXT, district TEXT, hazard_id TEXT,
    severity TEXT, confidence TEXT, onset TIMESTAMP, duration_h REAL,
    evidence TEXT, status TEXT DEFAULT 'draft',   -- draft|issued|superseded|expired  (D3: duty-officer gate)
    advisory_id INTEGER REFERENCES advisories(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_hazard_events_lookup
    ON hazard_events(province, district, hazard_id, status);
  ```
- [ ] **3.4** Additive-only migration runner (`utils/migrations/`, ordered `.sql` files, recorded in `schema_migrations` table)
- [ ] **3.5** `POST /api/v2/advisories` (generate → lands `status='draft'`), `GET /api/v2/advisories/<province>?days=` (with `?status=` filter), `GET /api/v2/hazards?province=&severity=&status=`, and *(D3)* `POST /api/v2/advisories/<id>/approve` + `/reject` (audited: who/when)
- [ ] **3.6** Keep legacy routes; internally they read v2 and project to v1 — legacy path reads **only `status='issued'`** advisories, so nothing unapproved leaks to the existing UI (D3)
- [ ] **3.7** Harden response errors (F-08): consistent `{"error": {"code":…, "message":…, "request_id":…}}`
- [ ] **3.8** Escalation/suppression logic: compare against `hazard_events` with `status='issued'` → `escalate` / `re-issue` / `suppress` (no churn on every refresh); `draft` events are visible to the reviewer but **never** suppress an issued one
- [ ] **3.9** Idempotency: same `(province, days, valid_from)` → upsert, not duplicate rows

**Tests**
- Migration up/down on a temp DB; round-trip v2→v1→v2 projection equality
- API contract tests (schema validation of every response body)
- Escalation test matrix (new / same / lower / expired)

**Acceptance criteria**
- [ ] Legacy UI renders unchanged from v2 data (v1 projection)
- [ ] A v2 payload with a hailstorm survives save → load → validate
- [ ] Re-issuing the same window does not duplicate `hazard_events`
- [ ] Migration runs from a clean DB and from the pre-existing `weather.db`
- [ ] A generated advisory is `draft` and **not** visible through legacy/public routes until approved (D3)

---

### Phase 4 — Agentic orchestration
**Goal:** an auditable, bounded tool loop that drafts, verifies and repairs the advisory — with deterministic fallback.
**Effort:** ~5–7 days · **Blocks:** Phase 6

**Checklist**

- [ ] **4.1** `agent/provider.py` — `LLMProvider` protocol with `OllamaProvider` + `OpenAICompatProvider` (LM Studio/vLLM — `.env` already carries LM Studio vars); config selects at runtime
- [ ] **4.2** `agent/tools.py` — register the 9 tools from §2.2 with JSON-schema contracts; **every tool is directly unit-testable without an LLM**
- [ ] **4.3** `agent/graph.py` — **fixed, bounded DAG** (not open-ended ReAct): `PLAN → DETECT → DRAFT → VERIFY → (REPAIR × ≤2) → PUBLISH`. Rationale: an EWS must be auditable and cheap; free-form agents are not.
- [ ] **4.4** `PLAN`: rank districts by detector score, decide how many to draft in full vs. summarise (token budget)
- [ ] **4.5** `DRAFT`: two-stage — (a) `draft_met_overview` (the existing met narrative, now fed the *full* enriched frame), (b) `draft_hazard_block` per finding (narrative + impacts + actions, EN+UR), plus a province roll-up
- [ ] **4.6** Prompt assets move out of code: `prompts/met_overview/v2.md`, `prompts/hazard_block/v2.md`, `prompts/summary/v2.md` with `prompt_version` stamped into the advisory
- [ ] **4.7** Glossary moves to `i18n/glossary.yaml` (EN↔UR, hazard names, severity words, action phrases) — loaded by both prompt renderer and validator
- [ ] **4.8** `VERIFY` (hard gate): schema validate → **every narrative hazard ∈ detector findings** → **every `evidence` value within ±tolerance of source data** → glossary compliance (no transliterated weather terms) → EN/UR claim parity (same numbers, same days, same severity)
- [ ] **4.9** `REPAIR`: pass structured errors back (`[{path, code, expected, actual}]`) for a bounded re-draft; on 2 failures → degrade to deterministic renderer
- [ ] **4.10** `DETERMINISTIC FALLBACK`: rules-only renderer that assembles EN/UR bullets from `HazardFinding` fields (templated, no LLM) — the system **never** returns 503 because the LLM is down
- [ ] **4.11** Observability: per-stage timing, token usage, tool-call log, and `verification_results` persisted with each advisory
- [ ] **4.12** Timeouts + circuit breaker per provider; structured logs with `request_id`
- [ ] **4.13** Unit tests for the graph with a scripted fake LLM (happy path, invalid JSON → repair, verifier failure ×2 → fallback, provider timeout → fallback)

**Tests**
- ≥15 graph tests with `FakeLLM` covering all branches
- Contract test: `validate_advisory` **rejects** a fixture that invents a hazard not in findings (the hallucination firewall)
- Contract test: fallback renderer produces a valid Advisory v2 with zero LLM calls

**Acceptance criteria**
- [ ] Full pipeline produces a valid Advisory v2 with `met_overview` + ≥1 hazard for the hail fixture
- [ ] With the LLM process killed, the endpoint still returns a valid advisory in <2s
- [ ] 100% of emitted advisories pass `validate_advisory` in CI
- [ ] Every advisory row is traceable to `rule_version` + `prompt_version` + `model` + tool-call log

---

### Phase 5 — Frontend: hazard-aware UI
**Goal:** hazards are visible, scannable and bilingual — not buried in prose.
**Effort:** ~3–4 days · **Blocks:** — (parallel with 6)

**Checklist**

- [ ] **5.1** `formatAlertText()` → render from Advisory v2: `met_overview` block, then hazard chips/badges (colour by severity, glyph per hazard, UR name alongside EN)
- [ ] **5.2** Hazard card: name, severity, confidence, onset window, peak, expandable evidence list ("CAPE 3150 J/kg ≥ 2500")
- [ ] **5.3** Actions/impacts lists rendered as bullet items (EN above, UR below, RTL block)
- [ ] **5.4** Map: marker colour = max severity in district; popup gets a hazard strip; legend added
- [ ] **5.5** Timeline strip: 7-day bar per district with hazard windows highlighted
- [ ] **5.6** `/api/v2/hazards` filter panel: by severity / hazard type / province
- [ ] **5.7** Sanitise all rendered strings (no raw `innerHTML` from LLM output — escape, then style)
- [ ] **5.8** Keep a "legacy view" toggle during rollout; remove once v2 is default
- [ ] **5.9** Responsive + RTL verification; remove Typed.js animation from hazard blocks (fast, scannable > cinematic for warnings)
- [ ] **5.10** A11y pass: severity conveyed by icon+text (not colour alone), keyboard navigation, `aria-live` on new advisories
- [ ] **5.11** *(D3, rollout gate)* Duty-officer review queue: list `draft` advisories, side-by-side EN/UR preview, evidence view, **Approve / Reject** with reason → calls `/api/v2/advisories/<id>/approve|reject`; approved advisories then surface as issued

**Tests**
- JS unit tests for the v2 renderer (jest/vitest or Python-served golden HTML snapshots)
- XSS test: advisory containing `<img onerror=…>` renders inert
- Visual snapshot of the hail fixture advisory

**Acceptance criteria**
- [ ] Hail fixture shows an orange/red "Hailstorm / گرگے" chip with onset and 2 evidence rows
- [ ] Met overview still reads as before (no regression for existing users)
- [ ] Zero unescaped LLM-derived markup in the DOM

---

### Phase 6 — Evaluation harness (the reason we can trust it)
**Goal:** measurable quality; no more "the new prompt feels better".
**Effort:** ~4–5 days · **Blocks:** Phase 7 rollout gate

**Checklist**

- [ ] **6.1** `evals/cases/` — ≥30 annotated cases: 10 synthetic fixtures + ≥10 real historical events (e.g. 2022 Pakistan floods, pre-monsoon hail events, 2023 heatwave) + ≥10 clear-negative days
- [ ] **6.2** Annotation format: per district, ground-truth `hazard_id`, `severity`, `window`
- [ ] **6.3** `evals/run.py` — executes full pipeline per case, writes `evals/results/{timestamp}.json`
- [ ] **6.4** Metrics: **POD**, **FAR**, **CSI** per hazard; severity accuracy; onset timing error (hours); schema-validity rate; **hallucinated-hazard rate** (target **0%**); EN/UR number parity
- [ ] **6.5** LLM-specific: nondeterminism check (3 runs/case, report disagreement), token cost/case, p50/p95 latency
- [ ] **6.6** `evals/report.py` → markdown + HTML diff report; CI job runs the *fast* subset on every PR and fails on regression > tolerance
- [ ] **6.7** Human-review rubric + 5-sample bilingual review protocol (documented in `docs/evaluation.md`)
- [ ] **6.8** Threshold calibration loop: feed `evals` results back into `thresholds.py` until CSI acceptable per hazard
- [ ] **6.9** Baseline snapshot recorded **before** any prompt/threshold change

**Acceptance criteria**
- [ ] Baseline metrics recorded and committed
- [ ] `hallucinated-hazard rate == 0` across the suite
- [ ] CSI ≥ agreed floor per hazard (set in 6.8; suggestion: ≥0.6 for `heavy_rain`/`heatwave`, ≥0.4 for `hailstorm`) — with documented justification where lower
- [ ] CI blocks a PR that regresses any metric beyond tolerance
- [ ] Cost and p95 latency within the budget agreed with ops

---

### Phase 7 — Production hardening
**Goal:** safe to expose beyond a dev laptop.
**Effort:** ~4–6 days · **Blocks:** rollout

**Checklist**

- [ ] **7.1** Auth: service tokens (`Authorization: Bearer`) for write endpoints; read endpoints gated or IP-restricted as policy dictates
- [ ] **7.2** Rate limiting (per token + per IP), with 429 + `Retry-After`
- [ ] **7.3** `CORS_ORIGINS` defaults to deny-all in production config; fail startup if `*` when `FLASK_ENV=production`
- [ ] **7.4** Structured JSON logging with `request_id` propagation into the agent tool log
- [ ] **7.5** `/metrics` (Prometheus): request counts/latency, LLM calls+tokens+errors, hazard counts by severity, verification-failure count, fallback-triggered count
- [ ] **7.6** Health check split: `/health/live` (no I/O) and `/health/ready` (cached dependency checks, TTL 30s) + DB check
- [ ] **7.7** `Dockerfile` (non-root, multi-stage) + `docker-compose.yml` (app + optional local LLM) + `.dockerignore`
- [ ] **7.8** Config: validate at startup, refuse defaults in production (`SECRET_KEY`, `MAPBOX_TOKEN`, origins); move secrets out of the repo; rotate the Groq key currently sitting in `.env`
- [ ] **7.9** Backup/retention: nightly `weather.db` snapshot or migrate to Postgres; retention policy for `advisories`/`hazard_events`
- [ ] **7.10** Graceful shutdown + single-worker vs multi-worker decision documented (SQLite ⇒ start with 1 worker + WAL, or move to Postgres before scaling out)
- [ ] **7.11** Security pass: `bandit`, `safety`, dependency pinning (`uv.lock` in CI), no secret scanning findings
- [ ] **7.12** CI upgrade: add migration test, eval fast subset, Docker build, ruff format check (currently only `ruff check`)

**Acceptance criteria**
- [ ] `docker compose up` serves a working dashboard with a valid advisory
- [ ] Unauthenticated write request → 401; burst → 429
- [ ] `/metrics` exposes hazard + LLM + verification counters
- [ ] Startup fails fast on missing/unsafe production config
- [ ] No secrets in git history for the new branches (rotate anything that leaked)

---

### Phase 8 — Rollout & handover
**Effort:** ~2–3 days

- [ ] **8.1** Staged rollout: `flag: ADVISORY_V2_ENABLED` — internal → PMD/NEOC duty officers → public
- [ ] **8.2** *(D3: REQUIRED)* Duty-officer approval gate live: v2 advisories are born `draft`, only `approve` flips them to `issued`, and the legacy/public projection serves issued only. Duty officers trained on the 5.11 queue; rejection reasons captured.
- [ ] **8.3** Runbook: `docs/runbook.md` (deploy, rollback, LLM outage behaviour, threshold override procedure, incident triage)
- [ ] **8.4** `docs/adr/0001-agentic-architecture.md`, `0002-hazard-detection-is-deterministic.md`, `0003-sqlite-vs-postgres.md`
- [ ] **8.5** Update `README.md`, `CLAUDE.md`, `AGENTS.md` to match reality (F-13)
- [ ] **8.6** Sprint-0 knowledge transfer: architecture walkthrough, threshold calibration session
- [ ] **8.7** Retrospective on the pre-agentic branch (`feature/agentic-platform-foundation`) — salvage anything worth keeping (ensemble ingestion, deterministic workflow) **into** this design rather than re-adopting `todos.md`

---

## Part 5 — Sequencing & Dependencies

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 6 ──► Phase 8
                                              │              ▲
                                              └─► Phase 5 ───┤ (parallel)
                                              └─► Phase 7 ───┘ (parallel, gate before 8)
```

| Phase | Depends on | Can start with | Est. effort |
|---|---|---|---|
| 0 Stabilise | — | now | 1–2 d |
| 1 Data enrichment | 0 | 0.1–0.2 | 2–3 d |
| 2 Hazard engine | 1.3 (gate) | fixtures in parallel | 4–6 d |
| 3 Schema + API | 2 | stub findings | 3–4 d |
| 4 Agentic loop | 3 | FakeLLM from day 1 | 5–7 d |
| 5 Frontend | 3 | v2 fixture JSON | 3–4 d |
| 6 Evaluation | 2, 4 | annotation can start at 0 | 4–5 d |
| 7 Hardening | 4 | 7.7 Docker early | 4–6 d |
| 8 Rollout | 5, 6, 7 | — | 2–3 d |

**Critical path:** 0 → 1 → 2 → 3 → 4 → 6 → 8 ≈ **4–5 weeks** single senior engineer; ~3 weeks with two (2‖5, 7‖6).

---

## Part 6 — Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | LLM invents a hazard not in the data | Med | **Critical** | Hard verifier gate (4.8) + hallucination metric = 0 in CI (6.4) + deterministic fallback |
| R2 | Thresholds produce false alarms → warning fatigue | High | High | Calibration loop (6.8), confidence floors (§3.2), human approval gate (8.2) |
| R3 | Open-Meteo variables unavailable for chosen models | Med | High | Availability probe is a **hard gate** (1.3) |
| R4 | Free-form agent = non-reproducible advisories | Med | High | Fixed DAG (4.3), versioned prompts + rules stamped on every row |
| R5 | SQLite write contention at concurrency | Med | Med | WAL (0.5) → Postgres before multi-worker (7.10) |
| R6 | Scope creep back toward `todos.md`-style agentic platform | Med | Med | This file is the plan of record; changes go through ADRs (8.4) |
| R7 | Urdu quality / transliteration regressions | Med | Med | Glossary as data (4.7), parity check in verifier, bilingual human sample (6.7) |
| R8 | Latency too high for a 155-district refresh | Med | Med | Plan stage ranks districts, drafts only flagged ones; fallback <2s |
| R9 | Python 3.14 vs `requires-python <3.13` | High | Low | Resolve in 0.8 before anything else depends on it |

---

## Part 7 — Definition of Done (programme level)

- [ ] All S1/S2 findings (F-01…F-12) closed with regression tests
- [ ] `detect_hazards()` produces evidence-backed findings for hailstorm, heavy rain, flash flood, heatwave, cold wave, fog, strong wind, snowfall, thunderstorm, UV — with **zero LLM involvement**
- [ ] Advisory v2 renders `met_overview` **and** a hazard list per district, bilingual, with onset + evidence
- [ ] Verifier rejects any advisory whose narrative claims an unsupported hazard (test-enforced)
- [ ] LLM outage → advisory still issued from the deterministic renderer
- [ ] Evaluation harness green in CI; hallucination rate 0; POD/FAR/CSI recorded per hazard
- [ ] Auth, rate limit, metrics, health split, Docker, secret hygiene all in place
- [ ] Duty-officer approval gate enforced end-to-end: `draft` → `issued` only via explicit approval; nothing unapproved reaches the public/legacy projection
- [ ] Runbook + ADRs + updated README/CLAUDE/AGENTS delivered
- [ ] `pytest`, `ruff check`, `ruff format --check`, `bandit`, `safety` all clean in CI

---

## Part 8 — Explicitly out of scope (v1)

- Nowcasting / radar / satellite ingestion (Open-Meteo is forecast-only)
- Non-meteorological hazards: seismic, public health, maritime
- `landslide`, `avalanche`, `riverine flood` — deferred to Phase 6/7 optional extensions (need DEM/soil/discharge layers)
- Automatic public dissemination (SMS/WhatsApp/email) — advisory issuance only; distribution is a separate programme
- Replacing the map/Folium stack
- Re-adopting the pre-agentic `todos.md` / MongoDB plan wholesale

---

## Appendix A — Decisions log

| # | Decision | Status | Date |
|---|---|---|---|
| D1 | **0.7 — dead background-task path: DELETE.** Remove `utils/background.py` and the `task_id` branch of `/generate_alerts`; the pipeline stays synchronous, matching the only UI path (`/generate_forecast_and_alerts`). | ✅ decided | 2026-09-28 |
| D2 | **2.14 — threshold reviewer: a domain reviewer IS available.** Every threshold in `docs/hazards.md` is marked `status: needs-review` until that reviewer signs off; engineering must not flip a threshold to "approved". | ✅ decided | 2026-09-28 |
| D3 | **8.2 — approval gate: DUTY-OFFICER APPROVAL.** v2 advisories are created with `status='draft'` and only become `status='issued'` after explicit human approval. Phases 3 and 8 must carry this through: `hazard_events.status` gains `draft`, and Phase 5 must ship the review/approve UI before public rollout. | ✅ decided | 2026-09-28 |
| D4 | Severity ladder names (§3.1) → to be mapped to PMD/NDMA official product levels by the domain reviewer. | ⏳ open | — |
| D5 | Ensemble mode default (1.4) and single vs multi model for v1. | ⏳ open (gate: 1.3 probe) | — |
| D6 | **LLM runtime: OpenAI-compatible server (LM Studio) serving `qwen/qwen3.8-27b` at `http://172.18.1.153:1234/v1`.** Ollama support removed; config keys are `LLM_*` (legacy `LM_STUDIO_*` still honoured); health check probes `GET /v1/models`; runtime client is `langchain-openai`. | ✅ decided | 2026-09-28 |

## Appendix B — File map of the target state

```
hazards/                 # Phase 2 — pure detection, no LLM
  types.py taxonomy.py thresholds.py engine.py confidence.py onset.py
  rules/{hailstorm,heavy_rain,flash_flood,heatwave,cold_wave,snowfall,
         fog,strong_wind,thunderstorm,dust_storm,uv_extreme}.py
agent/                   # Phase 4 — orchestration
  provider.py tools.py graph.py fallback.py verifier.py
advisory/                # Phase 3 — schema + projection
  models.py legacy.py
prompts/                 # Phase 4 — versioned prompt assets
  met_overview/v2.md hazard_block/v2.md summary/v2.md
i18n/glossary.yaml       # Phase 4 — shared EN/UR terminology
utils/migrations/        # Phase 3 — ordered SQL
evals/                   # Phase 6 — cases, run, report
docs/{hazards,evaluation,runbook}.md  docs/adr/*.md
```

---

*This file is the plan of record. Changes to scope, ordering, or thresholds should be recorded here with a date and an ADR reference — not absorbed silently.*
