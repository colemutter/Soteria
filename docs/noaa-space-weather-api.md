# NOAA SWPC Space Weather Products API Guide

This guide explains how to get, classify, understand, and use the NOAA Space
Weather Prediction Center (SWPC) product data service at:

https://services.swpc.noaa.gov/products/

The short version: SWPC exposes operational products as static JSON files under
browsable directory trees. There is no request body, API key, or query
language. Use `/products/` as the API reference and product layer for official
summaries, alerts, scales, and chart-ready feeds. Use `/json/` when you need
lower-level measurement feeds such as GOES X-rays, GOES protons, RTSW magnetic
field/plasma, active regions, and aurora grids.

## Evidence Check

| Claim | Verdict | Evidence | Confidence |
| --- | --- | --- | --- |
| SWPC product data can be fetched directly from public HTTPS endpoints. | Supported | The `/products/` directory lists product files and subdirectories, and representative files returned `Content-Type: application/json`. | High |
| NOAA G, S, and R scales can be read from SWPC products or reproduced from a small set of product measurements. | Supported with caveats | `/products/noaa-scales.json` exposes compact current/recent/forecast G/R/S status and probabilities. NOAA also publishes physical-measure thresholds for geomagnetic storms, solar radiation storms, and radio blackouts. Reproduction is straightforward for threshold classification, but official warnings and alerts can include forecaster judgment, persistence rules, and event definitions. | High |
| The feed is suitable for near-real-time monitoring. | Plausible but operationally bounded | Product pages and headers indicate minute-scale updates for major observations, but the JSON files should be treated as operational rolling products, not a guaranteed archive or SLA-backed API. | Medium |
| Raw measurements alone predict user impact exactly. | Contradicted | SWPC explains that impacts depend on daylight side, latitude, infrastructure, local geology, spacecraft conditions, GNSS/radio context, and model assumptions. | High |

## API Shape

Product reference root:

```text
https://services.swpc.noaa.gov/products/
```

Lower-level measurement root:

```text
https://services.swpc.noaa.gov/json/
```

Behavior observed on June 20, 2026:

- Public HTTPS GET access.
- Directory indexes are browsable HTML pages.
- JSON product files return `application/json`.
- The `/products/` directory itself returns HTML, not JSON.
- Representative files returned `Cache-Control: max-age=60`, `ETag`,
  `Last-Modified`, and `Access-Control-Allow-Origin: *`.
- Most high-cadence product files are rolling windows, not permanent archives.
- Some product files are arrays of objects; others are objects keyed by day or
  scale offset; some chart feeds are arrays whose first row is a header list.
- Timestamps are effectively UTC, but not every field includes a trailing `Z`.

Use conditional requests and respect the one-minute cache window:

```ts
const SWPC_ORIGIN = "https://services.swpc.noaa.gov";

type CachedResponse<T> = {
  status: "fresh" | "unchanged";
  data?: T;
  etag?: string;
  lastModified?: string;
};

export async function fetchSwpcJson<T>(
  path: string,
  cache?: { etag?: string; lastModified?: string },
): Promise<CachedResponse<T>> {
  const headers: Record<string, string> = {};
  if (cache?.etag) headers["If-None-Match"] = cache.etag;
  if (cache?.lastModified) headers["If-Modified-Since"] = cache.lastModified;

  const response = await fetch(`${SWPC_ORIGIN}/${path.replace(/^\/+/, "")}`, {
    headers,
  });

  if (response.status === 304) {
    return { status: "unchanged", etag: cache?.etag, lastModified: cache?.lastModified };
  }

  if (!response.ok) {
    throw new Error(`SWPC ${response.status} for ${path}`);
  }

  return {
    status: "fresh",
    data: await response.json() as T,
    etag: response.headers.get("etag") ?? undefined,
    lastModified: response.headers.get("last-modified") ?? undefined,
  };
}
```

## Product And Measurement Families

Use the directory index as the source of truth because files can change over
time. The important families are:

| Family | Examples | What it is useful for |
| --- | --- | --- |
| `/products/` current scales and alerts | `noaa-scales.json`, `alerts.json`, `noaa-planetary-k-index.json`, `noaa-planetary-k-index-forecast.json`, `10cm-flux-30-day.json`, `kyoto-dst.json` | Compact official scale status, watches/warnings/alerts, Kp history/forecast, F10.7 context, and Dst. |
| `/products/summary/` | `10cm-flux.json`, `solar-wind-mag-field.json`, `solar-wind-speed.json` | Single-latest-value dashboard cards. |
| `/products/solar-wind/` | `mag-2-hour.json`, `mag-6-hour.json`, `mag-7-day.json`, `plasma-2-hour.json`, `plasma-7-day.json`, `ephemerides.json` | Chart-ready magnetic-field and plasma windows. These are often header-row arrays. |
| `/products/geospace/` | `propagated-solar-wind.json`, `propagated-solar-wind-1-hour.json` | Solar wind propagated toward Earth for geospace products. |
| `/products/flares/` | `suvi-primary-131-hgs-grid.json`, `suvi-primary-094-hgs-grid.json` | Lists of SUVI flare imagery URLs in several coordinate/grid products. |
| `/products/glotec/` | `geojson_2d_urt.json` | Global total electron content product manifests. |
| `/products/ccor1/` and `/products/ccor2/` | `fits.json`, `jpegs.json` | Coronagraph file manifests where available. |
| `/json/` root products | `planetary_k_index_1m.json`, `boulder_k_index_1m.json`, `solar_regions.json`, `solar_probabilities.json`, `ovation_aurora_latest.json`, `45-day-forecast.json` | Current geomagnetic estimates, active solar regions, flare probabilities, aurora grid, and forecast products. |
| `/json/goes/` primary/secondary | `goes/primary/xrays-6-hour.json`, `goes/primary/integral-protons-6-hour.json`, `goes/primary/magnetometers-1-day.json` | Solar X-rays, energetic particles, magnetometers, EUV, SUVI flare detections, and satellite environment products. |
| `/json/rtsw/` | `rtsw/rtsw_mag_1m.json`, `rtsw/rtsw_wind_1m.json`, `rtsw/rtsw_ephemerides_1h.json` | Active real-time solar wind magnetic field and plasma from the upstream spacecraft. |

## Representative Schemas

These examples are intentionally schema-level, not fixed contracts. Always
validate the fields you use and store the raw record for audit.

| Endpoint | Shape | Important fields |
| --- | --- | --- |
| `/products/noaa-scales.json` | Object keyed by offsets such as `-1`, `0`, `1`, `2`, `3` | `DateStamp`, `TimeStamp`, `R`, `S`, `G`, scale text, forecast probabilities |
| `/products/alerts.json` | Array of official messages | `product_id`, `issue_datetime`, `message` |
| `/products/noaa-planetary-k-index.json` | Array of 3-hour records | `time_tag`, `Kp`, `a_running`, `station_count` |
| `/products/noaa-planetary-k-index-forecast.json` | Array of observed and forecast records | `time_tag`, `kp`, `observed`, `noaa_scale` |
| `/products/summary/solar-wind-mag-field.json` | Single-record array | `time_tag`, `bt`, `bz_gsm` |
| `/products/summary/solar-wind-speed.json` | Single-record array | `time_tag`, `proton_speed` |
| `/products/solar-wind/mag-2-hour.json` | Header-row array followed by rows | Header row: `time_tag`, `bx_gsm`, `by_gsm`, `bz_gsm`, `lon_gsm`, `lat_gsm`, `bt` |
| `/products/solar-wind/plasma-2-hour.json` | Header-row array followed by rows | Header row: `time_tag`, `density`, `speed`, `temperature` |
| `/json/planetary_k_index_1m.json` | Array of current-day records | `time_tag`, `kp_index`, `estimated_kp`, `kp` |
| `/json/goes/primary/xrays-6-hour.json` | Array of 1-minute X-ray records | `time_tag`, `satellite`, `flux`, `observed_flux`, `electron_correction`, `electron_contaminaton`, `energy` |
| `/json/goes/primary/integral-protons-6-hour.json` | Array of energetic-particle records | `time_tag`, `satellite`, `flux`, `energy` |
| `/json/rtsw/rtsw_mag_1m.json` | Array of magnetic-field records | `time_tag`, `active`, `source`, `bt`, `bx_gsm`, `by_gsm`, `bz_gsm`, `overall_quality` |
| `/json/rtsw/rtsw_wind_1m.json` | Array of solar-wind plasma records | `time_tag`, `active`, `source`, `proton_speed`, `proton_density`, `proton_temperature`, quality flags |
| `/json/solar_regions.json` | Array of active-region summaries | `observed_date`, `region`, `location`, `area`, `spot_class`, `mag_class`, flare counts, flare probabilities |
| `/json/ovation_aurora_latest.json` | Object with coordinate grid | `Observation Time`, `Forecast Time`, `Data Format`, `coordinates` |

Implementation notes:

- Do not assume records are sorted newest-first. Some files are ascending and
  some are descending. Sort by parsed timestamp.
- Detect header-row arrays in `/products/solar-wind/` before mapping records.
- Normalize timestamps as UTC. If a timestamp has no `Z`, append `Z` only after
  confirming it is an SWPC UTC field.
- Expect nulls and missing values during outages, calibrations, eclipses, or
  instrument issues.
- Preserve `source`, `active`, quality flags, and satellite IDs. They explain
  why a value might change or be suspect.
- The X-ray field is misspelled as `electron_contaminaton` in the observed JSON;
  use the API spelling when parsing.

## NOAA Scale Classification

NOAA's public space-weather scales communicate three event types:

- `G`: geomagnetic storms, based on Kp.
- `S`: solar radiation storms, based on >=10 MeV proton flux.
- `R`: radio blackouts, based on GOES 0.1-0.8 nm X-ray flux.

For an app that wants the official current/recent/forecast scale summary, start
with `/products/noaa-scales.json`. For an app that needs to explain, replay, or
pre-alert on the underlying measurements, compute the same scale classes from
the lower-level feeds below and label them as derived.

### G Scale: Geomagnetic Storms

Use `/products/noaa-planetary-k-index.json` for the 3-hour observed product,
`/products/noaa-planetary-k-index-forecast.json` for observed and forecast
charting, or `/json/planetary_k_index_1m.json` for a near-real-time Kp estimate.

| NOAA scale | Physical measure |
| --- | --- |
| None | Kp < 5 |
| G1 Minor | Kp = 5 |
| G2 Moderate | Kp = 6 |
| G3 Strong | Kp = 7 |
| G4 Severe | Kp = 8, including 9- |
| G5 Extreme | Kp = 9o |

The one-minute file is best treated as a nowcast of the current 3-hour Kp
interval. For product decisions, show "estimated" when using `estimated_kp`.
Prefer `estimated_kp` for classification when available. A rounded integer can
hide the G4/G5 edge case because NOAA treats Kp 9- as G4 and Kp 9o as G5.

### S Scale: Solar Radiation Storms

Use `/json/goes/primary/integral-protons-*.json`, filter to
`energy === ">=10 MeV"`, and classify the latest flux in pfu. Use
`/products/alerts.json` and `/products/noaa-scales.json` when you want official
SWPC event messages or current scale summaries.

| NOAA scale | >=10 MeV proton flux |
| --- | --- |
| None | < 10 pfu |
| S1 Minor | >= 10 pfu |
| S2 Moderate | >= 100 pfu |
| S3 Strong | >= 1,000 pfu |
| S4 Severe | >= 10,000 pfu |
| S5 Extreme | >= 100,000 pfu |

SWPC warnings, alerts, and summaries include event logic beyond a single raw
point, including onset, persistence, threshold crossings, and post-event
confirmation. Use the raw threshold for monitoring, not as a replacement for
official alert products.

### R Scale: Radio Blackouts

Use `/json/goes/primary/xrays-*.json`, filter to `energy === "0.1-0.8nm"`, and
classify the corrected `flux` in W/m^2. Use `/products/alerts.json` and
`/products/noaa-scales.json` when you want official SWPC event messages or
current scale summaries.

| NOAA scale | GOES X-ray class | 0.1-0.8 nm flux |
| --- | --- | --- |
| None | below M1 | < 1e-5 W/m^2 |
| R1 Minor | M1 | >= 1e-5 W/m^2 |
| R2 Moderate | M5 | >= 5e-5 W/m^2 |
| R3 Strong | X1 | >= 1e-4 W/m^2 |
| R4 Severe | X10 | >= 1e-3 W/m^2 |
| R5 Extreme | X20 | >= 2e-3 W/m^2 |

X-ray impacts are prompt but mostly affect the sunlit side of Earth. A raw R
classification should be paired with local daylight and affected-service logic.

### Classification Helpers

```ts
export function classifyG(kp: number | null | undefined) {
  if (kp == null || !Number.isFinite(kp)) return null;
  // Pass estimated_kp when available; rounded kp_index can blur 9- vs 9o.
  if (kp >= 9) return "G5";
  if (kp >= 8) return "G4";
  if (kp >= 7) return "G3";
  if (kp >= 6) return "G2";
  if (kp >= 5) return "G1";
  return null;
}

export function classifyS(protonFluxPfu: number | null | undefined) {
  if (protonFluxPfu == null || !Number.isFinite(protonFluxPfu)) return null;
  if (protonFluxPfu >= 100000) return "S5";
  if (protonFluxPfu >= 10000) return "S4";
  if (protonFluxPfu >= 1000) return "S3";
  if (protonFluxPfu >= 100) return "S2";
  if (protonFluxPfu >= 10) return "S1";
  return null;
}

export function classifyR(xrayFluxWm2: number | null | undefined) {
  if (xrayFluxWm2 == null || !Number.isFinite(xrayFluxWm2)) return null;
  if (xrayFluxWm2 >= 2e-3) return "R5";
  if (xrayFluxWm2 >= 1e-3) return "R4";
  if (xrayFluxWm2 >= 1e-4) return "R3";
  if (xrayFluxWm2 >= 5e-5) return "R2";
  if (xrayFluxWm2 >= 1e-5) return "R1";
  return null;
}
```

## How To Understand The Measurements

Think in terms of propagation speed and affected system:

| Signal | Feed | Lead time / timing | What it tells you |
| --- | --- | --- | --- |
| Solar X-rays | GOES XRS | Arrives at Earth in minutes, essentially immediate for operations | Solar flares and potential radio blackouts on the sunlit side. |
| Solar energetic protons | GOES integral protons | Roughly minutes to hours after an initiating event, depending on energy and magnetic connection | Radiation storm risk for spacecraft, polar aviation, and polar HF communication. |
| Solar wind magnetic field and plasma | RTSW / DSCOVR / ACE | L1-to-Earth lead time is often tens of minutes and varies with speed | Geomagnetic-storm drivers: southward `bz_gsm`, high speed, density jumps, shocks, and sustained coupling. |
| Kp | Planetary K-index | 3-hour geomagnetic response, updated/estimated during the interval | Global geomagnetic storm severity and alert/watch context. |
| Aurora grid | OVATION aurora latest | 30 to 90 minute forecast when L1 solar wind is available | Location and intensity of auroral oval, not a guaranteed local viewing forecast. |
| Active regions | Solar region summaries/probabilities | Daily/current solar-disk context | Where flares may originate and near-term C/M/X flare probability. |
| Solar cycle | Solar-cycle products | Monthly to multi-year context | Background activity regime and long-term risk context. |

Useful derived features:

- `bz_gsm < 0` and sustained: stronger magnetic coupling into Earth's
  magnetosphere.
- `bt` high: stronger interplanetary magnetic field magnitude.
- `proton_speed` high: shorter L1 propagation time and often stronger storm
  drivers when paired with southward Bz.
- `proton_density` jump: possible shock or compression region.
- Kp rising to 5 or more: NOAA G-scale storm conditions.
- X-ray `0.1-0.8nm` flux rising through M/X thresholds: NOAA R-scale radio
  blackout conditions.
- >=10 MeV proton flux rising through 10 pfu: NOAA S-scale radiation storm
  conditions.

## Recommended Ingestion Pipeline

1. Poll a small endpoint set every 60 seconds.
2. Use `ETag` or `Last-Modified` to skip unchanged files.
3. Parse into typed raw records and keep the original JSON payload.
4. Normalize timestamps and sort records.
5. Deduplicate by endpoint, timestamp, satellite/source, and measurement
   channel such as `energy`.
6. Validate expected keys and log schema drift.
7. Filter out nulls and flag bad-quality records rather than silently dropping
   whole windows.
8. Compute derived values and NOAA G/R/S classifications.
9. Store both raw observations and derived classifications.
10. Alert only after debouncing and persistence checks appropriate to the use
    case.

Minimal monitoring set:

```text
/products/noaa-scales.json
/products/alerts.json
/products/noaa-planetary-k-index.json
/products/noaa-planetary-k-index-forecast.json
/products/summary/solar-wind-mag-field.json
/products/summary/solar-wind-speed.json
/json/goes/primary/xrays-6-hour.json
/json/goes/primary/integral-protons-6-hour.json
/json/ovation_aurora_latest.json
/json/solar_regions.json
```

Operationally safer set:

```text
/products/noaa-scales.json
/products/alerts.json
/products/noaa-planetary-k-index.json
/products/noaa-planetary-k-index-forecast.json
/products/solar-wind/mag-2-hour.json
/products/solar-wind/plasma-2-hour.json
/json/goes/instrument-sources.json
/json/goes/satellite-longitudes.json
/json/goes/primary/xrays-6-hour.json
/json/goes/secondary/xrays-6-hour.json
/json/goes/primary/integral-protons-6-hour.json
/json/goes/secondary/integral-protons-6-hour.json
/json/rtsw/rtsw_mag_1m.json
/json/rtsw/rtsw_wind_1m.json
/json/planetary_k_index_1m.json
```

Use secondary GOES feeds as context or fallback, but label them clearly. Do not
mix primary and secondary observations without preserving the satellite/source.

## Product Design Guidance

Good default display:

- Current NOAA G/R/S badges with source timestamp and "estimated" labels where
  appropriate.
- A 6-hour sparkline for GOES X-ray flux, >=10 MeV proton flux, Kp, Bz, solar
  wind speed, and density.
- A feed health indicator: stale, fresh, partial, quality-flagged, or missing.
- Plain-language impact text by scale, linked to the official NOAA scales.
- Raw/latest values visible near every classification.

Good alerting defaults:

- Alert on new scale transitions, not every data refresh.
- Debounce repeated threshold crossings.
- Separate "observed threshold crossed" from "official SWPC alert/warning".
- Include timestamp, endpoint, satellite/source, energy band, value, threshold,
  and classification.
- For R-scale alerts, include whether the user's region is sunlit if the app has
  geolocation.
- For G-scale alerts, avoid promising local power-grid or GNSS impact from Kp
  alone.
- For aurora alerts, combine OVATION output with darkness, cloud cover, moon,
  latitude, and local horizon if the app targets observers.

## Failure Modes And Caveats

- Static JSON files are easy to fetch but can change shape without a versioned
  schema. Guard parsing and monitor unknown fields.
- Some feeds are rolling windows. Use NCEI archives for historical analysis.
- Operational products can have gaps from spacecraft outages, eclipses,
  calibrations, instrument issues, or ground-station coverage.
- Quality flags matter. A valid number is not always a trustworthy number.
- Kp is global and 3-hourly. Local ground-induced current risk needs local
  magnetic perturbations, ground conductivity, and grid/network context.
- X-ray flux classifies radio blackout potential, not where every radio service
  will fail.
- Proton flux thresholds indicate radiation storm severity, but actual aviation
  or spacecraft response depends on altitude, latitude, shielding, orbit, and
  mission rules.
- Aurora model grids are forecasts/nowcasts, not visibility guarantees.

## What Would Improve Confidence

- Compare local classifications against SWPC's official alerts, watches, and
  warnings over several months.
- Store raw payloads and replay them through the classifier after schema changes.
- Add endpoint-specific schema tests from real examples.
- Validate stale-data behavior by checking `Last-Modified` and source timestamp,
  not just successful HTTP responses.
- For high-stakes users, have a domain expert review thresholds, persistence
  rules, and alert copy.

## Sources

- [SWPC Products directory](https://services.swpc.noaa.gov/products/): API
  reference root for product JSON files and product subdirectories.
- [NOAA scales product](https://services.swpc.noaa.gov/products/noaa-scales.json):
  Compact current/recent/forecast G, S, and R scale status and probabilities.
- [SWPC alerts product](https://services.swpc.noaa.gov/products/alerts.json):
  Official watch, warning, alert, summary, continuation, cancellation, and
  related message text.
- [SWPC solar-wind products](https://services.swpc.noaa.gov/products/solar-wind/):
  Chart-ready magnetic-field and plasma product windows.
- [SWPC JSON directory](https://services.swpc.noaa.gov/json/): Root index for
  lower-level measurement feeds.
- [SWPC GOES JSON directory](https://services.swpc.noaa.gov/json/goes/):
  Primary/secondary GOES product directories and metadata files.
- [NOAA Space Weather Scales](https://www.spaceweather.gov/noaa-scales-explanation):
  Official G, S, and R scale definitions and physical thresholds.
- [GOES X-ray Flux product](https://www.spaceweather.gov/products/goes-x-ray-flux):
  X-ray passbands, event definitions, dynamic update behavior, and JSON access.
- [GOES Proton Flux product](https://www.spaceweather.gov/products/goes-proton-flux):
  Proton event thresholds, energy channels, and JSON access.
- [Planetary K-index product](https://www.spaceweather.gov/products/planetary-k-index):
  Kp meaning, update cadence, station sources, and alert/watch context.
- [Real Time Solar Wind product](https://www.spaceweather.gov/products/real-time-solar-wind):
  RTSW source switching, L1 upstream context, available data, and JSON access.
- [Aurora 30 Minute Forecast product](https://www.spaceweather.gov/products/aurora-30-minute-forecast):
  OVATION model interpretation, forecast horizon, and grid-format data.
