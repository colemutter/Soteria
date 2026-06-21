# Satellite Command Tool Mapping

This report maps the draft satellite-command tools in
`src/backend/agent/tools.py` to the command-dictionary records needed to turn
operator intent into verifiable commands. It is not a flight procedure,
command dictionary, or uplink sequence by itself.

Important distinction: commands cannot be truthfully invented from an objective
such as "enter safe mode." Real copy-pasteable command lines must come from the
mission command database, such as a Yamcs MDB, XTCE database, SCOS/EGS-CC
database, vendor ICD, or operator-approved procedure set. Without that source,
the truthful output is a missing-data finding, not a made-up command.

Related local reference:
[NOAA API Mappings For Satellite Operation Protection](./noaa-satellite-protection-api-mappings.md).

## Current Tool Contract

`get_satellite_command` is registered as the MCP tool name, while the Python
function is named `get_satellite_commands`. It currently accepts:

```text
satellite_type: str
operation: str
```

Today it is a stub that returns `"Return redacted command here."` The intended
role should be to fetch approved command records for a satellite type and
operation from a mission-owned command source. It should return command names,
typed arguments, dry-run command lines, preconditions, verifiers, and approval
metadata only when those records exist in the command source. It should not
invent mnemonics, binary packets, authentication material, command link details,
frequencies, timing offsets, or bypass steps.

`draft_satellite_command_plan` currently accepts:

```text
satellite_id: str
objective: str
constraints: str
```

Today it is also a stub that returns `"Return draft command plan here."` The
intended role should be to compose a human-reviewable draft from approved
command records, the stated objective, and constraints. Every output should be
marked `DRAFT / HUMAN REVIEW REQUIRED`.

## What Counts As A Command

For this project, a useful command mapping should resolve high-level intent to
operator-verifiable command records:

```json
{
  "intent": "payload_standby",
  "command_source": "yamcs_mdb",
  "command_path": "/MISSION/PAYLOAD/SET_STANDBY",
  "arguments": {
    "payload_id": "CAMERA_A",
    "standby_mode": "SAFE"
  },
  "copy_paste_dry_run": "yamcs commands run --dry-run --processor realtime --arg payload_id=CAMERA_A --arg standby_mode=SAFE /MISSION/PAYLOAD/SET_STANDBY",
  "copy_paste_submit_for_review": null,
  "preconditions": [
    "operator has command authority",
    "spacecraft is in a mode where payload standby is allowed",
    "thermal constraints allow this payload state"
  ],
  "verifiers": [
    {
      "telemetry": "/MISSION/PAYLOAD/CAMERA_A/MODE",
      "expected": "STANDBY"
    }
  ],
  "approval_state": "requires_human_review"
}
```

The example paths above show the format of the mapping, not real spacecraft
commands. In production, `command_path`, argument names, allowed values, and
verifiers must be read from the mission command source.

If the source is Yamcs, the CLI supports listing, describing, dry-running, and
running commands. A truthful implementation should use these primitives:

```bash
yamcs commands list --format json
yamcs commands describe /MISSION/PAYLOAD/SET_STANDBY
yamcs commands run --dry-run --processor realtime --arg payload_id=CAMERA_A --arg standby_mode=SAFE /MISSION/PAYLOAD/SET_STANDBY
```

Dry-run is the default copy-paste target for Soteria-generated output. Any
non-dry-run command should be produced only after mission-specific approval
rules decide that the operator is allowed to submit it.

## Science Check

The mapping below rests on three evidence-backed claims.

| Claim | Verdict | Confidence | Notes |
| --- | --- | --- | --- |
| Safe-mode or safe-hold planning should prioritize spacecraft survival over mission productivity. | Supported | High | NASA Hubble safe-mode reporting shows science instruments entering safe mode, staged recovery of instruments, and continued operation of the rest of the spacecraft while engineers investigated. |
| Space weather can justify operator actions around attitude, tracking, radiation-sensitive payloads, and communications. | Supported | High | NOAA's scales explicitly list satellite surface charging, orientation issues, drag, tracking problems, memory effects, imaging noise, star-tracker issues, and solar-panel degradation. |
| A generic tool can recommend command families, but not exact commands, because safe responses are spacecraft-specific. | Supported | High | The same environment creates different hazards by orbit, payload, power state, attitude mode, shielding, and mission phase. Capella's "low drag mode" is a concrete LEO example, but it is not transferable as-is to every spacecraft. |
| Copy-pasteable commands can be generated safely only from an approved command database or simulator. | Supported | High | Yamcs, CCSDS Mission Operations, XTCE, SCOS, and EGS-CC all assume a mission-specific command/telemetry model rather than universal command names. |

## Operator Command Families

Use these as the high-level `operation` values or as normalized operation
families behind `get_satellite_command`. Each family must map to concrete
command records in the mission command source before it becomes copy-pasteable.

| Operation family | Operator intent | Typical command categories | Telemetry gates |
| --- | --- | --- | --- |
| `enter_safe_hold` | Preserve the spacecraft after an anomaly or severe forecasted exposure. | Mode transition to safe-hold or survival mode; inhibit payload activity; place ADCS in robust attitude mode; configure thermal survival rules; use robust communications path; increase health telemetry. | Mode state, attitude validity, battery state of charge, bus voltage/current, solar array current, key temperatures, command receiver lock, fault flags. |
| `payload_standby` | Stop vulnerable or nonessential mission activity while keeping the bus nominal. | Stop observations; park mechanisms; close or protect apertures if available; disable detector high voltage; suspend payload heaters only if thermal rules allow; preserve payload telemetry. | Payload mode, detector voltage/current, mechanism position, focal-plane temperature, data-recorder state, payload fault counters. |
| `power_load_shed` | Reduce load during low generation, battery stress, thermal stress, or conservative operations. | Disable nonessential payloads; reduce duty cycle for high-power devices; move radios to planned contact-only use when acceptable; switch optional heaters to thermostatic/survival control; defer high-power slews or burns. | Power balance, battery state of charge, bus voltage, load current by channel, solar array pointing/current, thermal margins. |
| `low_drag_or_storm_attitude` | Reduce LEO drag exposure or ADCS stress during high-density geomagnetic conditions. | Select mission-approved low-drag attitude; defer drag-expensive attitudes; avoid nonessential slews; pause precision pointing; update attitude constraints; increase ADCS telemetry. | Attitude mode, body rates, momentum wheel speeds, torque rod activity, drag-sensitive area proxy, orbit decay estimate, ephemeris freshness. |
| `radiation_protect` | Reduce damage or bad data during solar-radiation events. | Pause sensitive observations; power down or safe high-voltage detectors; increase EDAC and memory-scrub monitoring; delay software uploads and critical table changes; increase reset/latchup telemetry. | Proton/electron environment state, EDAC counters, reset counters, latchup/current trips, star-tracker status, payload noise indicators. |
| `charging_protect` | Reduce risk from surface or internal charging, especially in GEO/MEO or disturbed magnetospheric conditions. | Avoid sensitive switching; defer mechanism moves; defer critical commanding; keep payloads in benign electrical states; increase housekeeping cadence for currents and fault counters. | Differential/current monitors if available, bus current transients, payload current, fault protection counters, local time/eclipse state, electron flux context. |
| `comm_resilience` | Protect operations when radio blackout, scintillation, or contact reliability is degraded. | Prefer robust command windows; avoid critical uploads during expected link fades; repeat noncritical status checks; select approved lower-rate or higher-margin link profiles; reschedule contacts. | Receiver lock, frame error rate, Eb/N0 or equivalent link margin, command accept counters, ground-station contact status, onboard command queue state. |
| `orbit_determination_refresh` | Improve orbit knowledge when drag uncertainty increases. | Request fresh tracking; increase OD cadence; upload updated ephemeris or navigation products only through normal review; widen screening margins; rerun conjunction assessment. | Latest OD epoch, covariance, residuals, TLE age if used, conjunction screening status, propagated position uncertainty. |
| `resume_nominal` | Return from protective posture after the hazard or anomaly is understood. | Recover one subsystem at a time; restore payloads in staged order; clear inhibits only after review; return attitude and power modes to nominal; re-enable planned operations. | Hazard cleared, no new fault signatures, stable power/thermal margins, subsystem aliveness, successful limited functional checks. |

## Space Weather To Command Mapping

| Hazard driver | Main spacecraft risk | Operator-style protective mapping |
| --- | --- | --- |
| Geomagnetic storm, elevated Kp/G-scale, sustained southward Bz | LEO drag, orbit-prediction error, ADCS disturbance, surface charging, tracking issues. | `low_drag_or_storm_attitude`, `orbit_determination_refresh`, `charging_protect`, `comm_resilience`. Escalate to `enter_safe_hold` only when spacecraft flight rules or telemetry justify it. |
| Solar-radiation storm, elevated GOES proton flux/S-scale | Single-event upsets, memory problems, latchup, detector noise, star-tracker degradation, solar-array degradation. | `radiation_protect`, `payload_standby`, `comm_resilience`; defer critical uploads, table loads, irreversible mechanism moves, and high-value observations. |
| Energetic electron enhancement | Surface or deep dielectric charging, especially for GEO/MEO and eclipse/local-time-sensitive cases. | `charging_protect`; avoid sensitive switching and increase current/fault monitoring until the mission-specific threshold clears. |
| Radio blackout, ionospheric scintillation, TEC disturbance, high R-scale | Weak command/telemetry reliability, GNSS/navigation degradation, lost contacts. | `comm_resilience`; avoid interpreting link drops as spacecraft faults without environment context; increase navigation uncertainty where GNSS is used. |
| Low power or poor solar array geometry during any hazard | Battery depletion and thermal risk. | `power_load_shed`, then `enter_safe_hold` if margins continue to degrade. |

## Safe Mode Mapping

For a request like "put the satellite into safe mode", the tool should resolve
the safe-mode procedure to source-backed command records. If the command source
does not contain a safe-hold transition command, payload safing commands, and
their verifiers, the tool should return `unresolved` rather than a substitute.

| Plan section | Command mapping requirement |
| --- | --- |
| Objective | Transition the spacecraft to its mission-approved safe-hold or survival posture. |
| Preconditions | Confirm ground authority, current mode, power-positive or survival margins, valid attitude knowledge or safe acquisition path, contact duration, and no mission phase inhibit. |
| Required command records | Source-backed commands for payload standby, optional power load shedding, safe-hold mode transition, robust communications profile, and increased housekeeping telemetry. |
| Copy-paste output | Dry-run or review command lines generated from those command records, such as `yamcs commands run --dry-run ... <SOURCE_BACKED_COMMAND_PATH>`. |
| Sequencing guidance | Stop mission activity first, protect payload mechanisms or detectors, reduce nonessential loads, transition attitude/control mode, then confirm communications and power/thermal stability. |
| Hold criteria | Stable safe-hold mode, power positive, temperatures inside survival limits, command receiver available, no escalating fault signatures. |
| Exit criteria | Environment or anomaly cleared, root cause understood enough for recovery, recovery sequence reviewed, subsystem-by-subsystem aliveness checks complete. |

## Power Reduction Mapping

For a request like "scale down the power", the draft should distinguish load
shedding from full safe mode.

| Plan section | Command mapping requirement |
| --- | --- |
| Objective | Reduce power draw while preserving bus health and enough communications for monitoring. |
| Preconditions | Confirm battery state of charge, solar array generation, eclipse timing, thermal dependencies, and which loads are mission-critical. |
| Required command records | Source-backed commands to disable or standby selected payloads, reduce duty cycle for high-power devices, change optional heater policy, inhibit nonessential activities, or defer high-current operations. |
| Copy-paste output | Dry-run or review command lines generated from the command source, one command per load or mode transition, each with typed arguments and verifier telemetry. |
| Telemetry confirmation | Bus voltage/current, battery charge/discharge state, load-channel currents, solar array current, temperatures, heater state, payload standby status. |
| Recovery | Restore loads in priority order after power-positive margins are sustained and thermal limits remain healthy. |

## Space Weather Protection Mapping

For a request like "protect against a space weather event", the draft should
tie the command family to the hazard type instead of using one generic response.

| Event class | First-line command families | Avoid by default |
| --- | --- | --- |
| G1-G2 geomagnetic storm | Increase monitoring, refresh orbit products, review ADCS margins, prepare low-drag posture if LEO and mission-approved. | Full safe mode unless telemetry or flight rules require it. |
| G3-G5 geomagnetic storm | Low-drag or storm attitude for LEO assets if approved; wider conjunction screening; ADCS and charging monitoring; defer nonessential slews and burns. | Precision attitude modes that increase drag or ADCS stress without operational need. |
| S2-S3 radiation storm | Payload standby for sensitive detectors, EDAC/latchup monitoring, defer critical uploads, consider star-tracker robustness checks. | Critical software/table loads and high-value detector operations during peak flux. |
| S4-S5 radiation storm | Strong radiation-protect posture, payload safeing, critical-command deferral, enhanced health telemetry, possible safe-hold if mission flight rules call for it. | Treating noisy sensors or trackers as ordinary hardware faults without checking the environment. |
| R-scale radio blackout or scintillation | Robust link scheduling, contact rescheduling, lower-rate/higher-margin profiles if approved, GNSS uncertainty increase. | Time-critical command plans that depend on marginal links. |

## Recommended `get_satellite_command` Response Shape

The command lookup tool should return structured command records when the
mission source contains them. It should fail closed when it cannot resolve a
real command.

```json
{
  "operation": "radiation_protect",
  "satellite_type": "generic_leo_imager",
  "command_source": {
    "type": "yamcs_mdb",
    "instance": "simulator",
    "version": "operator-controlled"
  },
  "allowed_use": "dry_run_or_human_review",
  "resolved_commands": [
    {
      "intent": "payload_standby",
      "command_path": "/MISSION/PAYLOAD/SET_STANDBY",
      "arguments": {
        "payload_id": "CAMERA_A",
        "standby_mode": "SAFE"
      },
      "copy_paste_dry_run": "yamcs commands run --dry-run --processor realtime --arg payload_id=CAMERA_A --arg standby_mode=SAFE /MISSION/PAYLOAD/SET_STANDBY",
      "verifiers": [
        {
          "telemetry": "/MISSION/PAYLOAD/CAMERA_A/MODE",
          "expected": "STANDBY"
        }
      ]
    }
  ],
  "required_prechecks": [
    "confirm current spacecraft mode",
    "confirm power and thermal margins",
    "confirm contact window and authority"
  ],
  "unresolved_commands": [],
  "not_included": [
    "binary packets",
    "credentials",
    "frequencies",
    "bypass procedures"
  ]
}
```

If no mission command source is available, return:

```json
{
  "operation": "radiation_protect",
  "status": "unresolved",
  "reason": "No mission command database is configured.",
  "required_source": "Yamcs MDB, XTCE, SCOS/EGS-CC database, vendor ICD, or approved procedure set",
  "safe_fallback": "Return operator intent and required command families, but do not emit copy-pasteable commands."
}
```

## Recommended `draft_satellite_command_plan` Output Shape

The planning tool should compose the final plan from resolved command records.
Every command line should be traceable to the command source and should include
verifier telemetry.

```json
{
  "label": "DRAFT / HUMAN REVIEW REQUIRED",
  "satellite_id": "SAT-EXAMPLE",
  "objective": "Protect spacecraft during S3 radiation storm watch",
  "command_source": {
    "type": "yamcs_mdb",
    "instance": "simulator"
  },
  "assumptions": [
    "resolved commands are present in the configured command source",
    "operator will validate against mission flight rules"
  ],
  "plan": [
    {
      "phase": "precheck",
      "actions": [
        "confirm current mode, power, thermal, communications, and fault status",
        "confirm event source and severity"
      ],
      "commands": []
    },
    {
      "phase": "protect",
      "actions": [
        "place sensitive payloads in standby"
      ],
      "commands": [
        {
          "intent": "payload_standby",
          "copy_paste_dry_run": "yamcs commands run --dry-run --processor realtime --arg payload_id=CAMERA_A --arg standby_mode=SAFE /MISSION/PAYLOAD/SET_STANDBY",
          "verifier": "/MISSION/PAYLOAD/CAMERA_A/MODE == STANDBY"
        }
      ]
    },
    {
      "phase": "monitor",
      "actions": [
        "track EDAC counters, reset counters, detector noise, star-tracker state, and power margins"
      ],
      "commands": []
    },
    {
      "phase": "recover",
      "actions": [
        "resume subsystems one at a time after event clearance and human review"
      ],
      "commands": []
    }
  ],
  "not_included": [
    "binary uplink packets",
    "credentials",
    "frequencies",
    "bypass procedures"
  ]
}
```

## Implementation Notes

- Keep `get_satellite_command` as a lookup of approved command records from a
  command source. Keep `draft_satellite_command_plan` as a composer of
  command-stack drafts.
- Add a configured command source before expecting command output. Acceptable
  sources include Yamcs MDB/API, XTCE, SCOS/EGS-CC exports, vendor ICDs, or
  operator-approved procedure files.
- Fail closed when a high-level operation cannot be resolved to source-backed
  command records. Do not substitute invented command paths.
- Normalize operation names to a controlled vocabulary such as
  `enter_safe_hold`, `power_load_shed`, `radiation_protect`,
  `charging_protect`, `low_drag_or_storm_attitude`, `comm_resilience`,
  `orbit_determination_refresh`, and `resume_nominal`.
- Require the draft plan to list assumptions, prechecks, telemetry gates,
  hold criteria, abort criteria, and recovery criteria.
- Always separate environmental evidence from command recommendations.
- Treat NOAA G/S/R scales as public severity context, not as direct flight
  rules. Mission flight rules and approved command dictionaries remain the
  authority.
- Generate copy-pasteable dry-run or review commands only when the mission
  command source provides exact command names, arguments, and verifiers.
- Do not generate binary packet formats, authentication flows, ground-station
  routing, or bypass steps.

## Sources

- [NOAA Space Weather Scales](https://www.spaceweather.gov/noaa-scales-explanation):
  G-scale, S-scale, and R-scale operational impact language for spacecraft,
  communications, navigation, drag, charging, memory effects, imaging noise,
  and star-tracker issues.
- [NOAA Satellite Drag](https://www.spaceweather.gov/impacts/satellite-drag):
  explanation of LEO drag increases during solar activity and geomagnetic
  storms, including orbit-prediction implications.
- [NOAA Satellite Communications](https://www.spaceweather.gov/impacts/satellite-communications):
  ionospheric effects on satellite communication links, including group delay,
  phase advance, attenuation, and scintillation.
- [NASA Returns Hubble to Full Science Operations](https://science.nasa.gov/missions/hubble/nasa-returns-hubble-to-full-science-operations/):
  concrete example of instruments entering safe mode, staged recovery, ground
  testing, and cautious return to science operations.
- [Doing Battle with the Sun: Lessons From LEO and Operating a Satellite
  Constellation in the Elevated Atmospheric Drag Environment of Solar Cycle
  25](https://arxiv.org/abs/2406.08342): operator example of a low-drag mode
  response to elevated atmospheric drag.
- [Satellite Drag Analysis During the May 2024 Gannon Geomagnetic Storm](https://arxiv.org/abs/2406.08617):
  peer-reviewed analysis of the May 2024 storm's LEO drag and orbit-safety
  implications.
- [Satellite orbital drag during magnetic storms](https://arxiv.org/abs/1910.09622):
  research basis for storm-time drag effects, altitude dependence, and orbit
  prediction uncertainty.
- [Yamcs command-line interface](https://docs.yamcs.org/yamcs-cli/yamcs_commands/):
  command listing, command description, command execution, and dry-run command
  validation interface.
- [Yamcs Python TM/TC processing](https://docs.yamcs.org/python-yamcs-client/tmtc/):
  examples of issuing commands, monitoring acknowledgments, and verifying
  command completion against a processor.
- [CCSDS Mission Operations Services Concept](https://public.ccsds.org/Pubs/520x0g3.pdf):
  spacecraft monitoring, control, scheduling, and mission-operations service
  concepts.
- [OMG XTCE specification](https://www.omg.org/spec/XTCE/):
  standard command and telemetry metadata exchange format.
