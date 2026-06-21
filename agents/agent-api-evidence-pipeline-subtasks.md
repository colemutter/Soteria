# Agent API Evidence Pipeline Subtasks

Generated: 2026-06-21

## Goal
Build the report-generation path around the agent code as it exists now: Airflow ingests SWPC data, event windows are derived, active satellites are fetched, Pydantic evidence bundles are built, Claude drafts report JSON, Pydantic validates citations and schema, and the system persists the validated report plus evidence metadata. The same validated tool and report contracts should be reusable by a later chat mode exposed over the backend API.

## Assumptions
- Current Airflow ingestion and event-window derivation are already represented by `src/data/airflow/dags/spaceweather_dag.py`, `src/data/airflow/dags/swpc_event_windows_dag.py`, `src/data/airflow/include/swpc/event_windows.py`, and `src/data/airflow/include/supabase_swpc_writer.py`.
- `src/backend/agent/tools.py`, `client.py`, `definition.py`, and `service.py` are the current agent direction, even though they are not yet committed.
- The first API/chat-ready boundary is validated JSON data, not UI polish.
- The existing `agents/scheduled-ground-truth-reports-subtasks.md` remains relevant; this plan narrows the work around agent/API contracts and evidence validation.
- The `satellites` table is available through Supabase because `get_user_satellites` already queries it, but its SQL schema is not yet represented in `src/data/airflow/include/swpc/supabase_schema.sql`.

## Execution Shape
- Critical path: T1 -> T2 -> T3 -> T4 -> T5 -> T6
- Parallel lanes: T7 can begin after T2; T8 can begin after T3
- Integration point: the scheduled report DAG and future chat/API route both consume the same Pydantic tool outputs, evidence bundle models, and validated report model
- Riskiest assumption: Claude Agent SDK can be constrained enough to reliably return JSON for validation; if not, the retry/repair path must be explicit and observable

## Subtasks

### T1: Validate Current Tool Output Contracts
Outcome: Add Pydantic models for all MCP tool outputs in `src/backend/agent/tools.py` and make each real tool validate before returning text JSON.

Scope: Include models for tool envelopes, event-window query metadata, event-window rows, satellite filters, satellite rows, and command-tool stub outputs. Keep the current MCP tool names and signatures stable. Out of scope: changing Supabase query semantics or implementing the command stubs.

Context packet: inspect `src/backend/agent/tools.py`, `src/backend/agent/client.py`, `src/backend/agent/definition.py`, and `src/backend/pyproject.toml`. Pydantic v2 is already present through FastAPI/lockfile; prefer `BaseModel.model_validate()` and `model_dump(mode="json")`.

Agent instructions: Create a small module such as `src/backend/agent/tool_models.py` or `src/backend/agent/report_models.py` if the repo wants one shared model module. Validate raw Supabase rows through Pydantic row models before they enter `_tool_text`. Preserve `is_error` behavior with a typed error payload. Do not silently drop fields unless the model explicitly marks them as optional or excluded.

Reuse/library check: Before implementing custom serialization helpers, check whether Pydantic v2 `model_dump(mode="json")`, `TypeAdapter`, or `RootModel` covers the list/dict validation need cleanly.

Acceptance criteria: `get_event_windows` and `get_user_satellites` only return payloads that have passed Pydantic validation; malformed row data raises or returns a typed error payload; JSON text remains compatible with Claude MCP tool responses.

Validation: Add backend unit tests with mocked query functions for valid rows, invalid datetime/number fields, empty results, and error responses.

Dependencies: None.

Handoff: Code changes, model names, and test results.

### T2: Build Evidence Bundle Models And Builder
Outcome: Create a deterministic evidence-bundle layer that turns validated tool outputs into per-report evidence bundles.

Scope: Define models for `EventWindowEvidence`, `SatelliteSnapshot`, `EvidenceSourceRef`, `EvidenceBundle`, and `EvidenceBundleMetadata`. Include `evidence_hash`, source IDs, window horizon, bundle creation time, and the exact tool query metadata used. Out of scope: Claude calls and report persistence.

Context packet: inspect `src/backend/agent/tools.py`, `src/data/airflow/include/swpc/event_windows.py`, `src/data/airflow/include/swpc/supabase_schema.sql`, and `agents/scheduled-ground-truth-reports-subtasks.md`.

Agent instructions: Build evidence from validated event-window and satellite models, not from free-form Claude text. The builder should support both scheduled generation and future chat mode by accepting typed tool outputs or direct DB rows. Compute the hash from canonical JSON so reruns with the same evidence produce the same value.

Reuse/library check: Before implementing custom canonicalization, check whether Pydantic JSON serialization plus standard-library `json.dumps(..., sort_keys=True)` is sufficient.

Acceptance criteria: each bundle lists all source event-window IDs and satellite IDs; hash is stable across key ordering differences; bundles can be serialized to JSON for Claude and persisted for audit.

Validation: Unit tests cover stable hash, missing source IDs, empty windows, empty satellites, and one active-satellite bundle.

Dependencies: T1.

Handoff: Evidence model module, builder function, and tests.

### T3: Define Validated Report JSON And Citation Rules
Outcome: Add the report schema Claude must satisfy and the validation logic that rejects invented citations.

Scope: Define models such as `GroundTruthCitation`, `RiskFinding`, `RecommendedAction`, `SatelliteEventReport`, and `ReportGenerationFailure`. Add validators that check every citation source exists in the evidence bundle and every material finding has at least one event-window citation plus one satellite citation. Out of scope: persistence and API presentation formatting.

Context packet: use the output of T2, `src/backend/agent/definition.py`, and the existing scheduled-report plan.

Agent instructions: Keep the schema operational and API-friendly: stable IDs, severity/risk enums, short summary fields, cited findings, recommended follow-up, model metadata, and prompt version. Avoid Markdown as the primary stored report. Pydantic should validate Claude JSON with `model_validate()` or `model_validate_json()`.

Acceptance criteria: malformed JSON, missing fields, invented event IDs, invented satellite IDs, unsupported risk levels, and uncited findings fail validation with actionable error messages.

Validation: Unit tests include one valid report and failures for invented event citation, invented satellite citation, missing citation, and invalid risk enum.

Dependencies: T2.

Handoff: Report model module and validation test suite.

### T4: Implement Claude Structured Report Drafting
Outcome: Add a service function that sends an evidence bundle to Claude, receives report JSON, validates it, and returns either a typed report or a typed failure.

Scope: Add a service such as `generate_satellite_event_report(bundle, session_id=None)` under `src/backend/agent/`. It should use the existing `create_agent_client` setup, prompt Claude to output only JSON matching the report schema, validate through T3 models, retry once with validation errors, and expose model/prompt metadata. Out of scope: database writes and Airflow scheduling.

Context packet: inspect `src/backend/agent/client.py`, `src/backend/agent/service.py`, `src/backend/agent/definition.py`, and Claude Agent SDK usage already in this repo.

Agent instructions: Keep Claude as the drafting engine only. Do not let Claude fetch database rows for scheduled report generation after the evidence bundle has been built. Preserve the existing agent definitions unless a small prompt change is required to support JSON output.

Reuse/library check: Before implementing custom JSON extraction, check Claude Agent SDK support for structured output or schema-constrained responses; adopt it only if it reduces complexity after integration cost.

Acceptance criteria: valid Claude JSON becomes a `SatelliteEventReport`; invalid JSON or failed citation validation retries once and then returns a structured failure; no uncaught validation exception escapes the service boundary.

Validation: Mock Claude responses for valid JSON, fenced JSON, malformed JSON, invented citation, and retry success.

Dependencies: T3.

Handoff: Report drafting service, prompt/schema text, retry behavior, and tests.

### T5: Persist Reports And Evidence Metadata
Outcome: Add durable persistence for validated reports and failed generation attempts.

Scope: Extend Supabase schema and writer/service code with `satellite_event_reports` and optionally `satellite_event_report_sources` or equivalent JSONB source metadata. Store evidence bundle JSON/hash, report JSON, source IDs, satellite ID, horizon, generation status, validation errors, model, prompt version, session ID, and timestamps. Out of scope: frontend report UI.

Context packet: inspect `src/data/airflow/include/swpc/supabase_schema.sql`, `src/data/airflow/include/supabase_swpc_writer.py`, and T2/T3 models.

Agent instructions: Use an idempotent upsert key based on satellite ID, horizon start/end, evidence hash, and prompt version. Persist failures too, because validation failures are operational signals. Keep secrets and raw prompts out of durable rows unless explicitly approved.

Acceptance criteria: successful reports and failures are auditable; duplicate reruns with the same evidence do not create duplicates; source event-window IDs and satellite IDs can be queried without parsing free-form text.

Validation: SQL migration applies locally; writer/service tests prove idempotent upsert and failure persistence.

Dependencies: T2, T3, T4.

Handoff: SQL migration/schema update, persistence functions, and tests.

### T6: Wire The Scheduled Airflow Report Path
Outcome: Add an Airflow task or DAG that runs after event-window derivation and generates reports from validated evidence bundles.

Scope: Fetch active satellites, build evidence bundles, call the report drafting service or a narrow backend-compatible function, validate/persist results, and emit a summary. Prefer a downstream task relationship from `swpc_event_window_etl` or a triggered/dataset DAG rather than a blind cron. Out of scope: chat UX and command-plan agents.

Context packet: inspect `src/data/airflow/dags/swpc_event_windows_dag.py`, `src/data/airflow/dags/spaceweather_dag.py`, `src/data/airflow/include/supabase_swpc_writer.py`, and T4/T5 outputs.

Agent instructions: Be careful about package boundaries between Airflow and backend. If importing backend agent code into Airflow creates deployment friction, create a thin shared module or call a backend API endpoint with a typed request/response. Make the dependency explicit in the handoff.

Acceptance criteria: reports run only after event windows are fresh; `max_active_runs=1`; retries are configured; summary includes attempted, succeeded, failed, skipped, and evidence hashes.

Validation: Airflow DAG parse test plus a local `dag.test()` or mocked task test that avoids real Claude/Supabase calls.

Dependencies: T5.

Handoff: DAG/task changes, deployment notes, and test output.

### T7: Expose API And Future Chat-Mode Contracts
Outcome: Add a minimal backend API surface that can call the current agent service and return typed responses suitable for later chat mode.

Scope: Create or repair `src/backend/api/agent.py` because `src/backend/main.py` imports it but only `src/backend/api/__init__.py` exists. Add request/response models for agent chat, report generation/readback, and report status as appropriate. Keep endpoints read/generate oriented; do not add frontend work.

Context packet: inspect `src/backend/main.py`, `src/backend/agent/service.py`, `src/backend/agent/client.py`, and the T1-T5 models.

Agent instructions: Use Pydantic FastAPI models at the HTTP boundary and reuse the same internal models where possible. Preserve session IDs for chat continuity. The API should not return raw Claude SDK message objects.

Acceptance criteria: FastAPI app imports cleanly; `/agent` or equivalent routes return typed JSON; future chat mode can use the same tool contracts and evidence/report validation models.

Validation: Backend import test and FastAPI route tests with mocked agent service.

Dependencies: T1, T3. Can run in parallel with T5/T6 after the model contracts settle.

Handoff: API route module, request/response models, and route tests.

### T8: Add End-To-End Contract QA
Outcome: Create a small contract test suite that proves the pipeline shape works without live external services.

Scope: Use fixtures/mocks for event windows, satellites, Claude JSON, and Supabase writes. Cover the path from validated tool output to evidence bundle, report validation, persistence payload, and API response shape. Out of scope: live Astronomer, live Supabase, live Claude, and frontend screenshots.

Context packet: use tests added in T1-T7 and current Airflow tests under `src/data/airflow/tests/`.

Agent instructions: Keep the test suite deterministic and fast. Favor unit/contract tests over brittle full orchestration. Include at least one regression test for invented citations because that is the core safety guarantee.

Acceptance criteria: one command can run the backend contract tests; failures identify whether the break happened at tool validation, evidence bundling, report validation, persistence shaping, or API response shaping.

Validation: Document the test command used, such as running pytest/unittest from `src/backend` and Airflow tests from `src/data/airflow`.

Dependencies: T1-T7.

Handoff: Test suite, fixtures, and command output.

## Coordination Notes
- The first implementation dispatch should be T1, because every downstream path needs validated tool outputs.
- Keep scheduled reports and chat mode sharing model contracts, but do not force them to share orchestration. Scheduled reports can be deterministic and batch-oriented; chat can remain session-oriented.
- Do not let Claude be the source of truth for event windows, active satellites, or citation IDs. Claude can draft narrative JSON only from an evidence bundle assembled by code.
- The existing `agents/scheduled-ground-truth-reports-subtasks.md` can still guide persistence and Airflow scheduling details; this plan should guide the agent/API model contracts.

## Suggested Next Dispatch
Implement T1 first: add Pydantic tool-output models for `src/backend/agent/tools.py`, validate `get_event_windows` and `get_user_satellites` outputs before `_tool_text`, preserve the current MCP response shape, and add mocked unit tests for valid rows, invalid row fields, empty results, and typed error payloads.
