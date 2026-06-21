# CubeSat NOS3 OpenC3 Commanding Subtasks

Generated: 2026-06-21

## Goal

Turn `docs/cubesat-nos3-command-evidence.md` into an agent-ready implementation plan for connecting to the NOS3-backed CubeSat simulation through OpenC3/COSMOS 5 and issuing actual NOS3/OpenC3 simulator commands.

This is a companion to `agents/cubesat-simulation-gcp-io-subtasks.md`. The prior plan covers the broad GCP, Supabase, state, and bridge architecture. This plan focuses on the missing operational slice:

1. A human operator can connect to OpenC3 and send source-backed NOS3 commands through Command Sender.
2. A Soteria bridge can submit approved commands to OpenC3 through a documented automation interface.
3. Telemetry and command results can be read back from OpenC3/NOS3 and written into Supabase.
4. The AI agent can request simulator commands only through the Soteria command queue, not through a public raw command endpoint.

## Source Basis

Local sources:

- `docs/cubesat-nos3-command-evidence.md`
- `agents/cubesat-simulation-gcp-io-subtasks.md`
- `docs/satellite-command-tool-mapping.md`
- `docs/demo-cubesat-command-source.md`

External sources to keep attached to the work:

- [NOS3 STF-1 CubeSat case study](https://arxiv.org/abs/1901.07583): NOS3's case study says the framework simulates hardware flight components, including the electrical power system, as part of a software-only virtual spacecraft.
- [NOS3 Getting Started](https://nos3.readthedocs.io/en/latest/NOS3_Getting_Started.html): NOS3 Linux/Docker flow and standard launch/stop workflow.
- [NOS3 Ground Software](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html): NOS3 support for COSMOS 5/OpenC3, `gsw = openc3`, and cFS command/telemetry ground-system links.
- [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html): concrete command examples such as `CFS CFE_ES_NOOP`, `SAMPLE SAMPLE_NOOP_CC`, `SAMPLE_SIM_SET_STATUS`, `GENERIC_ADCS_SET_MODE_CC`, and `GENERIC_RW_SET_TORQUE_CC`.
- [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html): radio output commands, sample enable/disable commands, EPS telemetry, and science-region setup examples.
- [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html): low-power operations, EPS switch telemetry, and load-shed behavior that must be dictionary-verified before automation.
- [NOS3 Simulators](https://nos3.readthedocs.io/en/latest/NOS3_Simulators.html): NOS Engine hardware models, XML-driven simulator configuration, time connections, and data-provider extension points for power-system gaps.
- [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender): operator GUI for sending target commands and parameterized commands.
- [OpenC3 cFS Guide](https://docs.openc3.com/docs/guides/cfs): target/plugin pattern, UDP command/telemetry interface examples, and a cFS Command Sender smoke test.
- [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api): external automation path for `cmd`, `tlm`, `tlm_raw`, and `tlm_formatted` over the OpenC3 API.
- [OpenC3 Scripting API](https://docs.openc3.com/docs/guides/scripting-api): script-level `cmd(...)`, `tlm(...)`, packet reads, and interface mapping functions.
- [OpenC3 Streaming API](https://docs.openc3.com/docs/development/streaming-api): WebSocket/ActionCable stream for raw or decommutated command and telemetry packets.
- [OpenC3 CLI](https://docs.openc3.com/docs/getting-started/cli): `openc3.sh cli` and headless script-run options.

## Assumptions

- The first simulator target is stock NOS3 + cFS + OpenC3/COSMOS 5. Custom 6U compute-payload behavior is a later extension after OpenC3 command and telemetry flow works.
- Commands must be actual NOS3/OpenC3 simulator commands from the NOS3 command dictionary, scenario scripts, or target definitions. Generic Soteria intents are not executable until translated into catalogued NOS3 records.
- OpenC3 provides two first-class command paths:
  - Manual operator path: OpenC3 browser UI, primarily Command Sender and Packet Viewer.
  - Automation path: OpenC3 JSON API, OpenC3 scripting/CLI, or a small bridge-owned script runner.
- Direct raw cFS/UDP command injection is not the production integration path. It can be used only as a lab diagnostic if OpenC3 is unavailable and must not become the Soteria agent path.
- The OpenC3 UI/API must not be publicly exposed. Use IAP, VPN, private networking, or SSH tunnel access for operators and bridge-to-OpenC3 access for automation.
- Supabase remains the product I/O layer: agent and UI write command requests into Supabase, the bridge executes through OpenC3, and bridge writes telemetry/state/results back to Supabase.
- Hazardous or high-impact commands should preserve OpenC3 hazard checks or add equivalent review gates in the Soteria bridge. Automation must not quietly use no-check command variants unless a test explicitly needs them.
- All outputs are simulator-only and must not be represented as flight-qualified behavior or real spacecraft command authority.

## Execution Shape

- Critical path: T1 -> T2 -> T3 -> T4 -> T5 -> T8 -> T9
- Parallel lanes after T2:
  - T3 proves manual OpenC3 commanding.
  - T4 chooses the automated OpenC3 control path.
  - T6 maps OpenC3 telemetry into Soteria state.
  - T7 designs secure GCP access.
- Integration point: T8 connects AI/event policy, Supabase command rows, the Soteria OpenC3 bridge, OpenC3 command execution, NOS3 telemetry verification, and Supabase command results.
- Power-system follow-on: T10 begins after T2 and T6 because it needs the exact command dictionary and telemetry map before it can model EPS state, load shedding, and power-related command effects.
- Minimum complete slice:
  - Boot NOS3 with OpenC3/COSMOS 5 enabled.
  - Reach OpenC3 over a private operator path.
  - Send `CFS CFE_ES_NOOP` through Command Sender.
  - Enable radio telemetry with `CFS_RADIO TO_ENABLE_OUTPUT`.
  - Enable and disable the sample instrument with `SAMPLE_RADIO SAMPLE_ENABLE_CC` and `SAMPLE_RADIO SAMPLE_DISABLE_CC`.
  - Set ADCS passive or sun-safe with `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC`.
  - Read telemetry proving each command effect.
  - Write command result/state rows to Supabase.
- Riskiest assumption: OpenC3 command automation can be used in the NOS3 deployment without bypassing command validation, losing telemetry correlation, or creating duplicate command execution.

## OpenC3 Connection Model

```text
Human operator
    |
    | private browser access: IAP / VPN / SSH tunnel
    v
OpenC3 Command Sender + Packet Viewer
    |
    v
OpenC3 command/telemetry services
    |
    v
cFS inside NOS3
    |
    v
NOS3 simulators and 42 dynamics

AI agent / Soteria worker
    |
    | writes approved simulator command request
    v
Supabase cubesat_commands
    |
    v
Soteria OpenC3 bridge on GCE
    |
    | JSON API, script runner, or CLI-mediated command
    v
OpenC3 command/telemetry services
    |
    v
Supabase command results and CubeSat state
```

The operator path and automated path should be deliberately separate. Operators need direct OpenC3 access for debugging, manual smoke tests, and training. The AI agent needs a constrained product path that records intent, validation, execution, and verification in Supabase.

## Command Seed Catalog For First Slice

Every item below still needs to be verified against the checked-out NOS3/OpenC3 command dictionary before automation. The table is eligible seed material because it is backed by NOS3 documentation and scenarios.

| Soteria intent | OpenC3 target | Command | Arguments | Expected verifier |
| --- | --- | --- | --- | --- |
| Connectivity check | `CFS` | `CFE_ES_NOOP` | none | Command counter increments; cFS event/console acknowledges command |
| Enable radio telemetry | `CFS_RADIO` | `TO_ENABLE_OUTPUT` | `DEST_IP=radio-sim`, `DEST_PORT=5011` | Radio telemetry becomes fresh |
| Resume radio telemetry | `CFS_RADIO` | `TO_RESUME_OUTPUT` | none | Radio packets resume |
| Disable radio telemetry | `CFS_RADIO` | `TO_DISABLE_OUTPUT` | none | Radio telemetry output stops |
| Sample payload NOOP | `SAMPLE` | `SAMPLE_NOOP_CC` | none | `SAMPLE_HK_TLM CMD_COUNT` increments |
| Enable sample instrument | `SAMPLE_RADIO` | `SAMPLE_ENABLE_CC` | none | Sample telemetry becomes fresh/enabled |
| Disable sample instrument | `SAMPLE_RADIO` | `SAMPLE_DISABLE_CC` | none | Sample telemetry indicates disabled/off |
| Inject sample device fault | `SIM_CMD_BUS_BRIDGE` | `SAMPLE_SIM_SET_STATUS` | scenario value such as `status=5` | Sample simulator/device status changes |
| Set ADCS passive | `GENERIC_ADCS` | `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE=PASSIVE` or dictionary value | ADCS mode telemetry and 42 behavior indicate passive/tumbling |
| Set ADCS sun-safe | `GENERIC_ADCS` | `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE=SUNSAFE_MODE` or dictionary value | ADCS mode telemetry and 42 behavior indicate sun-safe pointing |
| Reaction wheel torque demo | `GENERIC_REACTION_WHEEL` | `GENERIC_RW_SET_TORQUE_CC` | torque args from dictionary | Reaction wheel and attitude telemetry update |
| Enable science region AK | `MGR_RADIO` | `MGR_SET_AK_CC` | `AK_STATUS=ENABLE` | Manager telemetry confirms state |
| EPS load shed | unresolved until local dictionary extraction | unresolved | switch id/state from dictionary | EPS switch telemetry changes and power draw decreases |

Power-command caveat: first-slice commands can affect simulated power indirectly by enabling/disabling payload, radio, and ADCS behavior. True EPS switch commands must remain unresolved until the local NOS3/OpenC3 dictionary confirms the exact target, command name, arguments, and telemetry verifier.

## Subtasks

### T1: Boot NOS3 With OpenC3 As The Ground System

Outcome: A reproducible local or GCE bench runbook that starts stock NOS3 with OpenC3/COSMOS 5 selected and confirms OpenC3 is connected to cFS/NOS3 telemetry.

Scope: Prove the simulator process shape and ground-system selection before designing bridge automation around it. Out of scope: custom compute-payload implementation, Supabase schema changes, and production hardening.

Context packet:

- `docs/cubesat-nos3-command-evidence.md`
- `agents/cubesat-simulation-gcp-io-subtasks.md`
- NOS3 Getting Started docs.
- NOS3 Ground Software docs, especially the `gsw = openc3` configuration.
- OpenC3 cFS guide for command/telemetry server expectations.

Agent instructions:

- Produce `docs/cubesat-nos3-openc3-bench-runbook.md`.
- Pin the NOS3 source version, branch, release, or commit used for the bench.
- Document the exact host environment: local Linux VM, GCE Ubuntu VM, Docker version, Docker Compose version, CPU/RAM/disk, and open ports.
- Start stock NOS3 with OpenC3/COSMOS 5 as the ground system.
- Confirm OpenC3 is reachable only through a private path, even in the bench.
- Confirm cFS/NOS3 telemetry appears in OpenC3 before any custom bridge is considered.
- Record every setup deviation from the public NOS3 docs.

Expansion path: If stock NOS3 fails on the selected GCE VM shape, test one larger machine profile before changing architecture. Only fall back to a local machine if the failure is clearly GCE-specific and documented.

Reuse/library check: Use the official NOS3 Docker/Docker Compose flow first. Do not create a custom container layout until the stock flow is understood.

Acceptance criteria:

- Runbook lists exact commands, config changes, and expected outputs.
- OpenC3 browser UI is reachable through a private access method.
- OpenC3 shows fresh cFS/NOS3 telemetry.
- Operator can identify the target list that contains `CFS` and at least one NOS3 subsystem target.
- The runbook includes stop/restart instructions.

Validation:

- Restart the stack once from a clean stopped state.
- Verify telemetry becomes fresh again after restart.
- Capture the OpenC3 URL/access method without exposing credentials in the doc.

Dependencies: None.

Handoff: Bench runbook, NOS3 version pin, host sizing notes, and unresolved setup issues.

### T2: Extract And Version The OpenC3/NOS3 Command Dictionary

Outcome: A source-backed command catalog that maps Soteria simulator intents to exact OpenC3 target, command, argument, verifier, source evidence, and safety metadata.

Scope: Extract command definitions from the checked-out NOS3/OpenC3 target files and scenario scripts. Seed the catalog from `docs/cubesat-nos3-command-evidence.md`, then replace any inferred argument shapes with exact dictionary-backed values. Out of scope: executing commands.

Context packet:

- `docs/cubesat-nos3-command-evidence.md`
- `docs/satellite-command-tool-mapping.md`
- `docs/demo-cubesat-command-source.md`
- NOS3 Demonstration Scenario.
- NOS3 Commissioning Scenario.
- OpenC3 Command Sender docs.
- OpenC3 cFS guide target/plugin pattern.

Agent instructions:

- Produce `docs/cubesat-openc3-command-catalog.md`.
- Include a machine-readable appendix or companion JSON draft for the bridge, even if no code is written yet.
- For each command, record:
  - `catalog_version`
  - `simulator_stack`: `nos3_openc3`
  - `nos3_version` or commit
  - OpenC3 target
  - OpenC3 command name
  - typed arguments and allowed values
  - command intent
  - source file or source scenario
  - whether manual execution is allowed
  - whether automated execution is allowed
  - human-review requirement
  - precondition state checks
  - verifier telemetry packet/item
  - timeout
  - result classification
- Mark unresolved commands explicitly instead of guessing. The first unresolved item should be EPS load shed until the exact local target/command/args are extracted.

Expansion path: After stock command catalog extraction, add a second catalog section for future `compute_payload` component commands such as `JOB_START`, `JOB_PAUSE`, `JOB_CHECKPOINT`, and `SET_CPU_LIMIT`, but keep them non-executable until the component exists in NOS3.

Reuse/library check: Prefer parsing OpenC3 target command definition files or using OpenC3 command metadata if available. Avoid hand-copying a large command dictionary when a repeatable extraction script can be specified.

Acceptance criteria:

- Catalog includes at least the seed commands from this plan.
- Every executable command has exact target/command spelling from the local NOS3/OpenC3 checkout.
- Every command has at least one verifier telemetry signal or an explicit "no verifier yet" blocker.
- Catalog distinguishes manual-only, automation-allowed, and unresolved commands.
- Catalog clearly labels all commands as simulator-only.

Validation:

- Cross-check three catalog records against Command Sender target/command dropdowns.
- Cross-check three catalog records against source files or scenario scripts.
- Reject at least one generic Soteria command because it lacks a NOS3/OpenC3 target.

Dependencies: T1.

Handoff: Command catalog doc, unresolved command list, and recommended catalog version string.

### T3: Prove Manual OpenC3 Command Sender Operations

Outcome: A manual OpenC3 operating procedure that proves an operator can connect to the NOS3 CubeSat simulation and send real simulator commands through Command Sender.

Scope: Use Command Sender and telemetry tools manually. Prove the human path before the automated bridge path. Out of scope: Supabase command queue and AI command policy.

Context packet:

- `docs/cubesat-openc3-command-catalog.md` from T2.
- OpenC3 Command Sender docs.
- OpenC3 cFS guide command smoke test.
- NOS3 Demonstration Scenario.
- NOS3 Commissioning Scenario.

Agent instructions:

- Produce `docs/cubesat-openc3-operator-command-runbook.md`.
- Include private-access steps for opening OpenC3.
- Include a short smoke sequence:
  1. Send `CFS CFE_ES_NOOP`.
  2. Send `CFS_RADIO TO_ENABLE_OUTPUT` with `DEST_IP=radio-sim` and `DEST_PORT=5011`, if these arguments match the local dictionary.
  3. Send `SAMPLE SAMPLE_NOOP_CC`.
  4. Send `SAMPLE_RADIO SAMPLE_ENABLE_CC`.
  5. Send `SAMPLE_RADIO SAMPLE_DISABLE_CC`.
  6. Send `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` to `PASSIVE`.
  7. Send `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` to `SUNSAFE_MODE`.
- For each command, list expected telemetry, expected UI feedback, timeout, and failure interpretation.
- Include what an operator should not do: no no-check command variants, no direct UDP command injection, no public sharing of the OpenC3 URL, and no executing unresolved catalog entries.

Expansion path: Add a short training scenario for a space-weather event after the base smoke sequence works.

Reuse/library check: Use OpenC3 built-in tools first: Command Sender, Packet Viewer, Command and Telemetry Server, and Script Runner. Do not build a custom operator UI for first slice.

Acceptance criteria:

- A new operator can follow the runbook and issue at least three commands successfully.
- The runbook points to exact telemetry verifiers.
- The runbook describes recovery from a failed or mistyped command.
- The runbook preserves OpenC3 hazardous-command prompts if they appear.

Validation:

- Run the full smoke sequence twice.
- Confirm command counters or target telemetry change after each relevant command.
- Confirm failed command behavior is visible and does not corrupt the command catalog.

Dependencies: T1, T2.

Handoff: Operator runbook, manual smoke-test result notes, and any OpenC3 UI screenshots or packet names needed by later agents.

### T4: Choose The Automated OpenC3 Control Path

Outcome: A technical decision that chooses how the Soteria bridge will submit approved commands to OpenC3 and retrieve verification telemetry.

Scope: Compare OpenC3 JSON API, OpenC3 script runner/CLI, and direct cFS/UDP injection. Choose one primary path and one diagnostic fallback. Out of scope: implementing the bridge.

Context packet:

- OpenC3 JSON API docs for `cmd`, `tlm`, `tlm_raw`, and `tlm_formatted`.
- OpenC3 Scripting API docs for `cmd(...)`, `tlm(...)`, and packet helpers.
- OpenC3 Streaming API docs for raw/decommutated command and telemetry packet streams.
- OpenC3 CLI docs for headless script execution.
- OpenC3 cFS guide for interface and target shape.
- `docs/cubesat-openc3-command-catalog.md` from T2.

Agent instructions:

- Produce `docs/cubesat-openc3-automation-decision.md`.
- Evaluate these paths:
  - JSON API command execution from the Soteria bridge.
  - Bridge-generated OpenC3 script execution through Script Runner or CLI.
  - Streaming API only for telemetry observation, not command submission.
  - Direct cFS/UDP injection as a rejected production path and possible lab-only diagnostic.
- For each path, describe auth, command shape, telemetry shape, idempotency implications, error handling, deployment complexity, and safety impact.
- Define the recommended command call shape. Example shapes to validate against the actual OpenC3 deployment:
  - String form: `cmd("CFS CFE_ES_NOOP")`
  - Structured form: target `CFS`, command `CFE_ES_NOOP`, args object
- Define which no-check variants are forbidden by default: no range-check bypass, no hazardous-check bypass, and no all-check bypass unless an explicit test case and human approval exists.
- Define how telemetry verification should be read: synchronous API read, streaming subscription, packet polling, or a combination.

Expansion path: If JSON API auth or network constraints are awkward on GCE, choose a local bridge-side script runner that runs inside the same trusted OpenC3 environment, but keep Supabase as the external command queue.

Reuse/library check: Before writing custom OpenC3 clients, verify whether OpenC3's Ruby/Python scripting APIs or CLI can handle the full first-slice command and telemetry flow. Prefer the least custom code that still gives auditability.

Acceptance criteria:

- Decision names one primary automation path.
- Decision names one telemetry verification path.
- Decision rejects direct UDP/raw command injection for production.
- Decision explains how OpenC3 auth tokens or credentials are stored and rotated.
- Decision explains how command errors map into `cubesat_command_results`.
- Decision explains how to avoid duplicate command execution after bridge restarts.

Validation:

- Dry-run at least two catalog commands through the chosen path in a non-production bench.
- Dry-run one rejected command and confirm the result is stored as rejected, not silently dropped.
- Confirm telemetry can be read after command execution without relying only on logs.

Dependencies: T1, T2.

Handoff: Automation decision doc, sample command request/response payloads, auth notes, and rejected alternatives.

### T5: Specify The Supabase-To-OpenC3 Bridge Contract

Outcome: A bridge contract that defines how Soteria command rows become OpenC3 command executions and how command results, telemetry, and state updates return to Supabase.

Scope: Specify bridge behavior, schemas, status transitions, idempotency, locking, retries, telemetry correlation, and failure modes. Out of scope: writing bridge code or applying migrations.

Context packet:

- `agents/cubesat-simulation-gcp-io-subtasks.md`
- `docs/cubesat-openc3-command-catalog.md` from T2.
- `docs/cubesat-openc3-automation-decision.md` from T4.
- Existing Supabase migrations under `supabase/migrations/`.
- Existing agent tools in `src/backend/agent/tools.py`.

Agent instructions:

- Produce `docs/cubesat-openc3-bridge-contract.md`.
- Define command lifecycle:
  - `queued`
  - `accepted`
  - `rejected`
  - `running`
  - `succeeded`
  - `failed`
  - `expired`
  - `manual_review_required`
- Define row claiming semantics so two bridge workers cannot execute the same command.
- Define idempotency behavior using `idempotency_key`, `catalog_version`, `satellite_id`, and command args.
- Define rejection classes:
  - unknown command
  - unresolved catalog entry
  - unauthorized source
  - stale state
  - expired command
  - human review required
  - OpenC3 unavailable
  - telemetry verifier timeout
  - precondition failed
  - postcondition failed
- Define the result payload shape:
  - OpenC3 target/command/args actually sent
  - command send timestamp
  - OpenC3 response or error
  - telemetry verifier packet/item/value before command
  - telemetry verifier packet/item/value after command
  - correlation id
  - log pointers
- Define safe retry policy. Commands that may toggle state, inject faults, or change ADCS mode should not be retried blindly after an ambiguous send.

Expansion path: Add a separate manual-review queue only after first-slice commands prove stable. Do not block the first smoke path on a complex approval UI.

Reuse/library check: Reuse the existing event-window poller or job dispatch mechanism if it can claim command rows cleanly. Avoid introducing a second unrelated queue system unless Supabase row claiming is insufficient.

Acceptance criteria:

- Contract describes command rows, result rows, and latest-state updates.
- Contract includes a state-transition table.
- Contract includes at least four example command records: accepted NOOP, accepted sample disable, rejected unresolved EPS load shed, expired ADCS command.
- Contract includes retry and ambiguity handling.
- Contract makes the AI agent incapable of bypassing the catalog.

Validation:

- Walk one command from agent request to Supabase row to OpenC3 send to telemetry verifier to result row.
- Walk one bridge restart during `running` status.
- Walk one OpenC3 outage and confirm commands do not disappear.

Dependencies: T2, T4.

Handoff: Bridge contract doc, example JSON rows, and migration notes for the broader schema task.

### T6: Map OpenC3 Telemetry Into Soteria CubeSat State

Outcome: A telemetry mapping that lets Soteria publish live CubeSat state from OpenC3/NOS3 packets and command verification telemetry.

Scope: Define packet/item mappings, units, cadence, stale-data rules, derived fields, and gaps that require NOS3 extensions. Out of scope: implementing the telemetry publisher.

Context packet:

- `agents/cubesat-simulation-gcp-io-subtasks.md`
- `docs/cubesat-nos3-command-evidence.md`
- OpenC3 JSON API docs for telemetry reads.
- OpenC3 Streaming API docs for raw/decommutated packet streams.
- OpenC3 Packet Viewer and Command and Telemetry Server docs, if needed while operating the bench.

Agent instructions:

- Produce `docs/cubesat-openc3-telemetry-state-map.md`.
- Define how to populate `cubesat_state_current` from stock NOS3 telemetry where possible.
- Define which state fields are direct telemetry, derived telemetry, simulated extension fields, or unavailable in stock NOS3.
- Include required state fields from the broader plan:
  - orbit position
  - attitude mode
  - battery/power
  - payload power state
  - payload health
  - thermal state
  - radio/comms state
  - fault flags
  - command counters
  - last command result
- Define freshness thresholds per subsystem.
- Define a state quality field such as `fresh`, `stale`, `partial`, or `sim_extension_required`.

Expansion path: Add custom NOS3 data providers or a `compute_payload` simulator component for missing 6U edge-compute fields after stock telemetry is mapped.

Reuse/library check: Prefer OpenC3 decommutated telemetry reads or streaming subscriptions over scraping UI/log text. Use structured telemetry APIs where possible.

Acceptance criteria:

- Mapping identifies exact OpenC3 target/packet/item names for at least the first-slice verifiers.
- Mapping marks unknown packet/item names as blockers, not guesses.
- Mapping defines update cadence and stale thresholds.
- Mapping defines how command verification telemetry differs from dashboard state telemetry.
- Mapping states which fields can be written to the existing `satellites` table for compatibility.

Validation:

- For each first-slice command, identify the telemetry verifier that proves command effect.
- Simulate a stale telemetry condition and define what state row should look like.
- Confirm the mapping can support the AI agent reading current state before submitting a command.

Dependencies: T1, T2, T4.

Handoff: Telemetry/state mapping doc and stock-NOS3 gap list.

### T7: Secure GCP And OpenC3 Access

Outcome: A deployment access plan that lets operators connect to OpenC3 and lets the bridge call OpenC3 without exposing command authority publicly.

Scope: Define network topology, firewall rules, IAM, secrets, operator access, bridge access, logging, and incident controls. Out of scope: creating GCP resources.

Context packet:

- `agents/cubesat-simulation-gcp-io-subtasks.md`
- OpenC3 docs for web UI/API ports and auth assumptions.
- GCP Compute Engine, IAP TCP forwarding, Secret Manager, Cloud Logging, and firewall documentation should be checked during implementation planning.

Agent instructions:

- Produce `docs/cubesat-openc3-gcp-access-plan.md`.
- Specify one recommended first-slice access model:
  - GCE VM on a restricted VPC/subnet.
  - No public unauthenticated OpenC3 UI/API.
  - Operator access through IAP TCP forwarding, VPN, or SSH tunnel.
  - Bridge runs on the same VM or same private network as OpenC3.
  - Supabase credentials and OpenC3 credentials in Secret Manager or VM-injected secrets, not committed config.
- Specify firewall rules for:
  - OpenC3 UI/API access.
  - Bridge-to-OpenC3 access.
  - NOS3 internal simulator links.
  - SSH/IAP administration.
- Specify audit logs for operator login, bridge command execution, and command result rows.

Expansion path: Add Terraform only after the manual VM/network shape is validated. Add separate bridge VM or managed instance group only if the single-VM bench becomes operationally limiting.

Reuse/library check: Before finalizing, use `$deep-dive` to compare IAP TCP forwarding, VPN, bastion, private service access, and SSH tunnel patterns for a single protected GCE VM. Pick the simplest option that avoids public command exposure.

Acceptance criteria:

- No OpenC3 command surface is public by default.
- Operators have a documented connection path.
- The bridge has a documented OpenC3 connection path.
- Secrets handling is explicit.
- Logs and audit trails are explicit.
- The plan includes emergency disable steps for the bridge and OpenC3 external access.

Validation:

- Review firewall rules from the perspective of an unauthenticated internet client.
- Review bridge credentials from the perspective of a compromised frontend client.
- Confirm a manual operator can still access OpenC3 when the bridge is disabled.

Dependencies: T1, T4.

Handoff: GCP access plan, firewall sketch, credential list, and emergency-disable checklist.

### T8: Build The End-To-End Command Scenario Design

Outcome: A scenario design that proves an AI agent can respond to a solar-weather event by submitting a catalogued simulator command, while OpenC3 executes it and Supabase records the result.

Scope: Define the complete first-slice workflow and expected data at every hop. Out of scope: implementing the agent, bridge, or UI.

Context packet:

- Existing `space_weather_event_windows` table and poller design.
- Existing satellite table migration.
- `docs/cubesat-nos3-command-evidence.md`
- `docs/cubesat-openc3-command-catalog.md` from T2.
- `docs/cubesat-openc3-bridge-contract.md` from T5.
- `docs/cubesat-openc3-telemetry-state-map.md` from T6.

Agent instructions:

- Produce `docs/cubesat-openc3-end-to-end-scenarios.md`.
- Include at least three scenarios:
  1. Operator smoke test: human sends `CFS CFE_ES_NOOP` in Command Sender and confirms telemetry.
  2. Agent protective action: active event plus current state causes the agent to submit a safe, source-backed command such as sample payload disable or ADCS sun-safe.
  3. Rejected command: event requests EPS load shed but the EPS command remains unresolved in the catalog, so the bridge rejects or routes to manual review.
- For each scenario, include:
  - initial Supabase rows
  - current CubeSat state
  - command request
  - catalog lookup
  - OpenC3 call
  - telemetry verifier
  - final command result
  - final state update
  - operator-visible behavior

Expansion path: Add fault-injection scenarios after first-slice nominal commands work: sample device fault, radio telemetry disable/resume, low-power scenario, stale telemetry, and OpenC3 outage.

Reuse/library check: Reuse the existing event-window reaction mechanism if practical. The scenario should not require a new scheduler if the existing poller can enqueue agent work.

Acceptance criteria:

- Scenario doc contains complete row-level examples.
- Scenario doc shows both manual OpenC3 use and automated bridge use.
- Scenario doc includes one rejected command and one verification timeout.
- Scenario doc clearly distinguishes observed space weather, simulated spacecraft state, agent recommendation, executed simulator command, and verified result.

Validation:

- Tabletop the scenario with no code changes.
- Confirm every executable command maps to T2 catalog entries.
- Confirm every result field maps to T5 bridge contract.

Dependencies: T2, T3, T4, T5, T6.

Handoff: End-to-end scenario doc and a checklist for future implementation agents.

### T9: Define QA, Safety, And Handoff Gates

Outcome: A validation plan that future implementation work must pass before Soteria treats the NOS3/OpenC3 simulator as a usable command target.

Scope: Define smoke tests, integration tests, manual checks, safety checks, and documentation gates. Out of scope: writing test code.

Context packet:

- All docs produced by T1-T8.
- `docs/satellite-command-tool-mapping.md`
- `docs/cubesat-nos3-command-evidence.md`
- OpenC3 command, scripting, JSON API, and streaming docs.

Agent instructions:

- Produce `docs/cubesat-openc3-validation-plan.md`.
- Include validation gates:
  - NOS3/OpenC3 boots cleanly.
  - Manual Command Sender smoke test succeeds.
  - Automated command path can send NOOP and one subsystem command.
  - Telemetry verifier confirms command effect.
  - Supabase command lifecycle records all status changes.
  - Rejected commands are auditable.
  - Duplicate commands are not executed twice.
  - Expired commands do not execute.
  - OpenC3 UI/API is not publicly reachable.
  - AI agent cannot bypass catalog validation.
- Include rollback and disable controls:
  - pause bridge worker
  - revoke OpenC3 API token
  - disable operator access
  - stop NOS3/OpenC3 stack
  - mark simulator unavailable in Supabase

Expansion path: Add load tests only after first-slice correctness and safety gates pass. Telemetry volume optimization is a later concern unless state publication falls behind.

Reuse/library check: Use OpenC3 built-in command history, telemetry tools, and logs for validation evidence where possible. Avoid building custom observability until the built-ins are insufficient.

Acceptance criteria:

- Validation plan includes pass/fail criteria.
- Validation plan includes failure evidence to capture.
- Validation plan includes manual and automated checks.
- Validation plan includes security checks for public exposure and credential leakage.
- Validation plan includes explicit simulator-only labeling.

Validation:

- Run the validation plan as a tabletop exercise against T1-T8 outputs.
- Identify any missing docs or blockers before implementation starts.

Dependencies: T1-T8.

Handoff: Validation plan, launch-readiness checklist, and blocker register.

### T10: Extend Basic Power-System Simulation And Power Commands

Outcome: A follow-on power-system extension plan that uses NOS3's stock EPS simulation first, then extends it only where needed, while mapping every operator/agent power action to real NOS3/OpenC3 simulator commands or explicitly unresolved command gaps.

Scope: Define how Soteria should reuse stock NOS3 EPS behavior, where stock NOS3 needs configuration rather than code, where a custom NOS3 hardware model or data provider may be justified, and which actual OpenC3 commands interact with power-producing or power-consuming subsystems. This includes battery state, bus voltage/current, solar generation, load states, payload/radio/ADCS loads, EPS switch states, safe-mode thresholds, and load-shed behavior. Out of scope: flight-qualified EPS modeling, hardware vendor command sets, or invented commands not present in NOS3/OpenC3.

Context packet:

- `docs/cubesat-nos3-command-evidence.md`
- `docs/cubesat-openc3-command-catalog.md` from T2.
- `docs/cubesat-openc3-telemetry-state-map.md` from T6.
- `agents/cubesat-simulation-gcp-io-subtasks.md`, especially the power and thermal starter model from the pasted stack note.
- NOS3 STF-1 case study for evidence that NOS3 was designed to simulate hardware components such as an electrical power system.
- NOS3 Commissioning Scenario for EPS telemetry and sample/radio operations.
- NOS3 Low Power Scenario for low-power behavior and EPS switch/load-shed evidence.
- NOS3 Simulators docs for adding simulator components, data providers, or fault injectors when stock NOS3 does not expose the needed state.

Agent instructions:

- Produce `docs/cubesat-power-system-simulation-and-commands.md`.
- Start with this adoption map:
  - Adopt now: stock NOS3 `GENERIC_EPS` telemetry and low-power scenario behavior for battery state, EPS switch states, in-sun status, and observed power drain/recovery.
  - Adopt now: OpenC3 Packet Viewer, Telemetry Grapher, and `EPS_test.txt` for operator-visible power telemetry.
  - Adopt now: NOS3 config-driven initial conditions, especially the EPS `<battery-charge-state>` value in `cfg/sim/nos3-simulator.xml`, for deterministic low-power test setup.
  - Prototype/spike: exact EPS switch commands from the local NOS3/OpenC3 command dictionary and `PassSetupEPSCheck_LowPowerScen.rb`; do not assume the command name from docs screenshots.
  - Prototype/spike: Sim Bridge commands for manually setting state of charge to test low-power failsafes.
  - Prototype/spike: LC watchpoints and SC/RTS tables for autonomous safe-mode entry at thresholds such as 60% pause and 40% safe-state behavior.
  - Study/extend: NOS3 hardware model and data-provider APIs for custom EPS behavior if stock `GENERIC_EPS` cannot model Soteria's 6U edge-compute power channels.
- Document the stock NOS3 power mechanisms before inventing any new model:
  - `GENERIC_EPS` Packet Viewer telemetry.
  - `GENERIC_EPS_RADIO GENERIC_EPS_HK_TLM BATT_VOLTAGE` or the exact local equivalent from the OpenC3 telemetry dictionary.
  - `EPS_test.txt` telemetry graphing for power level, switch state, and in-sun status.
  - EPS switch telemetry, including the low-power scenario's switch 7 drain example.
  - EPS `<battery-charge-state>` in `cfg/sim/nos3-simulator.xml`.
  - LC watchpoint tables such as `cfg/nos3_defs/tables/lc_def_wdt.c`.
  - LC actionpoint tables such as `cfg/nos3_defs/tables/lc_def_adt.c`.
  - SC/RTS tables such as `cfg/nos3_defs/tables/sc_rts*.c`.
  - Sim Bridge state-of-charge manipulation for failsafe testing, if available in the checked-out NOS3 version.
- Define the minimum EPS state model:
  - solar input watts
  - battery state of charge
  - battery voltage
  - battery current
  - main bus voltage
  - main bus current
  - per-subsystem load watts
  - EPS switch/channel states
  - payload power state
  - radio power/output state
  - ADCS mode and estimated ADCS load
  - low-power and safe-mode flags
- Define the starter energy balance and explicitly mark it as simulator behavior:
  - `Pload = enabled_bus_loads + payload_load + radio_load + adcs_load + thermal_or_aux_load`
  - `Pnet = solar_power - Pload`
  - `SOCnext = clamp(SOC + Pnet * dt / battery_capacity_wh, 0, 1)` after unit normalization.
- Extract the exact NOS3/OpenC3 command records that interact with power-relevant state. At minimum, evaluate:
  - `SAMPLE_RADIO SAMPLE_ENABLE_CC` as a payload-load enable command.
  - `SAMPLE_RADIO SAMPLE_DISABLE_CC` as a payload-load disable command.
  - `CFS_RADIO TO_ENABLE_OUTPUT` as a radio telemetry/output enable command, if the local dictionary confirms the arguments.
  - `CFS_RADIO TO_DISABLE_OUTPUT` as a radio telemetry/output disable command.
  - `CFS_RADIO TO_RESUME_OUTPUT` as a radio telemetry/output resume command.
  - `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `PASSIVE` as an ADCS mode/power-management command.
  - `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` with `SUNSAFE_MODE` as an attitude/charging protection command.
  - The exact EPS switch or load-shed command from the local NOS3/OpenC3 command dictionary. Source candidates include the `GENERIC_EPS`/`GENERIC_EPS_RADIO` target definitions, the low-power scenario procedure `PassSetupEPSCheck_LowPowerScen.rb`, and any RTS tables that command switches off. If no exact target/command/args can be verified, keep EPS load shed unresolved and manual-review-only.
- For EPS switch commands, require exact extraction of:
  - OpenC3 target name.
  - Command name.
  - switch/channel argument name.
  - on/off argument name and allowed values.
  - whether Command Sender marks it hazardous.
  - telemetry packet/item for switch state.
  - telemetry packet/item for current draw or battery recovery.
  - whether command is safe for automation or manual-review-only.
- For each command, record whether it is:
  - a real NOS3/OpenC3 simulator command verified in the local dictionary
  - a real NOS3 scenario command still needing dictionary verification
  - a Soteria high-level intent that must not execute directly
  - a future command that requires a custom `compute_payload` or EPS simulator component
- For each command, define preconditions, expected telemetry verifier, timeout, failure interpretation, and whether the command is safe for automation.
- Define how power commands appear in both paths:
  - manual path through OpenC3 Command Sender
  - automated path through the Soteria bridge and Supabase command rows
- Include at least one power-aware AI policy example: during a severe solar-weather event or low-battery state, the agent recommends or submits a source-backed payload/radio/ADCS command and verifies power telemetry afterward.

Expansion path: After stock NOS3 command and telemetry gaps are known, add a custom NOS3 EPS or `compute_payload` component for missing power channels, power-limit commands, job pause/resume power behavior, thermal coupling, and workload throttling. New commands become executable only after they appear in the OpenC3 command dictionary and are added to the versioned catalog.

NOS3 extension options to evaluate before custom code:

- Configure stock EPS initial conditions and scenario timing first, because the low-power scenario already demonstrates battery state changes, switch states, sunlight/eclipse context, and low-power fault triage.
- Use LC/SC/RTS table changes to model autonomous power-protection behavior before adding a separate external controller. NOS3's low-power scenario explicitly points to LC watchpoints, actionpoints, and RTS tables for safe-state transitions.
- Use Sim Bridge state-of-charge control, if present in the pinned NOS3 version, to test threshold behavior quickly without waiting through long discharge cycles.
- If Soteria needs per-workload compute power draw or power-limit commands, add a NOS3-native `compute_payload` or EPS-adjacent hardware model with XML configuration and OpenC3 command/telemetry definitions, using NOS Engine time and bus connections.
- If Soteria needs orbit/environment-driven charging beyond stock behavior, add or configure a NOS3 data provider rather than running a disconnected synthetic model outside NOS3.

Reuse/library check: Prefer stock NOS3 EPS telemetry, scenario scripts, 42 environmental/orbit data, LC/SC/RTS tables, Sim Bridge test hooks, and NOS3-native data providers before building a separate synthetic power model. If a simplified power model is still needed, keep it small, documented, and calibrated against stock NOS3 telemetry where possible.

Acceptance criteria:

- Includes a short tech-discovery section explaining why NOS3 can be used for power-system simulation and what remains to be verified in the local checkout.
- Defines the minimum EPS state variables and units.
- Lists the exact source-backed OpenC3 commands that can change power-relevant state.
- Keeps unresolved EPS switch/load-shed commands non-executable until dictionary verification.
- Defines telemetry verifiers for battery, bus, switch, payload, radio, and ADCS power-related effects.
- Includes at least three power scenarios: nominal charging, payload/radio load shed, and low-power safe-mode entry/recovery.
- Distinguishes real NOS3 simulator commands from Soteria intents and future custom-component commands.
- Identifies whether stock NOS3 is sufficient for first-slice power simulation or whether a custom EPS/compute-payload hardware model is required.

Validation:

- Tabletop a payload disable command from agent request to OpenC3 send to power telemetry verifier.
- Tabletop a rejected EPS load-shed request when the exact EPS switch command remains unresolved.
- Step through the energy balance for one orbit day/night cycle and confirm state changes are physically plausible for a simulator.
- Confirm the manual Command Sender path and automated bridge path use the same catalogued command records.

Dependencies: T2, T4, T5, T6.

Handoff: Power-system simulation and commands spec, verified power-command catalog entries, unresolved EPS command gaps, and future custom-component requirements.

## Suggested Agent Assignment Order

1. T1 should run first because it proves NOS3/OpenC3 actually boots in the selected environment.
2. T2 should run immediately after T1 because every other task depends on exact target/command names.
3. T3 and T4 can run in parallel after T2: manual operation and automation decision reinforce each other.
4. T5 should wait for T4 so it can use the chosen automation path.
5. T6 can begin after T2 but should update after T4 selects telemetry access.
6. T7 can begin after T1 and T4 because access planning needs real ports/auth behavior.
7. T8 should integrate T2-T7 into row-level scenarios.
8. T9 should close the loop with launch-readiness gates.
9. T10 should follow T2 and T6 when the team is ready to extend beyond the first smoke slice into realistic EPS/load simulation and power-aware command policy.

## Minimum Backlog Slice

If this needs to become a small implementation sprint, cut the work to:

1. T1 bench runbook.
2. T2 catalog with five executable commands: `CFE_ES_NOOP`, `TO_ENABLE_OUTPUT`, `SAMPLE_NOOP_CC`, `SAMPLE_ENABLE_CC`, `SAMPLE_DISABLE_CC`.
3. T3 manual Command Sender smoke test.
4. T4 automation decision choosing JSON API or script runner.
5. T5 bridge contract for command lifecycle and result rows.
6. T8 one end-to-end scenario: space-weather event causes sample payload disable.

Everything else is important, but those six pieces prove the OpenC3 connection and command loop.
