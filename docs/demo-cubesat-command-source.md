# Demo CubeSat Command Source

Recommended demo target: NASA NOS3, the NASA Operational Simulator for Space
Systems. NOS3 is open source, CubeSat-derived, and built specifically for
software development, mission operations training, verification, validation,
and simulated spacecraft command/telemetry workflows.

## Why NOS3 Fits Soteria

NOS3 is the best fit for a truthful Soteria command demo because it has all of
the pieces that the current command-agent stubs are missing:

- A simulated spacecraft environment.
- cFS-based flight software.
- Ground software integrations, including COSMOS and Yamcs.
- 42 dynamics/environment simulation.
- Public scenario documentation with real command names.
- Public command-stack artifacts such as `gsw/LPT.ycs`.
- Operationally relevant scenarios for sun-safe mode, payload enable/disable,
  low power, radio output, ADCS control, and simulated device faults.

The important caveat is that this is a demo/simulator command source, not a
source of commands for an active spacecraft.

## Source-Backed Demo Commands

These command names are present in NOS3 docs or source artifacts and are useful
for Soteria's first command mapping.

| Soteria intent | NOS3 command or script line | Verifier telemetry or behavior |
| --- | --- | --- |
| Connectivity check | `/CFS/CMD/CFE_ES_NOOP` in Yamcs command stack, or `CFS CFE_ES_NOOP` in COSMOS | cFS command counter increments; FSW console prints NOOP event. |
| Enable radio telemetry | `cmd("CFS_RADIO TO_ENABLE_OUTPUT with DEST_IP 'radio-sim', DEST_PORT 5011")` | `CFS_RADIO` telemetry begins flowing through the radio path. |
| Disable radio telemetry | `cmd("CFS_RADIO TO_DISABLE_OUTPUT")` | Radio telemetry output stops; power-sensitive comm posture can be demonstrated. |
| Payload standby/off | `cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")` or `/SAMPLE/CMD/SAMPLE_DISABLE_CC` | Sample app telemetry and command counter update; payload is disabled. |
| Payload enable/on | `cmd("SAMPLE_RADIO SAMPLE_ENABLE_CC")` or `/SAMPLE/CMD/SAMPLE_ENABLE_CC` | Sample app telemetry becomes fresh; device-related telemetry updates. |
| Request EPS health | `/GENERIC_EPS/CMD/GENERIC_EPS_REQ_HK` | `/GENERIC_EPS/GENERIC_EPS_HK_TLM/*` updates, including battery voltage and temperature. |
| Set sun-safe attitude | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC with GNC_MODE SUNSAFE_MODE` | `GENERIC_ADCS` `MODE` reports sun-safe mode; 42 shows sun-safe pointing. |
| Set passive ADCS | `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC with GNC_MODE PASSIVE` | ADCS mode changes to passive; spacecraft begins to tumble in 42. |
| Power-load shedding | `GENERIC_EPS_SWITCH_CC` with `SwitchNumber` and `State = 0x00` in RTS tables | Target switch state changes; current draw decreases in EPS telemetry. |
| Simulated device fault | `SAMPLE_SIM_SET_STATUS` with a status value such as `5` through `SIM_CMD_BUS_BRIDGE` | Sample simulator reports changed status; FSW reports device disabled/status error. |
| Reaction wheel torque demo | `GENERIC_REACTION_WHEEL GENERIC_RW_SET_TORQUE_CC` | Spacecraft attitude changes in 42; reaction wheel telemetry updates. |

## Mapping Soteria Operations To NOS3

| Soteria operation | NOS3-backed command plan |
| --- | --- |
| `enter_safe_hold` | Disable sample payload, disable payload EPS switch, set ADCS to `SUNSAFE_MODE`, request EPS/ADCS housekeeping, optionally disable radio telemetry after verification. |
| `power_load_shed` | Request EPS housekeeping, disable nonessential switches using `GENERIC_EPS_SWITCH_CC`, disable sample payload, optionally disable radio telemetry output. |
| `payload_standby` | Send `SAMPLE_DISABLE_CC`, verify sample telemetry and command count. |
| `comm_resilience` | Enable radio telemetry with `TO_ENABLE_OUTPUT`, verify `CFS_RADIO` telemetry, then disable with `TO_DISABLE_OUTPUT` for a low-power posture. |
| `attitude_safe` | Use `GENERIC_ADCS_SET_MODE_CC` with `SUNSAFE_MODE`, verify `GENERIC_ADCS` mode and 42 visual state. |
| `simulate_fault` | Use `SAMPLE_SIM_SET_STATUS` through `SIM_CMD_BUS_BRIDGE` to force a sample-device fault and observe FSW response. |

## Recommended Demo Architecture

For the first demo, use NOS3 as a local simulator and command source:

```text
Soteria space-weather event
  -> command-agent operation: power_load_shed / enter_safe_hold
  -> NOS3 command mapping table
  -> COSMOS script lines or Yamcs command-stack JSON
  -> NOS3 simulator
  -> telemetry verification back into Soteria
```

The safest copy/paste output for the initial demo is a COSMOS procedure, because
NOS3's public scenarios already document script lines like:

```ruby
cmd("CFS_RADIO TO_ENABLE_OUTPUT with DEST_IP 'radio-sim', DEST_PORT 5011")
cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")
cmd("CFS_RADIO TO_DISABLE_OUTPUT")
```

For a more product-like demo, generate Yamcs command-stack JSON using command
paths from `gsw/LPT.ycs`, for example:

```json
{
  "type": "command",
  "name": "/SAMPLE/CMD/SAMPLE_DISABLE_CC",
  "extraOptions": [],
  "arguments": []
}
```

## First Implementation Slice

Add a `demo_nos3` command source behind `get_satellite_command`:

1. Normalize requested operation names such as `enter_safe_hold`,
   `power_load_shed`, `payload_standby`, and `comm_resilience`.
2. Return NOS3 command records with command name, ground-system format,
   arguments, and verifier telemetry.
3. Have `draft_satellite_command_plan` compose a COSMOS procedure or Yamcs
   command stack instead of generic prose.
4. Keep every output labeled as simulator-only unless a future real mission
   command source is explicitly configured.

## Sources

- [NASA NOS3 GitHub repository](https://github.com/nasa/nos3): open-source
  simulator suite, latest release, license, and repo health.
- [NOS3 documentation](https://nos3.readthedocs.io/en/latest/): user manual and
  scenario index.
- [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html):
  documented command examples for CFS NOOP, radio telemetry, sample component,
  ADCS passive mode, reaction wheel torque, and sun-safe mode.
- [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html):
  COSMOS scripting examples for radio enable/disable, sample payload
  enable/disable, and telemetry checks.
- [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html):
  low-power contingency scenario using EPS telemetry, switch state inspection,
  switch-off response, and safe-mode planning.
- [NOS3 STF-1 paper](https://arxiv.org/abs/1901.07583): describes NOS3 as a
  software-only simulation framework developed for the STF-1 3U CubeSat mission
  with cFS, 42, and COSMOS.
