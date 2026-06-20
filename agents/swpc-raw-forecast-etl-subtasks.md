# SWPC Raw Forecast ETL Subtasks

Generated: 2026-06-20

## Goal
Implement a working SWPC ingestion slice that fetches current NOAA products, stores raw payload metadata in Neon/Postgres, normalizes forecast-like rows into queryable records, and wires the Airflow DAG to run the flow.

## Assumptions
- Neon is reached through `NEON_DATABASE_URL` or the existing Airflow `warehouse` connection.
- Large raw payloads can be stored inline in `jsonb` for this first slice; `raw_uri` remains available for later object storage.
- The first normalized table targets forecast/event-source records, not all future measurement tables.
- The DAG can run one local verification path without a full scheduler if Airflow CLI or direct Python execution is available.

## Execution Shape
- Critical path: T1 -> T2 -> T3 -> T4 -> T6
- Parallel lanes: T5 can run alongside T3 after schemas are settled.
- Integration point: Airflow DAG imports the fetch, normalize, and Neon writer modules.

## Subtasks

### T1: Audit Existing ETL Scaffolding
Outcome: Identify current DAG structure, writer APIs, dependencies, and test conventions.

Scope: Inspect `src/backend/data/airflow/dags/spaceweather_dag.py`, `include/neon_db_writer.py`, endpoint definitions, requirements, and current tests.

Agent instructions: Preserve existing endpoint contracts and writer style. Do not introduce a new ORM unless it clearly reduces complexity.

Acceptance criteria: The implementation plan names the exact modules to add/edit and the minimal dependency changes.

Validation: Local file inspection and, if available, existing tests.

Dependencies: None.

Handoff: Short architecture note in implementation summary.

### T2: Design Database Schema and Migration Helper
Outcome: Create DDL for `swpc_raw_payloads` and `swpc_forecast_records`.

Scope: Include primary keys, uniqueness/idempotency keys, timestamps, endpoint/source metadata, JSONB payload/record fields, and useful indexes.

Agent instructions: Implement schema creation as code callable from the DAG and tests. Keep it compatible with Neon/Postgres.

Acceptance criteria: A single setup function can create both tables idempotently.

Validation: Unit test query strings where practical; integration run against Neon when configured.

Dependencies: T1.

Handoff: DDL module/function and any writer methods.

### T3: Implement NOAA Fetch and Raw Payload Persistence
Outcome: Fetch endpoint JSON with conditional headers and store raw payload rows.

Scope: Add fetch logic for SWPC endpoints, payload hashing, raw metadata rows, endpoint state usage, and idempotent upsert into `swpc_raw_payloads`.

Agent instructions: Respect existing `SWPC_ENDPOINTS` and `NeonDbWriter`. Do not print secrets. Handle unchanged responses and invalid JSON gracefully.

Acceptance criteria: Re-fetching the same payload does not duplicate raw rows because of `payload_hash` uniqueness.

Validation: Unit tests with mocked responses; live fetch during final verification.

Dependencies: T2.

Handoff: Fetch module plus DAG task integration.

### T4: Implement Forecast Record Normalization
Outcome: Normalize NOAA forecast-like products into `swpc_forecast_records`.

Scope: Support `noaa-scales`, alerts, Kp forecast/history, RTSW magnetic/plasma chart products where applicable enough for event-window inputs.

Agent instructions: Reuse `src/backend/data/util/classifier.py` behavior where useful. Store original parsed record in `record jsonb`; use typed columns for `valid_start`, `valid_end`, `issued_at`, `observed`, `severity`, `value`, and `units`.

Acceptance criteria: Normalization returns deterministic rows with stable `record_hash` or equivalent uniqueness.

Validation: Unit tests against representative payload examples and live NOAA payloads.

Dependencies: T2, T3.

Handoff: Normalizer module and writer method.

### T5: Add Focused Tests
Outcome: Protect schema creation, payload hashing, header-row parsing, and forecast-record extraction.

Scope: Tests should run without network and without Neon credentials.

Agent instructions: Use small inline payload fixtures. Avoid relying on current NOAA data for unit tests.

Acceptance criteria: Tests pass locally with the repo's Python test runner.

Validation: `pytest` or configured equivalent.

Dependencies: T2, T3, T4.

Handoff: Test files and command output summary.

### T6: Wire and Verify Airflow/Neon Execution
Outcome: Update `spaceweather_dag.py` so one run fetches current endpoints and writes raw + forecast records to Neon.

Scope: Ensure schema setup runs, endpoint fetches happen, raw payloads upsert, forecast records upsert, and current summary task reports counts.

Agent instructions: Prefer task functions that can also be imported and called directly for local verification. Request escalation for live NOAA/Neon network access. If credentials are absent, report the exact env/config needed.

Acceptance criteria: A local DAG/test execution writes rows when `NEON_DATABASE_URL` or Airflow `warehouse` is configured.

Validation: Run the DAG once through Airflow CLI if available; otherwise run the same task functions directly as a verification substitute and explain the difference.

Dependencies: T3, T4, T5.

Handoff: Final summary with files changed, verification command, and any blockers.

## Coordination Notes
- The minimum complete slice is raw payload insert plus normalized records from forecast-capable endpoints.
- The riskiest assumption is that Neon credentials are available in the execution environment.
- Event-window derivation should be a follow-up layer after this storage/forecast normalization slice is reliable.

## Suggested Next Dispatch
Implement T1 through T6 in the current repo, keeping changes scoped to the Airflow data package and adding tests for normalization/idempotency.
