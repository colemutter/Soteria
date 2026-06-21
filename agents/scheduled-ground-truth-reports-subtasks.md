# Scheduled Ground Truth Reports Subtasks

Generated: 2026-06-21

## Goal
Generate satellite-specific space-weather reports every 10 hours after Airflow ingests new SWPC data and derives event windows. Reports must be grounded in database truth, validated with Pydantic, and persisted with evidence citations.

## Assumptions
- `space_weather_event_windows` is the source of truth for event windows.
- `satellites` is the source of truth for user satellite state.
- Claude Agent SDK is used for report drafting, not for database writes.
- Airflow should own scheduling and idempotent persistence.
- The minimum report horizon is "now through N hours" with N configurable.

## Execution Shape
- Critical path: T1 -> T2 -> T3 -> T5 -> T6
- Parallel lanes: T4 can run after T1; T7 can run after T3
- Integration point: the report DAG calls the report-generation service with a Pydantic evidence bundle

## Subtasks

### T1: Design Report Persistence Schema
Outcome: Add a durable `satellite_event_reports` table and optional `satellite_event_report_sources` table.

Scope: Include report identity, satellite id, event horizon, source row ids, evidence bundle JSON, validated report JSON, model metadata, prompt version, generation status, and error text. Out of scope: frontend report UI.

Context packet: inspect `src/data/airflow/include/swpc/supabase_schema.sql`, `src/frontend/src/lib/satelliteSync.ts`, and `src/backend/agent/tools.py`.

Acceptance criteria: schema supports idempotent upsert by `(satellite_external_id, horizon_start, horizon_end, evidence_hash, prompt_version)` and stores enough source ids to audit every claim.

Validation: SQL migration applies locally or in Supabase; duplicate report generation upserts instead of duplicating rows.

### T2: Define Pydantic Evidence And Report Models
Outcome: Create `src/backend/agent/report_models.py`.

Scope: Models for `EventWindowEvidence`, `SatelliteSnapshot`, `EvidenceBundle`, `GroundTruthCitation`, `RiskFinding`, and `SatelliteEventReport`.

Agent instructions: Use strict Pydantic validation where useful. Add validators that reject citations whose `source_id` is not present in the evidence bundle. Require every finding to include at least one event-window citation and one satellite citation.

Acceptance criteria: invalid JSON, invented source IDs, missing citations, and out-of-range risk levels fail validation.

Validation: unit tests cover valid report, invented event id, invented satellite id, and missing citation cases.

### T3: Build Deterministic Evidence Bundle Query
Outcome: Create a Python service that queries event windows and satellites directly from Supabase and returns one evidence bundle per satellite.

Scope: Fetch event windows overlapping `[now, horizon_end]`, fetch active satellites, pair each satellite with relevant windows, compute `evidence_hash`, and remove unnecessary fields before sending to Claude.

Agent instructions: Treat DB rows as ground truth. Do not ask Claude to decide what rows exist. Keep TLE inclusion off by default unless a report explicitly needs orbital element context.

Acceptance criteria: service can produce bundles for all active satellites and records the row ids used.

Validation: mocked Supabase tests prove query filters and hash stability.

### T4: Implement Claude Structured Report Drafting
Outcome: Add `generate_satellite_event_report(bundle)` that calls Claude Agent SDK and validates the result through Pydantic.

Scope: Claude receives only the evidence bundle and report schema instructions. Pydantic parses the result and verifies citations. Failed validation should retry once with validation errors, then persist failure metadata.

Reuse/library check: Before implementing custom structured-output parsing, check Claude Agent SDK support for `output_format` or schema-constrained JSON; use it if it reduces code.

Acceptance criteria: output is a `SatelliteEventReport`, not free-form Markdown.

Validation: mocked Claude responses test valid JSON, malformed JSON, and invented citations.

### T5: Add Airflow Report Generation DAG
Outcome: Add an Airflow DAG that runs after event-window derivation and generates per-satellite reports.

Scope: Prefer a single chained DAG if ingestion, event-window derivation, and report generation should always run together. If separate DAGs are kept, use a sensor/dataset/trigger relationship so reports run after the successful event-window task, not on a blind clock.

Acceptance criteria: schedule is every 10 hours or event-driven from the 10-hour ingestion DAG; `max_active_runs=1`; retries are configured; report rows are idempotent.

Validation: `dag.test()` or local Airflow test executes with mocked Claude/Supabase dependencies.

### T6: Persist Reports And Audit Metadata
Outcome: Store validated reports and validation failures.

Scope: Upsert successful reports; persist failed attempts with error details, source ids, model, prompt version, and evidence hash. Do not discard failures silently.

Acceptance criteria: each report can be traced to exact event-window ids, satellite row id, evidence hash, prompt version, model, and generated timestamp.

Validation: tests prove reruns with identical evidence do not duplicate rows.

### T7: Add Minimal Operator/API Read Path
Outcome: Provide a backend route or helper to list latest reports by satellite.

Scope: Read-only API for latest reports; no frontend polish required.

Acceptance criteria: can retrieve latest report per satellite and inspect evidence metadata.

Validation: API test or direct service test with mocked Supabase.

## Coordination Notes
- Riskiest assumption: the `satellites` table schema exists in Supabase even though it is not yet represented in the SQL schema file.
- Grounding rule: Claude may summarize and reason over supplied rows, but it may not create source facts. Pydantic citation validation is the enforcement layer.
- Scheduling rule: "Every 10 hours after ingestion" is best modeled as a downstream report task in the same DAG or as a triggered/dataset DAG, not as a separate blind cron.

## Suggested Next Dispatch
Implement T2 first: create `report_models.py` with strict Pydantic models and citation validators, then add tests proving invented source IDs fail validation.
