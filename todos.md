# Agentic Extreme Weather Early Warning System Implementation Plan

## Purpose

Transform the current Flask weather dashboard into a production-grade, agentic early warning system that autonomously monitors forecasts up to 15 days, detects extreme-weather risks deterministically, creates grounded bilingual warning candidates, supports human approval, and distributes versioned warnings through reliable channels.

This plan is based on a code review of the current repository. It is intentionally safety-first: an LLM may explain and translate verified warning facts, but it must never be the authority that decides whether a hazard exists, its severity, geography, timing, or publication status.

## Current-State Verdict

The codebase is a useful prototype, not yet an operational early warning system.

- Weather retrieval is manual, single-source, daily, district-centroid based, and limited to 7 days (`utils/validation.py`, `services/weather_service.py`).
- The LLM currently interprets forecast text and creates public-facing hazard claims directly (`services/alert_service.py`).
- Important fetched fields such as probability, wind, gusts, snow, and UV are omitted from the LLM prompt.
- Parsed LLM output is weakly validated, old alerts are purged first, and partial or malformed output can erase valid alerts (`routes/api_routes.py`).
- Alerts are mutable cache rows rather than immutable, versioned warning events (`services/database.py`).
- Background work uses daemon threads and process-local dictionaries, with no durable job state or status endpoint (`utils/background.py`).
- Forecast and warning generation, cache deletion, and expensive LLM work are unauthenticated; CORS defaults to all origins.
- Model output is rendered with unsafe HTML patterns in the template and map popup code, creating stored-XSS risk.
- Weather/API failures can be swallowed or reported as success; partial district coverage is not represented reliably.
- The map can substitute unrelated district geometries, which is unacceptable for warning geography (`services/map_service.py`).
- The frontend lacks warning provenance, issue/valid times, certainty, lifecycle state, accessible mobile controls, and reliable degraded/offline behavior.
- Production deployment, observability, migrations, recovery, notification delivery, forecast verification, and model/rule governance are incomplete.

## Non-Negotiable Safety Principles

- [ ] **SAFE-001: Keep hazard decisions deterministic.** Rules and validated data determine hazard type, severity, certainty, urgency, affected area, onset, expiry, and allowed actions.
  - Acceptance: Replaying identical normalized data with the same rule/configuration version produces byte-equivalent hazard findings.
  - Acceptance: Every finding cites rule IDs, source run IDs, observations, units, and valid times.

- [ ] **SAFE-002: Restrict the LLM to grounded language work.** The LLM may summarize, translate, simplify, and create channel-length variants from a closed structured warning record.
  - Acceptance: The LLM cannot add, remove, or alter hazards, severity, geography, dates, numbers, or prescribed actions.
  - Acceptance: The system can publish approved deterministic templates when the LLM is unavailable.

- [ ] **SAFE-003: Fail closed, never to an all-clear.** Missing, stale, partial, invalid, or contradictory data must produce an explicit unavailable/insufficient-data state.
  - Acceptance: Provider, database, parser, or translation failure cannot generate "no severe weather" or replace a current warning.

- [ ] **SAFE-004: Preserve warning history.** Warning candidates and published warnings are immutable and versioned; correction, update, cancellation, and expiry are explicit events.
  - Acceptance: No workflow deletes or overwrites the last approved warning before a valid replacement is committed.

- [ ] **SAFE-005: Keep publication authority outside the LLM.** Publishing and delivery are policy-controlled operations with authenticated actors and complete audit history.
  - Acceptance: The LLM has no tool or database permission to approve, publish, cancel, or send warnings.

- [ ] **SAFE-006: Separate severity, certainty, and urgency.** Long-range uncertainty must not be hidden inside prose.
  - Acceptance: Every warning/outlook has independently computed severity, certainty, urgency, and confidence evidence.

## Target Architecture

Build a modular monolith first, with deep modules and explicit seams. Split into separately deployed systems only when operational scaling requires it.

1. **Scheduler and durable workflow** identifies source update times and starts idempotent forecast runs.
2. **Provider adapters** retrieve forecast, ensemble, observations, official warnings, flood, air-quality, and marine data through typed interfaces.
3. **Normalization and quality control** standardize units/time/geography, validate freshness/completeness, and retain raw payload provenance.
4. **Feature engine** derives duration, accumulation, heat stress, antecedent rainfall, trends, probabilities, and source agreement.
5. **Deterministic hazard engine** produces typed evidence-backed hazard findings.
6. **Reconciliation and lifecycle engine** compares prior runs, active warnings, official bulletins, and material changes to propose issue/update/escalate/cancel/expire/no-op.
7. **Language module** creates English, Urdu, audience, and channel variants from immutable canonical facts.
8. **Validation module** verifies schema, numeric grounding, terminology, translation parity, safety policy, and completeness.
9. **Review and approval module** applies severity-based human-on-the-loop policy.
10. **Publisher and delivery adapters** atomically publish and idempotently disseminate approved versions.
11. **Observer and evaluator** tracks freshness, latency, delivery, forecast skill, false alarms, misses, overrides, and incidents.

## Core Domain Contracts

- [ ] **ARCH-001: Define typed domain models before expanding behavior.**
  - Add models for `Location`, `ForecastRun`, `ForecastPoint`, `DataQualityReport`, `HazardFinding`, `WarningEvent`, `WarningVersion`, `Translation`, `Approval`, `DeliveryAttempt`, and `WorkflowRun`.
  - Use stable location IDs rather than province/district display names as primary identifiers.
  - Store timestamps in UTC and retain the source timezone for presentation.
  - Acceptance: Domain modules contain no Flask, Folium, pandas, LangChain, requests, or database-specific types.
  - Acceptance: JSON Schema/OpenAPI representations are versioned and reject unknown fields where safety-relevant.

- [ ] **ARCH-002: Create explicit interfaces at real seams.**
  - Define small interfaces for forecast providers, repositories, hazard evaluation, language rendering, workflow execution, approval policy, and delivery channels.
  - Inject adapters instead of importing module-level singletons.
  - Acceptance: Production and in-memory test adapters exist for each interface before calling the seam complete.

- [x] **ARCH-003: Introduce a Flask application factory and composition root.**
  - Remove import-time config validation, database initialization, service creation, logging file creation, and runtime directory creation from `app.py`, `config.py`, and `extensions.py`.
  - Acceptance: Tests create isolated applications with temporary databases and fake providers without patching global objects.
  - Acceptance: Importing the package performs no network, database, or filesystem writes.

## Phase 0: Immediate Safety and Integrity Baseline

Do not expose the system as an authoritative warning service until this phase is complete.

### Authentication, Authorization, and Abuse Prevention

- [ ] **SEC-001: Split public read routes from operator routes.**
  - Move APIs under a versioned prefix such as `/api/v1`.
  - Keep only explicitly published warning and public forecast endpoints anonymous.
  - Require authentication for generation, job status details, approval, publication, cancellation, replay, and cache/administration operations.
  - Acceptance: Anonymous requests to every mutation endpoint return `401`; authenticated viewers receive `403`; authorized roles pass.

- [ ] **SEC-002: Implement RBAC and actor audit identity.**
  - Define at least `viewer`, `analyst`, `approver`, `publisher`, `administrator`, and machine-service roles.
  - Acceptance: Every state-changing event records actor, role, timestamp, reason, source IP/client, correlation ID, and before/after identifiers.

- [ ] **SEC-003: Add CSRF protection, request limits, rate limits, and concurrency quotas.**
  - Apply CSRF when cookie-based operator authentication is used.
  - Rate-limit by actor/IP/operation and cap concurrent expensive workflows.
  - Acceptance: Security tests cover burst limits, sustained limits, oversized bodies, replay, and concurrent duplicate submission.

- [ ] **SEC-004: Lock down browser security.**
  - Replace wildcard production CORS with explicit origins, methods, and headers.
  - Add CSP with nonces/hashes, HSTS, `frame-ancestors`, `nosniff`, referrer policy, permissions policy, and secure cookie settings.
  - Acceptance: Production startup fails on wildcard CORS, default secret, debug mode, or insecure cookies.

### LLM and Browser Safety

- [ ] **AI-001: Add a strict warning-language output schema.**
  - Replace best-effort brace extraction in `AlertService.parse_district_alerts` with schema-constrained output and strict validation.
  - Require expected stable location IDs, non-empty English/Urdu, exact allowed fields, and no additional keys.
  - Acceptance: Malformed, truncated, duplicate, missing, extra-location, empty-language, oversized, and wrong-type outputs are rejected.

- [ ] **AI-002: Stop destructive alert replacement.**
  - Persist LLM output as an untrusted candidate.
  - Validate the complete expected result before an atomic candidate/version transition.
  - Never purge the active warning before replacement succeeds.
  - Acceptance: Failure-injection tests prove all current approved warnings remain unchanged after parsing, translation, database, or timeout failures.

- [ ] **SEC-005: Eliminate stored and DOM XSS.**
  - Treat LLM and database content as untrusted text.
  - Replace `innerHTML` use with `textContent`/explicit node creation for warnings and toasts.
  - Remove inline event handlers and unsafe `data-alert-text`; contextually escape map popup values.
  - Acceptance: Browser tests render script tags, SVG/event payloads, quotes, entities, bidi controls, and Urdu safely as inert text.

### Correctness and Failure Semantics

- [ ] **DATA-001: Centralize cache keys and fix purge behavior.**
  - Current weather keys use `weather_{days}_{province}_{district}`, while purge deletes `forecast_*`/`alerts_*` keys.
  - Replace string conventions with repository methods and typed identifiers.
  - Acceptance: Integration tests verify exact alert and raw-weather records are deleted, deletion counts are accurate, and unrelated records remain.

- [ ] **API-001: Standardize errors and partial-result semantics.**
  - Use a versioned envelope with error code, safe message, retryability, details, and correlation ID.
  - Use appropriate `4xx`, `5xx`, and `202` statuses; never return raw exception strings.
  - Return requested/succeeded/failed/stale/missing district counts.
  - Acceptance: A partially completed province run cannot return `success` or produce an all-clear summary.

- [ ] **DB-001: Stop swallowing persistence errors.**
  - Remove broad `except: pass` and empty fallback returns from safety-critical database functions.
  - Classify transient lock/contention, validation, integrity, and permanent storage errors.
  - Acceptance: Failed critical writes fail the workflow, preserve prior state, emit metrics, and are visible to operators.

- [ ] **API-002: Centralize request validation.**
  - Validate district membership in province, days, duplicates, basemap, JSON/form/query types, and district limits consistently.
  - Reject mixed valid/invalid district lists instead of silently filtering unless the contract explicitly permits partial filtering.
  - Acceptance: Contract tests cover cross-province, duplicate, malformed, empty, huge, and boundary inputs.

### Baseline Verification

- [ ] **TEST-001: Repair the existing test baseline.**
  - Fix the health mock target and replace copied parser tests with calls to production code.
  - Use a temporary database fixture and fake external adapters.
  - Record the current known suite result (51 passing, 1 failing in the repository virtual environment) and make all tests deterministic.
  - Acceptance: Unit/integration tests pass without LM Studio, Open-Meteo, Mapbox, network access, or the repository `weather.db`.

- [ ] **TEST-002: Add Phase 0 security and failure tests.**
  - Cover authentication, RBAC, CSRF, rate limiting, XSS, malformed LLM output, provider timeout, partial districts, DB lock/write failure, and process restart.
  - Acceptance: Each Phase 0 acceptance condition is represented by an automated test.

## Phase 1: Deterministic 15-Day Forecast and Hazard Core

### Forecast Horizon and Provider Ingestion

- [ ] **WX-001: Expand the product contract from 1-7 to 1-15 days.**
  - Update `validate_forecast_days`, constants, UI options, schemas, tests, and documentation.
  - Treat provider maximum capability separately from the product's 15-day limit.
  - Acceptance: API/UI accept 1, 7, 8, 14, and 15; reject 0 and 16; report actual returned horizon and missing dates.

- [x] **WX-002: Build a typed Open-Meteo provider adapter.**
  - Keep raw request/response snapshots, request parameters, retrieval timestamp, provider, model/model blend, run/init time where available, grid location, elevation, timezone, units, license/source URL, schema version, and checksums.
  - Use explicit connect/read/total deadlines, bounded retries with jitter, and circuit-breaker behavior.
  - Acceptance: Provider schema changes, unit mismatches, short horizons, stale runs, rate limits, and partial fields become explicit quality failures.

- [x] **WX-003: Store immutable forecast runs instead of cache-only payloads.**
  - Separate immutable source data from optional response caches.
  - Add migrations and repositories; use a production-capable relational database such as PostgreSQL/PostGIS for operational deployment.
  - Acceptance: An operator can reconstruct the exact source snapshot and normalized records used for any warning version.

- [ ] **WX-004: Ingest hourly data for short-range hazards and daily outlook data for the full horizon.**
  - Retain hourly data at least for days 1-7 and appropriate aggregate/outlook data for days 8-15.
  - Add apparent temperature, humidity/dew point or wet-bulb inputs, wind direction, visibility, pressure/freezing-level, cloud/convective fields, soil/antecedent conditions where supported.
  - Acceptance: Hazard contracts state mandatory/optional fields and produce `insufficient_data` when mandatory evidence is absent.

- [ ] **WX-005: Add source and model corroboration.**
  - Add ensemble/model-specific forecasts and at least one independent source where licensing and availability permit.
  - Preserve official PMD/NDMA warnings as authoritative external products rather than blending them into LLM prose.
  - Acceptance: Source disagreement and ensemble spread contribute to certainty and are visible in review and public provenance.

### Geography and Exposure

- [ ] **GEO-001: Replace display-name joins with an authoritative versioned gazetteer.**
  - Assign stable province/district codes, canonical names, aliases, administrative version, geometry, centroid, elevation, and sampling strategy.
  - Remove substitutions such as Layyah to Dera Ghazi Khan and Bajaur to Mansehra.
  - Acceptance: Every supported district resolves uniquely to its correct geometry; unmatched areas fail data-quality checks instead of borrowing another geometry.

- [ ] **GEO-002: Replace single-centroid forecasts for large/diverse districts.**
  - Use multiple grid points, zonal statistics, elevation bands, population centers, watersheds, or hazard-specific sampling.
  - Acceptance: Sampling metadata and aggregation method are attached to each district forecast and tested against authoritative boundaries.

- [ ] **GEO-003: Add impact and vulnerability layers.**
  - Model population exposure, critical infrastructure, agriculture, elevation, floodplains, and locally approved vulnerability factors separately from meteorological severity.
  - Acceptance: Hazard severity and impact/risk are distinct fields; vulnerability cannot alter source measurements.

### Normalization and Quality Control

- [ ] **WX-006: Create one normalization module.**
  - Remove duplicated DataFrame/JSON transformations from routes, map code, and utilities.
  - Validate aligned timestamps/array lengths, units, nulls, ranges, coordinates, timezone conversion, and horizon completeness.
  - Acceptance: All callers consume the same typed normalized representation; malformed source arrays cannot reach hazard evaluation.

- [ ] **WX-007: Implement data freshness and completeness policies.**
  - Distinguish valid, stale, partial, unavailable, contradictory, and invalid data.
  - Acceptance: UI/API/workflow expose freshness and completeness per source, district, valid time, and hazard.

### Deterministic Hazard Engine

- [ ] **HAZ-001: Define the versioned hazard rule interface and evidence model.**
  - Output hazard type, severity, certainty, urgency, affected locations/geometry, effective/onset/expiry, lead time, evidence, confidence components, rule version, and data-quality status.
  - Store thresholds/configuration outside presentation code and subject changes to expert review.
  - Acceptance: Rules are pure, replayable, unit-aware, and independently testable without Flask/database/LLM dependencies.

- [ ] **HAZ-002: Implement extreme heat and cold rules.**
  - Include apparent temperature/heat stress, overnight minimums, duration, season, elevation, regional climatology, and vulnerable-population context.
  - Acceptance: Golden tests cover immediately below/at/above thresholds, multi-day duration, missing humidity, and regional configurations.

- [ ] **HAZ-003: Implement heavy rain and flash-flood proxy rules.**
  - Use hourly intensity, accumulations, duration, antecedent rainfall/soil state, terrain/watershed context, and forecast probability.
  - Never label a river flood without hydrologic evidence.
  - Acceptance: Rules distinguish intense short rain, multi-day accumulation, flash-flood potential, river-flood evidence, and insufficient data.

- [ ] **HAZ-004: Implement wind, thunderstorm, hail, snow, fog/visibility, and compound-hazard rules.**
  - Use gusts and sustained wind, convective indicators/lightning where available, snowfall/rain-snow transition, visibility, freezing conditions, and coincident hazards.
  - Acceptance: Each hazard has reviewed evidence requirements and boundary/golden tests.

- [ ] **HAZ-005: Add hazard-specific modules for air quality, dust/smog, marine/coastal, and river flood only when supporting sources exist.**
  - Acceptance: Unsupported hazards remain disabled and cannot be inferred from generic weather codes or LLM language.

- [ ] **HAZ-006: Implement lead-time-aware uncertainty policy.**
  - Configure behavior for days 1-3, 4-7, 8-10, and 11-15.
  - Use forecast age, completeness, model agreement, ensemble probability/spread, observations, and official-source corroboration.
  - Acceptance: Days 8-15 default to outlook/watch candidates and cannot be represented as high-confidence imminent warnings without explicit corroboration policy.

### Hazard-Core Verification

- [ ] **TEST-003: Build domain-reviewed golden hazard fixtures.**
  - Cover historical Pakistan events, non-events, compound events, missing/stale inputs, all threshold boundaries, seasons, elevations, and lead-time buckets.
  - Acceptance: Domain experts approve fixture labels and expected evidence before production use.

- [ ] **TEST-004: Add deterministic replay and property tests.**
  - Verify order independence, unit conversion invariance, reproducibility, no NaN crashes, and monotonic behavior where appropriate.
  - Acceptance: Identical run + rule versions always produce identical findings and fingerprints.

## Phase 2: Durable Agentic Workflow and Warning Lifecycle

### Durable Orchestration

- [ ] **AGENT-001: Replace daemon threads with a durable workflow engine and scheduler.**
  - Evaluate Celery/RQ/Dramatiq for simple queues or Temporal for durable multi-stage workflows; record the decision in an ADR.
  - Persist queued/running/succeeded/partial/failed/cancelled/dead-letter status, progress, attempts, and timestamps.
  - Acceptance: Jobs survive web/worker restarts and status is consistent across multiple workers.

- [ ] **AGENT-002: Schedule autonomous forecast monitoring.**
  - Poll according to provider/model update cadence plus configurable safety intervals.
  - Detect new source runs rather than repeatedly regenerating on wall-clock alone.
  - Acceptance: Missed schedules, stale source data, and backlog raise operator alerts; duplicate schedulers do not duplicate work.

- [ ] **AGENT-003: Make every workflow stage idempotent and replayable.**
  - Define idempotency keys using source run, location, hazard, rule version, and workflow version.
  - Add leases/locks to prevent overlapping processing of the same run.
  - Acceptance: Retrying or replaying a stored run creates no duplicate findings, warning versions, or deliveries.

- [ ] **AGENT-004: Implement an explicit bounded agent state machine.**
  - Stages: discover run, fetch, quality-check, normalize, derive features, evaluate hazards, reconcile lifecycle, render language, validate, request review, publish, deliver, observe.
  - Tool calls use typed inputs/outputs, least-privilege credentials, deadlines, budgets, and audit events.
  - Acceptance: Invalid state transitions are rejected; an LLM cannot skip validation/review or call publication/delivery tools.

- [ ] **AGENT-005: Add robust retries, compensation, and dead-letter handling.**
  - Distinguish transient, permanent, policy, and data-quality failures.
  - Permit district-level retries without creating a province-wide all-clear from partial completion.
  - Acceptance: Failure simulations cover provider outage, model outage, DB lock, worker death, network partition, and poison messages.

### Warning Event Model and Lifecycle

- [ ] **WARN-001: Replace the `alerts` cache table with immutable warning events and versions.**
  - Include `event_id`, version, status, hazard type, areas/geometry, severity, certainty, urgency, effective/onset/expiry, source run IDs, evidence, rule version, confidence, dedupe fingerprint, instruction codes, translations, approvals, supersession references, and audit timestamps.
  - Acceptance: Full warning history remains queryable and no published version can be edited in place.

- [ ] **WARN-002: Implement lifecycle states and guarded transitions.**
  - Minimum states: `candidate`, `under_review`, `approved`, `published`, `updated`, `cancelled`, `expired`, `rejected`, and `failed`.
  - Acceptance: Transition rules enforce actor roles, required evidence, reasons, and timestamps.

- [ ] **WARN-003: Implement deterministic deduplication and material-change logic.**
  - Fingerprint hazard, area, validity window, evidence/run, and rule version.
  - Define reviewed thresholds for no-op, update, escalation, de-escalation, cancellation, and expiry.
  - Acceptance: Test matrices verify expected lifecycle action across prior/current evidence changes.

- [ ] **WARN-004: Implement active-warning reconciliation.**
  - Compare current findings with prior source runs, current active warning, official warnings, delivery state, and analyst decisions.
  - Acceptance: The system explains why it proposed issue/update/escalate/cancel/no-op and links all supporting records.

### Operational Memory

- [ ] **MEM-001: Separate authoritative event history from ephemeral cache.**
  - Retain forecast runs, findings, workflow decisions, warning versions, approvals, deliveries, outcomes, and operator feedback under explicit retention rules.
  - Do not use conversational LLM memory as authoritative state.
  - Acceptance: Every decision can be reconstructed without relying on logs or model memory.

- [ ] **MEM-002: Add safe replay and simulation mode.**
  - Replay stored source runs through alternate rules/prompts/models without changing production warning state or sending deliveries.
  - Acceptance: Simulation records are visibly marked and technically prevented from entering public delivery channels.

## Phase 3: Grounded Bilingual Generation, Human Review, and Publication

### Language Generation

- [ ] **AI-003: Redesign language generation around canonical warning facts.**
  - Input contains only approved hazard facts, evidence summaries, timing, locations, confidence, and allowed instruction codes.
  - Generate district, regional, audience, and channel variants separately with deterministic chunking/token budgets.
  - Acceptance: Model output contains no unsupported numeric or hazard claim and cannot omit mandatory safety instructions.

- [ ] **AI-004: Add a model/prompt/glossary registry.**
  - Version model ID/digest, inference parameters, prompt, schema, glossary, templates, and safety policy.
  - Store latency, token counts where available, output hash, validation results, and fallback reason.
  - Acceptance: Every translation can be reproduced or traced to exact generation artifacts.

- [ ] **AI-005: Build post-generation grounding validators.**
  - Check all numbers, units, dates, areas, hazard names, severity terms, actions, negation, and status against canonical facts.
  - Reject unsupported claims rather than automatically repairing substantive content.
  - Acceptance: Adversarial tests catch invented values, omitted negation, changed severity, wrong district, and unsafe advice.

- [ ] **AI-006: Treat English and Urdu as versioned translations of one canonical product.**
  - Move the glossary out of the prompt into a governed terminology resource.
  - Add approved template fallback and human review policy for severe Urdu products.
  - Acceptance: Automated parity checks cover numbers, units, dates, location, hazard, severity, actions, and negation; missing translation never becomes blank public content.

### Review and Approval

- [ ] **OPS-001: Define publication policy by severity, certainty, urgency, and source authority.**
  - Document which informational products may auto-publish and which require one or two authorized approvers.
  - Keep severe/extreme warnings human-approved unless an independently governed emergency auto-release policy exists.
  - Acceptance: Policy evaluation is deterministic, versioned, testable, and visible in each candidate.

- [ ] **OPS-002: Build an analyst review console.**
  - Show source freshness/completeness, maps, time series, model/ensemble disagreement, exact rule evidence, prior run, active warning, proposed lifecycle action, both languages, and validation results.
  - Support approve, reject, request changes, suppress, override, cancel, and emergency publish with mandatory reasons.
  - Acceptance: Reviewers can compare facts and changes without reading logs or raw database content.

- [ ] **OPS-003: Add four-eyes approval and emergency controls.**
  - Require role-separated approval for configured high-impact warnings.
  - Add break-glass actions with stronger authentication, prominent audit, and post-incident review.
  - Acceptance: The author cannot satisfy a separate-approver requirement; overrides always record rationale.

- [ ] **PUB-001: Implement atomic publication.**
  - Publish only a fully validated, approved warning version; update the active pointer transactionally.
  - Acceptance: Readers see either the previous complete version or the new complete version, never a partial transition.

## Phase 4: Notification Delivery and Public Product

### Delivery

- [ ] **DEL-001: Define a channel-independent canonical distribution contract.**
  - Include event/version IDs, lifecycle status, hazard metadata, areas, validity, canonical instructions, translations, and provenance.
  - Provide CAP-compatible import/export or formally document deviations.
  - Acceptance: Issuance, update, escalation, cancellation, and expiry are representable without parsing prose.

- [ ] **DEL-002: Implement at least two operational channels plus a signed webhook/feed.**
  - Candidate channels: SMS, email, push, WhatsApp, operations dashboard, CAP feed, and partner webhook.
  - Store delivery attempts, provider IDs, recipients/groups, timestamps, latency, status, retries, and failure reason.
  - Acceptance: Delivery is idempotent per warning version/channel/recipient group and supports retry/dead-letter workflows.

- [ ] **DEL-003: Deliver lifecycle changes consistently.**
  - Updates, escalations, cancellations, and corrections must reach recipients of the corresponding issuance.
  - Acceptance: Recipient-resolution tests prove cancellation and escalation target the original audience.

- [ ] **DEL-004: Add test/sandbox mode and delivery safeguards.**
  - Use separate credentials/endpoints, visible environment banners, recipient allowlists, and a hard production-send permission.
  - Acceptance: Simulation/test warnings cannot reach public channels even through operator error.

### Public and Operator UI

- [ ] **UI-001: Replace full synchronous Folium regeneration with data APIs and a stable client map.**
  - Serve versioned GeoJSON/vector data and warning/forecast JSON; update layers incrementally.
  - Keep map rendering separate from hazard and warning logic.
  - Acceptance: Map refresh does not rerender the whole page or serialize all country data on every request.

- [ ] **UI-002: Display operational warning metadata prominently.**
  - Show status, hazard, severity, certainty, urgency, issue/effective/onset/expiry times, last data refresh, source/model, provenance, and stale/partial/offline state.
  - Distinguish machine candidate, analyst-approved warning, official external warning, simulation, and cached historical product.
  - Acceptance: Users cannot confuse no warning, no data, stale data, failed load, candidate, cancelled, or expired states.

- [ ] **UI-003: Repair mobile and accessibility behavior.**
  - Implement the missing sidebar toggle; add landmarks, headings, explicit labels, keyboard/focus behavior, Escape handling, live regions, status/dialog semantics, named icon controls, and a text/table alternative to the map.
  - Honor `prefers-reduced-motion`; disable typing/blinking/pulsing where requested and never encode severity by motion/color alone.
  - Acceptance: Playwright + axe tests pass at mobile and desktop widths; manual keyboard and screen-reader checks cover English and Urdu.

- [ ] **UI-004: Make network/error handling truthful and resilient.**
  - Check `response.ok` and content type, consume typed error envelopes, support cancellation/timeouts, display correlation IDs, and render partial progress accurately.
  - Acceptance: Browser tests cover `400`, `401`, `403`, `429`, `500`, `503`, timeouts, malformed JSON, proxy HTML, and partial success.

- [ ] **UI-005: Provide degraded and offline-safe views.**
  - Self-host critical pinned assets; provide text/tabular warnings and last-known-data indicators when map tiles/CDNs fail.
  - Acceptance: An offline/degraded-network test still exposes current cached published warning text, validity, and stale state without executing third-party code.

## Phase 5: Production Operations, Observability, and Governance

### Database, Deployment, and Reliability

- [ ] **PLAT-001: Add schema migrations and production persistence.**
  - Introduce a migration tool, constraints, transactions, indexes, UTC handling, backups, restore procedures, retention, and integrity checks.
  - Decide SQLite support for local development versus PostgreSQL/PostGIS for production and record it in an ADR.
  - Acceptance: Migration forward/backward strategy, backup restore, concurrent workflows, and disk/storage failure are tested.

- [ ] **PLAT-002: Build a production deployment path.**
  - Run Flask via a supported WSGI server behind TLS/reverse proxy; disable debug/reloader; configure worker limits, graceful shutdown, request deadlines, secrets, and runtime data paths.
  - Containerize web, worker, scheduler, and dependencies as appropriate.
  - Acceptance: Deployment smoke tests verify production settings, graceful restart, in-flight durable job recovery, and no hard dependency on Mapbox for API startup.

- [ ] **PLAT-003: Split liveness, readiness, and diagnostics.**
  - Liveness is local and fast; readiness checks required database/queue/model configuration with bounded cached checks; detailed diagnostics require operator access.
  - Acceptance: Liveness does not fail because Open-Meteo/LM Studio is slow, while readiness detects missing model, DB write failure, queue failure, and stale ingestion.

- [ ] **PLAT-004: Define disaster recovery and continuity.**
  - Set RTO/RPO, backup frequency, failover, manual publication fallback, provider-outage behavior, and emergency contacts.
  - Acceptance: Restore and provider/channel outage drills meet approved RTO/RPO and retain published warning history.

### Observability and Audit

- [ ] **OBS-001: Add structured logs, metrics, and traces.**
  - Propagate correlation IDs across source run, workflow, finding, candidate, approval, publication, and delivery.
  - Emit JSON logs to managed output with redaction and retention; remove unbounded plain file logging.
  - Acceptance: One warning version can be traced end-to-end without searching by free text.

- [ ] **OBS-002: Define dashboards, alerts, and SLOs.**
  - Track source freshness, ingestion success/completeness, workflow latency/backlog, hazard volume, schema/grounding failures, approval age, publication latency, delivery success/latency, duplicate suppression, model latency/resource use, and storage health.
  - Acceptance: Alerts fire for missed schedules, stale data, queue backlog, anomalous warning volume, high validation failure, and delivery degradation.

- [ ] **OBS-003: Make the audit log immutable and queryable.**
  - Record policy/rule/model/config versions, actor actions, overrides, state transitions, and delivery operations.
  - Acceptance: Audit records cannot be modified through normal application roles and can reconstruct every public product.

### Evaluation and Model/Rule Governance

- [ ] **EVAL-001: Build forecast verification.**
  - Compare archived forecasts with observations by source/model, district/grid, hazard, season, and lead-time bucket.
  - Measure MAE/bias for continuous fields and probability calibration/Brier score where probabilities exist.
  - Acceptance: Verification reports run automatically and preserve dataset/code/config versions.

- [ ] **EVAL-002: Build warning skill evaluation.**
  - Measure probability of detection, false-alarm ratio, critical success index, lead time, geographic accuracy, update stability, and cancellation correctness.
  - Acceptance: Metrics are stratified by hazard, severity, season, area, and lead-time bucket, including days 8-15.

- [ ] **EVAL-003: Build language safety and translation evaluation.**
  - Maintain labeled tests for unsupported claims, numeric fidelity, action fidelity, English/Urdu equivalence, readability, glossary use, and negation.
  - Acceptance: Model/prompt/glossary changes cannot deploy if they regress approved thresholds.

- [ ] **GOV-001: Establish change governance.**
  - Require review/versioning for hazard rules, thresholds, source adapters, model/prompt/glossary, publication policy, and templates.
  - Use shadow evaluation and canary release where appropriate; never train automatically from operator feedback without governed curation.
  - Acceptance: Every production decision artifact identifies approved versions and approvers.

- [ ] **GOV-002: Conduct regular safety exercises.**
  - Exercise provider outage, missed event, false positive, compromised model output, malicious input, DB outage, queue backlog, operator error, and delivery-channel failure.
  - Acceptance: Findings become tracked remediation items with owners, deadlines, and repeat verification.

## Phase 6: Test, CI, Documentation, and Repository Quality

- [ ] **QA-001: Establish a layered test strategy.**
  - Unit: normalization, rules, confidence, lifecycle, policies, validators.
  - Contract: providers, APIs, schemas, delivery adapters.
  - Integration: database, queue, workflow, migrations, publication transactions.
  - End-to-end: analyst review through public warning and delivery sandbox.
  - Resilience/security: auth, CSRF, XSS, rate limits, failures, retries, restart, load, degraded/offline.
  - Acceptance: Critical safety paths have explicit coverage thresholds and mutation/failure tests, not only line coverage.

- [ ] **QA-002: Make CI reproducible and mandatory.**
  - Keep `uv.lock` authoritative; run formatting/lint, typing, tests, coverage, security/dependency/secret scans, migrations, frontend/a11y tests, and deployment smoke tests.
  - Fix the current mismatch where CI says type check but runs no type checker, and reconcile Ruff line length with repository guidance.
  - Acceptance: A clean clone can run all required checks without local services or undocumented files.

- [ ] **QA-003: Add load and capacity tests.**
  - Model nationwide ingestion, concurrent operator reads, workflow bursts, long provider latency, queue backlogs, and delivery spikes.
  - Acceptance: Capacity targets and graceful degradation behavior are documented and verified before launch.

- [ ] **DOC-001: Correct product and architecture documentation.**
  - Remove unsupported claims such as nowcasting/multiple-model intelligence until implemented.
  - Reconcile LM Studio defaults, dependency installation, configuration, entry points, API behavior, and authoritative data files.
  - Acceptance: README, `.env.example`, runbooks, architecture diagrams, OpenAPI, and code agree.

- [ ] **DOC-002: Add operational and safety runbooks.**
  - Cover deploy/rollback, migrations, backup/restore, secrets, provider outage, stale data, approval/correction/cancellation, false warning, missed warning, delivery failure, incident response, on-call, RTO/RPO, and manual fallback.
  - Acceptance: A tabletop exercise demonstrates that an on-call operator can follow each critical runbook.

- [ ] **REPO-001: Clean repository artifacts and dead code.**
  - Remove tracked coverage/lint/debug artifacts, backup templates, placeholder entry points, obsolete JSON caches, and runtime data beneath `static/`.
  - Resolve unused utilities and select one authoritative boundary dataset.
  - Do not remove current user changes without review.
  - Acceptance: A clean checkout contains only source, intentional fixtures/assets, lockfiles, migrations, and documentation.

## Recommended Delivery Milestones

### Milestone 1: Safe Internal Prototype

- Complete Phase 0.
- Support authenticated internal users only.
- Preserve current active alerts on every failure.
- Eliminate browser injection paths and false-success responses.

### Milestone 2: Deterministic 15-Day Decision Support

- Complete Phase 1.
- Produce structured hazard candidates and lower-confidence 8-15 day outlooks.
- Do not publicly auto-publish; use analyst review and simulation output.

### Milestone 3: Durable Human-Governed Warning Operations

- Complete Phase 2 and Phase 3.
- Run scheduled durable workflows with immutable warnings and full approval/audit trails.
- Operate in shadow mode alongside authoritative forecasters.

### Milestone 4: Controlled Dissemination Pilot

- Complete Phase 4 and production-critical Phase 5 items.
- Use sandbox/limited recipient groups, measured SLOs, and explicit incident procedures.

### Milestone 5: Production Readiness

- Complete all safety, reliability, evaluation, accessibility, security, recovery, and governance gates.
- Obtain meteorological, emergency-management, security, accessibility, and operational sign-off.

## Global Definition of Done

A task is not complete until:

- [ ] Its interface and failure modes are documented.
- [ ] Inputs, outputs, provenance, and timestamps are typed and validated.
- [ ] Unit and integration tests cover success, boundary, partial, stale, and failure cases.
- [ ] Security, privacy, accessibility, and audit implications are addressed.
- [ ] Metrics/logs/traces make production behavior observable.
- [ ] Database/schema/configuration changes include migration and rollback considerations.
- [ ] Public-safety behavior has domain-owner acceptance where applicable.
- [ ] Documentation and runbooks are updated in the same change.
- [ ] No generative model is the sole authority for a hazard or publication decision.

## First Implementation Slice

Execute this sequence first to reduce current risk while creating the correct architectural seams:

1. [x] Add app factory, injectable configuration, and temporary-test database (`ARCH-003`). Provider/repository interfaces remain under `ARCH-002`.
2. [ ] Protect mutation routes and add audit identity/rate limits (`SEC-001` through `SEC-004`).
3. [ ] Add strict language schema, non-destructive candidate persistence, and XSS-safe rendering (`AI-001`, `AI-002`, `SEC-005`).
4. [ ] Fix cache keys, persistence errors, API errors, and partial-result reporting (`DATA-001`, `DB-001`, `API-001`, `API-002`).
5. [ ] Add immutable forecast-run storage and a typed Open-Meteo adapter (`WX-002`, `WX-003`, `WX-006`).
6. [ ] Expand validated ingestion to 15 days and expose freshness/completeness (`WX-001`, `WX-007`).
7. [ ] Implement one end-to-end deterministic hazard tracer bullet, recommended: extreme heat, from source run through candidate review without public delivery (`HAZ-001`, `HAZ-002`, `WARN-001`, `WARN-002`).
8. [ ] Replace process-local background threads with a durable workflow for that tracer bullet (`AGENT-001` through `AGENT-004`).
9. [ ] Add grounded English/Urdu rendering and validators for the structured heat candidate (`AI-003` through `AI-006`).
10. [ ] Run the tracer bullet in shadow mode, evaluate it, then repeat for rain/flood proxy, wind/thunderstorm, snow/cold, and visibility hazards.
