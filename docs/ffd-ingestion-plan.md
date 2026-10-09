# Plan: river-flood monitoring from Flood Forecasting Division data

Status: proposal, not yet agreed. Written 2026-10-09 from the findings in
[`ffd-sources.md`](ffd-sources.md), which records what `ffd.pmd.gov.pk` actually
served on that date. Where this plan states a fact about the site, that note is the
source. It replaces the approach in issue #18 if adopted.

## 1. What changes, in one paragraph

Issue #18 planned a riverine-flood hazard from modelled discharge (GloFAS through
Open-Meteo) compared with a baseline, with thresholds still to calibrate. The Flood
Forecasting Division (FFD) publishes what that plan lacked: **observed** discharge at
named barrages, dams and gauges, the **official flood limits** for those sites, and a
24-hour forecast. This plan makes FFD observations the primary riverine-flood signal,
keeps GloFAS as the longer-range outlook, and uses FFD's multi-model weather feed to
judge how certain a rainfall signal is.

## 2. Two gates before any FFD data is stored

Both are yours to settle; neither can be engineered around.

| Gate | Why it blocks | What is needed |
|---|---|---|
| **Permission** | Every page says "All rights reserved"; the bulletin forbids reproduction without written permission; there is no terms page. The system stores raw payloads and shows them as alert evidence, which is storing and redisplaying FFD content. | A written yes from FFD (`ffd@weather.gov.pk`, the route its contact page names) covering automated fetching of the station feed, storage, and display with attribution. Ask in the same message for station coordinates and the request rate they are comfortable with. |
| **Station locations** | Coordinates exist only behind an endpoint the site marks as protected against scraping. This plan does not touch that endpoint. | Either coordinates from FFD, or a hand-built table (section 4) reviewed by someone who knows the river system. |

Until the permission gate is passed: the 13 captured samples in
`backend/tests/fixtures/ffd/` stay out of the public repository, and tests use
hand-written payloads of the same shape rather than copies.

## 3. Which dataset does which job

| Dataset | Job in this system | Phase |
|---|---|---|
| Station state, `/flood-assistant/station/{id}` — observed inflow and outflow, levels, 31-day series, 24-hour forecast | **Primary riverine-flood signal**: current state and next 24 hours | 1 |
| Station roster, `/flood-assistant/rivers` — 131 sites with stable ids | Checks that the curated station table still matches the site | 1 |
| Flood limits, `/flood-limits` — official limits for 35 sites | **Thresholds**, entered once by hand and reviewed; not fetched by cycles | 1 |
| GloFAS discharge, Open-Meteo Flood (already researched in `sources.md`) | **Outlook for days 2 to 7**, which FFD does not publish as numbers | 2 |
| Weather-model points, `/weather-model/point` — ICON, GFS, ECMWF | **Certainty** of a rainfall signal: do independent models agree? | 3 |
| Weather observations, `/weather/current` — the one feed FFD offers for reuse | Checking forecasts against what fell; evaluation | later |
| Daily bulletin (2026, HTML) | Not ingested: its forecast numbers are already in the station feed, and it carries the no-reproduction notice | — |
| Radar, dashboard maps, meteograms, PDFs, anything under a `robots.txt` disallow, the token-gated map feed | Not used | — |

## 4. Station registry (the real work of phase 1)

A curated table, in the same spirit as the district registry and its overrides.

- **Source file:** `backend/data/source/river_stations.json`, hand-maintained. One
  entry per station the system monitors:
  - FFD station id, name as FFD spells it, river, kind (barrage, dam, gauge)
  - which reading the limits apply to (inflow for barrages; reservoir level is not a
    discharge and dams are handled separately, see section 6)
  - the five FFD limits in cusecs, copied from the limits table
  - the **districts the station speaks for**, with a one-line reason each
  - coordinates, if and when they are available, for the map
- **Start with the 35 sites that have official limits.** A site with no limits cannot
  be classified, so adding it gains nothing yet.
- **Station to district is a judgement, not a lookup.** A barrage reading matters to
  the districts along the reach below it, not only the district it stands in. The
  first draft can be made from names and public geography; it must then be reviewed
  by hand, and the reviewer recorded.
- **Districts with no station are listed explicitly as having none**, as #18 already
  requires for river points, so the gap reads as a fact and not a bug.
- **Build step:** `ews.districts.build` validates the file and writes a report:
  stations whose id or name no longer appears in the FFD roster, limits that are not
  increasing, districts covered and not covered. The report is committed, like the
  district mismatch report.
- **Known traps to encode as checks:** Panjnad's limits in the station feed equal
  Trimmu's row of the limits table; names are spelled three ways across the site; the
  limits table is in lacs of cusecs while the feed is in cusecs.

## 5. Ingestion

- **Client:** `ews.sources.ffd.FfdClient`, in the pattern of the existing source
  clients: typed records out, `SourceError` on failure, a descriptive `User-Agent`
  naming the project and a contact.
- **Pacing:** the feed allows 40 requests in a window FFD does not state, one request
  per station. A cycle therefore fetches only registered stations, about one per
  second, reads the `x-ratelimit-remaining` header and stops early rather than run
  into the limit. Whatever rate FFD agrees to replaces this guess.
- **Freshness:** readings change a few times a day. A station fetched within the
  freshness window (the existing three-hour setting) is not fetched again.
- **Storage:** raw payloads are kept as immutable snapshots, as for every source.
  `source_snapshots` is keyed by district today, and a station is not a district. The
  proposal is to let a snapshot belong to either a district or a station, rather than
  duplicating one station payload per district it speaks for. This is a schema
  decision to confirm when the work is specified.
- **Failure handling:** FFD failing must not fail the cycle, exactly as air quality
  does not. Things to treat as "no reading" rather than as zero: a null value, the
  feed's own `is_stale` flag, and a station missing from the response.
- **Out of season:** the forecast exists only from 15 June to 15 October. Outside
  it, observed state still screens; the absence of a forecast is recorded, not
  treated as a fault.

## 6. Screening and alerts

- **Hazard:** `riverine_flood`, raised for a district when a station that speaks for
  it reaches a limit.
- **Classify with our own copy of the limits, not FFD's status field.** The feed's
  status disagreed with its own limits table in places. When our classification and
  FFD's status differ, that is recorded on the run so it can be looked at.
- **Level mapping, to be confirmed by you:**

  | FFD category | This system |
  |---|---|
  | Low flood | Recorded as a signal for context; no alert |
  | Medium flood | Moderate |
  | High flood | Severe |
  | Very high, exceptionally high | Extreme |

  FFD has five levels and the system has three, so some merging is unavoidable.
  Whether a low flood should alert is the main choice here.
- **Observed and forecast are different signals.** Observed above a limit is
  happening now: urgency immediate, certainty observed. The 24-hour forecast
  crossing a limit is expected: urgency expected. Both cite the station snapshot.
- **Dams:** the feed gives reservoir level in feet, with no discharge limits. Dams
  are left out of screening in phase 1 and kept only as context.
- **Alert wording:** names the river and the station and says the alert concerns
  areas along the river, not the whole district. The evidence table shows the
  reading, the limit and the time of the reading in cusecs, as FFD reports them.
- **Rule shape:** today's rules screen a daily series per district against three
  thresholds. A station reading against per-station limits is a different shape, so
  this needs a second, small rule type rather than forcing it into the first.
- **Attribution:** "Flood Forecasting Division, PMD. River data from WAPDA and
  provincial irrigation departments", wherever a value appears, in whatever wording
  FFD asks for.

## 7. GloFAS as the outlook (phase 2)

FFD's numbers stop at 24 hours. For days 2 to 7 the Open-Meteo Flood source in #18
still has a job, with two changes:

- It raises an **outlook**, lower certainty, never the same alert as an observed
  flood. If FFD shows a district's station in flood, the FFD signal wins.
- Its thresholds stay relative to that point's own history. **FFD limits are never
  applied to GloFAS values**: one is observed inflow at a structure in cusecs, the
  other modelled discharge at a grid cell in m³/s, and at Sukkur the two differed by
  more than a factor of two on consecutive days.

The river-point table from #18 is still needed for this, and can share the station
registry: a station's location is a natural river point once coordinates are known.

## 8. Weather models for certainty (phase 3)

FFD serves point forecasts from three independent models. The system's weather
signals come from one. Agreement between models is the standard evidence for how far
to trust a rainfall forecast, and today certainty is set from lead time alone.

- **Use it only for districts already flagged**, never for all 155. With the
  analyst's per-run limit that is a handful of requests per cycle, well inside the
  120-request limit on these endpoints. This also fits the "triage before inference"
  principle and does not add to the Open-Meteo quota problem.
- **First use:** a read-only analyst tool, "what do the other models say for this
  district on these days", returning daily rain per model. The analyst already sets
  certainty; this gives it evidence to do so. It belongs with #26.
- **Possible second use:** a plain rule (two of three models at or above the
  threshold means likely) so certainty does not depend on a model call. Decide after
  seeing the tool in use.
- **Caveats:** only about three days of cycles are kept; the 24-hour rain windows
  differ between models (08:00 to 08:00 for ICON, 05:00 to 05:00 for ECMWF), so
  daily totals must be compared with that in mind; these are the same global models
  Open-Meteo draws on, so agreement is corroboration, not independence from the
  forecast already held.

This does not solve the question you raised earlier, that one point per district
misses variation inside large districts. It is a separate piece of work.

## 9. Analyst, map and evaluation

- **Analyst tool (#26):** "river state for this district": the stations that speak
  for it, their readings, limits, trend and forecast.
- **Map:** a river-station layer and a river section in the district drawer. The
  layer needs coordinates, so it waits on gate 2; the drawer does not.
- **Evaluation:** scenarios built from station payloads at each FFD category, plus
  the traps in section 4. A real 2025 flood scenario would have to be rebuilt from
  bulletin PDFs and needs permission; it is not planned.

## 10. Phases

| Phase | Contents | Blocked by | Done when |
|---|---|---|---|
| 0 | Write to FFD; draft the station table for the 35 sites with limits; you confirm the level mapping | — | Permission answered; table reviewed |
| 1 | Station registry and build report; FFD client; station snapshots; riverine-flood rule and alerts; drawer section; attribution | Gate 1 for live data. The registry, client and rule can be built and tested against hand-written payloads before the answer arrives | A cycle raises a riverine-flood alert from a station reading, with evidence |
| 2 | GloFAS outlook with relative thresholds; river points shared with the registry | Phase 1 | A district shows an observed state and a separate multi-day outlook |
| 3 | Model-agreement tool for the analyst | #26, gate 1 | The analyst cites model agreement in an assessment |
| 4 | Station layer on the map | Gate 2 | Stations are on the map with their state |

## 11. Risks

| Risk | Mitigation |
|---|---|
| FFD says no, or does not answer | Phase 2 stands alone as the original #18 plan. FFD's limits table could still inform severity bands by hand, which is the lightest use, but that too is your call |
| The feed is the private back end of a beta widget and changes without notice | Typed parsing that fails loudly; the roster check in the build report; FFD failure never fails a cycle |
| A server outside Pakistan is challenged by Cloudflare | Unknown today: every test request left from inside Pakistan. Test from the eventual host before relying on it |
| Wrong station-to-district mapping produces a wrong alert | Hand review with the reviewer recorded; the alert names the station, so a reader can see what it rests on |
| Low-flood alerts every monsoon day wear readers out | Low flood is context only, pending your decision in section 6 |
| Thirty-one days of history is too little for a baseline | FFD is classified against absolute limits, so it needs no baseline; GloFAS supplies history for the outlook |

## 12. What I need from you

1. Will you write to FFD, and should work on phase 1 start against hand-written
   payloads before the answer?
2. May the 13 captured samples be committed, or do they stay local until FFD answers?
3. The level mapping in section 6, especially whether a low flood alerts.
4. Who reviews the station-to-district table?
5. Keep GloFAS as the outlook (phase 2), or drop it and accept a 24-hour horizon?
