# FFD (Flood Forecasting Division, PMD) as a river-flood source

Research note on what `https://ffd.pmd.gov.pk/` publishes and how a program could
ingest it, written to inform issue #18 (river-flood source and riverine-flood hazard).
It follows the convention set by `docs/sources.md`: primary sources only, every claim
tied to a URL that was fetched, and a clear line between what a page *says* and what
the response *contained*.

Everything below was observed on **2026-10-09 between 07:50 and 08:00 UTC
(12:50–13:00 PKT)** with `curl` from this repository's machine. About 75 requests were
made at roughly one per second; none was throttled, challenged or blocked. No news
article, blog post or third-party description was used. The site was not crawled: each
page named below was fetched once, and paths excluded by `robots.txt` were not
fetched at all.

The site is run by the Flood Forecasting Division, Lahore, of the Pakistan
Meteorological Department (the page header reads "Flood Forecasting Division, Lahore
· Pakistan Meteorological Department · Ministry of Defence, Government of Pakistan").
The task brief called it the "Federal Flood Division"; the site does not use that name.

## Summary of findings against the plan

Issue #18 and `ai.md` sections 5.1 and 5.2 plan a river-flood hazard from Open-Meteo
Flood (GloFAS modelled discharge) at one hand-curated river point per district, with a
"forecast relative to recent baseline" rule whose thresholds are still "to calibrate".
Against that plan:

1. **FFD publishes observed discharge as JSON, and it is fetchable without a browser.**
   `/flood-assistant/rivers` returns a roster of 131 distinct gauging sites with stable
   integer ids, and `/flood-assistant/station/{id}` returns the latest observed inflow
   and outflow in cusecs, gauge levels, a 31-day daily series, FFD's own flood status,
   and a 24-hour forecast where one exists. No key, cookie or token was needed.
2. **FFD publishes its own flood classification and the per-site limits behind it.**
   The six levels (normal / low / medium / high / very high / exceptionally high) and
   the discharge that starts each one are on `/flood-limits` as an HTML table for 35
   sites, and are repeated per station in the station JSON. That is an authoritative
   answer to the "to calibrate" cells in `ai.md`, for the sites it covers.
3. **The forecast horizon is 24 hours, for 22 sites.** FFD's quantitative forecast is a
   next-24-hours inflow range for 22 named stations, issued once a day around 11:30
   PKT. Anything longer is narrative text. GloFAS via Open-Meteo gives a daily series
   months ahead. The two sources are not substitutes on horizon.
4. **Station coordinates are not available to an unauthenticated program.** They exist
   — the map popup renders `station.latitude` and `station.longitude` — but only in
   `/river-state/data`, which the page source describes as "token-gated
   (anti-scraping)" and which returns HTTP 403 without the page-issued token. Mapping
   sites to districts therefore needs either FFD's permission or a hand-curated table,
   exactly like the GloFAS river points.
5. **The licence position is restrictive and partly explicit.** Every page footer says
   "All rights reserved"; the daily bulletin adds "No part of this content may be
   reproduced, distributed, or transmitted in any form or by any means without prior
   written permission". No terms-of-use, API or data-sharing page exists. This is a
   weaker footing than Open-Meteo's CC BY 4.0.
6. **There is no per-district product and no documented river API.** The only endpoints
   the site itself documents for outside use are the weather observation feed
   (`/weather/current`, `/weather/cities`). The river endpoints are internal feeds
   behind the site's own chat widget and map.
7. **The site also serves numerical weather model output as data, not just maps**:
   point forecasts from ICON, GFS and ECMWF as JSON at any latitude/longitude, with
   the tehsil and district the point falls in.

---

## 1. Station roster and per-station river state (JSON)

### Endpoint

- `GET https://ffd.pmd.gov.pk/flood-assistant/rivers` — roster.
- `GET https://ffd.pmd.gov.pk/flood-assistant/station/{id}?lang=en` — one station.
  `lang` is `en` or `ur` in the site's own calls.
- `GET https://ffd.pmd.gov.pk/flood-assistant/ask?q=…` — free-text lookup behind the
  chat box. **Not called.**

These are the back end of the "Flood Assistant BETA" widget on the home page. They
were found in an inline script of `https://ffd.pmd.gov.pk/`
(`var ROUTES = { rivers: …, ask: …, station: … }`), which calls them with
`fetch(url, { headers: { 'Accept': 'application/json' } })` and nothing else.

### What it is

Observed river state, with FFD's classification and its short forecast attached.

- **Roster**: nine groups — Indus (19 entries), Kabul (30), Jhelum (11), Neelum (5),
  Chenab (6), Ravi (6), Sutlej (6), "Nullahs (Chenab/Ravi)" (5) and "Other stations"
  (50). 138 entries, 131 distinct ids; 34 entries are named "… (Telemetry)". Each entry
  is `id`, `name`, `name_ur`, `is_dam`. Three have `is_dam: true`: Tarbela Dam (86),
  Mangla Dam (51), Warsak Dam (104).
- **Station**: `code`, `river`, `is_dam`, `is_barrage`, `metric` (`discharge` or
  `level`), `unit` (`cusecs` or `ft`), `status` and `status_label`, then:
  - `current`: `timestamp` (ISO 8601 with `+05:00`), `source` (`PRIMARY` or
    `TELEMETRY` in the samples), `inflow_discharge`, `outflow_discharge`,
    `inflow_level`, `outflow_level`, `dam_level`, `flow`, `is_stale`.
  - `thresholds`: list of `{level, label, min_discharge, colour}`.
  - `season_peak` and `all_time_peak`: `{year, value, at}`.
  - `trend`, `trend_inflow`, `trend_display`: direction over a `window_hours` of 6.
  - `forecast`: `qualitative`, `quantitative` (the raw string, e.g. `"45 - 55"` or
    `"No sig. change"`), `forecast_time`, `valid_to`, an English `explanation`, and a
    parsed `quant` object with `from`, `to`, `unit`, `scale`. `null` for stations with
    no forecast.
  - `series`: 31 `{t, v}` points, one per calendar day, ending on the fetch date.
  - `reply`: a ready-made English sentence.
- **Units**: discharge in **cusecs** (cubic feet per second), not m³/s; levels in feet.
  One cusec is 0.0283168 m³/s, so Sukkur's 12,800 cusecs is about 362 m³/s.
- **Timing as observed**: all six `PRIMARY` stations fetched at 12:51–12:55 PKT carried
  `timestamp: 2026-10-09T12:00:00+05:00`; the one `TELEMETRY` station carried 06:00.
  The site's notification feed (section 6) shows situation reports stamped 00:00,
  06:00, 12:00 and 18:00 PKT. That is consistent with a six-hourly cadence on this
  date; the cadence during a flood was not observable. Season and all-time peaks carry
  odd hours (`27 Aug 2025 02:00`, `22 Jul 2026 20:00`), so readings are evidently taken
  more often than six-hourly at times.
- **Forecast**: `forecast_time: 09 Oct 2026 11:30`, `valid_to: 10 Oct 2026 11:30` — the
  same issue time as that day's bulletin (section 5). Horizon 24 hours.

### Format and sample

`Content-Type: application/json`. Fully machine-readable. From
`flood_assistant_station_81_sukkur.json`, abridged only by the `…`:

```json
{"ok":true,"type":"station","station":{"id":81,"name":"Sukkur","name_ur":"…","code":"SU",
 "river":"Indus","is_dam":false,"is_barrage":false,"metric":"discharge","unit":"cusecs",
 "status":"NORMAL","status_label":"Normal","status_colour":"#10b981",
 "current":{"timestamp":"2026-10-09T12:00:00+05:00","timestamp_human":"09 Oct 2026 12:00",
   "source":"PRIMARY","inflow_discharge":52850,"outflow_discharge":12800,
   "inflow_level":197.5,"outflow_level":186,"dam_level":null,"flow":12800,"is_stale":false},
 "thresholds":[{"level":"LOW","label":"Low","min_discharge":200000,"colour":"#0057b4"},
   {"level":"MEDIUM","label":"Medium","min_discharge":350000,"colour":"#ffc107"},
   {"level":"HIGH","label":"High","min_discharge":500000,"colour":"#fd7e14"},
   {"level":"VERY_HIGH","label":"Very High","min_discharge":700000,"colour":"#fc192c"},
   {"level":"EX_HIGH","label":"Extremely High","min_discharge":900000,"colour":"#a10211"}],
 "season_peak":{"year":2026,"value":369534,"at":"01 Aug 2026 06:00"},
 "all_time_peak":{"year":2022,"value":579753,"at":"25 Aug 2022 06:00"},
 "forecast":{"headline":"Sukkur — Normal","qualitative":"Normal",
   "quantitative":"No sig. change","forecast_time":"09 Oct 2026 11:30",
   "valid_to":"10 Oct 2026 11:30","…":"…","quant":null},
 "series":[{"t":"2026-09-09","v":167850},"…",{"t":"2026-10-09","v":12800}],"reply":"…"}}
```

### Sites

Ids are small integers and appear stable (they are database keys: an unknown id
returns `No query results for model [App\Models\HydroStation] 9999`). The roster gives
names in English and Urdu and a short `code` per station (`SU`, `TADA2`, `MA`,
`TLM-009`). **It gives no coordinates, no district and no province.**

The full roster is in `flood_assistant_rivers.json`. The main-stem sites, with ids:

| River | Sites (id) |
|---|---|
| Indus | Skardu (80), Partab Bridge (64), Besham (9), Tarbela Dam (86), Attock Khairabad (95), Jinnah Barrage (96), Kala Bagh (38), Chashma (16), Taunsa (87), Chacharan Sharif (251), Guddu (33), Sukkur (81), Kotri (48) |
| Kabul | Warsak (90), Warsak Dam (104), Nowshera (60), plus 27 tributary and nullah gauges in Khyber Pakhtunkhwa |
| Jhelum | Muzaffarabad (57), Domel (26), Garhi Habibullah (30), Azad Pattan (3), Chattar Kallas (17), Kotli (47), Mangla Dam (51), New Rasul (59) |
| Chenab | Marala (52), Khanki (40), Qadirabad (67), Chiniot Bridge (18), Trimmu (88), Panjnad (63) |
| Ravi | Jassar (37), Shahdara (74), Balloki (7), Sidhnai (79) |
| Sutlej | Ganda Singh Wala (29), Sulemanki (82), Islam (35), Melsi Syphon (54) |

Seven stations were fetched individually: 81, 86, 52, 80, 142, 44 and 63.

### Limits and access

- No authentication. Identical 200 responses were not re-tested with other user
  agents on this endpoint, but `/home/river-status` (section 2) answered identically
  to `curl`'s default agent, `python-httpx/0.27.0` and an empty agent.
- Response headers: `x-ratelimit-limit: 40`, `x-ratelimit-remaining` counting down
  per request; `Cache-Control: no-cache, private`. The window length is not stated.
  The counter read 36 after four calls and was back at 39 on the next call about four
  minutes later. **A naive loop over all 131 stations would exceed 40 requests** in
  whatever the window is.
- Every response sets two cookies (`XSRF-TOKEN`, `ffd-lahore-session`). They were
  never sent back and were not needed.
- The widget labels itself "Beta — automated readings for guidance only. For official
  information call 042-99200139."

### Gotchas

- **River grouping in the roster is not a clean hierarchy.** Panjnad (63) is listed
  under Jhelum, Chenab, Ravi and Sutlej; Trimmu (88) under Neelum and Chenab; Deg
  Nullah (44) under three groups; Nowshera (60) under Indus and Kabul. A station's own
  record then carries a single `river`: Panjnad's says `"Jhelum"`. Do not derive
  "which river is this site on" from the roster grouping.
- **`all_time_peak` is not the historical record.** Sukkur's is 579,753 cusecs in
  2022, while `/historical-peaks` (section 8) lists 1,166,574 in 1986. The station
  feed evidently covers only the digital record; the map page's JSON-LD declares
  `"temporalCoverage": "2020-01-01/.."`.
- **Thresholds can disagree with the published limits table.** Panjnad's `thresholds`
  are 150,000 / 200,000 / 300,000 / 450,000 / 600,000, while `/flood-limits` gives
  Panjnad 1.5 / 2.5 / 4 / 5.5 / 7 lacs (150,000 / 250,000 / 400,000 / 550,000 /
  700,000). The JSON values equal the *Trimmu* row of the table. Sukkur, Tarbela and
  Marala match the table exactly. Reconcile per site before trusting either.
- **`thresholds` can be empty or short.** Skardu (80) and Besham Telemetry (142) return
  `[]`; Deg Nullah (44) returns four levels with no `EX_HIGH`. With no thresholds the
  station still reports `status: "NORMAL"`, which then means "unclassified", not
  "confirmed normal".
- **`status` is a different vocabulary from the public pages.** The JSON uses
  `NORMAL`, `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`, `EX_HIGH` with labels "Normal" …
  "Extremely High". The home page and bulletin call the lowest level "Below Low" and
  the highest "Exceptionally High"; `/flood-limits` says "Exceptional". Key on the
  code, not the label.
- **For dams, `metric` is `level` and `series` is reservoir level in feet**, not
  discharge: Tarbela's series runs 1548.57 → 1519.42. Its thresholds are still in
  cusecs of inflow.
- **`flow` is outflow, and classification is on inflow.** Sukkur's `flow` is 12,800
  (its `outflow_discharge`) while the forecast text classifies on the 52,850 inflow.
  For a barrage the two differ by the canal withdrawals.
- **`null` occurs in `series`** (Tarbela has two null days in 31), and telemetry
  stations can have null discharge throughout with only a gauge level.
- **`forecast.quantitative` is free text in thousands of cusecs** (`"45 - 55"`,
  `"No sig. change"`, `"0.1 - 0.2"`, `"05 - 15"`). Use the parsed `quant.from` /
  `quant.to`, which is absent (`null`) when the text is not a range.
- `series` has one value per day with no time; which reading of the day it is was not
  established.
- Level fields on barrages carry no unit of their own (`inflow_level: 197.5`); the
  widget's strings label gauge readings "ft".

### Fixtures

- `backend/tests/fixtures/ffd/flood_assistant_rivers.json` — fetched 07:51:23Z.
- `…/flood_assistant_station_81_sukkur.json` — 07:51:39Z, a barrage with a
  non-numeric forecast.
- `…/flood_assistant_station_86_tarbela.json` — 07:51:40Z, a dam with a numeric
  forecast range and nulls in the series.
- `…/flood_assistant_station_142_besham_telemetry.json` — 07:55:20Z, a telemetry
  station with no thresholds, no forecast and null discharge.

---

## 2. Rivers-at-a-glance status (JSON)

### Endpoint

`GET https://ffd.pmd.gov.pk/home/river-status` — named in the home page as
`data-strip="https://ffd.pmd.gov.pk/home/river-status"` on the "Rivers now" strip.

### What it is

One row per river (Indus, Kabul, Jhelum, Neelum, Chenab, Ravi, Sutlej): the highest
current status on that river, the station it occurs at, and that station's discharge.
Observed. The page shows "Updated 09-Oct-2026 12:00 PKT" beside the strip.

### Format and sample

`application/json`, 1,018 bytes, complete response in `home_river_status.json`:

```json
[{"river":"Indus","river_ur":"سندھ","status":"normal","label":"Below Low","rank":0,
  "station":"Besham","discharge":"43,000"},
 {"river":"Neelum","river_ur":"نیلم","status":"normal","label":"Below Low","rank":0,
  "station":"Trimmu","discharge":"588"}, "…"]
```

### Sites

Seven rivers; the station is named, with no id.

### Limits and access

`Cache-Control: max-age=300, public`, `x-ratelimit-limit: 120`. An `ETag` is returned
but `If-None-Match` with that tag still returned 200 with a full body, so conditional
requests do not save anything.

### Gotchas

- `discharge` is a **string with thousands separators** (`"43,000"`), and `status` is
  lower-case here (`"normal"`) where the station feed uses `NORMAL`.
- It reports the Neelum's highest station as **Trimmu**, which the limits table and
  bulletin both place on the Chenab. This follows from the roster grouping problem in
  section 1 and means the per-river summary cannot be taken at face value.
- No timestamp in the payload.

---

## 3. River-state map feed with coordinates (token-gated)

### Endpoint

`GET https://ffd.pmd.gov.pk/river-state/data` (optionally `?mine=1` for signed-in
users), called by the map page `https://ffd.pmd.gov.pk/river-state` with the headers
`X-Requested-With: XMLHttpRequest` and `X-FW-Token: <value embedded in the page>`.
The token in the page fetched had the form `<unix-time>.<64 hex characters>`, with
the time about 12 hours after the fetch.

### What it is

The data behind the home page's live map. **The payload was not retrieved.** From the
page's own rendering code, each station object carries `name`, `status`, `area_name`,
`height`, `latitude`, `longitude`, `recording_time`, `discharge`, `level`, a `gauges`
list (`type`, `discharge`, `trend`, `trend_icon`), `forecast_status`, `forecast_qual`,
`forecast_quant`, `cyp_discharge` / `cyp_status` / `cyp_date` (current-year peak) and
an optional `shape` polygon. The page says: "Number above a marker = discharge
(cusecs). Ring = 24h forecast status" and "Data from WAPDA & provincial irrigation
departments."

### Format and sample

Without the token:

```
HTTP/1.1 403 Forbidden
{"ok":false,"error":"Forbidden."}
```

(saved as `river_state_data_forbidden.json`).

### Sites

This is the only place on the site where gauging-site **coordinates** were found to
exist. They are displayed to three decimal places in the map popup.

### Limits and access

The page source carries two comments in the site developers' words:

> Station data is fetched from the token-gated endpoint (anti-scraping), not embedded
> in the page shell.

> Station data is token-gated (anti-scraping), not inlined. Fetch, then render.

The token was deliberately **not replayed** from a script. Doing so is technically
trivial — it is printed in the HTML — but the operator has stated in terms that this
control exists to stop programmatic collection, and the brief for this note was to
stop where the site signals it does not want a client. Whether replaying it would
work, how long a token lives and whether it is bound to a session are therefore
unconfirmed.

### Gotchas

- Do not build ingestion on this endpoint without FFD's agreement. The station feed in
  section 1 carries the same readings without the gate; only the coordinates, station
  height and river-reach polygons are unique to this one.
- The page also loads `https://ffd.pmd.gov.pk/kmz/rivers.kmz` (557 KB; one KML
  placemark holding 630 river line strings and **no** point features) and
  `/js/kmz_values.js` (a Pakistan boundary ring). Neither contains stations.

---

## 4. Flood limits (FFD's classification thresholds)

### Endpoint

`GET https://ffd.pmd.gov.pk/flood-limits`. The page ends "Last updated: 9-Sept 2025".

### What it is

The discharge at which each flood category begins, per site, plus the structure's
design capacity. Static reference data. Rivers are in **lacs of cusecs** (1 lac =
100,000) and nullahs in cusecs. Category names on this page: Low, Medium, High, Very
High, Exceptional. The level below "Low" is "Normal Flow" on the map legend and
"Below Low" in the bulletin.

`/flood-ews` describes the same scale in words: "River conditions are classified into
six levels based on observed discharge thresholds at each gauging site" — Normal
("Below minor flood level"), Low ("Minor inundation likely"), Medium ("Moderate
flooding"), High ("Significant flood risk"), Very High ("Severe inundation"),
Exceptional ("Catastrophic flooding").

### Format and sample

Server-rendered HTML, with the numbers present twice: as cards and as a plain
`<table>` ("Switch to Table View"). Machine-readable. Saved whole as
`flood_limits.html`. The table, transcribed from that response:

| River | Station | Design | Low | Medium | High | Very High | Exceptional |
|---|---|---|---|---|---|---|---|
| Indus | Tarbela | 15 | 2.5 | 3.75 | 5 | 6.5 | 8 |
| Indus | Attock | — | 2.5 | 3.75 | 5 | 6.5 | 8 |
| Indus | Kalabagh | 9.5 | 2.5 | 3.75 | 5 | 6.5 | 8 |
| Indus | Chashma | 9.5 | 2.5 | 3.75 | 5 | 6.5 | 8 |
| Indus | Taunsa | 10 | 2.5 | 3.75 | 5 | 6.5 | 8 |
| Indus | Guddu | 12 | 2 | 3.5 | 5 | 7 | 9 |
| Indus | Sukkur | 9 | 2 | 3.5 | 5 | 7 | 9 |
| Indus | Kotri | 8.75 | 2 | 3 | 4.5 | 6.5 | 8 |
| Kabul | Warsak | 5.4 | 0.4 | 0.6 | 1 | 1.5 | — |
| Kabul | Nowshera | — | 0.6 | 0.9 | 1.4 | 2 | — |
| Jhelum | Kohala | — | 1 | 1.5 | 2 | 3 | 4 |
| Jhelum | Mangla | 10.6 | 0.75 | 1.1 | 1.5 | 2.25 | 3 |
| Jhelum | Rasul | 8.5 | 0.75 | 1.1 | 1.5 | 2.25 | 3 |
| Chenab | Jammu Tawi | — | 0.2 | 0.7 | 0.83 | 1.7 | — |
| Chenab | Akhnur | — | 0.75 | 1.97 | 2.97 | 3.5 | — |
| Chenab | Marala | 11 | 1 | 1.5 | 2 | 4 | 6 |
| Chenab | Khanki | 11 | 1 | 1.5 | 2 | 4 | 6 |
| Chenab | Qadirabad | 9 | 1 | 1.5 | 2 | 4 | 6 |
| Chenab | Chinot Bridge | 8.07 | 1 | 1.5 | 2 | 4 | 6 |
| Chenab | Trimmu | 8.75 | 1.5 | 2 | 3 | 4.5 | 6 |
| Chenab | Panjnad | 8.65 | 1.5 | 2.5 | 4 | 5.5 | 7 |
| Ravi | Jassar | 2.75 | 0.5 | 0.75 | 1 | 1.5 | 2 |
| Ravi | Syphon | 4.5 | 0.4 | 0.65 | 0.9 | 1.35 | 1.8 |
| Ravi | Shahdara | 2.5 | 0.4 | 0.65 | 0.9 | 1.35 | 1.8 |
| Ravi | Balloki | 3.8 | 0.4 | 0.65 | 0.9 | 1.35 | 1.8 |
| Ravi | Sidhnai | 1.5 | 0.3 | 0.46 | 0.6 | 0.9 | 1.3 |
| Sutlej | Suleimanki | 3.25 | 0.5 | 0.8 | 1.2 | 1.75 | 2.25 |
| Sutlej | Islam | 3 | 0.5 | 0.8 | 1.2 | 1.75 | 2.25 |
| Sutlej | G.S. Wala | — | 0.5 | 0.8 | 1.2 | 1.75 | 2.25 |

Nullahs, in cusecs:

| Nullah (site) | Low | Medium | High | Very High | Exceptional |
|---|---|---|---|---|---|
| Bein (Chak Amru) | 1300 | 7000 | 20000 | 30000 | 35000 & Above |
| Bein (Shakargarh) | 1600 | 3000 | 24000 | 26000 | 43000 & Above |
| Aik (Ura) | 2000 | 9000 | 13000 | 16000 | 33000 & Above |
| Basantar (Jassar) | 4100 | 4700 | 7500 | 11600 | 17800 & Above |
| Deg (Kingra Bridge) | 10000 | 15000 | 22000 | 30000 | — |
| Palku (Wazirabad) | 2500 | 3100 | 5000 | 25000 | 26000 & Above |

### Sites

29 river sites and 6 nullah sites, by name only — no ids, no coordinates. Two (Jammu
Tawi, Akhnur) are upstream on the Chenab outside Pakistan-administered territory and
do not appear in the station roster.

### Limits and access

Plain page, `Cache-Control: no-cache, private`. Returned the same 123,041 bytes to a
custom non-browser user agent.

### Gotchas

- **Names do not join to the roster without a mapping.** "Chinot Bridge" / "Chiniot
  Bridge", "Suleimanki" / "Sulemanki", "G.S. Wala" / "Ganda Singh Wala", "Rasul" /
  "New Rasul", "Syphon" / "Ravi Syphon", "Kalabagh" / "Kala Bagh", "Punjnad" (bulletin)
  / "Panjnad". Kohala has limits but was not seen in the roster.
- Units switch between lacs (rivers) and cusecs (nullahs) within one page.
- "& Above" and "—" appear in numeric columns.
- The page disagrees with the station feed for Panjnad (section 1).
- Limits are thresholds on discharge at a structure, classified on inflow in the
  bulletin ("Qualitative Forecasted Flood Level (Inflow)").

---

## 5. Daily flood bulletin and advisories

### Endpoint

- Latest: `https://ffd.pmd.gov.pk/bulletin/bulletin` (bulletins),
  `https://ffd.pmd.gov.pk/bulletin/advisory` (advisories), `https://ffd.pmd.gov.pk/bulletin` (both).
- Permalink: `https://ffd.pmd.gov.pk/b/{uuid}` — e.g.
  `/b/e622b334-6363-4bc0-8794-ed6a93502e8f` for 9 October 2026. The uuid is not
  derivable from the date.
- PDF: `https://ffd.pmd.gov.pk/bulletin/{n}/download` and `/bulletin/{n}/inline`,
  where `n` is a sequential integer (129 for 9 October 2026; it is **not** the bulletin
  number, which was 117/26).
- Discovery: `https://ffd.pmd.gov.pk/sitemap.xml` lists `/b/{uuid}` entries with
  `<lastmod>`. On the fetch date it held exactly 100, from 2026-07-21 to 2026-10-09.
  The listing page paginates with `?page=N`; page 12 reached back to at least
  18 June 2026.
- Past seasons: `https://ffd.pmd.gov.pk/bulletins/archive` with `?year=2024|2025`,
  `?type=bulletin|advisory` and `?page=N`; files at
  `/bulletins/archive/{n}/download`.

### What it is

The division's official daily product during the flood season. The 9 October bulletin
was "BULLETIN No: 117/26 … Time: 11:30 hours (PST)", shown as "Issued: 09 Oct 2026,
11:30 · Published: 09 Oct 2026, 11:42". Issue times across the ten most recent ranged
from 10:30 to 12:00. `/depression-tracks` gives the flood season as "15 June –
15 October". Contents:

1. Rivers at a glance (six rivers, one category each).
2. Meteorological features and outlook, hydrological situation "at 0600 PST" and
   outlook — narrative.
3. Weather forecast for 24 hours and outlook for 48 hours — narrative, naming
   districts by province.
4. Weekly outlook (rainfall and flood) — narrative.
5. Reservoir levels at 0600 PST: Tarbela and Mangla level in feet, dead and maximum
   conservation level, live storage in MAF and percent.
6. **"Quantitative flood forecast of gauging stations (in thousands of cusecs)"**: for
   22 stations, observed inflow and outflow at 0600 PST, a quantitative forecast for
   the next 24 hours (inflow), the qualitative forecast flood level, the historical
   maximum with its category and year, and the 2026 season peak.
7. A headroom table repeating each station's limits and design capacity.
8. Catchment rainfall recorded in the last 24 hours (to 0800 PST), as text:
   `Jhelum: Qila Rohtas=35, Mangla=26, Mandi Bahauddin=16, …`.
9. Rainfall forecast maps (24 h and 48 h) and an observed-rainfall map — **images**.

The 22 forecast stations: Tarbela, Kalabagh, Chashma, Taunsa, Guddu, Sukkur, Kotri
(Indus); Nowshera (Kabul); Mangla, Rasul (Jhelum); Marala, Khanki, Qadirabad, Trimmu,
Punjnad (Chenab); Jassar, Shahdara, Balloki, Sidhnai (Ravi); G.S. Wala, Sulemanki,
Islam (Sutlej).

Advisories are event-driven. The most recent was "Flood Advisory — Chenab River",
issued 22 Jul 2026 17:18, structured as What / Where / When / Expected impacts /
Recommended actions, in prose.

### Format and sample

The 2026 bulletin is served as **HTML with the tables as real `<table>` elements and
`data-ffd` attributes on the cells**, alongside a PDF of the same content (4,497,410
bytes for 9 October). The numbers are machine-readable without touching the PDF. One
row of the forecast table, verbatim:

```html
<div data-ffd-block="quantitative-forecast"><figure class="table"><table …>
<tr><td …><strong>INDUS</strong></td><td … data-ffd="station">Tarbela</td>
<td … data-ffd="inflow">52.0</td><td … data-ffd="outflow">36.1</td>
<td … data-ffd="forecast">45 - 55</td>
<td … data-ffd="flood-level" data-ffd-value="Below Low" bgcolor="#017321"><strong>Below Low</strong></td>
<td …>832.0</td><td …>EH (2010)</td><td … data-ffd="season-peak">343.0</td></tr>
```

Block markers seen: `rivers-at-a-glance`, `severity-legend`, `forecast-maps`,
`weather-rainfall-forecast`, `reservoirs`, `quantitative-forecast`, `headroom-chart`,
`observed-rainfall-map`, `distribution`, `signatory`.

The page also prints a "Content SHA-256" and a "PDF file SHA-256" under "Document
authenticity", stating "This page is the authoritative copy of this bulletin."

Archived bulletins (2024 and 2025) are **PDF only**, named by date (`30092025.pdf`,
827,251 bytes, three pages, produced by FPDF 1.86). The one inspected has a text
layer (1,671 text-drawing operators); it is not a scanned image. Extracting its tables
was not attempted.

### Sites

Named stations only; no ids, no coordinates. Station names follow the bulletin's own
spelling, which differs from both the roster and the limits page.

### Limits and access

No login. The bulletin footer carries the strongest rights statement on the site:

> All rights reserved. No part of this content may be reproduced, distributed, or
> transmitted in any form or by any means without prior written permission

For that reason **no bulletin was saved as a fixture**. Storing bulletin HTML as an
immutable evidence snapshot, and quoting it in alerts, is "reproduction" on any plain
reading and should be cleared with FFD first.

### Gotchas

- **Seasonal.** Bulletins are a flood-season product. The 2025 archive's last entry is
  15 October 2025 and the 2026 series starts in mid-June. Outside 15 June – 15 October
  this source should be expected to go quiet; what the "latest" page shows then was not
  observable.
- **Days can be missing.** The 2025 archive lists 11 and 13 October 2025 but no
  12 October. The sitemap's `<lastmod>` is a modification time, not the issue date
  (the 2 October 2026 bulletin carries a 3 October `lastmod`), so do not date a
  bulletin from it.
- **Three formats across three years**: FPDF-generated PDFs for 2024–2025, structured
  HTML for 2026. The `data-ffd` markup is new and has no stated stability guarantee.
- The 2026 listing's older entries have different titles ("18 June 2026 Combined
  Bulletins", "20 June 2026 Flood Bulletins"), so early-season items may not share the
  October structure.
- "PST" on this site means Pakistan Standard Time (UTC+5), not US Pacific.
- Values are in **thousands of cusecs** here, cusecs in the station feed, lacs on the
  limits page.
- The forecast column mixes ranges and text (`45 - 55`, `No sig. change`,
  `0.1 - 0.2`), and the historical-peak category for G.S. Wala is `**`.
- Bulletins can be corrected after issue: the authenticity note says a copy whose code
  does not match "has either been altered, or superseded by a correction". A snapshot
  is therefore not guaranteed final.

---

## 6. Notifications feed

### Endpoint

`https://ffd.pmd.gov.pk/notifications`; individual items at
`/notifications/{yyyy-mm-dd}/{10-hex-id}`.

### What it is

Short updates, mostly an automated "flood situation report" in Urdu stamped 00:00,
06:00, 12:00 and 18:00 PKT ("Live · 708 updates" on the fetch date). On a quiet day
each says all reporting sites are at normal flow.

### Format and sample

HTML cards, Urdu text. No JSON feed, RSS or Atom link was found in the page. Push
delivery uses Firebase web push and requires a browser.

### Sites, limits, gotchas

Not investigated further: the content duplicates section 1 in prose and in Urdu. Its
value is as evidence of the six-hourly reporting cadence.

---

## 7. Numerical weather model data

### Endpoint

Behind the "Weather Model Viewer" at `https://ffd.pmd.gov.pk/weather-model`:

- `GET /weather-model/manifest?source={icon|gfs|ecmwf}` — the current cycle, the list
  of retained cycles and a description of every field.
- `GET /weather-model/point?source=…&cycle={yyyymmddhh}&lat={lat}&lon={lon}` — the
  forecast series at one point.
- Rendered and raw fields under the manifest's `base_url`, e.g.
  `/storage/nwp/icon/2026100900/tp/003d.png`, `/storage/nwp/icon/2026100900/tp.f32`,
  `/storage/nwp/icon/2026100900/wind/003d.json`. **These files were not fetched**;
  their names and sizes come from the manifest.

### What it is

Forecast fields from three global models, regridded over 0–40° N, 60–90° E. The
`/flood-ews` page credits ICON to DWD, GFS to NOAA/NCEP and ECMWF to the European
Centre. As returned on the fetch date:

| Source | Grid | Step | Steps | Horizon | Cycle | `generated_at` |
|---|---|---|---|---|---|---|
| `icon` | 0.125°, 321 × 241 | 3 h | 61 | 180 h | 2026100900 | 2026-10-09T03:43:33Z |
| `gfs` | 0.25°, 161 × 121 | 3 h | 81 | 240 h | 2026100900 | 2026-10-09T04:49:18Z |
| `ecmwf` | 0.25°, 161 × 121 | 6 h | 41 | 240 h | 2026100900 | 2026-10-09T07:47:59Z |

Cycles at 00, 06, 12 and 18 UTC; eleven or twelve were retained per source, going back
to 2026-10-06 06 UTC — about three days. The 00 UTC ICON run was available 3 h 44 min
after its nominal time.

Variables (ICON): `tp` total precipitation per step (mm), `tp24` 24-hour rainfall for
"08:00-08:00 PKT" windows (three frames only, to 75 h), `t2m` (°C), `r2` (%), `u10`,
`v10`, `wspd10` (m/s), `prmsl` (hPa), `tcc` (%). GFS adds `gust`, `lcc`, `mcc`, `hcc`.
ECMWF's `tp24` window is "05:00-05:00 PKT", not 08:00.

The point endpoint also returns `daily` (tmax, tmin, rain), `rain_days`, a `place`
object, a bilingual `narrative` and a cross-model `consensus` of daily rain.

### Format and sample

`application/json`. From `weather_model_point_icon_sukkur.json`, abridged:

```json
{"ok":true,"source":"icon","cycle":"2026100900","cycle_iso":"2026-10-09T00:00:00Z",
 "lat":27.68,"lon":68.88,"cell":{"lat":27.625,"lon":68.875},
 "steps":[0,3,6,"…",180],"valid_times":["2026-10-09T00:00:00Z","…"],"interval_hours":3,
 "units":{"t2m":"degC","r2":"%","tp":"mm","prmsl":"hPa","tcc":"%","wspd10":"m/s",
          "wdir10":"deg","tp_cum":"mm"},
 "series":{"t2m":[27.06,27.4,"…"],"tp":[0,0,"…"],"…":"…"},
 "daily":[{"date":"2026-10-09","tmax":37.44,"tmin":27.06,"rain":0,
           "rain_window":{"start":"2026-10-09T03:00:00Z","end":"2026-10-10T03:00:00Z"}},"…"],
 "place":{"name":"Rohri","district":"Sukkur","province":"Sindh","outline":{"type":"MultiPolygon","…":"…"}},
 "consensus":{"2026-10-09":{"models":{"icon":0,"gfs":0,"ecmwf":0},"median":0,"total":3,"spread":0}}}
```

The manifest describes raw grids as `"dtype":"float32_le"` with `bytes_f32` of
18,876,084 for a 61-step ICON field — 321 × 241 × 61 × 4 bytes, so the layout is
arithmetically consistent with a plain step × lat × lon cube, north to south.

### Sites

Not station-based: any latitude and longitude in the grid. The response reports the
tehsil, district and province the point falls in.

### Limits and access

No authentication. `x-ratelimit-limit: 120`; manifest `Cache-Control: max-age=600,
public`, point `max-age=300, public`. A per-district loop is 155 point calls per model.

### Gotchas

- **`cycle` is a required moving parameter.** Read it from the manifest first; an old
  cycle disappears after about three days. Behaviour for a missing or expired cycle
  was not tested.
- **`daily[].rain` is `null` beyond day three** in the ICON sample, because `tp24` has
  only three frames, even though the 3-hourly `tp` series runs to 180 h.
- The requested point is echoed rounded to two decimals (`27.68`) while `cell` gives
  the grid node actually used.
- Rain-day windows differ by model (08:00 PKT for ICON and GFS, 05:00 for ECMWF).
- These are third-party model fields redistributed by FFD. The same models are
  available from their owners and, for ICON, GFS and ECMWF, through the Open-Meteo
  forecast API this project already calls, under a clear licence.
- `/weather-assistant/{provinces|districts|places|forecast|ask}` is a second,
  tehsil-level route into the same models behind the home page's "Weather Assistant
  BETA". Only `/provinces` was called (seven provinces, `x-ratelimit-limit: 40`); the
  others are unexamined.

### Fixtures

- `…/ffd/weather_model_manifest_icon.json` — fetched 07:53:18Z.
- `…/ffd/weather_model_point_icon_sukkur.json` — 07:53:25Z, at 27.675 N, 68.875 E,
  the same Sukkur Barrage point as `open_meteo_flood_two_locations.json`.

---

## 8. Other products on the site

Grouped because none is a strong candidate for automated river-flood ingestion. Each
was fetched and is described from its response.

### Weather observations — `/weather/current`, `/weather/cities` (JSON, documented)

The only endpoints the site itself documents for outside use. `/weather-widget` says:
"Put live Pakistan Meteorological Department observations on your own website … no
account, no key, no script to install", and under "Prefer JSON?" lists
`GET /weather/current?city=lahore` ("Accepts `lat` & `lng` instead, and answers with
the nearest city") and `GET /weather/cities` ("Every city this feed covers, with
coordinates"). Observed: 101 cities with `slug`, `name`, `province`, `lat`, `lng`;
current conditions with `temperature`, `max_temp`, `min_temp`, `rainfall_mm`,
`rainfall_24h_mm`, `humidity_pct`, `pressure_hpa`, `observed_at`, `station`,
`source` (`"metar"` for Lahore), WMO codes, a 12-hour hourly forecast from ICON, and
an `attribution` field reading "Flood Forecasting Division — Pakistan Meteorological
Department". `Cache-Control: max-age=120`. This is observed rainfall at synoptic
stations, not river data. Fixtures: `weather_current_lahore.json`,
`weather_cities.json`.

### Radar — `/radar/manifest`, `/radar/archive` (JSON index, PNG frames)

`/radar/manifest` lists two sites, Islamabad and Karachi, each with three products:
`rain12` ("Rainfall — 12 h accumulation", mm, 60-minute cadence), `sri` ("Surface
rain rate", mm/hr, 10-minute) and `cappi01` ("CAPPI rain rate (1 km)", 10-minute),
with geographic bounds for 200 km and 450 km radii and 30 frame URLs each
(`/storage/radar/islamabad/rain12/2026-10-07/islamabad_N334057_E0730351_H0591_202610070400_rain_12h_450km.png`).
`archive_from` was `2026-09-09`, a 30-day retention. **The rainfall is locked in
colour-banded PNGs**; a page comment says the frames are "hard-quantised to the 16
legend bands". Reliability signal: on the fetch date all three Islamabad products
were flagged `"stale": true`, with the latest frame about 28 hours old, and two of
three Karachi products were stale. `/flood-ews` claims eight Doppler radars; two are
exposed here. Fixture: `radar_manifest.json`.

### Flood dashboard — `/flood-dashboard` (images)

Describes seven sections. The model-forecast, satellite and synoptic content is image
files: `/media/{uuid}/{unix-time}/ffgs-icon-24.png`, `jircks-48.png`, `jaxa-rain.jpg`,
`pressure-change.jpg`, `maximum.jpg`, `visibility.jpg`, and hashed names under
`/storage/pmd-images/{gfs|icon|satellite}/`. This is where the Flash Flood Guidance
System (FFGS) output and the "JIRCKS" precipitation forecast appear, and only as
pictures. Section 3, "Hydrological Data — Latest river flow values from WAPDA,
Irrigation and Police sources", is an iframe to `/staff/discharge-report-carousel`,
a path under the `robots.txt`-disallowed `/staff/` prefix; not fetched.

### Meteograms — `/meteograms` (PNG charts)

Ten-day point-forecast charts for 87 named places from GFS, ECMWF and ICON, as images
at `/meteograms/image/{slug}`, `/meteograms/ecmwf/image/{slug}` and
`/meteograms/icon/image/{slug}`. The page embeds the station list with coordinates as
a JavaScript array. Images only; the numbers are in section 7.

### Historical peaks — `/historical-peaks` (HTML table)

The three highest recorded peaks, with date and category, for 20 stations on the
Indus, Jhelum, Chenab, Ravi and Sutlej (e.g. Guddu 1,199,672 cusecs on 15 Aug 1976,
EH). Machine-readable HTML. Three events per site is far too little for a statistical
baseline. One cell reads "Overflow" instead of a number (Jassar, 25 Sep 1988).

### Annual flood reports — `/flood-reports` (PDF)

One PDF per year from 2006 to 2025 at `/flood-reports/{n}/download`, `n` from 1 to 20.
None was downloaded; their contents and whether they hold daily discharge tables are
unconfirmed.

### Reservoir inflow outlook — `/maf-forecast` (HTML)

A ten-day inflow forecast in million acre-feet for Tarbela and Mangla with the normal
for comparison ("01 Oct 2026 to 10 Oct 2026 … Tarbela 1.0-1.2 MAF, Normal: 1.07 MAF").
Two numbers, updated at the start of each ten-day period.

### Depression tracks — `/depression-tracks` (images)

Track maps "produced using ArcGIS", updated daily in season when a system is active;
"Outside the flood season this page reflects the last recorded system of that year."
On the fetch date: updated 28 Sep 2026, designation "NIL".

### Seasonal forecasts and the telemetric station list (images)

The Rabi and Kharif seasonal forecasts, the flood routing model diagram and the
"Telemetric Stations" list are single image files at `/file/{uuid}/view`. The
telemetric list (`telemetric_stations_list.jpg`, 341,943 bytes) is a sketch map
"Courtesy WAPDA" titled "Existing Telemetric Rain & River Stations", with 42 numbered
sites keyed to names and a latitude/longitude graticule at 72°, 75°, 78° E and 32°,
35° N. **It gives no coordinates as text.**

### Geographic layers — `/geojson/…` (GeoJSON)

Referenced by the model viewer and radar page: `pak-national.geojson`,
`pak-provinces.geojson`, `pak-districts.geojson`, `pak-tehsils.geojson`,
`pak-iok.geojson`, `region-neighbours.geojson`, `reservoirs.geojson`,
`osm/rivers.geojson`, `osm/waterbodies.geojson`, `osm-full/streams.geojson`. Only
`reservoirs.geojson` was fetched: six polygons (Tarbela, Mangla, Baran, Manchhar,
Wular Lake, Govind Sagar) with `name` and `country`. The river layers are labelled as
OpenStreetMap-derived by their path. A district boundary set exists here, but this
repository already has its own in `backend/data/source/`.

### Not fetched

- `/data/flood-watch` — "Flood Watch Beta: New interactive rainfall & river-gauge
  flood map. Experimental beta — features and data may be incomplete or change."
  Linked from the home page but under `Disallow: /data/`.
- `/hydro-dashboard`, `/inundation`, `/dashboard`, `/profile`, `/cms/`, `/staff/` —
  all disallowed. Their existence is known only from `robots.txt`.
- `http://faws.pmd.gov.pk/` ("Real-Time FAWS", a separate host linked from the home
  page). It answered `302` to `/faws/new`; the redirect was not followed.
- `/login` and everything behind it (personal gauge lists, meteogram screens,
  notification preferences).
- `/pollen`, `/internships`, `/address-book` — irrelevant.

---

## Access conditions (whole site)

**robots.txt** — `https://ffd.pmd.gov.pk/robots.txt`, complete and verbatim (saved as
`backend/tests/fixtures/ffd/robots.txt`):

```
User-agent: *
Allow: /

Disallow: /cms/
Disallow: /staff/
Disallow: /data/
Disallow: /dashboard
Disallow: /profile
Disallow: /hydro-dashboard
Disallow: /inundation

Sitemap: https://ffd.pmd.gov.pk/sitemap.xml
```

It was served with HTTP status **404** and `Content-Type: text/plain`, with the body
above. A strict client that ignores the body of a 404 would conclude there is no
robots file. `/flood-assistant/`, `/home/`, `/weather-model/`, `/weather/`, `/radar/`,
`/b/` and `/bulletin/` are not disallowed. No `Crawl-delay` is given.

**Terms, copyright, licence.**

- Every page footer: "© 2026 Flood Forecasting Division. All rights reserved."
- The bulletin's no-reproduction notice, quoted in section 5.
- The map popup: "© Flood Forecasting Division, Lahore"; the map page: "Data from
  WAPDA & provincial irrigation departments", so FFD is not the originator of the
  discharge readings.
- `/river-state` embeds schema.org `Dataset` metadata with
  `"isAccessibleForFree": true` and `"license": "https://ffd.pmd.gov.pk"`. The
  licence value is the home page, which contains no licence text. Free to view is not
  a grant to reuse.
- The weather widget page is the only place offering data for reuse, and only weather
  observations: "free, and no key required".
- No terms-of-use, disclaimer, privacy, API or data-policy page was found in the
  navigation, footer or sitemap of ffd.pmd.gov.pk.
- `https://www.pmd.gov.pk/` is now a signpost page ("Our live forecasts, warnings and
  advisories now publish at weather.gov.pk") with footer "© 2019-2026 Pakistan
  Meteorological Department" and no terms link. `https://weather.gov.pk/` has footer
  "©2026 PMD, All Rights Reserved." and no terms link on its home page.
- `/contact-us` invites contact "for flood information, data requests, and
  coordination" at 46 Jail Road, Lahore, +92 42 99200139, and an address that decodes
  from the page's Cloudflare obfuscation to `ffd@weather.gov.pk`. A data request is
  the route the site itself points to.

**Technical.**

- Laravel application behind Cloudflare (`Server: cloudflare`; observed edge `ISB`).
  Pages include Cloudflare's JavaScript-detection snippet
  (`/cdn-cgi/challenge-platform/scripts/jsd/main.js`), but no challenge page, CAPTCHA
  or 403 was served to `curl` on any ungated URL. Whether Cloudflare would challenge a
  client from a data-centre or non-Pakistani address is **unknown**; these requests
  were answered by Cloudflare's Islamabad edge, i.e. they came from inside Pakistan.
- hCaptcha is loaded on the home page; it guards the newsletter form, not reading.
- TLS: valid Let's Encrypt certificate for `CN=pmd.gov.pk`, expiring 2026-12-08.
  `http://` returns 301 to `https://`.
- Rate-limit headers: 120 on general endpoints, 40 on the two assistant APIs, window
  unstated.
- Responses did not differ between `curl/…`, `python-httpx/0.27.0`, an empty user
  agent and a descriptive custom agent, on the two URLs where that was tested.

## Reliability signals observed

- Radar products flagged stale by the site's own manifest (section 8).
- The home page's river summary attributes a Chenab station to the Neelum.
- Station thresholds that contradict the published limits table for at least one site.
- A bulletin day missing from the 2025 archive (12 October 2025).
- "Beta" labels on the Flood Assistant, Weather Assistant and Flood Watch.
- Asset names with content hashes (`/build/assets/public-BUUa4qWm.js`) and a model
  viewer under visible active development: the internal feeds this note describes are
  not a published contract and can change without notice.
- The station feed has an `is_stale` flag; it was `false` on all seven stations
  fetched, so what a stale reading looks like was not observed.

## Summary table

| Dataset | Observed / forecast | Format | Machine-readable | Update frequency (as observed) | Usable for automated ingestion |
|---|---|---|---|---|---|
| Station roster, `/flood-assistant/rivers` | reference | JSON | yes | static | yes, with caveats: undocumented, no coordinates, 40-request limit, rights reserved |
| Station state, `/flood-assistant/station/{id}` | observed + 24 h forecast | JSON | yes | readings stamped 12:00 on a 00/06/12/18 pattern; forecast daily ~11:30 PKT | with caveats: one call per station, undocumented, rights reserved |
| River summary, `/home/river-status` | observed | JSON | yes | 5-minute cache | no — seven rows, known mis-attribution |
| Map feed, `/river-state/data` | observed + forecast, with coordinates | JSON | yes, but gated | not observed | **no** — operator-declared anti-scraping token |
| Flood limits, `/flood-limits` | reference | HTML table | yes | "Last updated: 9-Sept 2025" | yes as a one-off hand-reviewed import, not per cycle |
| Daily bulletin 2026, `/b/{uuid}` | observed 06:00 + 24 h forecast + narrative | HTML with `data-ffd` cells; PDF | tables yes; rainfall maps no | daily 10:30–12:00 PKT, flood season only | with caveats: explicit no-reproduction notice, seasonal, new markup |
| Bulletin archive 2024–2025 | observed + forecast | PDF with text layer | partly — needs PDF table extraction | static | no for cycles; possible one-off for evaluation, subject to the notice |
| Advisories | forecast, narrative | HTML / PDF | text only | event-driven | no as a threshold input |
| Notifications | observed, narrative | HTML, Urdu | no | six-hourly | no |
| NWP point forecast, `/weather-model/point` | forecast | JSON | yes | four cycles a day, ~3 days retained | yes technically; duplicates Open-Meteo |
| NWP fields, `/storage/nwp/…` | forecast | float32 binary, PNG | yes (binary), not fetched | four cycles a day | unconfirmed |
| Weather observations, `/weather/current` | observed + 12 h forecast | JSON | yes | 2-minute cache | yes — the only documented feed |
| Radar | observed | PNG + JSON index | no (colour bands) | 10 and 60 min; stale on the day | no |
| Dashboard maps (FFGS, JIRCKS, satellite) | forecast / observed | PNG, JPG | no | daily | no |
| Meteograms | forecast | PNG | no | per model cycle | no |
| Historical peaks | observed, top three per site | HTML table | yes | yearly | reference only |
| Annual flood reports 2006–2025 | observed | PDF | unconfirmed | yearly | unconfirmed |
| MAF inflow outlook | forecast, 10 days, two dams | HTML | yes | every ten days | marginal |
| Telemetric station list | reference | JPEG map | no | static | no |

## Unconfirmed

- **Station coordinates.** Known to exist in `/river-state/data`; not retrieved.
  No other page gives them as text.
- **The `X-FW-Token` scheme**: lifetime, binding, and whether a scripted replay works.
  Not tested, by decision.
- **The rate-limit window** behind `x-ratelimit-limit`, and what an exhausted limit
  returns (status code, `Retry-After`).
- **Update cadence during a flood.** Only an end-of-season quiet day was seen.
- **What the site shows outside 15 June – 15 October**: whether the station feed keeps
  updating, and what `/bulletin/bulletin` returns between seasons.
- **What `is_stale: true` looks like**, and how old a reading must be to earn it.
- **Which daily reading the `series` value is**, and whether it is inflow or outflow
  for barrages (Sukkur's last value equals its outflow).
- **How far back any machine-readable record goes.** The station feed gives 31 days.
  The map page's metadata says 2020 onwards but no public endpoint for older readings
  was found. Whether `/flood-assistant/station/{id}` accepts a date or range parameter
  was not probed.
- **Whether the 2024–2025 archive PDFs' tables extract cleanly**, and the contents of
  the annual flood reports.
- **Contents of the disallowed and login-only areas**: Flood Watch, hydro-dashboard,
  inundation, the staff discharge report.
- **Whether the raw `.f32` grids and PNG layers are fetchable** and laid out as the
  manifest's byte counts imply.
- **Behaviour from a non-Pakistani or cloud IP address.**
- **Any licence terms beyond what is quoted here.** No terms page was found; that is
  not proof none exists, and a written answer from FFD would settle it.
- The roster was read in full, but only 7 of 131 station records were fetched. Claims
  about "stations" in general rest on those seven.

## Implications for issue #18

Facts and trade-offs only; the choice is the owner's.

**What each source is.** Open-Meteo Flood is a *model* (GloFAS) of discharge at any
river cell, as a daily series from 1984 to months ahead. FFD is *observation* at named
structures, with the national authority's own classification and a one-day forecast.
They answer different questions: "what does a model expect at this point over the next
week" against "what is the river doing now and what does the forecaster expect
tomorrow".

**Coverage.**

- FFD: 131 gauging sites, densest in Khyber Pakhtunkhwa tributaries and upper Punjab,
  with the Indus main stem to Kotri. Official limits for 35 sites and a quantitative
  forecast for 22. Nothing for Balochistan's rivers or hill torrents as gauged sites,
  and the map legend itself says the data come from WAPDA and the irrigation
  departments' structures. Many of the 155 districts have no FFD site.
- GloFAS: any cell with a modelled river, nationwide, but `docs/sources.md` showed it
  needs a hand-placed point and returns zero or null elsewhere.
- Both need the same artefact that #18 already calls for: a curated, hand-reviewed
  table in `backend/data/source/`. For FFD it would map district → station id(s)
  rather than district → `(lat, lon)`, and without published coordinates the mapping
  would have to be made by name against outside geography, then reviewed.

**Forecast horizon.** FFD: 24 hours, quantitative for 22 sites, issued once daily in
the late morning, flood season only; a weekly outlook exists only as prose. GloFAS via
Open-Meteo: daily values for the whole 7-day `forecast_days` window and beyond. A
hazard that must look several days ahead cannot be driven by FFD's published numbers
alone. A hazard about current state can.

**Thresholds.** `ai.md` leaves riverine-flood thresholds "to calibrate" against a
"recent baseline". FFD's limits are absolute discharges set by the responsible
agency. FFD has five flood levels above normal; the project has three (moderate /
severe / extreme), so a mapping must be chosen, and it is a judgement, not a lookup.
FFD limits are in cusecs at a structure and are not transferable to a GloFAS cell:
GloFAS is in m³/s, is a model with its own bias, and `docs/sources.md` records
3,482 m³/s (about 123,000 cusecs) at Sukkur Barrage on 2026-10-08 where FFD reported
an inflow of 52,850 cusecs a day later. Applying FFD limits to GloFAS values directly
would be comparing unlike quantities.

**Baseline and evaluation history.** GloFAS offers a consistent series from 1984 at
every point, which is what a "relative to baseline" rule and reconstructed evaluation
scenarios need. FFD's machine-readable history found here is 31 days per station, plus
one season of structured bulletins (mid-June 2026 onward) and two seasons of PDFs. A
2025 flood scenario could in principle be rebuilt from the 2025 bulletin PDFs — the
station feed shows Marala's peak of 902,240 cusecs on 27 Aug 2025 — but only by PDF
table extraction, and only with permission to store the result.

**Licence.** Open-Meteo: CC BY 4.0 with a specified attribution link, non-commercial
free tier, documented. FFD: all rights reserved, an explicit no-reproduction notice on
bulletins, no terms page, one endpoint the operator has declared protected against
scraping, and upstream data owned by WAPDA and provincial irrigation departments. The
project stores raw payloads as immutable snapshots and cites them in alerts, which is
storage and redisplay of FFD content. That needs a written yes from FFD; the site's
contact page names data requests as something to ask about.

**Ingestion effort.**

- Client: both are JSON over HTTPS with no key. FFD needs one request per station
  against a 40-request limit of unknown window, so a cycle must restrict itself to
  mapped stations and pace itself; Open-Meteo takes all points in one call.
- Stability: Open-Meteo is a versioned, documented API. The FFD feeds are the private
  back end of a beta chat widget on a site that is visibly being rebuilt; there is no
  contract, and the public pages disagree with each other in places.
- Parsing: FFD needs unit handling (cusecs, thousands, lacs), name reconciliation
  across three spellings, inflow-versus-outflow rules for barrages and dams, and
  handling for empty thresholds and null readings.
- Failure modes: seasonal silence, stale flags, possible Cloudflare challenge from a
  server address, and a 403 on the one endpoint with coordinates.

**Ways the two could be combined**, stated as options rather than a recommendation:

1. GloFAS as the forecast signal as planned, with FFD's observed status at the mapped
   station attached to an alert as corroborating evidence — the role `docs/sources.md`
   gave GDACS.
2. FFD observed status as a second riverine signal for districts that have a mapped
   station, alongside GloFAS.
3. FFD's limits table used only as the reference for choosing severity bands at the
   sites it covers, imported once by hand.
4. FFD not used until permission and coordinates are obtained.

Options 1 to 3 all depend on the licence question; option 3 depends on it least,
because a table of thresholds is reference fact rather than a stored copy of a daily
product, though that too is a judgement the owner should make with FFD's answer in
hand.

## Fixtures

All in `backend/tests/fixtures/ffd/`, raw and unmodified, fetched 2026-10-09:

| File | URL | Fetched (UTC) |
|---|---|---|
| `flood_assistant_rivers.json` | `/flood-assistant/rivers` | 07:51:23 |
| `flood_assistant_station_81_sukkur.json` | `/flood-assistant/station/81?lang=en` | 07:51:39 |
| `flood_assistant_station_86_tarbela.json` | `/flood-assistant/station/86?lang=en` | 07:51:40 |
| `flood_assistant_station_142_besham_telemetry.json` | `/flood-assistant/station/142?lang=en` | 07:55:20 |
| `home_river_status.json` | `/home/river-status` | 07:51:21 |
| `river_state_data_forbidden.json` | `/river-state/data` (no token; HTTP 403) | 07:52:07 |
| `flood_limits.html` | `/flood-limits` | 07:51:25 |
| `weather_model_manifest_icon.json` | `/weather-model/manifest?source=icon` | 07:53:18 |
| `weather_model_point_icon_sukkur.json` | `/weather-model/point?source=icon&cycle=2026100900&lat=27.6750&lon=68.8750` | 07:53:25 |
| `weather_current_lahore.json` | `/weather/current?city=lahore` | 07:55:04 |
| `weather_cities.json` | `/weather/cities` | 07:55:05 |
| `radar_manifest.json` | `/radar/manifest` | 07:54:39 |
| `robots.txt` | `/robots.txt` (served with HTTP 404) | 07:50:48 |

These files are untracked. Given the site's "All rights reserved" footer, decide
whether they may be committed to a public repository before adding them.
`flood_limits.html` contains an anonymous, session-scoped `csrf-token` meta value
from the fetch; it grants nothing but is noted because the file is unmodified. No
bulletin, PDF, image or map page was saved.
