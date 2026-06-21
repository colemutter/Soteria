# CubeSat Simulation GCP IO Subtasks

Generated: 2026-06-21

## Goal

Design a deployable CubeSat simulation service for Soteria that runs on a Google Cloud Platform compute instance, uses Supabase as the durable live I/O layer, accepts agent/operator commands, and publishes live simulated spacecraft state such as position, power, payload, thermal, attitude, communications, faults, and command results.

The user provided a preferred realism stack: NASA NOS3 + cFS + OpenC3 COSMOS 5. This plan preserves that direction, but recommends a staged deployment:

1. Minimum deployable simulator bridge: a containerized Soteria CubeSat simulation service on a GCE VM that reads commands from Supabase, advances a deterministic 6U CubeSat state model, and writes telemetry/state back to Supabase.
2. NOS3-aligned command vocabulary: model commands, telemetry, modes, and safety boundaries after the pasted NOS3/cFS/OpenC3 design so future replacement with a real NOS3 component is clean.
3. Full simulator bench later: run NOS3/cFS/OpenC3 on a larger GCE VM or separate operations host once the product I/O loop, database schema, and AI command policy are proven.

## Assumptions

- "Super base" means Supabase, matching the existing repository tables and backend tools.
- The first deployed service should be a simulator and command source only, not a real spacecraft uplink service.
- The AI agent may recommend or submit commands to the simulator, but commands must be validated against an allowlist and persisted with audit state before the simulator executes them.
- Supabase is the live integration bus for now: commands in, state/telemetry/events out, with Supabase Realtime or polling used by the UI and agent.
- The first service should simulate one or more 6U edge-compute CubeSats, not copy a flown spacecraft.
- Safe mode remains owned by the simulated onboard computer logic. The compute payload is a switched peripheral that can be powered down, paused, reset, overheated, or faulted without preventing the bus from protecting itself.
- GCP deployment target is Compute Engine, not Cloud Run, because the user explicitly asked for a compute instance.
- For the first implementation, avoid arbitrary shell execution for payload work. Use approved synthetic workloads or a small catalog such as FFT, image compression, SHA-256 hashing, matrix multiplication, ML inference, and data filtering.

## Existing Artifacts Inspected

- `/Users/lukepitstick/.codex/attachments/e1804843-b53e-443d-9b4c-03dc5074a918/pasted-text.txt`: recommends NASA NOS3 + cFS + OpenC3 COSMOS 5, compute payload commands, power/thermal equations, workflow persistence, and mode rules.
- `docs/demo-cubesat-command-source.md`: identifies NOS3 as the recommended simulator command source and maps Soteria operations to source-backed simulator commands.
- `docs/satellite-command-tool-mapping.md`: defines the safety rule that copy-pasteable commands must come from an approved simulator or mission command source.
- `supabase/migrations/20260620233000_create_satellites.sql`: existing satellite identity/orbit snapshot table.
- `src/backend/agent/tools.py`: existing MCP tools query `space_weather_event_windows` and `satellites`, but command tools are currently stubs.
- `src/backend/api/poller.py`: existing event-window poller can queue or dispatch reaction work from Supabase event windows.
- Current docs were checked through Context7 for Supabase Python client table operations and Google Cloud SDK Compute Engine container deployment references. Notably, `gcloud compute instances create-with-container` exists but is documented as deprecated, so this plan favors normal VM provisioning plus Docker/systemd or Docker Compose.

## Recommended Architecture

```text
NOAA/SWPC ingest and event windows
        |
        v
Supabase: space_weather_event_windows
        |
        v
Soteria AI agent / reaction job worker
        |
        | writes allowed simulator commands
        v
Supabase: cubesat_commands
        |
        | poll or realtime subscription
        v
GCE VM: soteria-cubesat-sim container
        |
        | validates, applies, advances model
        v
Supabase: cubesat_state_current
Supabase: cubesat_telemetry_samples
Supabase: cubesat_command_results
Supabase: cubesat_events
        |
        v
Soteria frontend, agent tools, reports, dashboards
```

Recommended first slice:

- Run a single containerized simulator service on a GCE VM.
- Keep all AI and UI integration through Supabase, not direct public VM command ports.
- Expose only a private health endpoint on the VM or behind an internal load balancer if needed.
- Use Supabase service role credentials only inside the simulator VM/container.
- Publish state every 1-5 seconds for `cubesat_state_current` and optionally retain lower-rate telemetry history in `cubesat_telemetry_samples`.
- Let the agent submit command records with `source = ai_agent`, `event_window_id`, `idempotency_key`, and `requires_human_review` flags.
- Let the simulator reject commands that violate mode, power, thermal, freshness, or allowlist rules.

Future NOS3 integration path:

- Keep the Supabase command/state contract stable.
- Add a NOS3 adapter process that converts `cubesat_commands` rows into OpenC3/COSMOS or cFS command calls and converts telemetry packets back into the same Supabase state tables.
- Keep the simulator-only flag visible so Soteria never confuses demo commands with real spacecraft commands.

## Proposed I/O Contract

### Inputs

Primary input should be durable Supabase command rows. Optional HTTP endpoints can exist for local testing, but Supabase should be the production command queue.

Minimum command fields:

```text
cubesat_commands
- id uuid primary key
- satellite_id uuid or text external id
- command_type text
- command_args jsonb
- source text: ai_agent, human_operator, test_harness, scenario
- source_ref jsonb: event_window_id, agent_run_id, scenario_id, user_id
- idempotency_key text unique
- status text: queued, accepted, rejected, running, succeeded, failed, expired
- priority text: low, normal, high, critical
- not_before timestamptz
- expires_at timestamptz
- requested_at timestamptz
- accepted_at timestamptz
- completed_at timestamptz
- validation_errors jsonb
- result jsonb
```

Minimum first commands:

- `NOOP`: connectivity and command-counter test.
- `REQUEST_HK`: force housekeeping/state publish.
- `SET_MODE`: requested bus mode, constrained to valid transitions.
- `PAYLOAD_STANDBY`: pause or disable compute payload activity.
- `PAYLOAD_ENABLE`: enable payload rail if mode and power rules permit.
- `SET_CPU_LIMIT`: constrain synthetic compute utilization.
- `JOB_START`: start an approved synthetic compute workload.
- `JOB_PAUSE`: pause at checkpoint.
- `JOB_RESUME`: resume a paused job.
- `JOB_CHECKPOINT`: persist current job state.
- `JOB_CANCEL`: cancel current payload job.
- `SET_COMMS_PROFILE`: switch telemetry cadence or link posture.
- `SET_ATTITUDE_MODE`: nominal, sun-safe, low-drag, passive, or storm-safe simulator mode.
- `INJECT_FAULT`: simulator-only fault injection for tests.
- `CLEAR_FAULT`: simulator-only recovery test command.

### Outputs

The simulator should publish both "latest state" and historical telemetry.

Latest state table:

```text
cubesat_state_current
- satellite_id primary key
- simulation_time timestamptz
- mode text: BOOT, RECOVERY, IDLE, COMPUTE, DOWNLINK, CHARGE, SAFE
- health text: nominal, degraded, safe, faulted
- latitude_deg double precision
- longitude_deg double precision
- altitude_km double precision
- speed_km_s double precision
- attitude_mode text
- battery_soc_percent double precision
- battery_capacity_wh double precision
- solar_power_w double precision
- load_power_w double precision
- payload_power_w double precision
- payload_power_state text
- payload_temperature_c double precision
- obc_temperature_c double precision
- cpu_utilization_percent double precision
- memory_used_mb double precision
- job_id text
- job_state text
- job_progress_percent double precision
- checkpoint_age_s double precision
- comms_profile text
- radio_power_state text
- fault_flags jsonb
- command_accept_count integer
- command_reject_count integer
- last_command_id uuid
- last_error text
- updated_at timestamptz
```

Historical output tables:

- `cubesat_telemetry_samples`: append-only samples for plots, replay, and tests.
- `cubesat_command_results`: immutable result/audit records for every command.
- `cubesat_events`: simulator events such as mode transition, command rejected, battery low, safe mode entered, fault injected, job completed.
- Optional update to existing `satellites`: write position snapshots into `latitude_deg`, `longitude_deg`, `altitude_km`, `speed_km_s`, and `position_time` so existing Soteria satellite tools can see simulated position without knowing the new telemetry tables.

### Agent I/O Behavior

The AI agent should not talk directly to a public command endpoint in the first production-shaped design. It should:

1. Read `space_weather_event_windows` and current CubeSat state.
2. Decide whether a protective simulator command is justified.
3. Write a command row to `cubesat_commands`, with an event reference and human-review policy.
4. Read `cubesat_command_results`, `cubesat_state_current`, and `cubesat_events` to verify effects.
5. Produce a report that distinguishes observed data, simulated state, recommended action, submitted simulator command, and result.

## Execution Shape

- Critical path: T1 -> T2 -> T3 -> T4 -> T6 -> T8
- Parallel lanes after T2: T3 simulator model, T4 command protocol, T5 agent policy, T6 GCP deployment design
- Integration point: T7 connects the event-window agent loop, command queue, simulator state publisher, and verification report.
- Minimum complete slice: one simulated 6U LEO CubeSat, one GCE VM, one Supabase project, command queue, latest-state publisher, command result audit trail, and one space-weather-triggered protective command scenario.
- Riskiest assumption: Supabase can serve as the live-enough command/state bus for the first demo without causing unacceptable command latency, duplicate execution, or stale-state decisions.

## Subtasks

### T1: Decide Simulator Fidelity And Reuse Boundaries

Outcome: A short architecture decision record that chooses the first deployed simulator fidelity level and clarifies what is implemented now versus deferred to NOS3.

Scope: Compare three options: lightweight Python simulator bridge, full NOS3/cFS/OpenC3 on GCE, and hybrid bridge now with NOS3 adapter later. Include cost, operational burden, latency, demo value, safety, and future replacement path. Out of scope: writing simulator code.

Context packet:

- Pasted stack note: `/Users/lukepitstick/.codex/attachments/e1804843-b53e-443d-9b4c-03dc5074a918/pasted-text.txt`
- `docs/demo-cubesat-command-source.md`
- `docs/satellite-command-tool-mapping.md`
- Google Cloud SDK docs note: `gcloud compute instances create-with-container` is documented as deprecated, so prefer a normal VM with Docker/systemd or Docker Compose.

Agent instructions: Produce `docs/cubesat-simulator-architecture-decision.md`. Recommend one path for the first release and one path for the full NOS3 milestone. Explain why the safe-mode controller stays in the simulated OBC and why the compute payload is treated as a separately switched peripheral.

Expansion path: If the decision depends on uncertain NOS3 cloud behavior, define a spike: start stock NOS3 on a Linux VM, select OpenC3, send CFS NOOP, enable radio telemetry, and run the low-power scenario.

Reuse/library check: Before recommending custom simulation code, use `$deep-dive` to check current NOS3, OpenC3, Orekit, Skyfield, poliastro, and any maintained Python orbit/telemetry libraries. Adopt only if integration cost is lower than a deterministic first-order model.

Acceptance criteria:

- Names the recommended first deployment architecture.
- Names the deferred NOS3 path and trigger for adopting it.
- Identifies at least five risks and mitigations.
- Does not claim simulator commands are valid for real spacecraft.

Validation: Architecture review against the pasted stack note and local Soteria command safety docs.

Dependencies: None.

Handoff: ADR path, recommended deployment option, and any spike tasks.

### T2: Design Supabase Simulator Schema

Outcome: A database design for simulator commands, current state, telemetry history, command results, simulator events, and integration with the existing `satellites` table.

Scope: Define tables, columns, indexes, RLS/service-role policy, retention strategy, and realtime subscription needs. Out of scope: applying migrations.

Context packet:

- Existing migration: `supabase/migrations/20260620233000_create_satellites.sql`
- Existing event windows table: `supabase/migrations/20260620225500_create_space_weather_event_windows.sql`
- Existing agent tool expectations in `src/backend/agent/tools.py`
- Supabase Python client supports `create_client(...)` and table `select`, `insert`, `update`, and `upsert` through `.execute()`.

Agent instructions: Produce `docs/cubesat-simulator-supabase-schema.md` and a proposed migration filename. Include exact SQL draft for tables and indexes, but do not apply it unless separately asked.

Expansion path: Add partitioning or retention policies if telemetry volume exceeds the first-slice estimate. Add Postgres triggers only if they simplify `updated_at`, dedupe, or status transitions without hiding business logic.

Reuse/library check: Check whether Supabase Realtime or polling is better for the command queue in this repo's operational model. Prefer simple polling for the first service if realtime client behavior adds fragility.

Acceptance criteria:

- Defines command lifecycle statuses and valid transitions.
- Defines latest-state and historical telemetry storage separately.
- Includes idempotency key and command expiry.
- Includes indexes for command polling, state lookups, telemetry time ranges, and event-window correlation.
- Explains which tables are writable by service role only and which can be read by anon/authenticated users.

Validation: Schema walkthrough using one example command from queue to accepted/rejected/result/state update.

Dependencies: T1 architecture decision.

Handoff: Schema report plus SQL draft.

### T3: Specify The CubeSat Simulation Model

Outcome: A simulator model specification for spacecraft modes, orbit approximation, EPS, battery, thermal, payload jobs, communications state, faults, and safe-mode rules.

Scope: Define behavior, equations, parameters, update cadence, units, and deterministic test scenarios. Out of scope: implementing runtime code.

Context packet:

- Pasted stack note power model:
  - `Pload = sum(enabled subsystem loads) + payload_idle_power + utilization * (payload_peak_power - payload_idle_power)`
  - `Pnet = solar_power - Pload`
  - `SOCnext = clamp(SOC + Pnet * dt / (battery_capacity_wh * 3600), 0, 1)`
- Pasted stack note thermal model:
  - `Tnext = T + dt / Cthermal * (heat_fraction * payload_power - (T - Tenvironment) / Rthermal)`
- Starter values from the pasted note: 80 Wh battery, 30 W max solar, 3 W OBC, 3 W ADCS, 1/8 W radio idle/transmit, 0/2/14 W compute off/idle/full, 2 W storage/aux.
- Mode rules from the pasted note: `BOOT -> RECOVERY -> IDLE -> COMPUTE`, branches to `DOWNLINK` and `CHARGE`, any mode to `SAFE`, safe recovery only after sustained margins and authorized command.

Agent instructions: Produce `docs/cubesat-simulator-model-spec.md`. Include state variables, command effects, transition guards, fault triggers, and telemetry field mapping to T2 tables. Keep the first orbit model simple enough for deterministic testing, while marking higher-fidelity orbit propagation as a later enhancement.

Expansion path: Split into child specs for orbit propagation, EPS/thermal, payload workflow execution, and fault injection if the model exceeds one agent's implementation scope.

Reuse/library check: Before implementing custom orbit propagation, use `$deep-dive` to compare Skyfield, Orekit, SGP4 bindings, and simple circular orbit approximation. Use a simple approximation only if it is sufficient for first demo claims.

Acceptance criteria:

- Defines every field written to `cubesat_state_current`.
- Defines at least six mode transitions and their guards.
- Defines safe-mode entry conditions for battery, temperature, EPS undervoltage, watchdog failure, payload overcurrent, and corrupted workflow state.
- Defines at least four deterministic scenarios: nominal orbit, geomagnetic storm protection, radiation protection, and low-power safe mode.

Validation: Scenario review by stepping through state transitions and expected telemetry changes.

Dependencies: T1, T2.

Handoff: Model spec with example state snapshots.

### T4: Design Command Validation And Execution Protocol

Outcome: A command protocol that lets the agent submit simulator commands safely and lets the simulator accept, reject, execute, and audit them.

Scope: Define command schemas, validation rules, idempotency, authorization assumptions, expiry, status transitions, result shape, and error codes. Out of scope: implementing command handlers.

Context packet:

- `docs/satellite-command-tool-mapping.md` safety rule: do not invent real spacecraft commands; only simulator/source-backed commands can be emitted.
- `docs/demo-cubesat-command-source.md` maps Soteria command families to NOS3-backed simulator operations.
- Pasted stack note command list: `JOB_START`, `JOB_PAUSE`, `JOB_RESUME`, `JOB_CHECKPOINT`, `JOB_CANCEL`, `SET_CPU_LIMIT`, workflow commands, and reset commands.

Agent instructions: Produce `docs/cubesat-simulator-command-protocol.md`. Include JSON schemas for each first-slice command type, command-to-state effects, rejection examples, and result examples.

Expansion path: Add workflows after basic commands work. Workflows must separate immutable workflow definitions from mutable execution state and use atomic state persistence.

Reuse/library check: Check whether Pydantic JSON Schema generation or existing command schema tools in the repo should define the command contract. Avoid hand-maintained duplicate schemas if a single typed model can generate docs and validation.

Acceptance criteria:

- Includes a normalized command vocabulary for the first release.
- Includes status transition diagram or table.
- Includes idempotency behavior for duplicate agent submissions.
- Includes stale-state protection: reject commands based on old state, expired event windows, or command expiry.
- Includes human-review flags for commands that should not auto-execute.

Validation: Dry-run three command records: `PAYLOAD_STANDBY`, `SET_ATTITUDE_MODE`, and `JOB_START`, with one accepted, one rejected by mode guard, and one expired.

Dependencies: T2, T3.

Handoff: Command protocol doc and JSON examples.

### T5: Define AI Agent Space-Weather Command Policy

Outcome: A policy spec that maps space-weather events and current CubeSat state to simulator command recommendations or command submissions.

Scope: Define what the agent reads, when it can write commands, command priority mapping, review requirements, and verification behavior. Out of scope: modifying the agent code.

Context packet:

- Existing `space_weather_event_windows` table.
- Existing `src/backend/api/poller.py` event-window poller and reaction job dispatcher.
- Existing `src/backend/agent/tools.py` can fetch event windows and satellites, while command tools are stubs.
- `docs/satellite-command-tool-mapping.md` maps geomagnetic, radiation, electron, radio-blackout, and low-power hazards to command families.

Agent instructions: Produce `docs/cubesat-agent-command-policy.md`. Make the policy explicit enough that future agent implementation can call tools, write command rows, and verify state changes without relying on hidden prompt text.

Expansion path: Add a policy matrix per orbit regime, mission class, payload sensitivity, and current mode. Add a human approval lane before auto-execution if risk or severity requires it.

Reuse/library check: Check whether the existing reaction job mechanism can dispatch command planning jobs instead of creating a second event loop. Prefer reuse if it keeps event-window dedupe and priorities in one place.

Acceptance criteria:

- Maps at least five hazard drivers to command families.
- Requires current state read before command submission.
- Requires post-command verification from command results and state telemetry.
- Separates "recommend only", "submit simulator command", and "requires human review".
- Explicitly labels all generated commands as simulator-only.

Validation: Run through example event windows: G3 geomagnetic storm, S3 radiation storm, R-scale radio blackout, low battery during event, and stale/ended event.

Dependencies: T2, T4.

Handoff: Agent policy spec and example agent prompts/tool flows.

### T6: Design GCP Compute Engine Deployment

Outcome: A deployment plan for running the simulator on a GCP Compute Engine VM with secure secrets, logs, restarts, networking, and upgrade flow.

Scope: Define VM shape, OS/container strategy, Artifact Registry image flow, Secret Manager usage, service account, firewall, health checks, logs, restart policy, and operational runbook. Out of scope: creating GCP resources.

Context packet:

- User requested a compute instance in GCP.
- Google Cloud SDK docs include `gcloud compute instances create-with-container`, but that command is documented as deprecated.
- Preferred approach: create a normal VM and use Docker Compose or systemd-managed Docker container; optionally use an instance template for repeatability.
- Full NOS3 path likely needs a larger VM than the lightweight simulator bridge.

Agent instructions: Produce `docs/cubesat-simulator-gcp-deployment.md`. Include two deployment profiles:

1. Lightweight simulator bridge: `e2-medium` or `e2-standard-2`, small persistent disk, one Docker container, service role key from Secret Manager.
2. Full NOS3 bench: larger Linux VM, Docker Compose, OpenC3 access through SSH/IAP tunnel or restricted firewall, no public unauthenticated ground-system UI.

Expansion path: Add Terraform only after manual deployment shape is validated. Add managed instance group only if high availability matters for the simulator.

Reuse/library check: Before writing custom deployment scripts, use `$deep-dive` to compare GCE startup scripts, instance templates, cos_containerd/container-optimized OS, Docker Compose on Ubuntu, and Cloud Deploy/Artifact Registry. Choose the least moving parts for a single VM.

Acceptance criteria:

- Recommends a concrete first VM profile.
- Specifies how the container gets environment variables without committing secrets.
- Specifies no public command endpoint by default.
- Specifies log collection and restart behavior.
- Specifies how to roll out a new image and how to rollback.
- Specifies how to access OpenC3 if/when NOS3 is deployed.

Validation: Dry-run deployment checklist from build to health check to Supabase state update.

Dependencies: T1, T2.

Handoff: GCP deployment plan and operator checklist.

### T7: Integrate End-To-End Scenario Design

Outcome: A scenario design that proves the full loop: space-weather event -> agent decision -> command row -> simulator state transition -> verification report.

Scope: Define one nominal scenario and two protective scenarios with expected database records and state changes. Out of scope: implementing or running the scenario.

Context packet:

- T2 schema.
- T3 simulation model.
- T4 command protocol.
- T5 agent policy.
- Existing Soteria event-window and satellite tables.

Agent instructions: Produce `docs/cubesat-simulator-end-to-end-scenarios.md`. Include sequence diagrams or step lists with exact table reads/writes and expected telemetry outputs.

Expansion path: Add scenario fixtures later for automated integration tests. Add NOS3-backed scenario variants after a NOS3 adapter exists.

Reuse/library check: Check whether existing test fixtures in the repo can be reused for Supabase client mocks and event-window examples before inventing new fixtures.

Acceptance criteria:

- Includes at least one geomagnetic-storm scenario that triggers low-drag or storm-safe attitude.
- Includes at least one radiation scenario that triggers payload standby.
- Includes one command rejection scenario.
- Includes expected command result and telemetry changes.
- Includes operator-visible report fields.

Validation: Review each scenario for deterministic expected outcomes and no hidden manual steps.

Dependencies: T2, T3, T4, T5.

Handoff: Scenario report with table-level examples.

### T8: Define Verification, QA, And Operations Gates

Outcome: A validation plan that future implementers can use to prove the simulator is correct enough, safe enough, and operable on GCP.

Scope: Define unit tests, integration tests, database migration checks, command validation tests, load/latency tests, deployment smoke tests, and operational alerts. Out of scope: writing tests.

Context packet:

- T2 through T7 outputs.
- Existing repo uses Python backend modules and Supabase integrations.
- The first simulator should be deterministic enough for automated testing.

Agent instructions: Produce `docs/cubesat-simulator-verification-plan.md`. Include measurable pass/fail checks and minimum telemetry/command latency targets for the demo.

Expansion path: Add high-fidelity validation after NOS3 is integrated: compare bridge state to NOS3 telemetry, verify OpenC3 command acceptance, and replay low-power scenario.

Reuse/library check: Check existing Python test stack before adding new testing tools. For Supabase-dependent tests, prefer client fakes or local Supabase only when it reduces flakiness.

Acceptance criteria:

- Includes tests for command idempotency, expiry, rejection, and success.
- Includes tests for safe-mode transitions and recovery guards.
- Includes tests for state publish cadence and stale-state detection.
- Includes GCP smoke test: container boots, reads secrets, writes state heartbeat, handles one `NOOP`, and survives restart.
- Includes operational alerts: no state heartbeat, repeated command failures, stale commands, low battery, safe-mode entry, and Supabase write failures.

Validation: QA review against the minimum complete slice.

Dependencies: T2, T3, T4, T6, T7.

Handoff: Verification plan and acceptance gate checklist.

### T9: Plan NOS3/cFS/OpenC3 Adapter Milestone

Outcome: A later-stage plan for replacing or augmenting the lightweight simulator core with NOS3/cFS/OpenC3 while preserving the same Soteria Supabase I/O contract.

Scope: Define adapter responsibilities, command translation, telemetry mapping, VM requirements, network exposure, and milestone acceptance. Out of scope: running NOS3 or writing adapter code.

Context packet:

- Pasted NOS3 stack note.
- `docs/demo-cubesat-command-source.md`
- `docs/satellite-command-tool-mapping.md`
- T2 Supabase schema and T4 command protocol.

Agent instructions: Produce `docs/cubesat-nos3-adapter-plan.md`. Describe how the adapter reads `cubesat_commands`, emits OpenC3/COSMOS or cFS commands, listens for telemetry, and writes the same state/result tables.

Expansion path: Add a `compute_payload` NOS3 component after stock NOS3 operation is proven. Follow the pasted note: create `components/compute_payload/{fsw,sims,gsw}`, assign message IDs, add OpenC3 command/telemetry definitions, and implement synthetic computation first.

Reuse/library check: Use `$deep-dive` to verify current NOS3 deployment, OpenC3 COSMOS 5 command APIs, and any available NOS3 component template docs before specifying adapter code.

Acceptance criteria:

- Keeps Supabase I/O contract unchanged.
- Defines how source-backed simulator commands are translated.
- Defines how telemetry packets map back to Soteria state.
- Defines first stock-NOS3 proof: launch, send CFS NOOP, enable radio telemetry, view EPS/ADCS/radio housekeeping, run low-power scenario.
- Defines network access restrictions for OpenC3 UI and command paths.

Validation: Design review against the NOS3 docs and first-slice Soteria simulator contract.

Dependencies: T1, T2, T4.

Handoff: NOS3 adapter milestone plan.

## Coordination Notes

- Do not start with full NOS3 unless the immediate goal is simulator fidelity over product integration. NOS3 is valuable, but the Supabase command/state contract is the product integration point that should be proven first.
- Keep the first simulator deterministic. Determinism makes event-triggered command tests, safe-mode transitions, and dashboard verification much easier.
- Do not expose the VM as a public command gateway. Supabase command rows plus strict service-role processing are a cleaner first security boundary.
- Treat all commands as simulator-only until a real mission command database exists and explicit approval controls are built.
- Update existing `satellites` position fields from the simulator only if the record is clearly marked simulated, for example `external_id = sim-6u-edge-001`, to avoid mixing real and simulated assets.
- If multiple agents execute these tasks, avoid having them edit the same docs simultaneously. T2, T3, T4, T5, and T6 can run in parallel after T1, then T7/T8 integrate their outputs.

## Suggested Next Dispatch

Start with T1:

```text
Use the CubeSat simulation GCP IO decomposition at agents/cubesat-simulation-gcp-io-subtasks.md. Execute T1 only. Produce docs/cubesat-simulator-architecture-decision.md. Decide the first deployed simulator fidelity level for Soteria, compare lightweight Python simulator bridge vs full NOS3/cFS/OpenC3 on GCE vs staged hybrid, and recommend the first release architecture. Do not write service code. Include risks, mitigations, and the future NOS3 trigger.
```
