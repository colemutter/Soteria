# CubeSat OpenC3 Operator Command Runbook

Generated: 2026-06-21

This runbook proves the manual operator path for a stock NOS3-backed CubeSat simulation using OpenC3/COSMOS 5 Command Sender and telemetry tools. It is simulator-only. It does not define flight operations, spacecraft command authority, Supabase queue behavior, or AI command policy.

Runtime status: this agent did not launch NOS3 or OpenC3. Execute the bench checklist below on the NOS3/OpenC3 bench before treating the procedure as demonstrated.

## Source Basis

| Source | Operator-relevant fact used here |
| --- | --- |
| [T1 bench runbook](cubesat-nos3-openc3-bench-runbook.md) | Use the stock NOS3 `v1_07_04` bench with `gsw = openc3`; access OpenC3 only through a private tunnel to `http://localhost:2900`; do not expose OpenC3 or cFS/NOS3 UDP ports publicly. |
| [T2 command catalog](cubesat-openc3-command-catalog.md) | Provides the exact target, command, argument, verifier telemetry, timeout, and status for every executable command in this smoke sequence. |
| [Task portfolio](../agents/cubesat-nos3-openc3-commanding-subtasks.md) | T3 must prove the manual Command Sender path before any automated bridge path. |
| [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender) | Command Sender selects commands through target and packet dropdowns, generates parameter fields, updates Status and Command History after sends, and prompts before hazardous commands. |
| [OpenC3 Packet Viewer](https://docs.openc3.com/docs/tools/packet-viewer) | Packet Viewer shows live telemetry values for selected target, packet, and item definitions, including stale/limit coloring. |
| [OpenC3 Telemetry Viewer](https://docs.openc3.com/docs/tools/tlm-viewer) | Telemetry Viewer can display target-owned screens or packet-generated screens for live telemetry inspection. |
| [OpenC3 Command and Telemetry Server](https://docs.openc3.com/docs/tools/cmd-tlm-server) | Use interfaces, targets, command packets, telemetry packets, byte counts, packet counts, and logs to diagnose command/telemetry flow. |
| [OpenC3 cFS guide](https://docs.openc3.com/docs/guides/cfs) | cFS/OpenC3 integrations use target definitions and UDP telecommand/telemetry interfaces; local OpenC3 access is documented at `http://localhost:2900`. |
| [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html) | Demonstrates `CFS CFE_ES_NOOP`, Packet Viewer verification, sample NOOP, and `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `PASSIVE` and `SUNSAFE_MODE`. |
| [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html) | Demonstrates radio enable with `CFS_RADIO TO_ENABLE_OUTPUT` using `DEST_IP 'radio-sim'` and `DEST_PORT 5011`, plus `SAMPLE_RADIO SAMPLE_ENABLE_CC` and `SAMPLE_RADIO SAMPLE_DISABLE_CC`. |

## Operator Safety Rules

- Send only commands listed in the T2 catalog with `manual_allowed = true` and non-`unresolved` status.
- Use the exact target, command, argument names, and argument values in this runbook.
- Preserve OpenC3 hazardous-command prompts. If a prompt appears, read it, confirm it matches the catalog row and current test objective, then manually accept or cancel. Do not bypass it.
- Do not enable Command Sender modes that ignore range checking, show hidden ignored fields for editing, or disable conversions during this smoke test.
- Do not use no-check command variants, direct UDP command injection, custom scripts, raw packet injection, or Command History edits to create commands that are not catalog-backed.
- Do not share a public OpenC3 URL, VM IP, screenshots with credentials, cookies, tokens, or first-run passwords.
- Do not execute unresolved catalog entries, including generic EPS load-shed, generic radiation protection, or future compute-payload commands.

## Prerequisites

1. Complete the T1 bench setup through `make launch` on the NOS3 bench host.
2. Confirm `cfg/nos3-mission.xml` has `gsw` set to `openc3`.
3. Confirm the checked-out NOS3 tag is `v1_07_04` and the T2 catalog version is `nos3-openc3-v1_07_04-cmdcat.20260621`.
4. Confirm OpenC3 target lists include `CFS`, `CFS_RADIO`, `SAMPLE`, `SAMPLE_RADIO`, and `GENERIC_ADCS`.
5. Open Packet Viewer or Telemetry Viewer and confirm at least one fresh cFS/NOS3 telemetry packet before sending commands.

If any required target or packet is missing, stop. Do not substitute similar target names.

## Private OpenC3 Access

From the operator workstation, open a private IAP SSH tunnel to the bench VM:

```bash
export PROJECT_ID="<gcp-project-id>"
export ZONE="us-central1-a"
export VM_NAME="soteria-nos3-bench"

gcloud config set project "${PROJECT_ID}"
gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" \
  --tunnel-through-iap \
  -- -L 2900:localhost:2900
```

Open the UI from the same workstation:

```text
http://localhost:2900
```

If local port `2900` is already in use, forward another local port and keep the VM side at `localhost:2900`:

```bash
gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" \
  --tunnel-through-iap \
  -- -L 12900:localhost:2900
```

Then browse to:

```text
http://localhost:12900
```

If OpenC3 asks for first-run credentials or login, use bench credentials stored in the operator password manager. Do not record credentials in this repository.

## UI Setup

1. Open Command Sender.
2. Open Packet Viewer in a second tab or window.
3. Open Command and Telemetry Server in a third tab or window for byte counts, packet counts, target/interface status, and log messages.
4. For each command, preselect the verifier target and packet in Packet Viewer before pressing Send.
5. Record the before value, send the command, wait only up to the listed timeout, then record the after value and Command Sender Status text.

Expected Command Sender feedback for a successful send is a Status update plus a Command History entry. A telemetry verifier is still required; UI "sent" does not by itself prove simulator effect.

## Catalog Confirmation

All executable smoke commands below are present in the T2 catalog.

| Catalog ID | Status | Target / command | Args | Primary verifier |
| --- | --- | --- | --- | --- |
| `cfs_noop` | `automation_allowed` | `CFS` / `CFE_ES_NOOP` | none | `CFS CFE_ES_HKPACKET CMDCOUNTER` increments |
| `radio_enable_output` | `automation_allowed` | `CFS_RADIO` / `TO_ENABLE_OUTPUT` | `DEST_IP=radio-sim`, `DEST_PORT=5011` | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` changes or radio packets become fresh |
| `sample_noop` | `automation_allowed` | `SAMPLE` / `SAMPLE_NOOP_CC` | none | `SAMPLE SAMPLE_HK_TLM CMD_COUNT` increments |
| `sample_enable` | `automation_allowed` | `SAMPLE_RADIO` / `SAMPLE_ENABLE_CC` | none | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == ENABLED` |
| `sample_disable` | `automation_allowed` | `SAMPLE_RADIO` / `SAMPLE_DISABLE_CC` | none | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == DISABLED` |
| `adcs_set_passive` | `automation_allowed_with_review` | `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE=PASSIVE` | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == PASSIVE` |
| `adcs_set_sunsafe` | `automation_allowed_with_review` | `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE=SUNSAFE_MODE` | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == SUNSAFE` |

Minimum acceptance for a first operator pass is three successful commands: `CFS CFE_ES_NOOP`, `CFS_RADIO TO_ENABLE_OUTPUT`, and `SAMPLE SAMPLE_NOOP_CC`. Continue through the full smoke sequence when those pass.

## Manual Smoke Sequence

| Step | Command Sender action | Expected UI feedback | Telemetry verifier | Timeout | Failure interpretation |
| --- | --- | --- | --- | --- | --- |
| 1 | Select target `CFS`, packet `CFE_ES_NOOP`, leave generated/default fields unchanged, send. | Status text updates and Command History records `CFS CFE_ES_NOOP`. If a hazardous prompt appears unexpectedly, cancel and investigate. | `CFS CFE_ES_HKPACKET CMDCOUNTER` increments, or the FSW console reports the NOOP event. | 10s | No counter or event means the cFS target is stale, the wrong packet was watched, the interface is not mapped, or cFS did not receive the command. A command error means stop and inspect logs before retrying. |
| 2 | Select target `CFS_RADIO`, packet `TO_ENABLE_OUTPUT`, set `DEST_IP` to `radio-sim` and `DEST_PORT` to `5011`, send. | Status text updates, Command History records both arguments, and Command and Telemetry Server byte/packet counters should begin moving for the radio path. | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` changes, or radio packets become fresh; Command and Telemetry Server byte counters increase. | 10s | No fresh radio telemetry means the destination is wrong, the radio interface is disconnected, the target alias is missing, or the bench network is not matching the catalog. Any destination other than `radio-sim:5011` is blocked for this runbook. |
| 3 | Select target `SAMPLE`, packet `SAMPLE_NOOP_CC`, leave generated/default fields unchanged, send. | Status text updates and Command History records `SAMPLE SAMPLE_NOOP_CC`. | `SAMPLE SAMPLE_HK_TLM CMD_COUNT` increments and `CMD_ERR_COUNT` stays unchanged. | 10s | No counter means the Sample app/target is not receiving commands or the wrong telemetry packet is selected. `CMD_ERR_COUNT` changing means the command was rejected or malformed. |
| 4 | Select target `SAMPLE_RADIO`, packet `SAMPLE_ENABLE_CC`, leave generated/default fields unchanged, send. | Status text updates and Command History records `SAMPLE_RADIO SAMPLE_ENABLE_CC`. | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == ENABLED`; `CMD_COUNT` increments; sample data becomes fresh. | 15s | If `DEVICE_ENABLED` remains disabled, the sample simulator or radio path is not communicating, the command was rejected, or the scenario state does not allow payload enable. |
| 5 | Select target `SAMPLE_RADIO`, packet `SAMPLE_DISABLE_CC`, leave generated/default fields unchanged, send. | Status text updates and Command History records `SAMPLE_RADIO SAMPLE_DISABLE_CC`. | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == DISABLED`; `CMD_COUNT` increments; sample data may stop or become stale as expected. | 15s | If the device remains enabled, the command did not reach the app or was rejected. If unrelated telemetry disappears, stop and check whether radio output or the wrong target was affected. |
| 6 | Select target `GENERIC_ADCS`, packet `GENERIC_ADCS_SET_MODE_CC`, set `GNC_MODE` to `PASSIVE`, send after operator review. | Status text updates and Command History records `GNC_MODE PASSIVE`. If OpenC3 shows a hazardous prompt, preserve it and accept only after confirming this row. | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == PASSIVE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments; 42 visual may show tumbling. | 30s | Mode mismatch means the command was rejected, ADCS telemetry is stale, or another control loop changed the mode. Treat any unexpected hazardous prompt as a review stop. |
| 7 | Select target `GENERIC_ADCS`, packet `GENERIC_ADCS_SET_MODE_CC`, set `GNC_MODE` to `SUNSAFE_MODE`, send after operator review. | Status text updates and Command History records `GNC_MODE SUNSAFE_MODE`. If OpenC3 shows a hazardous prompt, preserve it and accept only after confirming this row. | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == SUNSAFE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments; 42 visual should show sun-safe pointing when in sun. | 45s | Mode mismatch means command rejection, stale telemetry, or a scenario limitation such as eclipse/sun-vector availability. If the counter increments but attitude visual does not change, record the telemetry result and scenario lighting state. |

## Failed Or Mistyped Command Recovery

Use this recovery path before retrying anything:

1. If the command has not been sent, cancel or reselect the target and packet. Do not rely on edited Command History text for first-slice proof.
2. Compare the Command Sender target, packet, and arguments against the Catalog Confirmation table.
3. If OpenC3 Status reports an error, capture the status text, Command History line, target, packet, arguments, and any Command and Telemetry Server log entry.
4. If telemetry does not change before timeout, refresh Packet Viewer, reselect the exact verifier packet, check whether values are stale, and inspect Command and Telemetry Server byte/packet counters.
5. Retry once only after a concrete cause is corrected, such as wrong selected packet, disconnected interface, or stale viewer. Do not retry by enabling no-check or range-ignore modes.
6. If the wrong catalog-backed command was sent, record it as a bench deviation. Use an explicit catalog-backed corrective command only when the corrective action is obvious and operator-approved, such as `SAMPLE_RADIO SAMPLE_DISABLE_CC` after an unintended sample enable.
7. If recovery is unclear, stop the smoke sequence, preserve notes, and restart the NOS3/OpenC3 stack using the T1 stop/restart procedure before another run.

## Bench Execution Checklist

- [ ] OpenC3 reached only through IAP/VPN/SSH private access and a localhost browser URL.
- [ ] No public firewall rule or shared URL exposes OpenC3, cFS UDP, NOS3 simulator, or radio ports.
- [ ] OpenC3 target list includes `CFS`, `CFS_RADIO`, `SAMPLE`, `SAMPLE_RADIO`, and `GENERIC_ADCS`.
- [ ] Packet Viewer or Telemetry Viewer shows fresh telemetry before first command.
- [ ] Command and Telemetry Server shows relevant targets/interfaces connected.
- [ ] `CFS CFE_ES_NOOP` sent and `CFS CFE_ES_HKPACKET CMDCOUNTER` incremented within 10 seconds.
- [ ] `CFS_RADIO TO_ENABLE_OUTPUT` sent with only `DEST_IP=radio-sim` and `DEST_PORT=5011`; radio telemetry became fresh or `TO_HKPACKET ENABLEDROUTES` changed within 10 seconds.
- [ ] `SAMPLE SAMPLE_NOOP_CC` sent and `SAMPLE SAMPLE_HK_TLM CMD_COUNT` incremented within 10 seconds.
- [ ] `SAMPLE_RADIO SAMPLE_ENABLE_CC` sent and `DEVICE_ENABLED == ENABLED` within 15 seconds.
- [ ] `SAMPLE_RADIO SAMPLE_DISABLE_CC` sent and `DEVICE_ENABLED == DISABLED` within 15 seconds.
- [ ] `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `PASSIVE` sent only after operator review; `GENERIC_ADCS_GNC MODE == PASSIVE` within 30 seconds.
- [ ] `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `SUNSAFE_MODE` sent only after operator review; `GENERIC_ADCS_GNC MODE == SUNSAFE` within 45 seconds.
- [ ] Any hazardous prompts were preserved, read, and accepted or canceled manually.
- [ ] No no-check variants, direct UDP injection, unresolved commands, or public URLs were used.
- [ ] Results, failures, screenshots, and deviations were stored without credentials or sensitive browser state.

## Manual Smoke-Test Result Notes

Use this template during bench execution:

```text
Bench date/time:
Operator:
NOS3 tag:
NOS3 full SHA:
OpenC3 access method:
Browser URL observed:
Command catalog version:

Preflight telemetry:
- CFS packet/item/timestamp:
- Radio packet/item/timestamp:
- Sample packet/item/timestamp:
- ADCS packet/item/timestamp:

Command results:
1. CFS CFE_ES_NOOP
   Before verifier:
   After verifier:
   Command Sender Status:
   Result:
   Notes/screenshot reference:

2. CFS_RADIO TO_ENABLE_OUTPUT DEST_IP=radio-sim DEST_PORT=5011
   Before verifier:
   After verifier:
   Command Sender Status:
   Result:
   Notes/screenshot reference:

3. SAMPLE SAMPLE_NOOP_CC
   Before verifier:
   After verifier:
   Command Sender Status:
   Result:
   Notes/screenshot reference:

4. SAMPLE_RADIO SAMPLE_ENABLE_CC
   Before verifier:
   After verifier:
   Command Sender Status:
   Result:
   Notes/screenshot reference:

5. SAMPLE_RADIO SAMPLE_DISABLE_CC
   Before verifier:
   After verifier:
   Command Sender Status:
   Result:
   Notes/screenshot reference:

6. GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC GNC_MODE=PASSIVE
   Before verifier:
   After verifier:
   Command Sender Status:
   Hazard prompt observed:
   Result:
   Notes/screenshot reference:

7. GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC GNC_MODE=SUNSAFE_MODE
   Before verifier:
   After verifier:
   Command Sender Status:
   Hazard prompt observed:
   Result:
   Notes/screenshot reference:

Failures/deviations:
Recovery actions:
Open items for bridge agents:
```

## Handoff Notes For Later Agents

Packet names and items needed by automation and telemetry follow-on agents:

| Purpose | Target | Packet | Items |
| --- | --- | --- | --- |
| cFS command aliveness | `CFS` | `CFE_ES_HKPACKET` | `CMDCOUNTER` |
| Radio output | `CFS_RADIO` | `TO_HKPACKET` | `ENABLEDROUTES`, `CMDCOUNTER` |
| Sample app aliveness | `SAMPLE` | `SAMPLE_HK_TLM` | `CMD_COUNT`, `CMD_ERR_COUNT` |
| Sample device state | `SAMPLE_RADIO` | `SAMPLE_HK_TLM` | `DEVICE_ENABLED`, `CMD_COUNT` |
| ADCS mode | `GENERIC_ADCS` | `GENERIC_ADCS_GNC` | `MODE` |
| ADCS command counter | `GENERIC_ADCS` | `GENERIC_ADCS_HK_TLM` | `CMD_COUNT` |

No OpenC3 UI screenshots were captured by this agent because the bench was not executed here. During execution, capture redacted screenshots of Command Sender history and Packet Viewer verifiers only when they contain no credentials, tokens, cookies, private URLs beyond localhost, or sensitive project details.
