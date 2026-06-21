# CubeSat OpenC3 Validation Plan

Generated: 2026-06-21

This validation plan is simulator-only. It applies only to the stock
NOS3-backed CubeSat simulation connected through OpenC3/COSMOS 5 and Soteria's
future bridge. It is not a flight validation plan, flight command procedure,
spacecraft command authority, RF uplink path, or claim of flight qualification.

Runtime status: this T9 task did not launch NOS3, OpenC3, Supabase migrations,
or a bridge worker. The checks below are future implementation gates that must
pass before Soteria treats the NOS3/OpenC3 simulator as a usable command target.

## Source Basis

Local artifacts reviewed:

- [CubeSat NOS3 OpenC3 Bench Runbook](./cubesat-nos3-openc3-bench-runbook.md)
- [CubeSat OpenC3/NOS3 Command Catalog](./cubesat-openc3-command-catalog.md)
- [CubeSat OpenC3 Operator Command Runbook](./cubesat-openc3-operator-command-runbook.md)
- [CubeSat OpenC3 Automation Decision](./cubesat-openc3-automation-decision.md)
- [CubeSat OpenC3 Bridge Contract](./cubesat-openc3-bridge-contract.md)
- [CubeSat OpenC3 Telemetry State Map](./cubesat-openc3-telemetry-state-map.md)
- [CubeSat OpenC3 GCP Access Plan](./cubesat-openc3-gcp-access-plan.md)
- [CubeSat OpenC3 End-To-End Scenarios](./cubesat-openc3-end-to-end-scenarios.md)
- [CubeSat Power-System Simulation And Commands](./cubesat-power-system-simulation-and-commands.md)
- [Satellite Command Tool Mapping](./satellite-command-tool-mapping.md)
- [CubeSat NOS3 Command Evidence](./cubesat-nos3-command-evidence.md)

Official source links used by the local artifacts:

- [NOS3 Getting Started](https://nos3.readthedocs.io/en/latest/NOS3_Getting_Started.html)
- [NOS3 Ground Software](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html)
- [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html)
- [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html)
- [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html)
- [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api)
- [OpenC3 Scripting API](https://docs.openc3.com/docs/guides/scripting-api)
- [OpenC3 Streaming API](https://docs.openc3.com/docs/development/streaming-api)
- [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender)
- [OpenC3 Packet Viewer](https://docs.openc3.com/docs/tools/packet-viewer)
- [OpenC3 Security](https://docs.openc3.com/docs/getting-started/security)

## Readiness Rule

Soteria may treat the simulator as a usable command target only after every P0
gate in this plan passes with saved evidence. P1 gates may be waived only for a
time-boxed bench run, with a named owner, expiry date, and rollback control.

Passing a gate means both the command path and the evidence path work. A command
is not successful merely because OpenC3 says it was sent; success also requires
the catalog telemetry verifier and the Soteria result/audit record where the
automated bridge is involved.

## Evidence Rules

Capture enough evidence to prove the result without leaking authority:

- Use correlation IDs across Supabase rows, bridge logs, OpenC3 JSON-RPC IDs,
  OpenC3 Command History, and telemetry windows.
- Preserve before/after telemetry samples for every command verifier.
- Redact OpenC3 tokens, cookies, passwords, Authorization headers, Supabase
  service-role keys, VM credentials, Secret Manager values, and browser local
  storage.
- Store manual smoke screenshots or notes only when they contain no credentials
  and no public command endpoint.
- Record failures as first-class evidence, not as overwritten notes.

## Validation Gates

| Gate | Priority | Type | Pass criteria | Fail criteria | Failure evidence to capture |
| --- | --- | --- | --- | --- | --- |
| G1 NOS3/OpenC3 boots cleanly | P0 | Manual smoke | T1 bench starts stock NOS3 `v1_07_04` with `gsw = openc3`; `make prep`, `make`, and `make launch` complete; OpenC3/COSMOS, cFS/NOS3, simulator/radio/42-related containers or processes are running; restart after `make stop` also restores fresh telemetry. | Build/launch fails, stock topology is changed without review, containers crash-loop, restart cannot restore telemetry, or exact NOS3 tag/SHA is not recorded. | `git describe`, full SHA, submodule status, Docker/Compose versions, `docker ps`, failing logs, VM shape, `cfg/nos3-mission.xml` `gsw` value, telemetry packet/item/timestamp before and after restart. |
| G2 Private OpenC3 access only | P0 | Manual security | Operator reaches OpenC3 only through IAP/SSH/VPN-style private forwarding to localhost; no public OpenC3, JSON API, Script Runner, Redis, object storage, cFS UDP, NOS3 simulator, radio, or 42 port is reachable. | VM has external IP for OpenC3 path, firewall/public load balancer exposes `tcp:2900` or simulator ports, or a public scan reaches OpenC3 UI/API. | VM network summary, firewall rules, IAP audit pointer, negative external scan result, local forwarded URL used, no credentials in screenshots. |
| G3 Manual Command Sender smoke succeeds | P0 | Manual functional | T3 minimum smoke passes: `CFS CFE_ES_NOOP`, `CFS_RADIO TO_ENABLE_OUTPUT DEST_IP=radio-sim DEST_PORT=5011`, and `SAMPLE SAMPLE_NOOP_CC` are sent through Command Sender and each verifier passes within catalog timeout. | Target/packet missing, wrong args, no Command History entry, verifier does not change, hazardous prompt is bypassed, no-check/range-ignore mode is used, or a non-catalog command is substituted. | Command Sender status/history, Command and Telemetry Server counters/logs, Packet Viewer before/after values, target list, failed prompt text, recovery actions. |
| G4 Automated NOOP command path succeeds | P0 | Automated integration | Supabase enqueues `cfs_noop`; bridge claims once, records send intent, calls OpenC3 JSON API standard `cmd`, verifies `CFS CFE_ES_HKPACKET CMDCOUNTER` increments within 10s, writes `succeeded / success_when_counter_increments`, and updates latest simulator state from telemetry. | Bridge accepts raw command text, no send-intent row exists, no telemetry baseline, OpenC3 call is missing or uses a no-check method, result row is absent, verifier times out, or latest state is agent-written instead of telemetry-backed. | `cubesat_commands` lifecycle snapshots, append-only `cubesat_command_results`, bridge log with redacted auth, OpenC3 request/response, before/after `CMDCOUNTER`, latest-state update pointer. |
| G5 Automated subsystem command succeeds | P0 | Automated integration | One non-NOOP automation-allowed subsystem command succeeds through the same path, preferably `sample_disable` with `SAMPLE_RADIO SAMPLE_DISABLE_CC`; verifier shows `DEVICE_ENABLED == DISABLED` and `CMD_COUNT` increments within 15s. | Command reaches OpenC3 without catalog resolution, verifier packet is stale/missing, result omits state update, or subsystem state contradicts success. | Supabase rows, bridge logs, OpenC3 Command History pointer, JSON-RPC request/response, `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED` and `CMD_COUNT` samples, stale-packet ages. |
| G6 Telemetry verifier is authoritative | P0 | Automated integration | Every automated command has an immediate pre-send baseline, exactly one `cmd` send attempt, bounded polling through `tlm`, `tlm_raw`, or `tlm_formatted`, and terminal success/failure based on the catalog verifier. Streaming data may support freshness but is not the sole proof unless separately validated. | UI status, logs, or streaming cache alone are treated as success; unknown packet/item names are guessed; verifier samples are overwritten or omitted. | Verifier plan, polling timestamps, before/after samples, packet ages, timeout boundary, unknown packet/item blocker notes. |
| G7 Supabase lifecycle is complete | P0 | Automated integration | `cubesat_commands` records all required status transitions (`queued`, `accepted`, `running`, terminal states as applicable); `cubesat_command_results` is append-only; `correlation_id`, `execution_id`, `attempt_number`, `send_outcome`, result class, and payload are populated for each attempt. | Status jumps hide claim/send/verify stages, result rows are mutable/destructive, missing correlation IDs, or terminal rows can be re-opened by public clients. | Database row snapshots by transition, RLS/RPC test results, append-only audit proof, terminal immutability test, bridge log pointers. |
| G8 Rejected commands are auditable and not sent | P0 | Automated negative | Unknown, unresolved, manual-only, unauthorized, stale-precondition, and missing-review requests terminate before OpenC3 with `send_outcome = not_sent` and a result class such as `unknown_command`, `unresolved_catalog_entry`, `precondition_failed`, or `human_review_required`. Use `eps_load_shed_policy` and `radiation_protect_generic` as required rejects. | Any rejected request creates an OpenC3 Command History entry, fills `openc3_target`, calls Script Runner/CLI/UDP, or lacks a durable result row. | Rejected command/result rows, bridge "not sent" log, OpenC3 Command History absence for correlation window, no JSON-RPC `cmd` call, catalog row reason. |
| G9 Duplicate commands are not executed twice | P0 | Automated negative | Reusing the same idempotency tuple returns the existing row and does not enqueue a second send; two bridge workers racing on the same queued row produce one claim and one OpenC3 command; recovery from `running` resumes verification only. | Duplicate active rows exist, two OpenC3 Command History entries share one idempotency action, a recovery worker resends after send intent, or claim-token checks can be bypassed. | Unique-index/RPC result, concurrent worker logs, claim-token update counts, OpenC3 history count for the target command, recovery row evidence. |
| G10 Expired commands do not execute | P0 | Automated negative | Rows with `expires_at <= now()` become `expired / expired_command` before send; review-required commands that expire while awaiting approval remain not sent. | Expired row is claimed for send, OpenC3 history shows the command, or stale approval requeues after expiry. | Expired command/result rows, bridge log showing expiry gate before OpenC3, OpenC3 no-send evidence, approval timestamp comparison. |
| G11 AI agent cannot bypass catalog validation | P0 | Automated security | Agent/UI can submit only `catalog_version`, `catalog_command_id`, typed args, source, expiry, and idempotency data; raw `target`, `command`, `command_string`, OpenC3 URL, method names, credentials, no-check variants, UDP ports, and network destinations are rejected or ignored before execution. | Agent-controlled data changes OpenC3 target/command/method, inserts no-check method names, supplies public destinations, or reads bridge secrets. | API/RLS rejection responses, sanitized row shape, bridge resolution log showing catalog source, negative tests for raw fields and no-check names, frontend bundle/response check for absent secrets. |
| G12 Credential leakage check passes | P0 | Manual and automated security | Repository, logs, screenshots, Supabase rows, frontend bundle, and result payloads contain no OpenC3 tokens/passwords, Supabase service keys, Secret Manager values, SSH/IAP credentials, cookies, or Authorization headers. | Any authority secret is committed, logged, stored in command rows/results, exposed to frontend, or shown in screenshots. | Secret-scan output, log sample review, redaction test, frontend bundle search, result payload sample, incident/rotation record if leakage occurred. |
| G13 Rollback controls work | P0 | Manual and automated safety | Operators can pause the bridge worker, revoke/rotate the OpenC3 API token, disable operator access, stop the NOS3/OpenC3 stack, quarantine queued/running rows, and mark the simulator unavailable in Supabase without losing audit evidence. | Disable path requires code changes during an incident, queued commands continue executing, manual access remains after operator disable, token revocation is ignored, or Soteria still presents simulator as commandable after shutdown. | Bridge pause log, failed post-revoke auth attempt, IAM/firewall/IAP change log, `make stop`/container status, Supabase unavailable/stale-state marker, quarantined row evidence. |
| G14 Simulator-only labeling is visible | P0 | Documentation and UI | Docs, catalog records, command rows, latest-state rows, UI labels, and result summaries identify `simulator_stack = nos3_openc3` and avoid flight-command wording. | UI/docs imply flight authority, hide simulator scope, or present NOS3 commands as real spacecraft commands. | Screenshots or rendered docs, sample row payloads, UI text review, catalog version display. |
| G15 Power extension boundaries hold | P1 | Tabletop and negative | T10 power paths use source-backed commands such as `sample_disable` or reviewed `radio_disable_output`; generic `eps_load_shed_policy` remains rejected until a load-to-switch policy exists; `eps_switch7_off_manual` stays manual-only for the low-power scenario. | Agent or bridge substitutes `GENERIC_EPS_SWITCH_CC` for generic load shed, infers SOC from voltage alone, or automates switch 7 outside the documented low-power scenario. | Rejected EPS load-shed row, no OpenC3 EPS switch command history, power telemetry notes, low-power scenario checklist if switch 7 is tested manually. |

## Manual Check Sequence

1. Execute the T1 bench runbook on the target GCE VM and save clean boot,
   restart, private access, and fresh telemetry evidence.
2. Execute the T3 Command Sender smoke sequence. Minimum first-pass proof is
   `cfs_noop`, `radio_enable_output`, and `sample_noop`; full operator
   readiness includes sample enable/disable and reviewed ADCS commands.
3. Record target, packet, and item names exactly as observed in the running
   OpenC3 instance. Differences from T2/T6 are blockers until the catalog and
   verifier map are updated.
4. Run the T10 manual power checks only as simulator exercises: inspect EPS
   telemetry, reproduce the low-power scenario when scheduled, and keep
   `eps_switch7_off_manual` manual-only with operator approval.
5. Confirm no public OpenC3/API/simulator exposure before and after the smoke
   run.

## Automated Check Sequence

1. Apply future migrations for `cubesat_commands`,
   `cubesat_command_results`, and `cubesat_latest_state` following T5.
2. Start one bridge worker with command execution enabled and one test worker
   or harness for race/duplicate checks.
3. Enqueue `cfs_noop` through the public product path and verify the complete
   lifecycle through `succeeded`.
4. Enqueue one subsystem command, preferably `sample_disable`, and verify the
   telemetry postcondition and latest-state update.
5. Enqueue rejected cases: unknown command, `eps_load_shed_policy`,
   `radiation_protect_generic`, manual-only command, missing-review ADCS
   command, stale-state command, expired command, and unauthorized source.
6. Run duplicate/idempotency tests with repeated requests and concurrent bridge
   workers.
7. Simulate bridge restart after send intent. Recovery may read telemetry and
   finish the row; it must not call `cmd` again.
8. Simulate OpenC3 auth failure, token rotation, API outage before send, and
   timeout after possible send. Verify each maps to the T4/T5 result class.
9. Run public-exposure and credential-leakage checks after the bridge and UI are
   wired.

## Rollback And Disable Controls

Use the narrowest control that contains the issue. Evidence from rollback tests
is part of readiness.

| Control | Required behavior | Validation evidence |
| --- | --- | --- |
| Pause bridge worker | Stop the worker service/container or set `SOTERIA_BRIDGE_COMMANDING_ENABLED=false`; no queued command is claimed while paused; manual OpenC3 access may remain available. | Worker status/logs, queued row unchanged, manual Command Sender still reachable if intended. |
| Revoke OpenC3 API token | Remove or rotate the bridge OpenC3 credential; bridge clears cached token, auth fails closed, and no OpenC3 command is sent until the new credential passes telemetry-read and approved `cfs_noop` checks. | Secret Manager audit log, bridge `failed_openc3_auth`, redacted auth context, post-rotation success evidence. |
| Disable operator access | Remove operator group from IAP/OS Login or disable the IAP SSH firewall rule while retaining break-glass admin control. | IAM/firewall change audit, denied tunnel attempt, incident commander approval. |
| Stop NOS3/OpenC3 stack | Run the T1 stop path or stop the VM; Soteria marks telemetry stale/unavailable and no bridge sends occur. | `make stop`/container status, OpenC3 unreachable from bridge, latest-state stale/unavailable marker. |
| Mark simulator unavailable in Supabase | Set the future simulator availability/state-quality field so UI and agents cannot treat the simulator as commandable; queued/running rows are paused, expired, failed, or manual-review-required per T5/T7. | Supabase row snapshot, UI/API readout, bridge skip log, quarantine result rows. |

## Documentation Gates

- The command catalog is versioned and immutable for a run:
  `nos3-openc3-v1_07_04-cmdcat.20260621`.
- Every executable catalog row has target, command, typed args, manual/automated
  policy, human-review policy, preconditions, verifier, timeout, and result
  classification.
- Every unresolved command family remains non-executable and explains the next
  evidence needed.
- The bridge contract is implemented from a machine-readable table or generated
  artifact, not by scraping prose at runtime.
- Operator docs and UI copy preserve simulator-only labeling.
- Evidence templates exist for manual smoke, automated integration, rejected
  commands, security checks, rollback checks, and blocker closure.

## Tabletop Exercise

T9 reviewed T1-T8, T10, `satellite-command-tool-mapping.md`, and
`cubesat-nos3-command-evidence.md` as a tabletop exercise. Result:

| Scenario | Tabletop result | Readiness implication |
| --- | --- | --- |
| Stock bench boot and private OpenC3 | T1/T7 define a plausible GCE/IAP/localhost path but record that no live NOS3 bench has been run. | P0 blocker until runtime evidence exists. |
| Manual Command Sender path | T3 defines exact Command Sender smoke steps and verifier notes; no screenshots or runtime values exist yet. | P0 blocker until the smoke run passes on the live bench. |
| Automated bridge happy path | T4/T5/T8 define JSON API `cmd`, `tlm` verification, lifecycle rows, result payloads, and example `cfs_noop`/`sample_disable` rows. | Ready to implement after migrations and catalog materialization, but not validated until code exists. |
| Rejected command behavior | T2/T5/T8/T10 consistently reject generic EPS load shed and generic radiation protection before OpenC3. | Must be a first negative integration test. |
| Duplicate and expiry behavior | T4/T5 define idempotency, atomic claims, no resend after send intent, and `expired_command`. | Must be tested with concurrent workers and expired rows before enabling command execution. |
| Telemetry state and verifier names | T3/T6 provide verifier names but explicitly require live OpenC3 confirmation. | P0 blocker for any packet/item mismatch. |
| Power extension | T10 permits stock EPS telemetry and source-backed payload/radio/ADCS posture commands, but keeps generic load shed unresolved. | The first implementation may support `sample_disable` as a power-aware action, not generic EPS load shedding. |
| Security posture | T7 defines no public OpenC3/API/simulator ingress, bridge-only secrets, and emergency controls. | Must be proven with network and secret-leak checks. |

## Launch-Readiness Checklist

- [ ] Live NOS3/OpenC3 bench run completed with stock tag/SHA and private access evidence.
- [ ] OpenC3 target list and verifier packet/item names confirmed from the running instance.
- [ ] Manual Command Sender smoke passes without no-check/range-ignore/bypass modes.
- [ ] Supabase migrations for command queue, result audit, and latest state exist and pass RLS/RPC tests.
- [ ] Bridge implements catalog-only resolution, standard OpenC3 JSON API `cmd`, verifier polling, lifecycle transitions, and append-only result rows.
- [ ] Automated `cfs_noop` and one subsystem command pass with telemetry-backed success.
- [ ] Negative tests prove rejected, duplicate, expired, missing-review, stale-state, and unauthorized commands do not call OpenC3.
- [ ] Public exposure checks prove OpenC3 UI/API and simulator ports are not internet reachable.
- [ ] Credential leakage checks pass for repo, logs, Supabase rows, screenshots, and frontend bundle.
- [ ] Rollback controls are rehearsed: pause bridge, revoke OpenC3 token, disable operator access, stop stack, and mark simulator unavailable in Supabase.
- [ ] UI/docs/result rows clearly label all behavior as `nos3_openc3` simulator-only.
- [ ] Blocker register below is closed or explicitly waived by an owner for a limited bench-only run.

## Blocker Register

| ID | Blocker | Why it blocks readiness | Owner to assign | Exit criteria |
| --- | --- | --- | --- | --- |
| B1 | Live NOS3 bench not yet run | T1/T3/T8 are planning artifacts; no runtime proof exists that stock NOS3/OpenC3 boots, restarts, and exposes fresh telemetry on the target VM. | Bench/operator agent | Saved boot/restart/private-access/telemetry evidence and manual smoke notes. |
| B2 | OpenC3 auth behavior not yet confirmed | T4/T7 define token handling and rotation, but session-token lifetime, refresh mechanics, and failure behavior need the exact NOS3-bundled OpenC3/COSMOS version. | Bridge/security agent | Auth flow tested with redacted logs, token rotation rehearsal, `401/403` fail-closed result. |
| B3 | Verifier packet/item names need live confirmation | T2/T3/T6 names are extracted and source-backed, but the running target aliases and packets may differ. Unknown names are blockers, not guessable fields. | Telemetry/bridge agent | Live target/packet/item inventory reconciled with T2/T6 and catalog updated if needed. |
| B4 | Generic EPS load-shed policy unresolved | T2/T8/T10 reject `eps_load_shed_policy`; no approved load-to-switch map, restore order, or threshold policy exists. | Power-systems/product agent | Load-to-switch policy, verifier packet/items, review rule, and catalog row approved; until then generic load shed remains rejected. |
| B5 | Migrations and bridge implementation not yet built | T5 schema and bridge behavior are contractual docs only; no queue/result/latest-state tables or worker exist yet. | Backend/bridge agent | Migrations applied, RLS/RPC tests pass, bridge integration tests pass G4-G13. |
| B6 | Catalog is still a documentation artifact | Runtime bridge needs immutable machine-readable catalog data and should not scrape prose. | Catalog/backend agent | Signed/generated table or file loaded by bridge with version pin and tests. |
| B7 | Human-review flow not yet implemented | ADCS, radio-disable outside smoke, manual-only EPS switch, and other reviewed rows need approval records and operator audit. | Product/backend agent | Approval schema/UI/RLS implemented and tested through `manual_review_required` and approved execution. |
| B8 | Manual smoke audit path not productized | T8 notes manual Command Sender smoke does not create T5 result rows. | Product/ops agent | Decide whether manual evidence remains bench notes or add a separate operator-evidence ingestion path. |

## Suggested Child Tasks

- Implement Supabase migrations and RLS/RPC tests for T5.
- Generate a machine-readable command catalog from T2 with checksum/versioning.
- Build the first bridge worker slice for `cfs_noop` and `sample_disable`.
- Build an integration harness for duplicate, expired, rejected, and restart
  recovery cases.
- Run the live NOS3/OpenC3 bench and reconcile actual target/packet/item names.
- Add a simulator availability field or table used by UI, agents, and bridge
  disable logic.
- Define the operator approval flow for reviewed simulator commands.
- Define the generic EPS load-to-switch policy only after the low-power
  scenario has live telemetry evidence.
