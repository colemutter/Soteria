# CubeSat OpenC3 Telemetry State Map

Generated: 2026-06-21

This map is simulator-only. It maps stock NOS3/OpenC3 telemetry into the
logical Soteria `cubesat_state_current` row and separates dashboard state from
per-command verification telemetry. It does not define a flight telemetry
contract, a flight rule, or a real spacecraft command path.

## Source Basis

Local artifacts:

- [CubeSat NOS3 Command Evidence](./cubesat-nos3-command-evidence.md)
- [CubeSat OpenC3/NOS3 Command Catalog](./cubesat-openc3-command-catalog.md)
- [CubeSat OpenC3 Automation Decision](./cubesat-openc3-automation-decision.md)
- [CubeSat NOS3 OpenC3 Commanding Subtasks](../agents/cubesat-nos3-openc3-commanding-subtasks.md)
- `supabase/migrations/20260620233000_create_satellites.sql`
- `src/frontend/src/lib/satelliteSync.ts`

External and extracted sources:

- [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api)
- [OpenC3 Streaming API](https://docs.openc3.com/docs/development/streaming-api)
- [OpenC3 Packet Viewer](https://docs.openc3.com/docs/tools/packet-viewer)
- [OpenC3 Command and Telemetry Server](https://docs.openc3.com/docs/tools/cmd-tlm-server)
- [OpenC3 COSMOS and NASA cFS guide](https://docs.openc3.com/docs/guides/cfs)
- [NOS3 Ground Software](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html)
- [NOS3 Simulators](https://nos3.readthedocs.io/en/latest/NOS3_Simulators.html)
- [NOS3 target aliases](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/system/stash/system.txt)
- [SIM_42_TRUTH telemetry definition](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/SIM_42_TRUTH/cmd_tlm/SIM_42_TRUTH_TLM.txt)
- [CFS ES telemetry definition](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/ES_TLM.txt)
- [CFS TO telemetry definition](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/TO_TLM.txt)
- [Generic EPS telemetry definition](https://github.com/nasa-itc/generic_eps/blob/1aad19930ada314091d5be0b75bfd4379a39765d/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_TLM.txt)
- [Generic ADCS telemetry definition](https://github.com/nasa-itc/generic_adcs/blob/01a2088629a3b05332c2457e5df8ec3d0eaceb30/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_TLM.txt)
- [Sample payload telemetry definition](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE/cmd_tlm/SAMPLE_TLM.txt)
- [Generic radio telemetry definition](https://github.com/nasa-itc/generic_radio/blob/687db4817499e5e617aac2b75b89f89f22624c56/gsw/GENERIC_RADIO/cmd_tlm/GENERIC_RADIO_TLM.txt)
- [Generic reaction wheel telemetry definition](https://github.com/nasa-itc/generic_reaction_wheel/blob/22c3c4c313d81465797a57d845b3729a236c0254/gsw/GENERIC_REACTION_WHEEL/cmd_tlm/GENERIC_REACTION_WHEEL_TLM.txt)
- [MGR telemetry definition](https://github.com/nasa-itc/mgr/blob/e4f56752df4549ffe074b79d768374f51099357b/gsw/MGR/cmd_tlm/MGR_TLM.txt)

Version basis from T2:

| Field | Value |
| --- | --- |
| Catalog version | `nos3-openc3-v1_07_04-cmdcat.20260621` |
| Simulator stack | `nos3_openc3` |
| NOS3 release/tag | `1.7.4` / `v1_07_04` |
| NOS3 commit | `4428de566833527c49b16d322157ed11ad8f2318` |
| OpenC3 scope | `DEFAULT` unless the bench deliberately changes scope |

## Read Path

Use OpenC3 structured telemetry APIs. Do not scrape Packet Viewer text or
OpenC3 logs for state.

JSON API reads are the source of truth for synchronous command verification:

```json
{
  "jsonrpc": "2.0",
  "method": "tlm",
  "params": ["GENERIC_EPS", "GENERIC_EPS_HK_TLM", "BATT_VOLTAGE"],
  "id": "state_poll_001",
  "keyword_params": { "scope": "DEFAULT" }
}
```

Use `tlm` for converted values, `tlm_raw` only when raw ADC/count values are
needed, and `tlm_formatted` only for operator-facing display strings. The
OpenC3 JSON API supports both string and structured parameter forms and
requires the scope in `keyword_params`.

The Streaming API may maintain the dashboard freshness cache. Streaming item
topics should use OpenC3's double-underscore form:

```text
DECOM__TLM__SIM_42_TRUTH__SIM_42_TRUTH_DATA__POSITION_N_0__CONVERTED
DECOM__TLM__GENERIC_EPS__GENERIC_EPS_HK_TLM__BATT_VOLTAGE__CONVERTED
DECOM__TLM__GENERIC_ADCS__GENERIC_ADCS_GNC__MODE__CONVERTED
DECOM__TLM__SAMPLE_RADIO__SAMPLE_HK_TLM__DEVICE_ENABLED__CONVERTED
```

The publisher should retain both packet/item `observed_at` and database
`written_at`. If OpenC3 JSON reads do not expose a packet timestamp, use the
bridge receive time and also preserve packet `CCSDS_SECONDS`/`CCSDS_SUBSECS`
where the packet defines them.

## Logical State Row

`cubesat_state_current` is a logical latest-state table for the bridge. This
task does not implement or migrate it, but downstream schema work should keep
these fields.

| Field | Type | Source |
| --- | --- | --- |
| `satellite_id` | UUID or text | Soteria satellite row or simulator external id |
| `external_id` | text | Stable value such as `nos3-sim-primary` |
| `simulator_stack` | text | `nos3_openc3` |
| `catalog_version` | text | T2 command catalog version |
| `state_observed_at` | timestamptz | Max observation time across core packets |
| `state_written_at` | timestamptz | Bridge write time |
| `state_quality` | enum | `fresh`, `partial`, `stale`, `sim_extension_required` |
| `quality_reasons` | text array | Stale packets, missing packets, unresolved extension fields |
| `source_packet_ages_s` | jsonb | Age per target/packet |
| `orbit` | jsonb | Position, velocity, lat/lon/alt, sun/orbit derived fields |
| `attitude` | jsonb | Mode, quaternion, body rates, validity flags |
| `power` | jsonb | Battery, bus rails, solar array, switch states/currents |
| `payload` | jsonb | Sample payload enabled/health/data/science status |
| `thermal` | jsonb | Stock EPS, battery, and solar-array temperatures |
| `radio` | jsonb | TO route state, generic radio HK, radio-path freshness |
| `fault_flags` | jsonb | Derived flags from counters, validity flags, and stale packets |
| `command_counters` | jsonb | Per-subsystem command/error counters |
| `last_command_result` | jsonb | Latest `cubesat_command_results` summary, not OpenC3 dashboard telemetry |

State classifications:

- `direct_telemetry`: OpenC3 item directly exists in the target dictionary.
- `openc3_derived_telemetry`: OpenC3 target file defines a derived item.
- `soteria_derived`: Soteria derives from exact OpenC3 items.
- `command_result`: Comes from Soteria command execution/result rows.
- `sim_extension_required`: Requires a future NOS3 data provider or component.
- `unavailable_stock_nos3`: No exact packet/item found in the pinned stock
  dictionary and no safe derivation exists.

Unknown packet, item, target, or units names are blockers. A publisher must
skip the field and add `quality_reasons[]`, not guess spellings from similar
systems.

## Dashboard State Mapping

| Soteria field | Classification | OpenC3 target / packet / item | Units and derivation | Fresh threshold | Notes |
| --- | --- | --- | --- | --- | --- |
| `orbit.position_eci_m` | direct telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA POSITION_N_0`, `POSITION_N_1`, `POSITION_N_2` | meters, inertial position | 3s | Core orbit state. |
| `orbit.velocity_eci_m_s` | direct telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA VELOCITY_N_0`, `VELOCITY_N_1`, `VELOCITY_N_2` | m/s, inertial velocity | 3s | Used for speed and orbit-normal derivations. |
| `orbit.position_ecef_m` | direct telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA POSITION_W_0`, `POSITION_W_1`, `POSITION_W_2` | meters, Earth-fixed position | 3s | Preferred input for longitude derivation. |
| `orbit.velocity_ecef_m_s` | direct telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA VELOCITY_W_0`, `VELOCITY_W_1`, `VELOCITY_W_2` | m/s, Earth-fixed velocity | 3s | Optional dashboard detail. |
| `orbit.latitude_deg` | openc3_derived_telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA GEOCENTRIC_LATITUDE` | degrees | 3s | Geocentric, not geodetic. If UI needs geodetic latitude, derive in Soteria from ECEF and label it separately. |
| `orbit.longitude_deg` | soteria_derived | `SIM_42_TRUTH SIM_42_TRUTH_DATA POSITION_W_0..2` | degrees from `atan2(y, x)` on ECEF | 3s | No exact stock longitude item found in extracted target file. |
| `orbit.altitude_km` | soteria_derived | `SIM_42_TRUTH SIM_42_TRUTH_DATA POSITION_W_0..2` or `POSITION_N_0..2` | `(norm(position_m) - earth_radius_m) / 1000` | 3s | Use the same Earth radius as frontend orbital helpers unless schema work chooses WGS84 geodetic altitude. |
| `orbit.speed_km_s` | soteria_derived | `SIM_42_TRUTH SIM_42_TRUTH_DATA VELOCITY_N_0..2` | `norm(velocity_m_s) / 1000` | 3s | Compatible with existing `satellites.speed_km_s`. |
| `orbit.in_sun` | openc3_derived_telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA IN_SUN` | positive means in sun, zero means eclipse | 3s | Useful for power interpretation. |
| `orbit.beta_deg` | openc3_derived_telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA BETA` | degrees | 3s | OpenC3 item may be an array value; preserve raw converted value. |
| `attitude.mode` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC MODE` | enum: `PASSIVE=0`, `BDOT=1`, `SUNSAFE=2`, `INERTIAL=3` | 5s | First-slice ADCS command verifier. |
| `attitude.quaternion_body_inertial` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC QBN_0`, `QBN_1`, `QBN_2`, `QBN_3` | unitless quaternion | 5s | ADCS estimate. Truth packet also has `SIM_42_TRUTH ... QN_0..3`. |
| `attitude.truth_quaternion_body_inertial` | direct telemetry | `SIM_42_TRUTH SIM_42_TRUTH_DATA QN_0`, `QN_1`, `QN_2`, `QN_3` | unitless quaternion | 3s | Use for simulator dashboard truth, not command verification by itself. |
| `attitude.body_rate_rad_s` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC WBN_X`, `WBN_Y`, `WBN_Z` | rad/s | 5s | Truth alternatives: `SIM_42_TRUTH ... WN_0..2` or `GYRO_B_X/Y/Z`. |
| `attitude.q_valid` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC Q_VALID` | `1` valid, `0` invalid | 5s | Drives fault flags. |
| `attitude.sun_valid` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC SUN_VALID` | `1` valid, `0` invalid | 5s | Drives sun-safe preconditions. |
| `attitude.rw_momentum_body_nms` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_GNC RW_MOMENTUM_X`, `RW_MOMENTUM_Y`, `RW_MOMENTUM_Z` | Nms | 5s | Aggregate body-frame ADCS value. |
| `attitude.rw_momentum_wheel_nms` | direct telemetry | `GENERIC_REACTION_WHEEL GENRW_HK_TLM_T MOMENTUM_NMS_0`, `MOMENTUM_NMS_1`, `MOMENTUM_NMS_2` | Nms | 5s | First-slice reaction wheel verifier. |
| `power.battery_voltage_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_VOLTAGE` | V | 10s | Derived in OpenC3 from `RAW_BATTERY_VOLTAGE` with slope `0.001`. |
| `power.battery_temperature_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_TEMPERATURE` | C | 10s | Source file spells units label as `Celcuis`; store normalized `C`. |
| `power.bus_3p3_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BUS_3P3V` | V | 10s | Derived from raw bus rail. |
| `power.bus_5p0_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BUS_5P0V` | V | 10s | Derived from raw bus rail. |
| `power.bus_12_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BUS_12V` | V | 10s | Derived from raw bus rail. |
| `power.solar_array_voltage_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SA_VOLTAGE` | V | 10s | Pair with `orbit.in_sun`. |
| `power.solar_array_temperature_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SA_TEMPERATURE` | C | 10s | Also part of thermal summary. |
| `power.eps_temperature_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM EPS_TEMPERATURE` | C | 10s | Also part of thermal summary. |
| `power.switches[n].state` | direct telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_0_STATE` through `SWITCH_7_STATE` | enum: `ON=0xAA`, `OFF=0x00` | 10s | Exact switch-to-load policy is not defined by stock NOS3. |
| `power.switches[n].flags` | direct telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_0_FLAGS` through `SWITCH_7_FLAGS` | `HEALTHY=0x00` where defined | 10s | Any nonzero or unrecognized flag becomes a fault flag. |
| `power.switches[n].voltage_v` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SW_0_VOLTAGE` through `SW_7_VOLTAGE` | V | 10s | Derived from raw switch voltage items. |
| `power.switches[n].current_a` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SW_0_CURRENT` through `SW_7_CURRENT` | A | 10s | Derived from raw switch current items. |
| `power.battery_soc_pct` | sim_extension_required | none found | Requires EPS model or derived battery capacity model | n/a | Do not infer from voltage alone without an approved model. |
| `payload.power_state` | direct telemetry | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED` | enum: `DISABLED=0`, `ENABLED=1` | 15s | First-slice payload enable/disable verifier. `SAMPLE SAMPLE_HK_TLM DEVICE_ENABLED` is the non-radio equivalent. |
| `payload.health.device_status` | direct telemetry | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_STATUS` | uint32 simulator status | 15s | Fault-injection verifier uses this item. |
| `payload.health.device_config` | direct telemetry | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_CONFIG` | uint32 | 15s | Preserve as raw config value. |
| `payload.health.device_counter` | direct telemetry | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_COUNTER` | count | 15s | Reported device command counter. |
| `payload.sample_vector` | openc3_derived_telemetry | `SAMPLE_RADIO SAMPLE_DATA_TLM SAMPLE_X`, `SAMPLE_Y`, `SAMPLE_Z` | unit vector components | 20s when enabled | If payload is disabled, stale `SAMPLE_DATA_TLM` is expected and should not degrade whole-state quality. |
| `payload.science_region_status` | direct telemetry | `SAMPLE_RADIO SAMPLE_DATA_TLM RegionStatus` | enum: science region/status values | 20s when enabled | Also reflected at manager level as `SCIENCE_STATUS`. |
| `payload.manager_spacecraft_mode` | direct telemetry | `MGR_RADIO MGR_HK_TLM SPACECRAFT_MODE` | enum: `SAFE`, `SAFE_REBOOT`, `SCIENCE`, `SCIENCE_REBOOT` | 15s | Useful high-level mode independent of ADCS mode. |
| `payload.manager_science_status` | direct telemetry | `MGR_RADIO MGR_HK_TLM SCIENCE_STATUS` | enum: science status values | 15s | Dashboard field for science/demo posture. |
| `payload.ak_config` | direct telemetry | `MGR_RADIO MGR_HK_TLM AK_CONFIG` | enum: `DISABLED=0`, `ENABLED=1` | 15s | First-slice MGR verifier. |
| `thermal.eps_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM EPS_TEMPERATURE` | C | 10s | Stock thermal coverage is EPS-only. |
| `thermal.battery_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_TEMPERATURE` | C | 10s | Stock thermal coverage is EPS-only. |
| `thermal.solar_array_c` | openc3_derived_telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM SA_TEMPERATURE` | C | 10s | Stock thermal coverage is EPS-only. |
| `thermal.compute_payload_c` | sim_extension_required | none found | Future `compute_payload` component | n/a | Required for 6U edge-compute realism. |
| `radio.to_enabled_routes` | direct telemetry | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` | route bitmask | 10s | First-slice radio enable verifier. |
| `radio.to_config_routes` | direct telemetry | `CFS_RADIO TO_HKPACKET CONFIGROUTES` | route bitmask | 10s | Dashboard context. |
| `radio.to_cmd_counter` | direct telemetry | `CFS_RADIO TO_HKPACKET CMDCOUNTER` | count | 10s | Radio resume/disable verifier. |
| `radio.to_err_counter` | direct telemetry | `CFS_RADIO TO_HKPACKET ERRCOUNTER` | count | 10s | Drives fault flags. |
| `radio.generic_proximity_signal` | direct telemetry | `GENERIC_RADIO_RADIO GENERIC_RADIO_HK_TLM PROXIMITY_SIGNAL` | uint32 simulator signal | 15s | Stock radio health signal. `GENERIC_RADIO` is the direct target equivalent. |
| `radio.forward_count` | direct telemetry | `GENERIC_RADIO_RADIO GENERIC_RADIO_HK_TLM FORWARD_COUNT` | count | 15s | Optional radio dashboard counter. |
| `radio.forward_error_count` | direct telemetry | `GENERIC_RADIO_RADIO GENERIC_RADIO_HK_TLM FORWARD_ERR_COUNT` | count | 15s | Drives fault flags. |
| `radio.packet_loss_pct` | sim_extension_required | none found | Future radio link model or bridge metric | n/a | Do not derive from route state alone. |
| `fault_flags.cfs_errors` | soteria_derived | `CFS CFE_ES_HKPACKET ERRCOUNTER` | flag if increased or nonzero against baseline | 10s | Keep raw counter in `command_counters`. |
| `fault_flags.command_errors` | soteria_derived | subsystem `ERRCOUNTER`, `CMD_ERR_COUNT`, `ERROR_COUNT` items | flag if counters increase after command or since baseline | per subsystem | Include CFS, TO, SAMPLE, ADCS, EPS, MGR, radio, reaction wheel. |
| `fault_flags.invalid_attitude_solution` | soteria_derived | `GENERIC_ADCS GENERIC_ADCS_GNC Q_VALID`, `SUN_VALID` | true if either is invalid for a command that needs it | 5s | Important before ADCS commands. |
| `fault_flags.eps_switch_faults` | soteria_derived | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_*_FLAGS` | true for any non-healthy flag | 10s | Exact flag vocabulary beyond `HEALTHY` is a future extraction task. |
| `fault_flags.payload_fault` | soteria_derived | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_STATUS`, `DEVICE_ERR_COUNT` | true if status indicates fault or error count increments | 15s | Fault code semantics should be documented before automation uses them. |
| `fault_flags.space_weather_fault` | sim_extension_required | none found | Future space-weather fault injector/data provider | n/a | Stock NOS3 command catalog rejected generic radiation protection. |
| `command_counters.cfs_es` | direct telemetry | `CFS CFE_ES_HKPACKET CMDCOUNTER`, `ERRCOUNTER` | counts | 10s | Connectivity command verifier. |
| `command_counters.sample` | direct telemetry | `SAMPLE SAMPLE_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | counts | 15s | Sample NOOP verifier. |
| `command_counters.sample_radio` | direct telemetry | `SAMPLE_RADIO SAMPLE_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | counts | 15s | Payload enable/disable verifier path. |
| `command_counters.adcs` | direct telemetry | `GENERIC_ADCS GENERIC_ADCS_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | counts | 5s | ADCS set-mode secondary verifier. |
| `command_counters.eps` | direct telemetry | `GENERIC_EPS GENERIC_EPS_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | counts | 10s | EPS switch command verifier context. |
| `command_counters.reaction_wheel` | direct telemetry | `GENERIC_REACTION_WHEEL GENRW_HK_TLM_T COMMAND_COUNT`, `ERROR_COUNT` | counts | 5s | Reaction wheel torque verifier context. |
| `command_counters.manager` | direct telemetry | `MGR_RADIO MGR_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | counts | 15s | MGR command verifier context. |
| `last_command_result` | command_result | `cubesat_command_results` latest row | status, result class, verifier before/after samples | n/a | Not a stock NOS3 telemetry item. It is required so the AI agent can see the last bridge action and outcome. |

## Freshness And Cadence

Cadence is the bridge publishing cadence. It must be validated on the running
bench because OpenC3 target definitions define packets/items, not guaranteed
runtime rates.

| Subsystem | Packets | Publish cadence | Fresh | Stale | Hard stale / outage | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Orbit/truth | `SIM_42_TRUTH SIM_42_TRUTH_DATA` | stream, write 1 Hz | age <= 3s | age > 3s | age > 10s | The OpenC3 truth grapher config uses 10 Hz refresh, but Soteria should write latest state at 1 Hz. |
| ADCS | `GENERIC_ADCS_GNC`, `GENERIC_ADCS_HK_TLM` | stream, write 1 Hz | age <= 5s | age > 5s | age > 15s | Required before ADCS mode commands. |
| Reaction wheel | `GENRW_HK_TLM_T` | stream/poll, write 1 Hz | age <= 5s | age > 5s | age > 15s | Required only for reaction-wheel torque verification. |
| EPS/power/thermal | `GENERIC_EPS_HK_TLM` | stream, write 0.5 to 1 Hz | age <= 10s | age > 10s | age > 30s | Required before power-sensitive commands. |
| CFS health | `CFE_ES_HKPACKET` | stream/poll, write 1 Hz | age <= 10s | age > 10s | age > 30s | Required for connectivity and global command-counter context. |
| Radio TO | `CFS_RADIO TO_HKPACKET` | stream/poll, write 1 Hz | age <= 10s | age > 10s | age > 30s | If radio output is intentionally disabled, mark expected outage rather than generic failure. |
| Generic radio | `GENERIC_RADIO_RADIO GENERIC_RADIO_HK_TLM` | stream/poll, write 1 Hz | age <= 15s | age > 15s | age > 45s | Optional for first slice, useful for comms dashboard. |
| Sample payload HK | `SAMPLE_RADIO SAMPLE_HK_TLM` | stream/poll, write 1 Hz | age <= 15s | age > 15s | age > 45s | Required before payload commands. |
| Sample payload data | `SAMPLE_RADIO SAMPLE_DATA_TLM` | stream when enabled, write 0.5 to 1 Hz | age <= 20s | age > 20s | age > 60s | Expected stale when `DEVICE_ENABLED == DISABLED`. |
| MGR/science | `MGR_RADIO MGR_HK_TLM` | stream/poll, write 1 Hz | age <= 15s | age > 15s | age > 45s | Required for science-region command verification. |
| Last command result | Supabase result row | event-driven | latest terminal result exists | n/a | n/a | Not age-gated, but include `completed_at`. |

Quality rules:

- `fresh`: all core packets needed for the enabled dashboard state are within
  fresh thresholds, and no required field is blocked by missing target metadata.
- `partial`: at least one optional packet is stale or missing, or an expected
  outage is active, but core command-precondition packets remain fresh.
- `stale`: any required packet for the current dashboard mode is past its stale
  threshold and no expected outage explains it.
- `sim_extension_required`: the requested state view depends on fields that
  stock NOS3 does not expose, such as compute payload CPU load or battery SOC.

## Command Verification Telemetry

Command verification is separate from dashboard state. The bridge should read a
baseline immediately before the `cmd` call, send exactly one command, then poll
the verifier item until the T2 timeout. Dashboard state can use the same items
for context, but it must not replace before/after command verification.

| Catalog ID | Command | Verifier telemetry | Success condition | Timeout |
| --- | --- | --- | --- | --- |
| `cfs_noop` | `CFS CFE_ES_NOOP` | `CFS CFE_ES_HKPACKET CMDCOUNTER` | Increments from baseline | 10s |
| `radio_enable_output` | `CFS_RADIO TO_ENABLE_OUTPUT` | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` | Changes, or radio packets become fresh | 10s |
| `radio_resume_output` | `CFS_RADIO TO_RESUME_OUTPUT` | `CFS_RADIO TO_HKPACKET CMDCOUNTER` | Increments and radio packets become fresh | 10s |
| `radio_disable_output` | `CFS_RADIO TO_DISABLE_OUTPUT` | `CFS_RADIO TO_HKPACKET CMDCOUNTER`, `ENABLEDROUTES` | Counter increments and output stops or goes stale as expected | 10s |
| `sample_noop` | `SAMPLE SAMPLE_NOOP_CC` | `SAMPLE SAMPLE_HK_TLM CMD_COUNT`, `CMD_ERR_COUNT` | `CMD_COUNT` increments and `CMD_ERR_COUNT` does not increase | 10s |
| `sample_enable` | `SAMPLE_RADIO SAMPLE_ENABLE_CC` | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED`, `CMD_COUNT` | `DEVICE_ENABLED == ENABLED` and command count increments | 15s |
| `sample_disable` | `SAMPLE_RADIO SAMPLE_DISABLE_CC` | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED`, `CMD_COUNT` | `DEVICE_ENABLED == DISABLED` and command count increments | 15s |
| `sample_sim_set_status` | `SIM_CMDBUS_BRIDGE SAMPLE_SIM_SET_STATUS` | `SAMPLE SAMPLE_HK_TLM DEVICE_STATUS` | Equals requested `STATUS` | 15s |
| `adcs_set_passive` | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` | `GENERIC_ADCS GENERIC_ADCS_GNC MODE`, `GENERIC_ADCS GENERIC_ADCS_HK_TLM CMD_COUNT` | `MODE == PASSIVE` and command count increments | 30s |
| `adcs_set_sunsafe` | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` | `GENERIC_ADCS GENERIC_ADCS_GNC MODE`, `GENERIC_ADCS GENERIC_ADCS_HK_TLM CMD_COUNT` | `MODE == SUNSAFE` and command count increments | 45s |
| `rw_set_torque` | `GENERIC_REACTION_WHEEL GENERIC_RW_SET_TORQUE_CC` | `GENERIC_REACTION_WHEEL GENRW_HK_TLM_T COMMAND_COUNT`, `MOMENTUM_NMS_0/1/2` | Command count increments and selected wheel momentum changes | 30s |
| `mgr_set_ak_enable` | `MGR_RADIO MGR_SET_AK_CC` | `MGR_RADIO MGR_HK_TLM AK_CONFIG` | `AK_CONFIG == ENABLED` | 15s |
| `eps_switch7_off_manual` | `GENERIC_EPS GENERIC_EPS_SWITCH_CC` | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_7_STATE` | `SWITCH_7_STATE == OFF` | 20s |
| `eps_load_shed_policy` | unresolved | blocker | No generic verifier until load-to-switch policy exists | n/a |
| `radiation_protect_generic` | unresolved/rejected | blocker | No stock NOS3 target/packet/item found | n/a |

Command result rows should preserve verifier samples separately:

```json
{
  "execution_id": "cmdexec_20260621_sample_enable_001",
  "catalog_command_id": "sample_enable",
  "status": "succeeded",
  "result_class": "success_when_enabled",
  "verifier": {
    "target": "SAMPLE_RADIO",
    "packet": "SAMPLE_HK_TLM",
    "item": "DEVICE_ENABLED",
    "before": "DISABLED",
    "after": "ENABLED",
    "observed_at": "2026-06-21T18:00:05Z"
  }
}
```

The latest terminal result can be summarized into `last_command_result` on the
state row, but the audit evidence remains in `cubesat_command_results`.

## Stale Telemetry Simulation

Example: the bridge receives fresh truth, ADCS, CFS, and sample packets, but no
`GENERIC_EPS GENERIC_EPS_HK_TLM` update for 42 seconds. EPS stale threshold is
10 seconds and hard-stale threshold is 30 seconds, so the row is `stale` for
power-sensitive use. The publisher may keep the last EPS values for display,
but every stale field must carry source age.

```json
{
  "external_id": "nos3-sim-primary",
  "simulator_stack": "nos3_openc3",
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "state_observed_at": "2026-06-21T18:00:42Z",
  "state_written_at": "2026-06-21T18:00:43Z",
  "state_quality": "stale",
  "quality_reasons": [
    "GENERIC_EPS/GENERIC_EPS_HK_TLM age 42s exceeds hard stale threshold 30s",
    "power-sensitive commands blocked until EPS telemetry is fresh"
  ],
  "source_packet_ages_s": {
    "SIM_42_TRUTH/SIM_42_TRUTH_DATA": 1.0,
    "GENERIC_ADCS/GENERIC_ADCS_GNC": 2.0,
    "GENERIC_EPS/GENERIC_EPS_HK_TLM": 42.0,
    "SAMPLE_RADIO/SAMPLE_HK_TLM": 3.0,
    "CFS/CFE_ES_HKPACKET": 4.0
  },
  "orbit": {
    "quality": "fresh",
    "position_eci_m": [123.0, 456.0, 789.0],
    "latitude_deg": 12.3,
    "longitude_deg": -45.6,
    "altitude_km": 410.2,
    "speed_km_s": 7.67
  },
  "power": {
    "quality": "stale",
    "battery_voltage_v": 7.41,
    "battery_voltage_observed_at": "2026-06-21T18:00:00Z",
    "switches": {
      "7": {
        "state": "ON",
        "state_observed_at": "2026-06-21T18:00:00Z"
      }
    }
  },
  "last_command_result": {
    "catalog_command_id": "sample_enable",
    "status": "succeeded",
    "completed_at": "2026-06-21T17:59:55Z"
  }
}
```

An AI agent may read this state for context, but it must not submit EPS load
shed, payload enable, radio disable, or other power-sensitive commands until
the EPS packet becomes fresh. Non-power commands still need their own
subsystem-specific preconditions.

## AI Command Preconditions

The current-state row supports the AI agent by making preconditions machine
readable before a command request is inserted.

Minimum pre-command checks:

| Command family | Required current-state checks |
| --- | --- |
| Connectivity NOOP | `CFS/CFE_ES_HKPACKET` fresh enough to baseline `CMDCOUNTER`. |
| Radio enable/resume | `CFS_RADIO/TO_HKPACKET` fresh or known disabled; OpenC3 private path healthy; no public destination args. |
| Radio disable | Human review outside smoke tests; command result path can tolerate expected radio stale/outage. |
| Sample enable | `SAMPLE_RADIO/SAMPLE_HK_TLM` fresh; `DEVICE_ENABLED != ENABLED`; EPS packet fresh if power posture matters. |
| Sample disable | `SAMPLE_RADIO/SAMPLE_HK_TLM` fresh; disabling does not hide required verifier telemetry unexpectedly. |
| ADCS passive/sunsafe | `GENERIC_ADCS_GNC` fresh; `MODE` known; `Q_VALID` and `SUN_VALID` considered for sun-safe; human review present. |
| Reaction wheel torque | `GENRW_HK_TLM_T` fresh; selected wheel baseline captured; manual-only command approval present. |
| MGR science-region config | `MGR_RADIO/MGR_HK_TLM` fresh; science/config context approved. |
| EPS switch 7 off | `GENERIC_EPS_HK_TLM` fresh; `SWITCH_7_STATE == ON`; low-power scenario and human approval present. |
| Generic EPS load shed | Blocked until load-to-switch policy and telemetry thresholds exist. |
| Radiation protection | Blocked until a stock target or simulator extension exists. |

If `state_quality` is `stale` or `sim_extension_required`, the agent may still
draft a recommendation, but the bridge should reject automatic execution unless
the command's catalog row explicitly allows operation under that degraded state.

## Existing `satellites` Compatibility

The existing `satellites` table is a broad space-object table. It can mirror
NOS3 position/state for compatibility with current map and report code, but it
cannot hold subsystem telemetry.

Writable compatibility fields:

| `satellites` field | Populate from NOS3/OpenC3 | Notes |
| --- | --- | --- |
| `external_id` | Stable simulator id such as `nos3-sim-primary` | Must be stable for upsert. |
| `name` | Fixed label such as `NOS3 CubeSat Sim` | Product/UI label. |
| `operational_status` | `active` while bridge is running; optionally `stale` only if downstream filters accept it | Current backend defaults filter for active satellites. |
| `orbit_regime` | `LEO` for stock NOS3 scenario unless TLE/orbit config proves otherwise | Do not infer MEO/GEO from stale state. |
| `reference_epoch` | State observation time | Same value as latest truth packet observation time. |
| `position_time` | State observation time | Existing frontend uses this for latest position. |
| `latitude_deg` | Derived from `SIM_42_TRUTH` position | Existing column expects degrees. |
| `longitude_deg` | Derived from `SIM_42_TRUTH POSITION_W_0..2` | Existing column expects degrees. |
| `altitude_km` | Derived from `SIM_42_TRUTH` position norm | Existing column expects km. |
| `speed_km_s` | Derived from `SIM_42_TRUTH VELOCITY_N_0..2` | Existing column expects km/s. |
| `updated_at` | Bridge write time | Database bookkeeping. |

Leave these fields null or externally configured unless a future task provides
a source: `norad_cat_id`, `operator`, `country`, `mission_class`, `tle_line1`,
`tle_line2`, `tle_epoch`, `mass_kg`, `cross_section_area_m2`,
`ballistic_coefficient_kg_m2`. Keep detailed ADCS/EPS/payload/radio state in
`cubesat_state_current`, not `satellites`.

## Stock NOS3 Gaps

| Gap | Status | Required follow-up |
| --- | --- | --- |
| Compute payload state: jobs, CPU, memory, thermal, power draw, checkpoint state | `sim_extension_required` | Add a NOS3 `compute_payload` component and OpenC3 target definitions. |
| Battery state of charge and energy margin | `sim_extension_required` | Add EPS model telemetry or an approved energy model; do not infer SOC from voltage alone. |
| Generic EPS load-to-switch policy | `sim_extension_required` | Define which `SWITCH_*` powers which load, allowed shed order, restore order, and thresholds. |
| Radiation/space-weather protection flags | `sim_extension_required` | Add fault injector/data provider for single-event effects, charging, drag, sensor degradation, and radio blackout effects. |
| Radio link packet loss/SNR | `sim_extension_required` | Add radio link model telemetry or bridge-side link metrics. |
| Detailed payload health beyond sample status/config/counter | `sim_extension_required` | Replace sample payload with mission-specific compute/payload component. |
| Component temperature coverage outside EPS, battery, solar array | `sim_extension_required` | Add ADCS/radio/payload thermal telemetry where needed. |
| Unknown live-bench target differences | blocker until verified | T3/T8 must confirm target/packet/item names in the running OpenC3 instance before automation depends on them. |

## Validation Summary

- Mapped every T2 first-slice command with exact target/packet/item verifier
  names where the command is executable or manual-only.
- Marked unresolved command families as blockers instead of inventing packet
  names.
- Defined dashboard state telemetry separately from command verification
  telemetry.
- Defined freshness thresholds and an explicit stale-state row shape.
- Confirmed the map lets an AI agent read current subsystem quality,
  preconditions, command counters, and latest command result before requesting a
  command.
- Identified existing `satellites` compatibility fields and kept subsystem
  telemetry out of that table.
