# External sources

Research notes for the four new ingestion sources named in `ai.md` section 5.2:
Open-Meteo Flood, Open-Meteo Air Quality, GDACS and the USGS earthquake feed.

This is the first research note in the repository, so it also sets the convention:
`docs/` holds agent skills under `docs/agents/` and research notes as flat Markdown
files at `docs/`. A note records what a provider's own documentation says, cites the
page that owns each claim, and records what the live API actually returned when it
was called. Blog posts, Stack Overflow answers and wrapper-library READMEs are not
sources.

Everything below was confirmed against provider documentation and against live calls
made on 2026-10-08 from this repository. Fixtures captured during that work live in
`backend/tests/fixtures/` and are raw, unmodified responses.

## Summary of findings against the plan

`ai.md` section 5.2 says of the four sources only that they are keyless, that exact
endpoints and terms are to be confirmed, and that Open-Meteo's free tier is
non-commercial. All four are keyless and all four returned usable data. Three
assumptions in the plan need correcting:

1. **The flood API cannot be driven from district centroids.** GloFAS models river
   cells, and a district centroid is almost never on one. Of the 155 district
   centroids in the registry, one returns `null` and none returns a discharge above
   100 m³/s; 59 return exactly `0.00`. A point on the Indus a few kilometres away
   returns 3,482 m³/s. Ticket #18 needs a curated river point per district, not the
   centroid.
2. **GDACS has no district granularity and no clear licence.** Its unit of data is a
   country-level event with a centroid point; the published terms of use grant no
   rights at all. Usable, but as context rather than as a screening input.
3. **The air-quality forecast is shorter than the project's forecast horizon.** The
   repository's `forecast_days` setting is 7, but CAMS global only reaches about five
   and a half days, so the tail of a seven-day request is `null`. See the review note
   on `feature/air-quality-source` below.

---

## 1. Open-Meteo Flood API

### Endpoint

`https://flood-api.open-meteo.com/v1/flood` — a dedicated hostname, not
`api.open-meteo.com`
([docs](https://open-meteo.com/en/docs/flood-api)). Plain HTTP also answers with
HTTP 200 and no redirect, so always request HTTPS explicitly.

### Parameters

Required: `latitude`, `longitude`. Optional, with defaults as documented
([docs](https://open-meteo.com/en/docs/flood-api)):

| Parameter | Default | Notes |
|---|---|---|
| `daily` | none | comma-separated variable list |
| `forecast_days` | `92` | 0–210 |
| `past_days` | `0` | |
| `start_date` / `end_date` | none | `yyyy-mm-dd` |
| `ensemble` | none | adds the 50 member series |
| `cell_selection` | `nearest` | |
| `timeformat` | `iso8601` | |
| `apikey` | none | commercial tier only |

`timezone` is not listed on the flood documentation page but is accepted and does
change the result; see gotchas.

Daily variables, all in m³/s: `river_discharge`, `river_discharge_mean`,
`river_discharge_median`, `river_discharge_max`, `river_discharge_min`,
`river_discharge_p25`, `river_discharge_p75`
([docs](https://open-meteo.com/en/docs/flood-api)). The model is GloFAS at 0.05°
(about 5 km) for v4, with data from January 1984 and seven months of forecast
([docs](https://open-meteo.com/en/docs/flood-api)).

### Response shape

Identical in structure to the forecast API already in use. One location returns an
object; several return an array of objects in request order, with `location_id`
present from the second element onwards. Captured verbatim in
`backend/tests/fixtures/open_meteo_flood_two_locations.json`:

```json
{"latitude":27.675003,"longitude":68.875015,"generationtime_ms":1.7237663269042969,"utc_offset_seconds":0,
 "timezone":"GMT","timezone_abbreviation":"GMT","elevation":59.0,
 "daily_units":{"time":"iso8601","river_discharge":"m³/s"},
 "daily":{"time":["2026-10-08", "…"],"river_discharge":[3482.37, "…"]}}
```

The returned `latitude`/`longitude` are the snapped grid-cell centre, not the
requested point.

### Multiple locations

**Yes.** The documentation states "Multiple coordinates can be comma separated"
([docs](https://open-meteo.com/en/docs/flood-api)) and no maximum is published. All
155 district coordinates were sent in a single call and 155 objects came back
(HTTP 200, about 62 KB). One call per cycle is enough; the existing
`forecast_batch_size` of 50 is not needed here, though keeping it is harmless.

### Rate limits

Shared across all Open-Meteo hostnames: "Less than 10'000 API calls per day, 5'000
per hour and 600 per minute" ([terms](https://open-meteo.com/en/terms)), and 300,000
calls per month ([pricing](https://open-meteo.com/en/pricing)). Calls are weighted:
requests covering more than 10 variables or more than two weeks for a single location
count as more than one call, computed fractionally
([pricing](https://open-meteo.com/en/pricing)). A seven-day, one-variable,
155-location request stays well inside one call. No rate-limit headers are returned.
Open-Meteo reserves the right to "block applications and IP addresses that misuse our
service without prior notice" ([terms](https://open-meteo.com/en/terms)).

### Terms and licence

Free tier is non-commercial only. Open-Meteo's definition includes "private or
non-profit websites or apps that do not have subscriptions or advertising"; operating
a site with subscriptions or advertisements is commercial
([terms](https://open-meteo.com/en/terms)). A portfolio project with no subscription
and no advertising qualifies.

API data are offered under CC BY 4.0, and the attribution requirement is specific:
"You must include a link next to any location Open-Meteo data are displayed, for
example: `<a href="https://open-meteo.com/">Weather data by Open-Meteo.com</a>`"
([licence](https://open-meteo.com/en/licence)). The frontend must carry that link
wherever flood, air-quality or forecast values are shown.

Upstream, GloFAS is a Copernicus Emergency Management Service product and Open-Meteo
links to a CEMS-FLOODS licence ([licence](https://open-meteo.com/en/licence)). That
link, and the sibling "Licence to use Copernicus Products" link, both return HTTP 404
as of 2026-10-08. The live dataset page is
[cems-glofas-forecast on the Copernicus Early Warning Data Store](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast).
Crediting Copernicus/GloFAS alongside Open-Meteo is the safe course.

### Gotchas

- **Centroids are useless.** Of the 155 district centroids, 1 gives `null`
  (Korangi Creek Cantonment, a sea cell), 59 give exactly `0.00`, 89 give under
  10 m³/s, 6 give 10–100 m³/s and **none** gives 100 m³/s or more. Meanwhile the
  Indus at Sukkur Barrage (27.675, 68.875) gives 3,482 m³/s and the Chenab at Trimmu
  (31.175, 72.075) gives 858 m³/s. Evidence: the centroid case is saved as
  `open_meteo_flood_sukkur_centroid.json`, the river case as
  `open_meteo_flood_two_locations.json`.
- **`null` really occurs**, for cells with no modelled river. The client must accept
  `None` in the `river_discharge` array, not assume floats.
- **Default timezone is GMT and it changes the numbers.** Without `timezone`, days
  are UTC days. For the same point and date, `timezone=Asia/Karachi` returned
  3,563.51 m³/s for 2026-10-08 where the default returned 3,482.37 — the latter is
  the Karachi-time value for the following day. Pass `timezone` explicitly and
  consistently with the forecast client.
- **`forecast_days` defaults to 92.** Always set it.
- `river_discharge_mean`/`_max`/`_min` are returned without `ensemble=true`; the
  flag is only needed for the individual `_memberNN` series.

### Fixtures

- `backend/tests/fixtures/open_meteo_flood_two_locations.json` — Indus at Sukkur
  Barrage and Chenab at Trimmu, `forecast_days=7`, with mean/max/min.
- `backend/tests/fixtures/open_meteo_flood_sukkur_centroid.json` — the Sukkur
  district centroid from the registry, showing an all-zero series. Kept deliberately
  as the evidence behind the centroid finding.

---

## 2. Open-Meteo Air Quality API

### Endpoint

`https://air-quality-api.open-meteo.com/v1/air-quality`
([docs](https://open-meteo.com/en/docs/air-quality-api)). Confirmed live and current.
It is a different hostname from both the forecast API (`api.open-meteo.com`) and the
flood API, as the unmerged `feature/air-quality-source` branch already assumes. The
rate limits are not per-hostname; they are the account-wide limits quoted above
([terms](https://open-meteo.com/en/terms)).

### Parameters

Required: `latitude`, `longitude`. Optional
([docs](https://open-meteo.com/en/docs/air-quality-api)): `hourly`, `current`,
`domains` (`auto`, `cams_europe`, `cams_global`; default `auto`), `forecast_days`
(0–7, default 5), `past_days` (0–92), `forecast_hours`, `past_hours`, `start_date`,
`end_date`, `start_hour`, `end_hour`, `timezone` (default GMT), `cell_selection`
(default `land`), `timeformat`, `apikey`.

Variables used by this project: `pm2_5` and `pm10` in μg/m³, `european_aqi` in
`EAQI`, `us_aqi` in `USAQI`. Global coverage comes from CAMS global at 0.4° (about
45 km) and three-hourly steps, available from August 2022; the 0.11° European domain
does not cover Pakistan ([docs](https://open-meteo.com/en/docs/air-quality-api)).

### Response shape

Captured verbatim in `backend/tests/fixtures/open_meteo_air_quality_lahore.json`:

```json
{"latitude":31.5,"longitude":74.40001,"generationtime_ms":0.3604888916015625,"utc_offset_seconds":18000,
 "timezone":"Asia/Karachi","timezone_abbreviation":"GMT+5","elevation":219.0,
 "hourly_units":{"time":"iso8601","pm2_5":"μg/m³","pm10":"μg/m³",
                 "european_aqi":"EAQI","us_aqi":"USAQI"},
 "hourly":{"time":["2026-10-08T00:00", "…"],"pm2_5":[72.9, "…"]}}
```

`current` is also supported and returns a flat object with `time`, `interval` and one
key per requested variable.

### Multiple locations

**Yes**, same comma-separated form, documented on the page
([docs](https://open-meteo.com/en/docs/air-quality-api)). All 155 district
coordinates in one call returned 155 objects (HTTP 200, about 650 KB). `location_id`
appears from the second element onwards, exactly as in
`open_meteo_forecast_two_locations.json`.

### Rate limits, terms and licence

Identical to the flood API: the same account-wide quota, the same CC BY 4.0 licence
and the same mandatory `Weather data by Open-Meteo.com` link
([terms](https://open-meteo.com/en/terms),
[licence](https://open-meteo.com/en/licence)). Upstream the data are Copernicus
(CAMS); Open-Meteo's own licence page lists "air quality forecasts … from Copernicus
Climate Change Service C3S" ([licence](https://open-meteo.com/en/licence)).

### Gotchas

- **The forecast is shorter than seven days.** With `forecast_days=7` and
  `timezone=Asia/Karachi`, every one of the 155 locations returned 168 hourly values
  of which the last **42 were `null`**: day 7 entirely, and day 6 from 06:00 onwards.
  The last non-null timestamp was `2026-10-13T05:00` on a run made on 2026-10-08.
  With `forecast_days=5`, all 155 locations returned 120 values and zero nulls.
- **The coarse grid merges districts.** The 155 district centroids snap to only 151
  distinct 0.4° cells, so a few neighbouring districts will always carry identical
  PM2.5. Worth saying so in the UI rather than implying independent measurement.
- **The unit string uses U+03BC (`μ`, Greek small letter mu), not U+00B5 (`µ`, micro
  sign).** Any equality check against a hand-typed `µg/m³` will fail.
- Hourly values are interpolated from a three-hourly global model, so consecutive
  hours are smooth and should not be read as hourly observations.
- Returned `latitude`/`longitude` are the snapped cell centre: Lahore's 31.4614,
  74.3552 comes back as 31.5, 74.40001.

### Review note on `feature/air-quality-source`

That branch is unmerged at the time of writing. Its endpoint, variable name and
multi-location handling are all correct. Two findings against it:

1. **Its fixture is not evidence.** `open_meteo_air_quality_two_locations.json` on
   that branch is hand-written: round values, four hourly timestamps, no
   `generationtime_ms`, no `elevation`, no `timezone`, no `location_id`, and the unit
   string typed with U+00B5 rather than the U+03BC the API actually sends. The real
   capture is in this repository at the same path and should win any merge conflict.
2. **The daily mean is unsound at the project's forecast horizon.** The client is
   called with `days` from `settings.forecast_days`, which is 7. Given the 42 trailing
   nulls above, the final day's `pm2_5_mean_ug_m3` becomes `None`, and — more
   seriously — **day 6's mean is computed from only the six hours 00:00–05:00**. In
   smog season those overnight hours carry the day's highest PM2.5, so that partial
   mean is biased high and could trip the 55/150/250 µg/m³ thresholds and issue a
   false alert. The fix is to request at most `forecast_days=5` for air quality, or to
   discard any day with fewer than a full set of hours. The existing `parse_daily`
   already tolerates `None` values, so only the horizon and the partial-day rule need
   changing.

### Fixtures

- `backend/tests/fixtures/open_meteo_air_quality_lahore.json` — Lahore district
  centroid from the registry, `forecast_days=5`, `pm2_5`, `pm10`, `european_aqi`,
  `us_aqi`.
- `backend/tests/fixtures/open_meteo_air_quality_two_locations.json` — Lahore plus
  the Karachi coordinates used by the existing forecast fixture. This path collides
  with the hand-written file on `feature/air-quality-source`; keep this one.

---

## 3. USGS earthquake feed

### Endpoint

`https://earthquake.usgs.gov/fdsnws/event/1/query` with `format=geojson`
([API documentation](https://earthquake.usgs.gov/fdsnws/event/1/)). A
`/fdsnws/event/1/count` endpoint with the same filters returns a bare integer and is
useful for bounding a query before running it. The pre-baked summary feeds under
`https://earthquake.usgs.gov/earthquakes/feed/v1.0/` are global and are "updated every
minute" ([feed documentation](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php));
they are not filterable, so the query service is the right choice here.

### Parameters

All optional ([API documentation](https://earthquake.usgs.gov/fdsnws/event/1/)):

| Group | Parameters | Notes |
|---|---|---|
| Format | `format` | `geojson`, `csv`, `kml`, `quakeml` (default), `text`, `xml` |
| Rectangle | `minlatitude`, `maxlatitude`, `minlongitude`, `maxlongitude` | ±90, ±360 |
| Circle | `latitude`, `longitude`, `maxradius` (0–180°), `maxradiuskm` (0–20,001.6) | |
| Time | `starttime` (default now − 30 days), `endtime` (default now), `updatedafter` | ISO 8601; "Unless a timezone is specified, UTC is assumed" |
| Magnitude | `minmagnitude`, `maxmagnitude` | |
| Results | `limit` (1–20,000), `offset` (default 1), `orderby` (`time`, `time-asc`, `magnitude`, `magnitude-asc`), `eventtype` | maximum 20,000 events per query |

### Response shape

A GeoJSON `FeatureCollection` with a `metadata` block. Captured verbatim in
`backend/tests/fixtures/usgs_earthquakes_pakistan.json`:

```json
{"type":"FeatureCollection",
 "metadata":{"generated":1791475334000,"url":"…","title":"USGS Earthquakes",
             "status":200,"api":"2.7.0","count":18},
 "features":[{"type":"Feature",
   "properties":{"mag":4.3,"place":"17 km WNW of Ashkāsham, Afghanistan",
                 "time":1791236313955,"updated":1791254347040,"tz":null,
                 "url":"…","detail":"…","felt":null,"cdi":null,"mmi":null,"alert":null,
                 "status":"reviewed","tsunami":0,"sig":284,"net":"us","code":"6000tzsr",
                 "ids":",us6000tzsr,","sources":",us,","types":",origin,phase-data,",
                 "nst":25,"dmin":1.83,"rms":0.68,"gap":136,"magType":"mb",
                 "type":"earthquake","title":"M 4.3 - 17 km WNW of Ashkāsham, Afghanistan"},
   "geometry":{"type":"Point","coordinates":[71.3436,36.7206,203.432]},
   "id":"us6000tzsr"}]}
```

The fields this project needs: `id` (stable event identifier), `properties.mag` and
`magType`, `properties.time` and `updated` as **milliseconds since the Unix epoch in
UTC** (verified: `1791236313955` is `2026-10-05T21:38:33.955Z`), `properties.place`,
`properties.status` (`automatic` or `reviewed`), `properties.tsunami`,
`properties.sig`, and `geometry.coordinates` as
`[longitude, latitude, depth in kilometres]`
([feed documentation](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)).

### Multiple locations

**Not applicable, and better than batching.** This is not a per-point service: one
bounding-box or radius query returns every event in the area, so a single call covers
all 155 districts. Mapping an event to districts is then a geometric join done
locally, not an API concern.

### Rate limits

None published. The service sets `Cache-Control: public, max-age=60` and is fronted
by CloudFront, so polling faster than once a minute buys nothing; the summary feeds
are likewise regenerated every minute
([feed documentation](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php)).
The hard constraint is the 20,000-event cap
([API documentation](https://earthquake.usgs.gov/fdsnws/event/1/)).

### Terms and licence

USGS-authored data are in the US public domain and may be used without restriction;
the agency asks that proper credit be given, with a credit line such as
"U.S. Geological Survey"
([Copyrights and Credits](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits),
[Acknowledging or Crediting USGS](https://www.usgs.gov/information-policies-and-instructions/acknowledging-or-crediting-usgs)).
Commercial and non-commercial use are equally permitted. Note that both of those
policy pages return HTTP 403 to automated fetchers and are rendered client-side, so
the wording above was read from the pages' indexed text rather than fetched directly;
re-read them in a browser before quoting them in product copy.

### Gotchas

- **An over-broad query fails with HTTP 503 and a plain-text database error**, not a
  clean 4xx. A query for all events since 2020 with no magnitude floor returned
  `Error 503: Service Unavailable … The table '…' is full`. Always bound the query by
  time, area and magnitude, and treat a non-JSON body as a source error.
- **No results is a clean HTTP 200** with `"count":0` and `"features":[]`.
- **Most events in a Pakistan bounding box are not in Pakistan.** The captured
  30-day, M4+ query over 23.5–37.5 N, 60.5–77.5 E returned 18 events: 14 Afghanistan,
  2 Tajikistan, 2 Pakistan. The Hindu Kush dominates the catalogue. District
  assignment must be geometric and should allow a distant event to affect Pakistani
  districts, rather than filtering on the country name in `place`.
- **Nulls are the norm on the impact fields.** Across those 18 events, `tz`, `mmi`
  and `alert` were null in all 18, `felt` and `cdi` in 16. `alert` (the PAGER colour)
  is only populated for significant events, so it cannot be relied on as a severity
  input.
- `place` contains non-ASCII characters, delivered as `\uXXXX` escapes in UTF-8.
- `ids`, `sources` and `types` are comma-delimited strings wrapped in leading and
  trailing commas, not arrays.
- Events are revised: `status` moves from `automatic` to `reviewed` and `mag` can
  change, so `updated` matters and re-ingesting the same `id` must update rather than
  duplicate.

### Fixture

`backend/tests/fixtures/usgs_earthquakes_pakistan.json` — 18 events, M4+, 2026-09-08
to 2026-10-08, bounding box 23.5–37.5 N by 60.5–77.5 E, ordered by time. Saved
exactly as returned; USGS emits one feature per line, which is why this fixture is
the only multi-line one.

---

## 4. GDACS

### Endpoint

GDACS publishes an OpenAPI description at
`https://www.gdacs.org/gdacsapi/swagger/v1/swagger.json`, rendered at
[swagger/index.html](https://www.gdacs.org/gdacsapi/swagger/index.html), and a
two-page quick start,
[GDACS_API_quickstart_v2.pdf](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf).
Three event-list endpoints matter:

| Endpoint | Purpose |
|---|---|
| `/gdacsapi/api/events/geteventlist/SEARCH` | filtered search by type, alert level, date, country |
| `/gdacsapi/api/events/geteventlist/EVENTS4APP` | current events, no parameters |
| `/gdacsapi/api/events/geteventlist/eventsbyarea` | events intersecting a WKT polygon |

Supporting endpoints: `/gdacsapi/api/events/geteventdata` (one event in detail) and
`/gdacsapi/api/polygons/getgeometry` (an event's polygons).

### Parameters

From the OpenAPI document, `SEARCH` takes `eventlist`, `alertlevel`, `fromDate`,
`toDate`, `country`, `severity`, `pageSize`, `pageNumber`, `caller` — all optional.
The quick start writes the same names in lower case (`fromdate`, `pagenumber`); ASP.NET
binds query names case-insensitively and both forms work. `eventsbyarea` takes
`geometryArea` and `days`. `getgeometry` takes `eventtype`, `eventid`, `episodeid`,
`polygontype`, `source`, `showPreliminary`, `showBaseGeometry`.

Event-type codes are `EQ`, `TC`, `FL`, `DR`, `VO`, `WF`, semicolon-separated.
Alert levels are `Green`, `Orange`, `Red`, also semicolon-separated.

### Response shape

A GeoJSON `FeatureCollection` whose properties are GDACS-specific. From
`backend/tests/fixtures/gdacs_events_pakistan.json`:

```json
{"type":"Feature","bbox":[71.0216,36.611,71.0216,36.611],
 "geometry":{"type":"Point","coordinates":[71.0216,36.611]},
 "properties":{"eventtype":"EQ","eventid":1569499,"episodeid":1737725,"eventname":"",
   "glide":"","name":"Earthquake in Afghanistan","description":"…","htmldescription":"…",
   "icon":"…","iconoverall":"…",
   "url":{"geometry":"…","report":"…","details":"…"},
   "alertlevel":"Green","alertscore":1,"episodealertlevel":"Green","episodealertscore":0.0,
   "istemporary":"false","iscurrent":"true","country":"Afghanistan",
   "fromdate":"2026-10-04T20:27:25","todate":"2026-10-04T20:27:25",
   "datemodified":"2026-10-04T21:07:42","iso3":"AFG","source":"NEIC","sourceid":"",
   "polygonlabel":"Centroid","Class":"Point_Centroid",
   "affectedcountries":[{"iso2":"AF","iso3":"AFG","countryname":"Afghanistan"}],
   "severitydata":{"severity":4.8,"severitytext":"Magnitude 4.8M, Depth:248.906km",
                   "severityunit":"M"}}}
```

The fields worth storing: `eventtype`, `eventid` + `episodeid` (the pair identifies a
revision), `alertlevel`, `alertscore`, `country`, `iso3`, `affectedcountries`,
`fromdate`/`todate`/`datemodified`, `severitydata`, and `url.report` as a citation
link.

### Multiple locations

**Not applicable; one spatial call covers the country.** `eventsbyarea` accepts a WKT
polygon and returns every event intersecting it, so a single call with a Pakistan
bounding polygon serves all 155 districts. The call used for the fixture was
`geometryArea=POLYGON((60.5 23.5,77.5 23.5,77.5 37.5,60.5 37.5,60.5 23.5))&days=30`.
A `bbox=` style string is rejected with HTTP 500; WKT is required. `SEARCH` can filter
by `country` instead, but see gotchas.

Per-district resolution is not available from GDACS at all. `getgeometry` returns the
polygons behind an event, but for the August 2025 Pakistan flood those polygons —
labelled `Affected area` and `Global area` — are a pair of rings about 0.0005° across
near 71.48 E, 34.00 N, not a flood footprint. GDACS geometry cannot be intersected
with districts to any useful effect.

### Rate limits

None published anywhere in the quick start, the OpenAPI document or the terms of use.
The quick start's only guidance is to cache: "We suggest checking the methods that
return a collection, considering the cache stored by GDACS any time there is a new
update … The user may save a collection and then (programmatically) check for updates,
e.g. by comparing the `datetime` property, before calling the GDACS API again"
([quick start](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf)). One
call per monitoring cycle is clearly within the spirit of that.

### Terms and licence

**Unclear, and this should be stated plainly rather than assumed.** The GDACS terms of
use
([GDACS_Terms_of_use_Mar_25.pdf](https://www.gdacs.org/documents/2025/GDACS_Terms_of_use_Mar_25.pdf),
linked from [About/termofuse.aspx](https://www.gdacs.org/About/termofuse.aspx))
contains eight numbered clauses and **no copyright statement and no licence grant at
all**. It is entirely disclaimer: the data are provided "as is" without warranty of
any kind; "GDACS services are not meant to substitute nor to override any official
information or alert message from local or national disaster management authorities";
and the stakeholders "DO NOT ASSUME ANY RESPONSIBILITY OR LIABILITY WHATSOEVER WITH
REGARD TO THE INFORMATION PROVIDED BY GDACS".

Three other statements are the only positive permissions on record:

- The quick start says "GDACS data are free and available through its APIs" and "We
  only request to acknowledge the source as 'Global Disaster Awareness and
  Coordination System, GDACS'"
  ([quick start](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf)).
- The RSS feed declares `<copyright>public domain</copyright>` in its channel element
  ([rss.xml](https://www.gdacs.org/xml/rss.xml)).
- gdacs.org's footer points at the European Commission legal notice, under which
  EU-owned content is reusable under CC BY 4.0 pursuant to the Commission Decision of
  12 December 2011 on the reuse of Commission documents, provided "appropriate credit
  is given and changes are indicated"
  ([EC legal notice](https://commission.europa.eu/legal-notice_en)). That notice
  explicitly does not cover third-party works, and GDACS aggregates third-party data
  (NOAA, NEIC and others appear in the `source` field).

**Assessment.** Non-commercial portfolio use with visible attribution to "Global
Disaster Awareness and Coordination System, GDACS" is well within the only stated
request. There is no explicit grant for redistribution, so GDACS content should be
displayed with attribution and a link back to `url.report`, and should not be
republished as a bulk dataset.

### Gotchas

- **`SEARCH` silently hides Green events by default.** The same date window returned
  43 events with no `alertlevel` (35 Orange, 8 Red) and 100 with
  `alertlevel=Green;Orange;Red`. Always pass `alertlevel` explicitly.
- **100 records per page, silently truncated.** "Currently, the API provides no more
  than 100 records at once, ordered by date"; use `pagenumber` and `pagesize`
  ([quick start](https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf)).
  A response of exactly 100 features means there is more.
- **Empty results are not an empty FeatureCollection.** `SEARCH` with
  `country=Pakistan` over July–October 2026 returned **HTTP 204 with no body**, and
  `eventsbyarea` with `days=1` returned **HTTP 404**. A client that treats any
  non-200 as an error will fail on the common case of nothing happening. Both must be
  mapped to "no events".
- **`country` takes English names, not ISO codes.** `country=Pakistan` works;
  `country=PAK` returns 204. Unrecognised parameters such as `iso3` or `bbox` are
  silently ignored and the response comes back unfiltered, which is easy to mistake
  for a working filter.
- **One property is capitalised**: `Class`, among otherwise all-lowercase keys.
- **Dates are naive local-looking ISO strings** (`2026-10-04T20:27:25`) with no
  offset. GDACS works in UTC; treat them as UTC explicitly.
- **`istemporary` and `iscurrent` are the strings `"true"`/`"false"`**, not booleans.
- **Coverage over Pakistan is sparse.** There were no GDACS events for Pakistan at all
  between July and October 2026. Over a longer window: two Orange floods in 2025, one
  Orange cyclone (ASNA-24) in 2024, one Red flood in 2022. GDACS fires a handful of
  times a year, so a cycle that depends on it will almost always see nothing.
- The `events4app` endpoint takes no parameters and returns current global events
  (89 on 2026-10-08) — simple, but it must be filtered client-side.

### Fixture

`backend/tests/fixtures/gdacs_events_pakistan.json` — `eventsbyarea` with the
Pakistan bounding polygon and `days=30`, returning 7 events (one M4.5 earthquake in
Pakistan, four in Afghanistan and Tajikistan, one flood in India). Saved exactly as
returned, untrimmed.

Note that this window contains no GDACS event whose `country` is Pakistan other than
the earthquake. A fixture covering a Pakistan flood would need
`SEARCH?fromDate=2025-01-01&toDate=2026-10-08&country=Pakistan`, which returns the two
Orange floods of 2025.

---

## Summary table

| Source | Multi-location in one call | Rate limit | Licence | Suitable as-is |
|---|---|---|---|---|
| Open-Meteo Flood | Yes — 155 coordinates verified in one call | 600/min, 5,000/hour, <10,000/day, 300,000/month, shared across Open-Meteo hosts | CC BY 4.0, mandatory `Weather data by Open-Meteo.com` link; non-commercial tier; GloFAS upstream is Copernicus | Endpoint yes, **inputs no** — district centroids return zero or null, so curated river points are required |
| Open-Meteo Air Quality | Yes — 155 coordinates verified in one call | same shared Open-Meteo quota | same as above; CAMS upstream | Yes, with `forecast_days` capped at 5 |
| GDACS | Not per-point; one WKT polygon query covers the country | none published; quick start asks for caching | **No licence grant published**; only a request to acknowledge "GDACS"; RSS declares public domain; EC legal notice implies CC BY 4.0 for EU-owned content | Usable as context only — country-level granularity, sparse coverage, unclear licence |
| USGS earthquakes | Not per-point; one bounding-box query covers the country | none published; 60-second cache, 20,000-event cap | US public domain, credit requested | Yes |

## Recommendations for the implementation tickets

**#18, flood.** Do not call the flood API with district centroids. The ticket needs a
curated table of river points: for each district that sits on a modelled river, one
`(lat, lon)` on the GloFAS channel, stored next to the district registry in
`backend/data/source/` and built into the generated registry the same way district
geometry is. Districts with no river point simply have no riverine-flood signal, which
is honest — Khuzdar has no Indus. Verify each candidate point returns a plausible
discharge before committing it. The client must accept `None` values, must pass
`timezone` explicitly, and must set `forecast_days`.

**#17, air quality.** Cap the air-quality request at `forecast_days=5` rather than
reusing `settings.forecast_days`, and drop any day whose hourly series is incomplete
before computing a daily mean. Compare the `feature/air-quality-source` branch against
the captured fixture before landing it; its own fixture is fabricated and its
seven-day horizon produces a biased partial-day mean.

**#19, events.** USGS and GDACS are different shapes from the Open-Meteo sources: one
call returns a list of events for the whole country, not a per-district series. The
schema should reflect that — an events table keyed by provider event id, with the
district association derived geometrically, rather than forcing events into the
per-district snapshot shape. Handle USGS revisions via `updated` and the stable `id`.
Handle GDACS's HTTP 204 and 404 as "no events" rather than as source failures, pass
`alertlevel` explicitly, and page past 100 records. Treat GDACS as corroborating
context attached to an alert, not as a screening threshold, because it has no
district granularity and fires only a few times a year over Pakistan.

**Attribution.** The frontend must carry a `Weather data by Open-Meteo.com` link
wherever Open-Meteo values appear, credit "U.S. Geological Survey" for earthquakes and
"Global Disaster Awareness and Coordination System, GDACS" for GDACS events, and
credit Copernicus for the GloFAS and CAMS products underneath Open-Meteo.
