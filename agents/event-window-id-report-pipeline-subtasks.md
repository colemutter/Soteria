# Event Window ID Report Pipeline Subtasks

Generated: 2026-06-21

## Goal
Design and implement a report-generation pipeline where a real local Poller run proves the full flow: the local Poller reads live Supabase event windows, posts event-window IDs to the local backend, the backend resolves those IDs from live Supabase, calls the real cloud Agent SDK, validates one report per event window with Pydantic, and rejects any report that invents severity levels or possible outcomes outside fixed enums.

## Frame
- Desired outcome: report generation is driven by the event-window IDs in the Poller message, not by the agent independently searching for broad event data during report writing.
- Known constraints: the validation gate must use a real local Poller process, live Supabase data, and a real cloud Agent SDK connection. Mocked tests remain useful for development, but they are not the final proof.
- AI constraint: the AI may interpret and choose from predefined categories, but it must not create new severity scores, possible outcomes, event IDs, satellite IDs, or schema fields.
- Stakeholders affected: backend API, Poller integration, report agent, future frontend report display, and satellite operators consuming severity/outcome summaries.
- Existing artifacts inspected: `src/backend/api/poller.py`, `src/backend/api/agent.py`, `src/backend/agent/definition.py`, `src/backend/agent/service.py`, `src/backend/agent/tools.py`, `agents/agent-api-evidence-pipeline-subtasks.md`, and `docs/satellite-command-tool-mapping.md`.
- Assumption: the current Poller batch model in `EventWindowReactionBatch` is the right upstream shape, but the endpoint may still need to accept both a single reaction and a batch during transition.

## Proposed Deterministic Contract
These names are the starting contract for implementation. The first task should confirm or revise them once, then treat them as set-in-stone until a deliberate schema migration changes them.

Severity enum:
- `none`
- `minor`
- `moderate`
- `major`
- `severe`
- `extreme`

Possible outcome enum:
- `increased_drag`
- `orbit_prediction_degraded`
- `adcs_disturbance`
- `surface_charging`
- `deep_dielectric_charging`
- `single_event_effects`
- `payload_noise`
- `star_tracker_degraded`
- `solar_array_degradation`
- `communication_degraded`
- `gnss_navigation_degraded`
- `tracking_uncertainty`
- `no_material_satellite_effect_expected`

Suggested report unit: one `EventWindowSatelliteReport` per event window, with a list of affected satellite findings. A local Poller dispatch with multiple `event_window_ids` should produce one validated report for each referenced event window.

## Execution Shape
- Critical path: T1 -> T2 -> T3 -> T5 -> T6 -> T7 -> T8
- Parallel lanes: T4 can run after T1; mocked negative-path tests from T8 can start after T3, but the live validation waits for T6/T7
- Integration point: the live local Poller validation combines Poller process startup, live Supabase reads, HTTP endpoint intake, deterministic evidence building, real cloud Agent SDK output, Pydantic validation, and persistence/readback if implemented
- Riskiest assumption: the agent can be made to reliably emit JSON conforming to the Pydantic report schema; the pipeline must still fail closed when it does not

## Work Map
- Research/design: lock deterministic severity and possible-outcome enums, mapping rules, and report schema.
- Architecture: separate deterministic data resolution from AI drafting; AI receives already-resolved event-window/satellite evidence.
- Implementation: add or adjust the Poller-facing agent endpoint, data resolver, report generator, validator, and optional persistence.
- QA: mocked tests cover schema and failure modes quickly; the primary validation is a live local Poller run against live Supabase and the real cloud Agent SDK.
- Operations: log accepted IDs, missing IDs, validation failures, generated report IDs, and per-event-window outcomes.
- Reuse check: prefer Pydantic v2 enums, validators, `TypeAdapter`, and existing Supabase query helpers over custom schema parsing.

## Subtasks

### T1: Lock The Report Taxonomy And Pydantic Models
Outcome: Produce the canonical Pydantic report schema and deterministic enums the AI must choose from.

Scope: Define models for event severity, possible satellite outcomes, event-window evidence, satellite impact findings, and per-event-window reports. Include IDs, citations/source references, confidence, selected severity, selected outcomes, concise rationale, and validation metadata. Out of scope: Claude calls, database persistence, and frontend display.

Context packet: inspect `src/backend/api/poller.py`, `src/backend/agent/definition.py`, `src/backend/agent/tools.py`, `agents/agent-api-evidence-pipeline-subtasks.md`, and `docs/satellite-command-tool-mapping.md`.

Agent instructions: Create a model module such as `src/backend/agent/report_models.py`. Use Pydantic `Enum` or `Literal` types for severity and possible outcomes. Add validators that reject unknown event IDs, unknown satellite IDs, empty reports, invented enum values, and findings with no source reference. Make model names and enum values stable and boring because later API/UI code will depend on them.

Expansion path: If the proposed enum list is incomplete, add a short decision section explaining why each new enum is needed and which local evidence supports it. Do not leave open-ended “other” categories.

Reuse/library check: Before implementing custom validation helpers, use Pydantic v2 validators, `TypeAdapter`, and `model_validate_json()` where they fit.

Acceptance criteria: report schema validates one report per event window; invented severity values fail; invented outcome values fail; reports cannot cite event-window IDs or satellite IDs absent from the evidence input.

Validation: Unit tests for valid report JSON, invalid severity, invalid outcome, missing event-window citation, missing satellite citation, and unexpected extra fields.

Dependencies: None.

Handoff: Pydantic model module, enum names, validation tests, and a short note confirming the final taxonomy.

### T2: Build Event-Window ID Resolution
Outcome: Convert Poller-provided event-window IDs into typed event-window rows before the agent is invoked.

Scope: Add a resolver function that accepts `event_window_ids`, fetches matching rows from `space_weather_event_windows`, validates them through the T1 evidence models or dedicated row models, and returns found rows plus missing IDs. Out of scope: AI generation and report formatting.

Context packet: inspect `src/backend/api/poller.py` for `EventWindowReactionBatch`, `_reaction_batch`, and `EVENT_WINDOW_COLUMNS`; inspect `src/backend/agent/tools.py` for existing Supabase query conventions.

Agent instructions: Implement the resolver in a backend/agent service module or a small API helper module. Preserve input ordering where possible. Fail closed if no IDs resolve. Make missing IDs explicit instead of silently ignoring them. Avoid giving the AI permission to call `get_event_windows` to fill gaps.

Expansion path: If the current Poller sends single `EventWindowReactionMessage` objects in production, design the resolver to normalize single and batch payloads into the same internal list of IDs.

Reuse/library check: Use the existing Supabase client pattern already present in `src/backend/agent/tools.py` or `src/backend/api/operations.py`; do not create a new database abstraction unless it removes duplicated error handling.

Acceptance criteria: given IDs `["a", "b"]`, the resolver queries only those IDs; missing IDs are reported; resolved event windows pass Pydantic validation; duplicate IDs are deduped or explicitly preserved by documented behavior.

Validation: Unit tests with a fake Supabase client for all-found, partially-missing, all-missing, duplicate IDs, and malformed DB row cases.

Dependencies: T1.

Handoff: Resolver function, tests, and a documented internal return shape.

### T3: Build Deterministic Report Evidence Bundles
Outcome: Produce the complete typed input the AI receives, containing event-window rows and relevant satellite context.

Scope: Build one evidence bundle per event window. Include the event window, active/relevant satellites, static taxonomy enum values, deterministic mapping hints, source metadata, and an evidence hash. Out of scope: AI output generation and UI.

Context packet: inspect `src/backend/agent/tools.py` for `_query_satellites` and `get_user_satellites`; inspect `supabase/migrations/20260620233000_create_satellites.sql`; inspect T1/T2 outputs.

Agent instructions: The evidence builder should take resolved event windows, fetch active satellites once, and create per-event-window bundles. The AI should receive this bundle as JSON and should not need to call tools for event data. Include deterministic mapping hints such as “geomagnetic storm can map to `increased_drag`, `orbit_prediction_degraded`, `adcs_disturbance`, `surface_charging`, `tracking_uncertainty` depending on orbit/context.” Keep hints constrained to enum values.

Expansion path: If satellite relevance is too broad, start with all active satellites and add a later relevance filter by orbit regime/event type. Do not block the first live local validation on perfect relevance scoring.

Reuse/library check: Use Pydantic serialization plus standard-library `json.dumps(..., sort_keys=True)` for stable evidence hashes before considering custom canonical JSON code.

Acceptance criteria: one input bundle is produced for each resolved event window; each bundle includes allowed severity values and allowed outcome values; evidence hashes are stable for equivalent data; no free-form outcome vocabulary enters the bundle.

Validation: Unit tests for one event/one satellite, one event/multiple satellites, multiple events, no active satellites, and stable hash behavior.

Dependencies: T1, T2.

Handoff: Evidence builder, typed bundle models, mapping-hint structure, and tests.

### T4: Update The Agent Prompt And Tool Boundaries
Outcome: Change the event report agent’s role from data gathering to constrained classification and report drafting from supplied evidence.

Scope: Update `event-report-agent` prompt text and allowed tool expectations so it uses the provided evidence bundle and returns schema-conforming JSON. Out of scope: changing command-agent behavior.

Context packet: inspect `src/backend/agent/definition.py`, `src/backend/agent/service.py`, T1 models, and T3 bundle shape.

Agent instructions: Remove or soften “Use get_event_windows before writing reports” for this report path. Tell the agent it must not invent severity values, possible outcomes, event-window IDs, satellite IDs, source products, or measurements. It may choose only from the provided enums. It must output JSON only, matching the Pydantic schema.

Expansion path: If the same agent still needs ad-hoc chat tools later, split “event-report-agent” and “event-report-from-evidence-agent” rather than mixing unconstrained chat and production report generation.

Reuse/library check: Check whether the Claude Agent SDK supports structured-output or schema-constrained responses in this project’s current version before implementing custom JSON extraction.

Acceptance criteria: prompt explicitly forbids new enum values; prompt references supplied evidence instead of broad tool fetching; tests or snapshots cover the generated prompt content.

Validation: Unit tests for prompt/message builder showing allowed enum lists are included and tool-fetch instructions are not part of the evidence-driven report path.

Dependencies: T1, T3.

Handoff: Updated agent definition or new agent definition, message builder, and prompt tests.

### T5: Implement Validated AI Report Generation
Outcome: Add a service that sends each evidence bundle to the agent through the real Agent SDK path, validates the AI JSON with Pydantic, and returns typed reports or typed failures.

Scope: Implement a function such as `generate_reports_for_event_windows(event_window_ids, session_id)` that resolves IDs, builds bundles, calls the AI once per event window or in a controlled batch, validates every report, and returns all successes/failures. Out of scope: frontend and command runbook generation.

Context packet: inspect `src/backend/api/agent.py`, `src/backend/agent/service.py`, T1-T4 outputs, and existing backend tests.

Agent instructions: Treat Pydantic as the authority. If the AI response includes an invented severity/outcome, fail validation and optionally retry once with the validation error. Do not coerce unknown enum values into known ones. Prefer a result shape with `reports`, `failures`, `missing_event_window_ids`, and `session_id`.

Expansion path: If single-call batch generation creates ambiguous partial failures, switch to one AI call per event window for traceability, then optimize later.

Reuse/library check: Use existing `ask_soteria_agent` and `create_agent_client` unless a small wrapper is needed for structured JSON; avoid building a second cloud Agent SDK client stack.

Acceptance criteria: all resolved event windows produce either a valid report or a typed failure; invalid AI output does not crash the endpoint; invented categories are captured as validation failures; session IDs are deterministic enough to trace a local Poller dispatch.

Validation: Mock AI responses for all-valid, one-invalid-in-batch, invented severity, invented outcome, malformed JSON, and retry-success cases. Add an opt-in integration test or smoke script that calls the real cloud Agent SDK with a small evidence bundle when `CLAUDE_API_KEY` and the required live-test flag are present.

Dependencies: T1, T2, T3, T4.

Handoff: Report generation service, retry/validation behavior, and unit tests.

### T6: Add The Poller-Style Report Intake Endpoint
Outcome: Provide the backend endpoint that receives the local Poller HTTP dispatch and starts or performs report generation for all event-window IDs in the message.

Scope: Add or adjust an endpoint such as `POST /agent/reactions` or `POST /api/poller/report` to accept an `EventWindowReactionBatch`-style payload with `event_window_ids` from `HttpReactionDispatcher`. Return an accepted/generated response that includes counts, event-window IDs, report IDs or inline validated report summaries, and failures. Include local run instructions that set `SOTERIA_REACTION_SERVICE_URL` to the local backend endpoint. Out of scope: production Poller deployment changes unless needed after local validation passes.

Context packet: inspect `src/backend/api/agent.py`, `src/backend/api/poller.py`, `src/backend/main.py`, and T5 service.

Agent instructions: Keep the HTTP boundary typed with Pydantic. If background processing is used, return `202 accepted` plus a job/session ID. For live local validation, provide a deterministic way to wait for or retrieve completed report results. Do not allow the agent endpoint to accept arbitrary free-form report prompts for this production path.

Expansion path: Support both single-message and batch payloads only if transition risk is real; otherwise keep the new endpoint batch-only and update tests/dispatcher later.

Reuse/library check: Reuse the existing `EventWindowReactionBatch` model if it already expresses the needed Poller payload; avoid duplicating almost-identical request models.

Acceptance criteria: local Poller HTTP dispatch with multiple event-window IDs is accepted; the service receives exactly those IDs; response or readback reports generated/failed/missing counts; invalid request payloads return FastAPI validation errors.

Validation: FastAPI route tests with fake resolver and fake AI service remain required. The primary validation scenario is live: start the backend locally, set `SOTERIA_REACTION_SERVICE_URL` to the local report endpoint, run `uv run python -m api.poller` locally with live Supabase credentials, confirm the Poller posts real event-window IDs, and confirm the backend uses live Supabase plus the real cloud Agent SDK to produce validated reports for all dispatched event windows.

Dependencies: T5.

Handoff: Endpoint code, request/response models, and route tests.

### T7: Persist Or Expose Validated Reports
Outcome: Make generated validated reports retrievable after the live local Poller dispatch.

Scope: Either persist reports to Supabase or expose them through a tested in-process result shape, depending on current product need. If persisting, add a migration/table for event-window reports with report JSON, evidence hash, event-window ID, validation status, failures, and timestamps. Out of scope: frontend UI polish.

Context packet: inspect `src/backend/api/operations.py`, `supabase/migrations/20260621050000_create_command_runbooks.sql`, T1 report models, and T5 service results.

Agent instructions: Prefer durable persistence if the endpoint runs in background mode. Store validated reports as JSONB and separately indexed event-window IDs/status for querying. Store validation failures too; they are useful signal. Keep raw model prompts out of persistence unless the project explicitly chooses to audit prompts.

Expansion path: Add read endpoints only after write persistence is stable; start with enough fields for backend tests and future UI.

Reuse/library check: Reuse the Supabase query style from `operations.py`; do not add an ORM for this narrow slice.

Acceptance criteria: validated reports can be retrieved by event-window ID or session/job ID; failures are visible; duplicate live Poller dispatches with the same evidence hash are idempotent or explicitly documented as new attempts.

Validation: Migration applies; persistence tests cover success, validation failure, and duplicate/evidence-hash behavior.

Dependencies: T5, T6.

Handoff: Migration, persistence helper, optional read endpoint, and tests.

### T8: Add Live End-To-End Validation
Outcome: Prove the whole pipeline works with a real local Poller, live Supabase, and the real cloud Agent SDK.

Scope: Build a live integration validation script or opt-in test that starts or coordinates the local backend, runs the local Poller against live Supabase, receives the real Poller HTTP dispatch, resolves event-window and satellite rows from live Supabase, calls the real cloud Agent SDK, and validates/persists final reports. Keep mocked E2E tests as a separate fast safety net. Out of scope: browser/UI testing and production deployment.

Context packet: inspect `src/backend/tests/test_agent_api.py`, `src/backend/tests/test_operations_api.py`, T1-T7 outputs.

Agent instructions: Make the live validation read like the desired story: “local Poller running; live Supabase event window detected; backend receives real Poller HTTP dispatch; backend resolves IDs from live Supabase; agent receives evidence data through the real cloud Agent SDK; agent outputs reports for all event windows; Pydantic accepts only fixed severities/outcomes.” Include a mocked negative test where the fake AI invents an outcome and the endpoint reports validation failure, since forcing the live model to invent invalid output is not a reliable validation method.

Expansion path: After the first manual live run passes, wrap it in an opt-in command such as `RUN_LIVE_AGENT_PIPELINE_TESTS=true ...` so it can be repeated without hitting cloud services during default unit tests.

Reuse/library check: Use existing FastAPI/local-process test patterns, the current Poller entrypoint, and small shell/Python orchestration before creating a custom integration-test framework.

Acceptance criteria: one live local validation run dispatches at least one real event-window ID from the local Poller; live Supabase contains the event-window rows and satellite rows used for evidence; the real cloud Agent SDK returns report JSON; Pydantic validates one report per dispatched event window; generated reports or failures are retrievable; a mocked negative test still fails closed on invented outcome.

Validation: `uv run python -m unittest discover -s tests` passes from `src/backend` for mocked coverage, then the opt-in live validation passes with required env vars such as `SUPABASE_URL`, `SUPABASE_KEY` or `SUPABASE_SERVICE_ROLE_KEY`, `CLAUDE_API_KEY`, and `SOTERIA_REACTION_SERVICE_URL=http://127.0.0.1:<port>/<report-endpoint>`.

Dependencies: T6; T7 if persistence is included in the live validation path.

Handoff: Live validation script or command sequence, captured Poller payload example, generated report/readback evidence, mocked negative-path tests, and exact validation command output.

## Coordination Notes
- Critical decision gate: T1 must lock enum values before downstream agents implement prompt text, validation, persistence, or frontend contracts.
- Keep the AI behind a typed boundary. The backend owns event-window lookup, satellite lookup, allowed enums, and validation. The agent only drafts/selects within those constraints.
- The first implementation slice can use mocked tests for speed, but the acceptance gate is live: local Poller -> live Supabase rows -> local backend HTTP endpoint -> real cloud Agent SDK -> Pydantic report validation.
- Avoid assigning two agents to edit `src/backend/api/agent.py` at the same time. T6 owns endpoint edits; T5 owns service logic; merge through a single integration pass.
- The existing `agents/agent-api-evidence-pipeline-subtasks.md` overlaps with this plan but is broader. This plan supersedes it only for the Poller-ID-driven report-generation slice.

## Suggested Next Dispatch
Implement T1 first:

```
Use the task card T1 from agents/event-window-id-report-pipeline-subtasks.md. Lock the deterministic report taxonomy and add Pydantic models/tests for event-window report validation. Do not implement endpoint or Claude calls yet. Treat invented severity values, invented possible outcomes, invented event-window IDs, and invented satellite IDs as validation errors.
```
