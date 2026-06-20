# NOAA API Mappings For Satellite Operation Protection

This document connects the SWPC endpoints described in
[NOAA SWPC Space Weather Products API Guide](./noaa-space-weather-api.md) to
satellite-protection features, derived fields, and operational meaning.

Use this as the feature contract between ingestion, analytics, and alerting. The
API guide explains how to fetch and classify the data; this document explains
why each measurement matters and how to map it to satellite operations.

## Bottom Line

No single NOAA field means "satellite unsafe." Useful protection signals combine:

- Upstream drivers: solar wind magnetic field, speed, density, and pressure.
- Near-Earth response: Kp, Dst, alerts, auroral/ionospheric context.
- Radiation environment: GOES proton and electron flux by energy channel.
- Asset exposure: orbit regime, altitude, latitude, local time, shielding, and
  spacecraft mode.

The same storm can be mostly a drag problem for LEO, a charging problem for GEO,
a radiation problem for polar/high-altitude assets, and a communications problem
for users on the sunlit side of Earth.

## Endpoint-To-Feature Map

| Endpoint | Raw fields | Derived features | Why it matters |
| --- | --- | --- | --- |
| `/json/rtsw/rtsw_mag_1m.json` | `time_tag`, `bt`, `bz_gsm`, `bx_gsm`, `by_gsm`, `active`, `source`, `overall_quality` | `southward_bz`, `southward_bz_duration`, `integrated_southward_bz`, `bt_high`, `bz_turning_rate` | Sustained negative `bz_gsm` is a primary upstream driver for magnetic coupling into Earth's magnetosphere. High `bt` makes southward intervals more consequential. |
| `/json/rtsw/rtsw_wind_1m.json` | `time_tag`, `proton_speed`, `proton_density`, `proton_temperature`, quality flags | `l1_eta_minutes`, `speed_high`, `density_jump`, `dynamic_pressure_proxy`, `shock_flag` | High speed shortens warning time from L1 and can strengthen storm driving. Density and pressure jumps can indicate shocks or compression regions. |
| `/products/solar-wind/mag-2-hour.json` | Header-row array with `bz_gsm`, `bt`, `bx_gsm`, `by_gsm` | Same as RTSW magnetic features, with chart-ready history | Useful when the app needs a compact rolling window for charts or recent persistence checks. |
| `/products/solar-wind/plasma-2-hour.json` | Header-row array with `density`, `speed`, `temperature` | Same as RTSW plasma features, with chart-ready history | Useful for visualizing speed, density, and shock-like changes over the last few hours. |
| `/products/summary/solar-wind-mag-field.json` | `time_tag`, `bt`, `bz_gsm` | `latest_bz_state`, `latest_bt_state` | Good for dashboard cards, but not enough for alerting without recent history and quality checks. |
| `/products/summary/solar-wind-speed.json` | `time_tag`, `proton_speed` | `latest_speed_state`, `latest_l1_eta_minutes` | Good for a current-speed card and rough lead-time estimate. |
| `/json/planetary_k_index_1m.json` | `time_tag`, `estimated_kp`, `kp`, `kp_index` | `estimated_g_scale`, `kp_slope`, `kp_ge_5_duration` | Near-real-time geomagnetic response indicator. Kp at or above 5 maps to NOAA G-scale storm conditions. |
| `/products/noaa-planetary-k-index.json` | `time_tag`, `Kp`, `a_running`, `station_count` | `observed_g_scale`, `storm_interval`, `kp_max_24h` | Official 3-hour planetary K-index history for storm severity, replay, and validation. |
| `/products/noaa-planetary-k-index-forecast.json` | `time_tag`, `kp`, `observed`, `noaa_scale` | `forecast_g_scale`, `forecast_storm_windows` | Helps operators prepare for likely geomagnetic-storm windows before they are observed. |
| `/products/kyoto-dst.json` | Dst records, when available | `ring_current_intensity`, `storm_main_phase`, `dst_min_24h` | Dst is useful for storm development and recovery context; it is slower-moving than upstream solar-wind features. |
| `/json/goes/primary/xrays-6-hour.json` | `time_tag`, `flux`, `observed_flux`, `energy`, `satellite` | `r_scale`, `flare_class`, `xray_flux_slope`, `m_or_x_crossing` | X-ray flux drives NOAA R-scale radio blackout classification. It matters for command links, GNSS/radio impacts, and flare context. |
| `/json/goes/primary/integral-protons-6-hour.json` | `time_tag`, `flux`, `energy`, `satellite` | `s_scale_10mev`, `proton_flux_slope_10mev`, `proton_flux_100mev` | `>=10 MeV` flux drives NOAA S-scale radiation storm classification. Higher-energy channels help estimate more penetrating radiation risk. |
| `/json/goes/primary/integral-electrons-6-hour.json` and `/json/goes/primary/differential-electrons-6-hour.json`, if used | `time_tag`, `flux`, `energy`, `satellite` | `electron_flux_high`, `deep_charging_risk_proxy`, `electron_flux_duration` | Energetic electrons are important for internal/deep dielectric charging, especially for GEO/MEO assets. |
| `/json/goes/primary/magnetometers-1-day.json`, if used | GOES magnetic field records | `geo_field_disturbance_context` | Useful local GEO context, but should be treated as supporting evidence rather than a global storm classifier. |
| `/products/noaa-scales.json` | `R`, `S`, `G`, current/recent/forecast scale fields | `official_scale_state`, `scale_transition` | Compact official NOAA scale status. Use as the user-facing state when possible; label locally computed scales as derived. |
| `/products/alerts.json` | `product_id`, `issue_datetime`, `message` | `official_watch_warning_alert`, `alert_transition`, `event_lifecycle` | Official SWPC messages capture forecaster logic, persistence, warnings, cancellations, and summary text beyond raw thresholds. |
| `/products/glotec/geojson_2d_urt.json` | TEC product manifests | `tec_disturbance_context` | TEC changes matter for GNSS delay and communications/navigation quality. |
| `/json/ovation_aurora_latest.json` | `Observation Time`, `Forecast Time`, `coordinates` | `auroral_oval_exposure`, `polar_precipitation_context` | Useful proxy for high-latitude particle precipitation and auroral-zone exposure, especially for polar LEO passes. |
| `/json/solar_regions.json` | `region`, `location`, `mag_class`, flare counts/probabilities | `flare_source_context`, `active_region_risk` | Context for flare/CME likelihood. It is not a direct satellite hazard by itself. |

## Derived Feature Definitions

Use these names consistently in downstream tables and alert payloads.

| Feature | Formula or rule | Primary source |
| --- | --- | --- |
| `southward_bz` | `max(0, -bz_gsm)` | RTSW magnetic field |
| `southward_bz_duration` | Continuous minutes where `bz_gsm < 0`, optionally requiring quality-good records | RTSW magnetic field |
| `integrated_southward_bz` | Sum of `max(0, -bz_gsm) * delta_minutes` over a rolling window | RTSW magnetic field |
| `coupling_ey_mvm` | `proton_speed * max(0, -bz_gsm) / 1000` | RTSW magnetic + plasma |
| `l1_eta_minutes` | Roughly `1500000 / proton_speed / 60`, using km and km/s | RTSW plasma |
| `dynamic_pressure_proxy` | `proton_density * proton_speed^2`; use consistent units and label it as a proxy unless fully normalized | RTSW plasma |
| `density_jump` | Rolling relative or absolute increase in `proton_density` over 5-15 minutes | RTSW plasma |
| `shock_flag` | Density jump plus speed jump plus `bt` jump within a short window | RTSW magnetic + plasma |
| `estimated_g_scale` | Classify `estimated_kp` with NOAA G thresholds | Kp nowcast |
| `observed_g_scale` | Classify observed `Kp` with NOAA G thresholds | Kp product |
| `r_scale` | Classify GOES `0.1-0.8nm` `flux` with NOAA R thresholds | GOES X-ray |
| `s_scale_10mev` | Classify GOES `>=10 MeV` proton `flux` with NOAA S thresholds | GOES protons |
| `electron_flux_duration` | Time above mission-specific electron flux threshold by energy channel | GOES electrons |
| `scale_transition` | Change in G/R/S level after debouncing and stale-data checks | NOAA scales and derived classifications |

## Why These Features Matter By Operation

| Operation | Best signals | Why they matter | Typical protective response |
| --- | --- | --- | --- |
| LEO orbit maintenance | Kp/ap, sustained southward Bz, high speed, density/pressure jumps, drag model outputs | Geomagnetic storms heat the thermosphere, increase neutral density, and increase drag. Orbit predictions and conjunction screening degrade. | Increase orbit determination cadence, refresh ephemerides, rerun conjunction assessment, delay precision burns when appropriate, enter low-drag attitude if available. |
| Collision avoidance | Kp, storm duration, thermospheric density proxies, asset altitude and ballistic coefficient | Drag uncertainty is one of the largest LEO propagation errors during storms. | Widen screening margins, request fresher tracking, avoid stale TLE-only decisions for high-value assets. |
| Attitude/orientation safety | Kp/G scale, density/pressure changes, charging indicators, star-tracker noise context | Drag torques, sensor noise, and charging can disturb attitude determination and control. | Avoid nonessential slews, monitor ADCS residuals, bias toward robust attitude modes during severe intervals. |
| GEO/MEO charging protection | Energetic electrons, geomagnetic activity, Kp, alerts, spacecraft local time/eclipse context | Hot plasma and energetic electrons can drive surface or deep dielectric charging and discharge anomalies. | Avoid sensitive switching, increase telemetry monitoring, defer risky commanding, use charging-aware mode rules. |
| Electronics/radiation protection | `>=10 MeV` and higher-energy proton flux, S scale, proton flux slope, alerts | Solar energetic particles can cause single-event upsets, latchup, detector noise, and solar-array degradation. | Enable scrubbing, protect detectors, pause sensitive observations, avoid critical uploads during high SEU risk. |
| Payload/image quality | Proton flux, electron flux, flare context, S scale | Energetic particles can add image noise, saturate detectors, and affect star trackers. | Flag affected products, pause exposures, use safe detector configurations. |
| Command and telemetry reliability | R scale, X-ray flux, Kp, TEC/scintillation, local daylight | Flares and ionospheric disturbances can degrade radio paths and GNSS-based timing/navigation. | Prefer robust links, schedule alternate contacts, avoid interpreting link dropouts as spacecraft faults without environment context. |
| GNSS navigation and timing | Kp, TEC, scintillation, R scale, auroral exposure | Ionospheric density structure changes delay and scintillate GNSS signals. | Increase navigation uncertainty, cross-check with non-GNSS sensors, gate autonomous decisions that rely on tight GNSS accuracy. |
| Polar/high-inclination passes | Proton flux, aurora grid, Kp, southward Bz | Polar regions are more exposed to particle precipitation and communication absorption. | Tag high-risk passes, adjust command windows, expect degraded polar communications. |

## Alerting Guidance

Separate four alert classes:

| Alert class | Trigger examples | User-facing meaning |
| --- | --- | --- |
| Watch | Forecast G/S/R risk, active region risk, rising upstream drivers | Conditions may become operationally relevant; prepare but do not assume impact. |
| Driver detected | Sustained negative `bz_gsm`, shock flag, high `coupling_ey_mvm` | Upstream solar-wind conditions are capable of driving geomagnetic response. |
| Response observed | Kp crosses 5, official G scale rises, Dst drops, auroral oval expands | Earth's near-space environment is disturbed now. |
| Asset-specific risk | Response observed plus vulnerable orbit/mode/exposure | This asset or service is plausibly exposed; apply mission rules. |

Good alert payload fields:

- `alert_type`
- `asset_id` or `asset_group`, when asset-specific
- `endpoint`
- `source`
- `time_tag`
- `fetched_at`
- `raw_value`
- `derived_value`
- `threshold`
- `classification`
- `quality_state`
- `staleness_seconds`
- `why_it_matters`
- `recommended_operator_check`

## Minimal Protection Feature Set

Start with this if the first product is a satellite-operations dashboard:

```text
/products/noaa-scales.json
/products/alerts.json
/json/rtsw/rtsw_mag_1m.json
/json/rtsw/rtsw_wind_1m.json
/json/planetary_k_index_1m.json
/products/noaa-planetary-k-index.json
/products/noaa-planetary-k-index-forecast.json
/json/goes/primary/xrays-6-hour.json
/json/goes/primary/integral-protons-6-hour.json
```

Add these when you need better asset-specific protection:

```text
/json/goes/secondary/xrays-6-hour.json
/json/goes/secondary/integral-protons-6-hour.json
/json/goes/primary/integral-electrons-6-hour.json
/json/goes/secondary/integral-electrons-6-hour.json
/json/goes/primary/differential-electrons-6-hour.json
/json/goes/secondary/differential-electrons-6-hour.json
/json/goes/primary/magnetometers-1-day.json
/json/ovation_aurora_latest.json
/products/glotec/geojson_2d_urt.json
/products/kyoto-dst.json
```

## Implementation Notes

- Keep official NOAA scales and locally derived scales separate.
- Preserve raw records, endpoint path, satellite ID, source, and quality flags.
- Debounce threshold crossings; do not alert on every one-minute refresh.
- Treat stale-but-successfully-fetched data as stale. Check both HTTP metadata
  and source timestamps.
- Do not mix primary and secondary GOES records without preserving provenance.
- Sort by parsed timestamp; do not assume newest-first ordering.
- Make orbit regime part of the risk model. A generic "space weather high"
  signal is less useful than a LEO drag, GEO charging, or radiation-risk signal.
- Use mission-specific thresholds for protective actions. NOAA scales are public
  severity categories, not a substitute for flight rules.

## Validation Checks

Before using a feature operationally:

- Replay several months of raw payloads against official SWPC alerts and scales.
- Confirm derived G/R/S transitions match official scale products except where
  forecaster/event logic intentionally differs.
- Test stale-data, missing-field, null-value, and source-switch behavior.
- Review alert text with a satellite operator or space-weather domain expert.
- Validate each asset-specific action against mission rules, not just public
  NOAA thresholds.

## Sources

- [NOAA SWPC Space Weather Products API Guide](./noaa-space-weather-api.md):
  local endpoint, schema, ingestion, and G/R/S classification reference.
- [NOAA Space Weather Scales](https://www.spaceweather.gov/noaa-scales-explanation):
  official G, S, and R scale definitions and impact language.
- [NOAA Real Time Solar Wind](https://www.spaceweather.gov/products/real-time-solar-wind):
  upstream L1 solar-wind magnetic field and plasma context.
- [NOAA Satellite Drag](https://www.spaceweather.gov/impacts/satellite-drag):
  LEO drag and orbit-prediction impacts.
- [NOAA Geomagnetic Storms](https://www.spaceweather.gov/phenomena/geomagnetic-storms):
  storm mechanisms and upper-atmosphere effects.
