# CubeSat Power-System Simulation And Commands

Generated: 2026-06-21

This document is simulator-only. It defines how Soteria should reuse and extend
stock NOS3/OpenC3 power behavior for a NOS3-backed CubeSat bench. It is not a
flight EPS model, flight rule, spacecraft command authority, RF uplink path, or
hardware vendor command set.

The governing catalog is
[`nos3-openc3-v1_07_04-cmdcat.20260621`](./cubesat-openc3-command-catalog.md).
Every executable command below must be resolved from that catalog by ID. Soteria
intents such as "shed load" or "enter safe mode" are not executable commands
unless they resolve to catalog rows with exact OpenC3 target, command, args,
review policy, and telemetry verifiers.

## Adoption Map

| Fit | Capability | Adopt or investigate | First step |
| --- | --- | --- | --- |
| Adopt now | Stock EPS telemetry and low-power behavior | Use `GENERIC_EPS` telemetry, switch states/currents, voltage rails, in-sun context, and the NOS3 low-power scenario before adding any custom EPS model. | Reproduce the low-power scenario and verify the T6 `GENERIC_EPS GENERIC_EPS_HK_TLM` packet names on the running bench. |
| Adopt now | Operator-visible power telemetry | Use OpenC3 Packet Viewer, Telemetry Grapher, and the NOS3 `EPS_test.txt` graph config. | Open `GENERIC_EPS` in Packet Viewer and run `EPS_test.txt` during a scenario pass. |
| Adopt now | Config-driven EPS initial conditions | Use `<battery-charge-state>` in `cfg/sim/nos3-simulator.xml` for deterministic low-power setup. | Configure a low-SOC scenario, rebuild/relaunch stock NOS3, and record actual EPS telemetry values. |
| Prototype/spike | Exact EPS switch operations | Use the catalogued `GENERIC_EPS GENERIC_EPS_SWITCH_CC` switch 7 row only for the low-power scenario; keep generic load shed non-executable. | Tabletop and then bench-test `eps_switch7_off_manual` with operator approval and verifier samples. |
| Prototype/spike | Sim Bridge SOC controls | Use Sim Bridge state-of-charge controls only if present in the pinned NOS3 checkout. | Inspect the local NOS3/OpenC3 Sim Bridge target and add a catalog row only after exact command metadata is extracted. |
| Prototype/spike | LC/SC/RTS safe-mode behavior | Study LC watchpoints, LC actionpoints, and SC/RTS tables for 60% pause and 40% safe-state behavior. | Review `cfg/nos3_defs/tables/lc_def_wdt.c`, `lc_def_adt.c`, and `sc_rts*.c`; do not bridge table patches until a separate review task approves them. |
| Study/extend | 6U compute-payload power channels | Add a NOS3-native hardware model or data provider only if stock EPS cannot represent Soteria compute loads, job pause/resume, CPU power limits, or compute thermal coupling. | Design a future `compute_payload` component with OpenC3 command/telemetry definitions and an explicit power-channel map. |

## Source Basis

Local Soteria artifacts:

- [CubeSat NOS3 Command Evidence](./cubesat-nos3-command-evidence.md)
- [CubeSat OpenC3/NOS3 Command Catalog](./cubesat-openc3-command-catalog.md)
- [CubeSat OpenC3 Automation Decision](./cubesat-openc3-automation-decision.md)
- [CubeSat OpenC3 Bridge Contract](./cubesat-openc3-bridge-contract.md)
- [CubeSat OpenC3 Telemetry State Map](./cubesat-openc3-telemetry-state-map.md)
- [CubeSat NOS3 OpenC3 Commanding Subtasks](../agents/cubesat-nos3-openc3-commanding-subtasks.md)

Primary external sources:

- [NOS3 STF-1 CubeSat case study](https://arxiv.org/abs/1901.07583): describes NOS3 as a software-only STF-1 3U CubeSat simulator using hardware-component simulators such as EPS, 42 dynamics, cFS, and COSMOS.
- [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html): documents `GENERIC_EPS_RADIO GENERIC_EPS_HK_TLM BATT_VOLTAGE`, `SAMPLE_RADIO SAMPLE_ENABLE_CC`, `SAMPLE_RADIO SAMPLE_DISABLE_CC`, and `CFS_RADIO TO_DISABLE_OUTPUT` examples.
- [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html): documents `<battery-charge-state>`, `EPS_test.txt`, Packet Viewer inspection of `GENERIC_EPS`, switch 7 manual triage, 60%/40% low-power logic, LC/RTS patch work, and Sim Bridge SOC testing.
- [NOS3 Simulators](https://nos3.readthedocs.io/en/latest/NOS3_Simulators.html): documents NOS3 hardware models, XML configuration, data providers, command connections, and time connections for custom simulator behavior.
- [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender): defines the manual target/packet command path and hazardous-command prompts.
- [OpenC3 Packet Viewer](https://docs.openc3.com/docs/tools/packet-viewer) and [Telemetry Grapher](https://docs.openc3.com/docs/tools/tlm-grapher): provide operator telemetry inspection and graphing.
- [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api): supports `cmd`, `tlm`, `tlm_raw`, and `tlm_formatted` for bridge automation.

Pinned command/telemetry source links from T2/T6:

- [Generic EPS command definitions](https://github.com/nasa-itc/generic_eps/blob/1aad19930ada314091d5be0b75bfd4379a39765d/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_CMD.txt)
- [Generic EPS telemetry definitions](https://github.com/nasa-itc/generic_eps/blob/1aad19930ada314091d5be0b75bfd4379a39765d/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_TLM.txt)
- [Sample command definitions](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE/cmd_tlm/SAMPLE_CMD.txt)
- [Sample telemetry definitions](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE/cmd_tlm/SAMPLE_TLM.txt)
- [Generic ADCS command definitions](https://github.com/nasa-itc/generic_adcs/blob/01a2088629a3b05332c2457e5df8ec3d0eaceb30/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_CMD.txt)
- [Generic ADCS telemetry definitions](https://github.com/nasa-itc/generic_adcs/blob/01a2088629a3b05332c2457e5df8ec3d0eaceb30/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_TLM.txt)
- [CFS TO command definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/TO.txt)
- [CFS TO telemetry definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/TO_TLM.txt)

## Tech Discovery: Why NOS3 First

The reusable technology map favors stock NOS3 first:

| Capability | Recommendation | Why it fits | Risk/constraint | First integration step |
| --- | --- | --- | --- | --- |
| CubeSat EPS simulation baseline | Adopt stock NOS3 `GENERIC_EPS` | NOS3 was built for a CubeSat simulator and includes EPS-like hardware simulator behavior, telemetry, and low-power exercises. | Stock telemetry does not expose every Soteria variable, especially live SOC, bus current, solar current, and compute workload power. | Use T6 telemetry fields and reproduce the NOS3 low-power scenario without custom code. |
| Operator power diagnosis | Adopt OpenC3 Packet Viewer and Telemetry Grapher | NOS3 low-power docs explicitly use `GENERIC_EPS` Packet Viewer and `EPS_test.txt` to find the power drain. | Manual tools prove behavior but do not create bridge audit rows. | Use these tools for bench validation, then mirror exact packet/item reads through the JSON API. |
| Automated command/telemetry path | Adopt T4 bridge path: OpenC3 JSON API standard `cmd` plus `tlm` polling | OpenC3 JSON API supports commands and telemetry without raw packet construction. | No-check methods exist and must stay forbidden by bridge policy. | Resolve catalog ID, send standard `cmd`, then poll catalog verifier. |
| Low-power autonomy | Prototype LC/SC/RTS table behavior | NOS3 low-power docs use LC watchpoints/actionpoints and RTS tables for threshold behavior. | Table patching is higher blast radius than first-slice commands and needs separate review. | Treat as a lab spike, not an AI-executable bridge command. |
| Fast threshold testing | Prototype Sim Bridge SOC controls | NOS3 low-power docs mention manually setting SOC through Sim Bridge to trigger failsafe tests. | Availability and exact command shape must be verified in the pinned NOS3 checkout. | Extract target/command/args before any catalog row is added. |
| 6U compute power realism | Study/extend NOS3 hardware model/data providers | NOS3 simulator docs provide the native extension path for custom hardware models and data providers. | Adds code, OpenC3 dictionaries, test fixtures, and calibration burden. | Defer until first-slice command bridge proves stock EPS gaps are real blockers. |

What remains to verify locally:

- Confirm whether the running OpenC3 target is `GENERIC_EPS`, `GENERIC_EPS_RADIO`, or both; T6 uses `GENERIC_EPS`, while the NOS3 commissioning script example uses `GENERIC_EPS_RADIO`.
- Confirm actual runtime cadence, freshness, units, and limit behavior for `GENERIC_EPS_HK_TLM`.
- Confirm whether the pinned bench exposes Sim Bridge SOC commands and whether they are safe as manual-only test hooks.
- Confirm whether Command Sender marks `GENERIC_EPS_SWITCH_CC` or selected states as hazardous.
- Confirm the low-power procedure `PassSetupEPSCheck_LowPowerScen.rb` and any RTS tables do not differ from the pinned catalog version.

## Stock NOS3 Power Mechanisms

Use these mechanisms before inventing a Soteria-specific power model:

- `GENERIC_EPS GENERIC_EPS_HK_TLM` Packet Viewer telemetry for battery voltage, bus voltages, solar-array voltage/temperature, EPS/battery temperature, switch states, switch flags, and switch voltage/current.
- `GENERIC_EPS_RADIO GENERIC_EPS_HK_TLM BATT_VOLTAGE` from the commissioning scenario, or the local T6 equivalent `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_VOLTAGE`.
- `EPS_test.txt` in Telemetry Grapher for power level, switch state, and in-sun status during the low-power scenario.
- EPS switch telemetry, especially `SWITCH_7_STATE` and `SW_7_CURRENT` for the documented low-power switch 7 drain example.
- `<battery-charge-state>` under the EPS section of `cfg/sim/nos3-simulator.xml`; the NOS3 low-power scenario changes it from `1.0` to `0.65` to start at 65% charge.
- LC watchpoint table candidates such as `cfg/nos3_defs/tables/lc_def_wdt.c`.
- LC actionpoint table candidates such as `cfg/nos3_defs/tables/lc_def_adt.c`.
- SC/RTS table candidates such as `cfg/nos3_defs/tables/sc_rts*.c`, including the low-power scenario's reference RTS patterns.
- Sim Bridge SOC manipulation if the checked-out NOS3 version exposes it; keep it a test hook until catalogued.

## Minimum EPS State Model

These are the minimum state variables Soteria should store or derive for power-aware policy. `Stock source` means T6 has a source-backed packet/item or stock NOS3 config. `Extension required` means do not invent a packet/item; derive only inside an explicitly documented simulator model.

| Variable | Unit | First-slice source/status | Verifier or derivation |
| --- | --- | --- | --- |
| `orbit.in_sun` | boolean/int | Stock source | `SIM_42_TRUTH SIM_42_TRUTH_DATA IN_SUN`; used to interpret charging. |
| `solar_input_w` | W | Extension required or calibrated simulator derivation | Start as model input: `solar_power_w = f(IN_SUN, SA_VOLTAGE, optional future solar current/area config)`. Do not treat `SA_VOLTAGE` alone as power. |
| `battery_soc_frac` | 0..1 fraction | Config source for initial condition; live telemetry gap | `<battery-charge-state>` config and possible Sim Bridge controls. T6 marks live `power.battery_soc_pct` as `sim_extension_required`. |
| `battery_soc_pct` | percent | Derived from `battery_soc_frac` | `battery_soc_frac * 100`; only valid when the SOC model/source is approved. |
| `battery_voltage_v` | V | Stock source | `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_VOLTAGE`, fresh <= 10s. |
| `battery_current_a` | A | Extension required | Needed for a complete EPS model; do not infer from voltage alone. |
| `battery_temperature_c` | C | Stock source | `GENERIC_EPS GENERIC_EPS_HK_TLM BATT_TEMPERATURE`. |
| `main_bus_voltage_v` | V | Stock source by rails | Use `BUS_3P3V`, `BUS_5P0V`, `BUS_12V`; store per rail, and derive a display summary only if the UI labels it. |
| `main_bus_current_a` | A | Derived/extension required | Candidate first-slice derivation is sum of `SW_0_CURRENT..SW_7_CURRENT`; true main-bus current needs EPS model confirmation. |
| `solar_array_voltage_v` | V | Stock source | `GENERIC_EPS GENERIC_EPS_HK_TLM SA_VOLTAGE`. |
| `solar_array_current_a` | A | Extension required unless local dictionary exposes it | Required for true solar power; unresolved in T6. |
| `solar_array_temperature_c` | C | Stock source | `GENERIC_EPS GENERIC_EPS_HK_TLM SA_TEMPERATURE`. |
| `switches[n].state` | enum | Stock source | `SWITCH_0_STATE..SWITCH_7_STATE`, `ON=0xAA`, `OFF=0x00`. |
| `switches[n].flags` | enum/bitfield | Stock source | `SWITCH_0_FLAGS..SWITCH_7_FLAGS`; T6 treats non-healthy flags as faults. |
| `switches[n].voltage_v` | V | Stock source | `SW_0_VOLTAGE..SW_7_VOLTAGE`. |
| `switches[n].current_a` | A | Stock source | `SW_0_CURRENT..SW_7_CURRENT`; switch 7 current is the low-power drain verifier. |
| `loads[n].power_w` | W | Derived/extension required | `switch_voltage_v * switch_current_a` where a load-to-switch map exists; otherwise model-only. |
| `payload.power_state` | enum | Stock source | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED`, `ENABLED`/`DISABLED`. |
| `payload.power_w` | W | Extension required | Assign a simulator load only after calibration to EPS current changes or custom compute-payload model. |
| `radio.output_state` | route/counter state | Stock source | `CFS_RADIO TO_HKPACKET ENABLEDROUTES`, `CMDCOUNTER`, packet freshness. |
| `radio.power_w` | W | Extension required | Radio output commands affect comm posture; power draw must be calibrated or modeled. |
| `adcs.mode` | enum | Stock source | `GENERIC_ADCS GENERIC_ADCS_GNC MODE`, `PASSIVE`, `BDOT`, `SUNSAFE`, `INERTIAL`. |
| `adcs.power_w` | W | Extension required | First slice may use mode-based placeholder loads; custom model needed for wheel/actuator details. |
| `low_power_flag` | boolean | Soteria derived / LC spike | Derived from approved SOC/voltage thresholds and LC watchpoint status when available. |
| `safe_mode_flag` | boolean | Stock/future mixed | Candidate sources: `MGR_RADIO MGR_HK_TLM SPACECRAFT_MODE`, ADCS mode, and future LC/SC results. |
| `state_quality` | enum | Soteria derived | `fresh`, `partial`, `stale`, or `sim_extension_required` from T6 freshness rules. |

## Science And Engineering Check

| Claim | Verdict | Evidence and constraint | Practical implication |
| --- | --- | --- | --- |
| NOS3 can be the first power-simulation base. | Supported for simulator use | The STF-1 case study describes NOS3 as a software-only CubeSat simulation framework with hardware-component simulators, and the NOS3 low-power scenario exercises EPS telemetry, switch states, sunlight/eclipse context, and contingency logic. | Start with stock NOS3 EPS behavior and scenario configuration. |
| Stock NOS3 alone provides a complete Soteria 6U power model. | Not supported | T6 found source-backed voltage, temperature, and switch current items, but marked live SOC, compute payload power, and several bus/solar current fields as extension gaps. | Use stock telemetry for first-slice verification; add custom EPS/compute fields only where the gaps block real scenarios. |
| Battery voltage is enough to report SOC. | Contradicted for this plan | Voltage depends on chemistry, load, temperature, and model assumptions. T6 explicitly says not to infer SOC from voltage alone. | Treat SOC as config/model/Sim Bridge state until a source-backed EPS model exposes it. |
| A simple energy-balance overlay is plausible for simulator behavior. | Plausible but uncalibrated | The formula conserves energy at the Wh level and responds correctly to sunlight, loads, and load shedding. It is not validated against stock NOS3 telemetry yet. | Use it for tabletop policy tests, then calibrate against NOS3 or replace with a native EPS model. |

## Starter Energy Balance

This is simulator behavior, not a flight-qualified EPS model. Use it only to
make Soteria's state transitions plausible when stock NOS3 does not expose a
direct SOC or load-power signal.

```text
Pload_w = enabled_bus_loads_w
        + payload_load_w
        + radio_load_w
        + adcs_load_w
        + thermal_or_aux_load_w

Pnet_w = solar_power_w - Pload_w

SOCnext = clamp(
  SOCcurrent + (Pnet_w * dt_hours / battery_capacity_wh),
  0.0,
  1.0
)
```

Starter rules:

- Use stock telemetry where it exists: battery voltage, rail voltages, switch currents, switch states, and in-sun status.
- Treat `solar_power_w`, subsystem `*_load_w`, and `battery_capacity_wh` as scenario parameters until calibrated.
- Prefer measured `SW_n_CURRENT * SW_n_VOLTAGE` for mapped switch loads when a load-to-switch map exists.
- Never infer battery SOC from voltage alone without an approved voltage-to-SOC model.
- Store model fields as `simulator_model` or `soteria_derived`, not as stock NOS3 telemetry.

One-orbit plausibility tabletop:

| Step | Duration | Solar W | Load W | Net W | SOC start | SOC end | Interpretation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sunlight nominal | 60 min | 34 | 24 | +10 | 0.550 | 0.675 | Battery charges while in sun with payload/radio/adcs active. |
| Eclipse after load shed | 35 min | 0 | 14 | -14 | 0.675 | 0.573 | Battery discharges in eclipse, but shed loads keep SOC above the 0.40 safe-state threshold used in the NOS3 low-power scenario. |

Assumptions for the tabletop: `battery_capacity_wh = 80`, `dt_hours = minutes / 60`. These numbers are placeholders for simulator tuning; they are not spacecraft design parameters.

## Power-Relevant Command Catalog

The rows below are the only T10 power-relevant commands currently source-backed by T2. They can affect power state directly, indirectly, or by changing the posture that a Soteria power model uses.

| Catalog ID | Command class | Real OpenC3 command | Power role | Preconditions | Telemetry verifier | Timeout | Failure interpretation | Automation safety |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sample_enable` | Real NOS3/OpenC3 simulator command verified by T2 | `SAMPLE_RADIO SAMPLE_ENABLE_CC` | Enables the sample payload/device and may add payload load in the model. | `SAMPLE_RADIO` target present; sample HK fresh; scenario allows payload enable; EPS fresh if power posture matters. | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == ENABLED`; `CMD_COUNT` increments. | 15s | If enabled state does not change, command may not have reached Sample, Sample app may reject it, or telemetry may be stale. If EPS current unexpectedly rises beyond policy, mark postcondition failed for power-aware runs. | Automation allowed by catalog; require human review when current state is power-constrained. |
| `sample_disable` | Real NOS3/OpenC3 simulator command verified by T2 | `SAMPLE_RADIO SAMPLE_DISABLE_CC` | Disables the sample payload/device and is the first executable payload load-shed action. | `SAMPLE_RADIO` target present; sample HK fresh; disabling will not hide required verifier telemetry. | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == DISABLED`; `CMD_COUNT` increments; optional EPS verifier: mapped payload switch current or total switch-current sum trends down if calibrated. | 15s | If state remains enabled, command failed or telemetry is stale. If power telemetry does not improve, either payload load is not mapped to EPS currents, the model is wrong, or another load dominates. | Automation allowed by catalog; safe first-slice low-power action when preconditions are fresh. |
| `radio_enable_output` | Real NOS3/OpenC3 simulator command verified by T2 | `CFS_RADIO TO_ENABLE_OUTPUT` with `DEST_IP=radio-sim`, `DEST_PORT=5011` | Enables radio telemetry/output path; can add comms load in the model. | `CFS_RADIO` alias present; destination matches local NOS3 bench; OpenC3/UDP path private. | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` changes or radio packets become fresh; Command and Telemetry Server counters increase. | 10s | No fresh telemetry means destination/path mismatch, radio interface problem, or target alias mismatch. Bad destination is blocked. | Automation allowed for bench smoke; require review if changing long-running power posture. |
| `radio_disable_output` | Real NOS3/OpenC3 simulator command verified by T2 | `CFS_RADIO TO_DISABLE_OUTPUT` | Disables radio telemetry/output; may reduce comms load but can hide radio telemetry. | Operator or bridge confirms expected telemetry loss is acceptable and an alternate health path exists. | `CFS_RADIO TO_HKPACKET CMDCOUNTER` increments, `ENABLEDROUTES` changes, and radio output stops or goes stale as expected. | 10s | No counter increment means command failure. Unplanned telemetry loss outside radio path is a stop condition. | Automation allowed but human review required outside smoke tests. |
| `radio_resume_output` | Real NOS3/OpenC3 simulator command verified by T2 | `CFS_RADIO TO_RESUME_OUTPUT` | Restores radio telemetry/output after a pause or disable sequence where applicable. | Radio output previously enabled or paused; `CFS_RADIO` target expected. | `CFS_RADIO TO_HKPACKET CMDCOUNTER` increments and radio packets become fresh. | 10s | Counter not incrementing or packets not fresh means command/path failure or target mismatch. | Automation allowed. |
| `adcs_set_passive` | Real NOS3/OpenC3 simulator command verified by T2 | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `GNC_MODE=PASSIVE` | Moves ADCS to passive attitude behavior; may reduce pointing/actuator load but can harm charging attitude. | Operator/bridge confirms passive is intended; ADCS telemetry and truth visualization available; no pending command needs sun-safe hold. | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == PASSIVE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments. | 30s | Mode mismatch means rejected command, stale telemetry, or another controller changing mode. Charging may worsen if passive attitude reduces solar input. | Automation allowed with human review. |
| `adcs_set_sunsafe` | Real NOS3/OpenC3 simulator command verified by T2 | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `GNC_MODE=SUNSAFE_MODE` | Sets a sun-safe/charging-protection posture in the simulator. | Sun vector/sensor validity adequate or operator accepts demo limitation; ADCS telemetry fresh. | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == SUNSAFE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments; 42 view may show sun-safe pointing in sun. | 45s | Mode mismatch means command failure, stale telemetry, or scenario limitation such as eclipse/sun-vector availability. | Automation allowed with human review. |
| `eps_switch7_off_manual` | Real NOS3/OpenC3 simulator command verified by T2, manual-only | `GENERIC_EPS GENERIC_EPS_SWITCH_CC` with `SWITCH_NUMBER=SWITCH_7`, `STATE=OFF` | Direct switch-level power triage for the NOS3 low-power scenario's switch 7 drain. | Low-power scenario active; switch 7 verified unexpectedly on; operator confirms switch 7 is nonessential for this scenario; EPS telemetry fresh. | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_7_STATE == OFF`; `SW_7_CURRENT` decreases; `CMD_COUNT` increments. | 20s | If switch remains on, command rejected or wrong target/arg. If current does not decrease, mapping or telemetry is suspect. | Manual-only; not AI-executable. Command Sender hazardous behavior must be verified locally. |
| `eps_load_shed_policy` | Soteria high-level intent, unresolved | None | Generic load-shed policy such as "shed nonessential loads." | Blocked until Soteria/NOS3 maps loads to switches, allowed order, restore order, thresholds, and thermal/comms dependencies. | No generic verifier exists. Candidate after resolution: selected `SWITCH_n_STATE`, `SW_n_CURRENT`, bus/battery voltage/current fields. | n/a | Must reject as `blocked_unresolved_mapping`; do not substitute switch 7 or another switch from context. | Not executable manually or automatically from Soteria. |

## Manual And Automated Paths

Manual OpenC3 path:

1. Open OpenC3 over the private T1/T7 access path.
2. In Packet Viewer or Telemetry Grapher, capture fresh baseline telemetry for the relevant packet/item.
3. In Command Sender, choose the catalog target and packet. Do not use range-ignore, hazardous-bypass, or no-check modes.
4. Send only the catalog command and typed args. Preserve any hazardous prompt for operator review.
5. Verify using the same telemetry packet/items in this document and record before/after values.

Automated bridge path:

1. Agent or UI writes a Supabase command row with `catalog_version`, `catalog_command_id`, typed args, expiry, source, and idempotency key.
2. Bridge claims the row and resolves the target/command/args from the pinned catalog, not from agent-provided command text.
3. Bridge reads baseline telemetry with OpenC3 JSON API `tlm`.
4. Bridge sends exactly one standard OpenC3 JSON API `cmd` request.
5. Bridge polls the catalog verifier until success or timeout and writes `cubesat_command_results`.
6. Rows with `manual_only`, `unresolved`, missing approval, stale EPS telemetry, or failed preconditions stop before OpenC3.

The manual path and automated path must use the same catalog records. A command proven only in Command Sender is not bridge-executable until the catalog row allows automation and the verifier is mapped.

## Power Scenarios

### 1. Nominal Charging

Purpose: prove stock telemetry and the starter model show positive power balance during sunlight.

Procedure:

1. Start NOS3 in a nominal or configured in-sun segment.
2. Use Packet Viewer or JSON API to read `SIM_42_TRUTH ... IN_SUN`, `GENERIC_EPS ... BATT_VOLTAGE`, `BUS_3P3V`, `BUS_5P0V`, `BUS_12V`, `SA_VOLTAGE`, `SW_*_CURRENT`, and switch states.
3. Keep payload and radio in the planned scenario state. If enabling the sample payload, use `sample_enable`.
4. Compute `Pload_w` from approved model loads or mapped switch currents; compute `SOCnext` only when the model source is explicit.
5. Success: battery voltage remains healthy for the scenario, solar-array voltage and in-sun state are consistent with charging, and modeled SOC rises or remains power-positive.

Do not claim live SOC unless Sim Bridge or a future EPS model provides it.

### 2. Payload/Radio Load Shed

Purpose: use exact source-backed commands to reduce load without invoking unresolved generic EPS load shed.

Procedure:

1. Preconditions: EPS packet fresh, Sample HK fresh, radio path fresh or expected, current state shows low margin or operator-approved test.
2. Send `sample_disable` through Command Sender or the bridge.
3. Verify `DEVICE_ENABLED == DISABLED` and `CMD_COUNT` increments within 15s.
4. Optional, with review: send `radio_disable_output` only if expected telemetry loss is acceptable.
5. Verify `CFS_RADIO TO_HKPACKET CMDCOUNTER` and `ENABLEDROUTES` behavior within 10s.
6. Power verifier: compare `SW_*_CURRENT`, bus voltages, and battery voltage before/after. Use a calibrated mapping when available; otherwise state "payload/radio command succeeded, EPS power effect unresolved."

If an agent requests "turn off nonessential EPS loads" without a load-to-switch policy, reject `eps_load_shed_policy` before OpenC3.

### 3. Low-Power Safe-Mode Entry And Recovery

Purpose: reuse NOS3's low-power scenario to define the future safe-mode procedure while keeping bridge execution bounded.

Procedure:

1. Configure the low-power scenario with mission time/orbit changes and `<battery-charge-state> = 0.65` as described by NOS3.
2. Run `EPS_test.txt` and `PassSetupEPSCheck_LowPowerScen.rb`.
3. In Packet Viewer, inspect `GENERIC_EPS`; if switch 7 is unexpectedly on and drawing current, the operator may use `eps_switch7_off_manual`.
4. Verify `SWITCH_7_STATE == OFF`, `SW_7_CURRENT` decreases, and `CMD_COUNT` increments within 20s.
5. For future autonomous behavior, prototype LC watchpoint/actionpoint/RTS changes for the scenario thresholds: existing 60% science pause behavior and new 40% safe-state behavior. Keep these table changes outside bridge automation until approved.
6. Recovery restores loads in reviewed order: verify EPS stable, restore radio output if needed with `radio_resume_output` or `radio_enable_output`, return ADCS to the approved mode, then re-enable payload with `sample_enable` only after power-positive margins persist.

Recovery is not a single command. It is a reviewed procedure with staged telemetry checks.

## Power-Aware AI Policy Example

Input state:

- `state_quality == fresh`
- `GENERIC_EPS_HK_TLM` age <= 10s
- `battery_soc_frac` from approved simulator model is 0.43, trending down
- `orbit.in_sun == 0`
- `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == ENABLED`
- `CFS_RADIO TO_HKPACKET` fresh
- `GENERIC_ADCS GENERIC_ADCS_GNC MODE != SUNSAFE`

Policy:

1. Recommend or submit `sample_disable` first because it is catalog-backed, automation-allowed, and has a direct payload verifier.
2. Require human review before `radio_disable_output` because it intentionally affects telemetry output.
3. Require human review before `adcs_set_sunsafe`; send it only if sun-safe is meaningful for the current sun/eclipse context and ADCS telemetry is fresh.
4. Reject `eps_load_shed_policy` as `blocked_unresolved_mapping`; do not choose `SWITCH_7` unless the low-power switch 7 scenario preconditions are true and an operator is manually commanding it.
5. After each command, require verifier telemetry plus a power telemetry sample: battery voltage, bus rail voltages, switch currents, and state freshness.

Example accepted bridge row:

```json
{
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "catalog_command_id": "sample_disable",
  "args": {},
  "source": "ai_agent",
  "idempotency_key": "agent-low-power-20260621T120000Z-sample-disable",
  "required_state_fresh_after": "2026-06-21T11:59:50Z",
  "expires_at": "2026-06-21T12:01:00Z"
}
```

Example rejected bridge row:

```json
{
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "catalog_command_id": "eps_load_shed_policy",
  "args": {"intent": "shed_nonessential_loads"},
  "source": "ai_agent",
  "result": {
    "status": "rejected",
    "result_class": "blocked_unresolved_mapping",
    "openc3": null
  }
}
```

## Validation Performed

Tabletop payload disable:

1. Agent requests `sample_disable` with no raw OpenC3 target/command fields.
2. Bridge resolves catalog row to `SAMPLE_RADIO SAMPLE_DISABLE_CC`.
3. Bridge reads baseline `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED`, `CMD_COUNT`, and fresh EPS context.
4. Bridge sends standard OpenC3 JSON API `cmd`.
5. Bridge verifies `DEVICE_ENABLED == DISABLED` and `CMD_COUNT` increments within 15s.
6. Bridge stores power verifier context from `GENERIC_EPS_HK_TLM` before/after. If current mapping is not approved, result states that payload state changed but EPS load reduction is uncalibrated.

Tabletop rejected EPS load shed:

1. Agent requests "shed nonessential loads."
2. Product API maps the request to `eps_load_shed_policy`.
3. Bridge sees catalog status `unresolved` and rejects before OpenC3.
4. Result is `rejected / blocked_unresolved_mapping`; no `GENERIC_EPS_SWITCH_CC` command is sent.

One-orbit energy balance:

- With placeholder `battery_capacity_wh = 80`, `SOC0 = 0.55`, sunlight for 60 minutes at `solar_power_w = 34` and `Pload_w = 24` raises SOC to `0.675`.
- Eclipse for 35 minutes with loads shed to `Pload_w = 14` lowers SOC to `0.573`.
- The result is plausible for simulator behavior because sunlight charges, eclipse discharges, and load shed reduces eclipse drain. It remains a placeholder until calibrated against NOS3 telemetry or a custom EPS model.

Manual/automated path consistency:

- Manual path sends `SAMPLE_RADIO SAMPLE_DISABLE_CC` in Command Sender and checks `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED`.
- Automated path sends catalog ID `sample_disable`, resolves the same OpenC3 target/command, and checks the same verifier through JSON API.
- Both paths use the same T2 catalog record.

## Sufficiency And Extension Decision

Stock NOS3 is sufficient for the first-slice power simulation when the goal is:

- Operator-visible EPS telemetry and low-power diagnosis.
- Source-backed payload/radio/ADCS posture commands.
- Manual switch 7 triage in the documented low-power scenario.
- A simple Soteria energy-balance overlay clearly labeled as simulator-derived.
- Bridge-level rejection of generic load-shed intents until policy is approved.

Stock NOS3 is not sufficient by itself when the goal is:

- Live, source-backed battery SOC in Soteria state.
- Verified solar generation in watts.
- Verified main-bus current in amperes.
- Per-workload 6U compute power draw, job pause/resume, CPU throttling, checkpoint load, or thermal coupling.
- Automated generic load shedding across arbitrary loads.
- Space-weather-specific EPS, charging, radiation, or radio-link effects.

Future custom-component requirements:

- Add a NOS3-native `compute_payload` component with OpenC3 target definitions for `JOB_START`, `JOB_PAUSE`, `JOB_RESUME`, `JOB_CHECKPOINT`, and `SET_CPU_LIMIT` only after those commands exist in the command dictionary.
- Add explicit telemetry for compute load watts, CPU/GPU utilization, compute temperature, job state, and optional per-channel current.
- Add or extend EPS/data-provider behavior for battery SOC, battery current, solar current, solar input watts, and main-bus current.
- Define a load-to-switch map: load name, switch number, normal state, safe state, shed priority, restore order, thermal dependency, comms dependency, verifier packet/item, timeout, and review requirement.
- Add LC/SC/RTS table procedures only after a separate table-patching safety review; the AI bridge should not generate or send table patches from free-form policy.

## Remaining Risks

- The running bench may expose `GENERIC_EPS_RADIO` aliases differently from T6's `GENERIC_EPS` source mapping.
- Command Sender hazardous flags for EPS switch commands were not verified in this document.
- Sim Bridge SOC command availability and exact metadata remain unverified in the pinned checkout.
- Stock NOS3 switch currents may not correspond to Soteria's intended 6U compute loads without a load-to-switch map.
- The starter energy model is intentionally simple and must be calibrated before it drives user-facing confidence scores.
