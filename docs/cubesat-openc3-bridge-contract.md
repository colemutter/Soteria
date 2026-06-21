# CubeSat OpenC3 Bridge Contract

Generated: 2026-06-21

This contract is simulator-only. It defines how Soteria command requests become
OpenC3/COSMOS command executions against the NOS3-backed CubeSat bench, and how
execution results, telemetry verification, and latest simulator state return to
Supabase. It is not a flight command procedure, spacecraft command authority,
RF uplink path, or claim of flight qualification.

## Scope And Sources

This document specifies behavior and future schema shape only. It does not
write bridge code, apply Supabase migrations, create OpenC3 targets, or change
agent tools.

Local source basis:

- `docs/cubesat-openc3-command-catalog.md`: versioned catalog
  `nos3-openc3-v1_07_04-cmdcat.20260621`, exact OpenC3 target/command names,
  typed args, automation/review flags, preconditions, and telemetry verifiers.
- `docs/cubesat-openc3-automation-decision.md`: primary automation path is the
  private OpenC3 JSON API using standard `cmd`; telemetry verification uses
  bounded `tlm`, `tlm_raw`, or `tlm_formatted` reads; direct cFS/UDP injection
  and no-check command variants are rejected for production automation.
- `agents/cubesat-nos3-openc3-commanding-subtasks.md`: Supabase is the product
  I/O layer; the bridge executes through OpenC3 and writes results/state back.
- Existing migrations under `supabase/migrations/`: current schema has
  `satellites`, `command_runbooks`, and event/report tables, but no command
  queue, command result, or latest CubeSat simulator-state tables yet.
- `src/backend/agent/tools.py`: current satellite command tools are redacted or
  draft-only; future executable tooling must remain catalog-id based.

Official OpenC3 source basis:

- [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api): external
  applications can send commands and read telemetry through JSON-RPC at
  `/openc3-api/api`; supported command methods include `cmd`, and telemetry
  methods include `tlm`, `tlm_raw`, and `tlm_formatted`.
- [OpenC3 command configuration](https://docs.openc3.com/docs/configuration/command):
  command definitions own target command spelling, parameter names, defaults,
  ranges, and required parameters.
- [OpenC3 telemetry configuration](https://docs.openc3.com/docs/configuration/telemetry):
  COSMOS decommutates telemetry and makes raw/decommutated values available for
  real-time and historical access.
- [OpenC3 Scripting API](https://docs.openc3.com/docs/guides/scripting-api):
  standard `cmd` preserves command checks; no-check variants are available but
  must not be used by this bridge unless a future catalog row explicitly allows
  a simulator-only, human-approved bench test.

## Contract Principles

1. The AI agent never sends OpenC3 target names, command names, raw command
   strings, OpenC3 credentials, UDP packets, or no-check method names.
2. Soteria writes only catalog command requests to Supabase. The private bridge
   resolves target/command/args from the pinned catalog after claiming a row.
3. No catalog entry means no send. `unresolved`, `manual_only`, unknown, stale,
   expired, unauthorized, or unapproved rows terminate before OpenC3.
4. Every possible send has a durable correlation id, send-intent result record,
   and row claim before the bridge calls OpenC3.
5. OpenC3 commands are side-effecting. The bridge may retry only when it can
   prove no send reached OpenC3. Ambiguous sends are verification-only and must
   not be blindly resent.
6. Command success requires both an OpenC3 command response and catalog-defined
   telemetry/postcondition verification unless the catalog explicitly defines a
   different verifier.

## Proposed Supabase Contract

The names below are the contract names for future migrations. They are not
present in the current migrations yet.

### `cubesat_commands`

One row per requested simulator command.

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key. |
| `satellite_id` | uuid | yes | References `public.satellites(id)`. Part of idempotency. |
| `satellite_external_id` | text | no | Copy from `satellites.external_id` for diagnostics. |
| `catalog_version` | text | yes | Must match a pinned Soteria/OpenC3 catalog version. |
| `catalog_command_id` | text | yes | Catalog ID such as `cfs_noop`; no raw target/command text is accepted. |
| `args` | jsonb | yes | Request args before bridge defaulting. Empty object for no-arg commands. |
| `canonical_args_hash` | text | yes | Hash of catalog-validated, defaulted, sorted args. |
| `idempotency_key` | text | yes | Caller-provided stable key for the user action or agent decision. |
| `source` | text | yes | Allowed values: `ai_agent`, `operator_ui`, `system_test`, `bridge_recovery`. |
| `source_actor_id` | text | no | User, agent session, or service identity. |
| `source_trace_id` | text | no | Report/runbook/session trace for audit. |
| `runbook_id` | uuid | no | Optional reference to `command_runbooks(id)`. |
| `requested_at` | timestamptz | yes | Insert time. |
| `not_before` | timestamptz | no | Earliest time the bridge may claim the command. |
| `expires_at` | timestamptz | yes | Hard stop; no OpenC3 call after this instant. |
| `status` | text | yes | One of the lifecycle states below. Starts as `queued`. |
| `priority` | int | yes | Claim ordering inside eligible rows. |
| `required_state_version` | bigint | no | Optional optimistic state guard from `cubesat_latest_state`. |
| `required_state_fresh_after` | timestamptz | no | Reject as stale if latest state is older. |
| `approval_id` | text | no | Required before sending catalog rows with human review. |
| `approved_by` | text | no | Operator identity for reviewed rows. |
| `approved_at` | timestamptz | no | Review timestamp. |
| `correlation_id` | text | yes | Stable id shared across command, result, logs, and telemetry samples. |
| `attempt_count` | int | yes | Number of bridge attempts. |
| `retry_after` | timestamptz | no | Backoff gate for safe no-send retries. |
| `claimed_by` | text | no | Worker id that currently owns the row. |
| `claim_token` | uuid | no | Random token required for all bridge updates after claim. |
| `claimed_at` | timestamptz | no | Claim acquisition time. |
| `claim_expires_at` | timestamptz | no | Recovery time if worker disappears. |
| `last_result_id` | uuid | no | Most recent `cubesat_command_results(id)`. |
| `last_error_class` | text | no | Last rejection/failure class. |
| `created_at` / `updated_at` | timestamptz | yes | Database-managed timestamps. |

Required uniqueness:

```text
UNIQUE (
  satellite_id,
  catalog_version,
  catalog_command_id,
  idempotency_key,
  canonical_args_hash
)
```

If the same idempotency tuple is inserted again, the API returns the existing
row. If the same `idempotency_key` is reused for the same
`satellite_id/catalog_version/catalog_command_id` with different args, the API
rejects the request as an idempotency conflict.

### `cubesat_command_results`

Append-only audit trail for bridge validation, send, verifier, recovery, and
terminal outcomes.

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `id` | uuid | yes | Primary key. |
| `command_id` | uuid | yes | References `cubesat_commands(id)`. |
| `satellite_id` | uuid | yes | Copy for partitioning/querying. |
| `correlation_id` | text | yes | Same value as command row. |
| `execution_id` | text | yes | Bridge/OpenC3 JSON-RPC id for this attempt. |
| `attempt_number` | int | yes | Copy of command attempt. |
| `bridge_worker_id` | text | yes | Worker that wrote the row. |
| `status` | text | yes | Lifecycle status after this event. |
| `result_class` | text | yes | Success, rejection, or failure class. |
| `send_outcome` | text | yes | `not_sent`, `confirmed`, or `ambiguous`. |
| `openc3_target` | text | no | Resolved target actually sent. Null when not sent. |
| `openc3_command` | text | no | Resolved command actually sent. Null when not sent. |
| `openc3_args` | jsonb | yes | Resolved args actually sent, or `{}` when not sent. |
| `sent_at` | timestamptz | no | Time the bridge made the OpenC3 command call. |
| `finished_at` | timestamptz | no | Time this result became terminal for the attempt. |
| `payload` | jsonb | yes | Full result payload shape below. |
| `created_at` | timestamptz | yes | Insert timestamp. |

The result table is append-only. Corrections are new rows with the same
`command_id` and `correlation_id`, not updates to old payloads.

### `cubesat_latest_state`

One row per simulator satellite with the newest bridge-observed state.

| Field | Type | Required | Contract |
| --- | --- | --- | --- |
| `satellite_id` | uuid | yes | Primary key and reference to `satellites(id)`. |
| `simulator_stack` | text | yes | `nos3_openc3`. |
| `catalog_version` | text | yes | Catalog used to interpret state. |
| `openc3_scope` | text | yes | Usually `DEFAULT`. |
| `state_version` | bigint | yes | Monotonic version incremented on every update. |
| `state` | jsonb | yes | Normalized simulator state used by Soteria. |
| `telemetry` | jsonb | yes | Latest raw/converted/formatted telemetry samples by source. |
| `fresh_at` | timestamptz | yes | Newest telemetry observation included in `state`. |
| `stale_after` | timestamptz | yes | State is stale after this time unless refreshed. |
| `last_command_id` | uuid | no | Last command that changed or verified state. |
| `last_result_id` | uuid | no | Result row supporting the state change. |
| `last_correlation_id` | text | no | Correlation id for the supporting command/verifier. |
| `updated_by` | text | yes | Bridge worker or telemetry ingestor id. |
| `updated_at` | timestamptz | yes | Database-managed timestamp. |

Latest-state writes must be source-backed by OpenC3 telemetry. Agent
assertions, report text, and runbook text never update this table directly.

## Lifecycle

| Status | Meaning | OpenC3 send allowed? |
| --- | --- | --- |
| `queued` | Row is durable and eligible for a bridge claim after `not_before` and before `expires_at`. | Not yet. |
| `accepted` | A worker has exclusively claimed the row and passed initial catalog/source/expiry gates. | Not until send-intent result is durable. |
| `rejected` | Terminal no-send outcome for invalid, unauthorized, stale, unresolved, or failed-precondition requests. | No. |
| `running` | Send-intent is durable and the OpenC3 command is in progress, confirmed sent, or being verified. Treat as possibly side-effected. | Already attempted; do not duplicate. |
| `succeeded` | OpenC3 response and telemetry verifier/postcondition satisfied. | No further send. |
| `failed` | OpenC3 call, ambiguous send, verifier, or postcondition failed after claim. | No automatic resend unless explicitly classified no-send and requeued before terminal failure. |
| `expired` | `expires_at` passed before the bridge could safely send. | No. |
| `manual_review_required` | Catalog row is valid but needs operator approval before queueing/execution can continue. | No until approved. |

### State-Transition Table

| From | To | Trigger | Required result class |
| --- | --- | --- | --- |
| insert | `queued` | `enqueue_cubesat_command` accepts catalog-id request. | n/a |
| `queued` | `accepted` | Atomic worker claim. | `accepted` |
| `queued` | `expired` | Claim or expiry sweep sees `expires_at <= now()`. | `expired_command` |
| `accepted` | `rejected` | Catalog/source/state/precondition gate fails before send. | See rejection classes. |
| `accepted` | `manual_review_required` | Catalog requires human review and approval fields are absent. | `human_review_required` |
| `manual_review_required` | `queued` | Operator approval arrives before expiry. | `approved_for_execution` |
| `manual_review_required` | `expired` | Approval does not arrive before `expires_at`. | `expired_command` |
| `accepted` | `queued` | Safe retry: transient OpenC3/auth/read failure before any send attempt. | `openc3_unavailable` |
| `accepted` | `running` | Send-intent result is durable and bridge is about to call OpenC3. | `send_intent_recorded` |
| `running` | `succeeded` | OpenC3 response plus verifier/postcondition succeeds. | Catalog success class. |
| `running` | `failed` | OpenC3 error, ambiguous send, verifier timeout, or failed postcondition. | See rejection/failure classes. |
| `accepted` | `expired` | Expiry reached before send-intent. | `expired_command` |
| terminal | terminal | `succeeded`, `failed`, `rejected`, and `expired` are immutable. | n/a |

## Row Claiming And Recovery

Workers must claim with one database transaction. The intended PostgreSQL shape
is:

```sql
WITH candidate AS (
  SELECT id
  FROM cubesat_commands
  WHERE status = 'queued'
    AND COALESCE(not_before, now()) <= now()
    AND COALESCE(retry_after, now()) <= now()
    AND expires_at > now()
  ORDER BY priority DESC, requested_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE cubesat_commands c
SET status = 'accepted',
    claimed_by = :worker_id,
    claim_token = gen_random_uuid(),
    claimed_at = now(),
    claim_expires_at = now() + interval '90 seconds',
    attempt_count = attempt_count + 1,
    updated_at = now()
FROM candidate
WHERE c.id = candidate.id
RETURNING c.*;
```

Every later update must include `WHERE id = :id AND claim_token = :claim_token`
and must fail closed if no row is updated. This prevents two bridge workers
from executing the same command.

For `running` rows whose claim expired, a recovery worker may claim with a
separate recovery query. Recovery claims must not resend. They may only inspect
the durable result payload, resume telemetry verification, and move the row to
`succeeded` or `failed`.

## Catalog Resolution And Bypass Prevention

The bridge resolves commands in this order:

1. Load the exact `catalog_version` requested by the row.
2. Find `catalog_command_id`.
3. Reject `unknown_command` if the ID is missing.
4. Reject `unresolved_catalog_entry` if the row is `unresolved`,
   `unresolved_rejected`, `manual_only`, or lacks target/command/verifier data.
5. Reject `human_review_required` if the row has
   `human_review_required = true` and no valid approval fields.
6. Validate `source` against the command's allowed source policy.
7. Canonicalize and type-check args. Defaults come from the catalog/OpenC3
   dictionary. Unknown args, out-of-range args, and enum mismatches are rejected
   before OpenC3.
8. Evaluate latest-state freshness and preconditions.
9. Use the catalog's target, command, args, verifier, timeout, and result class
   to build the OpenC3 JSON-RPC call.

Bridge input rows must not contain executable `target`, `command`,
`command_string`, `openc3_method`, or network-address fields. If a future API
or runbook stores those fields for display, the bridge ignores them and
resolves execution only from the catalog. The bridge always uses OpenC3
standard `cmd`; it must not call `cmd_no_range_check`,
`cmd_no_hazardous_check`, `cmd_no_checks`, raw command injection, or direct
cFS/UDP paths for current first-slice automation.

## Idempotency

Idempotency is enforced before a row can be queued.

Canonical key components:

```json
{
  "satellite_id": "<uuid>",
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "catalog_command_id": "sample_disable",
  "idempotency_key": "agent-session-42:disable-sample:20260621T190000Z",
  "canonical_args": {}
}
```

Rules:

- The client supplies `idempotency_key`; the server computes
  `canonical_args_hash` after catalog validation and defaulting.
- Repeating the same key, catalog version, satellite, command id, and canonical
  args returns the existing command row and does not enqueue a duplicate.
- Reusing the same key for different args or catalog version is rejected as an
  idempotency conflict.
- Idempotency prevents duplicate Soteria queue rows. It does not make OpenC3
  command execution itself idempotent, so bridge retry rules still apply.

## Rejection And Failure Classes

| Class | Terminal status | OpenC3 called? | Meaning |
| --- | --- | --- | --- |
| `unknown_command` | `rejected` | no | `catalog_command_id` is absent from `catalog_version`. |
| `unresolved_catalog_entry` | `rejected` | no | Catalog row is unresolved, rejected, manual-only, or lacks executable target/command/verifier data. |
| `unauthorized_source` | `rejected` | no | `source` or actor is not allowed to request this catalog command. |
| `stale_state` | `rejected` | no | Required `cubesat_latest_state` version/freshness guard is not satisfied. |
| `expired_command` | `expired` | no | `expires_at` passed before safe send. |
| `human_review_required` | `manual_review_required` | no | Catalog row needs approval and no valid approval exists. |
| `openc3_unavailable` | `queued` or `failed` | no if requeued; maybe ambiguous if already running | OpenC3 API/auth/transport is unavailable. Safe no-send attempts may retry; ambiguous attempts do not. |
| `telemetry_verifier_timeout` | `failed` | yes | Command response returned, but verifier condition did not become true before timeout. |
| `precondition_failed` | `rejected` | no | Catalog precondition failed before send. |
| `postcondition_failed` | `failed` | yes | Verifier ran but observed a contradictory postcondition. |
| `ambiguous_send` | `failed` | unknown | Bridge cannot prove whether OpenC3 received the command. No automatic resend. |
| `openc3_command_error` | `failed` | yes | JSON-RPC error or command rejection returned by OpenC3. |

## Result Payload Shape

Every `cubesat_command_results.payload` uses this shape. Null values are
allowed only when no send occurred.

```json
{
  "contract_version": "cubesat-openc3-bridge-contract.v1",
  "command_row_id": "00000000-0000-0000-0000-000000000001",
  "result_row_id": "00000000-0000-0000-0000-000000000101",
  "satellite_id": "00000000-0000-0000-0000-0000000000a1",
  "correlation_id": "cmdcorr_20260621_190000_0001",
  "execution_id": "cmdexec_20260621_190000_0001",
  "attempt_number": 1,
  "idempotency": {
    "idempotency_key": "agent-session-42:cfs-noop:20260621T190000Z",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "cfs_noop",
    "canonical_args_hash": "sha256:..."
  },
  "catalog": {
    "simulator_stack": "nos3_openc3",
    "target": "CFS",
    "command": "CFE_ES_NOOP",
    "result_classification": "success_when_counter_increments",
    "source_doc": "docs/cubesat-openc3-command-catalog.md"
  },
  "openc3": {
    "api": "json_rpc",
    "scope": "DEFAULT",
    "method": "cmd",
    "target": "CFS",
    "command": "CFE_ES_NOOP",
    "args": {},
    "json_rpc_id": "cmdexec_20260621_190000_0001",
    "send_started_at": "2026-06-21T19:00:03Z",
    "sent_at": "2026-06-21T19:00:03.214Z",
    "send_outcome": "confirmed",
    "request": {
      "jsonrpc": "2.0",
      "method": "cmd",
      "params": ["CFS", "CFE_ES_NOOP", {}],
      "id": "cmdexec_20260621_190000_0001",
      "keyword_params": {"scope": "DEFAULT"}
    },
    "response": {
      "jsonrpc": "2.0",
      "result": ["CFS", "CFE_ES_NOOP", {}],
      "id": "cmdexec_20260621_190000_0001"
    },
    "error": null
  },
  "telemetry_verifier": {
    "target": "CFS",
    "packet": "CFE_ES_HKPACKET",
    "item": "CMDCOUNTER",
    "type": "CONVERTED",
    "condition": "increments",
    "timeout_seconds": 10,
    "polling_rate_seconds": 0.5,
    "before": {
      "value": 41,
      "observed_at": "2026-06-21T19:00:02.800Z",
      "source": "openc3_json_api:tlm"
    },
    "after": {
      "value": 42,
      "observed_at": "2026-06-21T19:00:04.118Z",
      "source": "openc3_json_api:tlm"
    },
    "samples": [
      {"value": 41, "observed_at": "2026-06-21T19:00:03.600Z"},
      {"value": 42, "observed_at": "2026-06-21T19:00:04.118Z"}
    ],
    "status": "satisfied"
  },
  "state_updates": [
    {
      "table": "cubesat_latest_state",
      "state_path": "cfs.command_counter",
      "before": 41,
      "after": 42,
      "state_version_after": 1235
    }
  ],
  "logs": {
    "bridge_log_pointer": "gcp-log://soteria-openc3-bridge/cmdcorr_20260621_190000_0001",
    "openc3_command_log_pointer": "openc3://cmd-history/CFS/CFE_ES_NOOP/cmdexec_20260621_190000_0001",
    "telemetry_window_pointer": "openc3://tlm/CFS/CFE_ES_HKPACKET/CMDCOUNTER?from=2026-06-21T19:00:02Z&to=2026-06-21T19:00:05Z"
  },
  "error": null
}
```

Result payloads must never include OpenC3 auth tokens, Supabase service-role
keys, SSH/IAP credentials, or unredacted secrets.

## Retry And Ambiguity Handling

Safe retry is allowed only for no-send attempts:

- catalog/source/state/precondition failures are terminal and not retried;
- OpenC3 auth/token refresh may retry once in memory before result recording;
- OpenC3 unavailable before send-intent or before any command request bytes are
  sent may requeue with exponential backoff while `expires_at` remains in the
  future;
- after the bridge records send-intent and enters `running`, any transport
  timeout, process crash, or missing HTTP response is `ambiguous_send` unless
  OpenC3 later proves command rejection or success;
- ambiguous sends are not retried automatically, even if the catalog command
  appears harmless;
- recovery may continue telemetry verification for an ambiguous or confirmed
  send, because verification is read-only;
- humans may create a new command row with a new idempotency key after reviewing
  logs, state, and telemetry.

Suggested attempt limits:

| Case | Automatic retries | Notes |
| --- | --- | --- |
| OpenC3 auth refresh fails before send | 1 immediate refresh, then backoff attempt | No command sent. |
| OpenC3 API unreachable before send | Up to 3 attempts or until `expires_at` | Requeue as `queued` with `retry_after`; terminal `failed` after limit. |
| JSON-RPC command error | 0 | Terminal `failed`; OpenC3 rejected or errored. |
| HTTP timeout after request transmission | 0 sends; verifier-only recovery allowed | Terminal if verifier cannot prove success. |
| Telemetry verifier timeout after confirmed send | 0 | Terminal `failed`; do not resend side-effecting command. |
| Bridge restart while `running` | 0 sends; verifier-only recovery allowed | Claim expired `running` row and resume verification. |

## Example Rows

### 1. Accepted NOOP

Command row after bridge claim:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "11111111-1111-1111-1111-111111111111",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "cfs_noop",
    "args": {},
    "canonical_args_hash": "sha256:44136fa355b3678a1146ad16f7e8649e",
    "idempotency_key": "agent-evt-9001:cfs-noop",
    "source": "ai_agent",
    "source_actor_id": "satellite-command-agent",
    "requested_at": "2026-06-21T19:00:00Z",
    "expires_at": "2026-06-21T19:02:00Z",
    "status": "accepted",
    "attempt_count": 1,
    "claimed_by": "openc3-bridge-worker-a",
    "claimed_at": "2026-06-21T19:00:02Z",
    "claim_expires_at": "2026-06-21T19:01:32Z",
    "correlation_id": "cmdcorr_noop_001"
  }
}
```

Bridge result after acceptance, send, and verifier success:

```json
{
  "table": "cubesat_command_results",
  "row": {
    "command_id": "11111111-1111-1111-1111-111111111111",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_noop_001",
    "execution_id": "cmdexec_noop_001",
    "attempt_number": 1,
    "status": "succeeded",
    "result_class": "success_when_counter_increments",
    "send_outcome": "confirmed",
    "openc3_target": "CFS",
    "openc3_command": "CFE_ES_NOOP",
    "openc3_args": {},
    "sent_at": "2026-06-21T19:00:03Z",
    "payload": {
      "openc3": {
        "method": "cmd",
        "target": "CFS",
        "command": "CFE_ES_NOOP",
        "args": {},
        "response": {"result": ["CFS", "CFE_ES_NOOP", {}]}
      },
      "telemetry_verifier": {
        "target": "CFS",
        "packet": "CFE_ES_HKPACKET",
        "item": "CMDCOUNTER",
        "condition": "increments",
        "before": {"value": 41},
        "after": {"value": 42},
        "status": "satisfied"
      }
    }
  }
}
```

### 2. Accepted Sample Disable

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "22222222-2222-2222-2222-222222222222",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "sample_disable",
    "args": {},
    "canonical_args_hash": "sha256:44136fa355b3678a1146ad16f7e8649e",
    "idempotency_key": "operator-demo:disable-sample",
    "source": "operator_ui",
    "requested_at": "2026-06-21T19:05:00Z",
    "expires_at": "2026-06-21T19:07:00Z",
    "status": "accepted",
    "attempt_count": 1,
    "claimed_by": "openc3-bridge-worker-a",
    "claimed_at": "2026-06-21T19:05:02Z",
    "claim_expires_at": "2026-06-21T19:06:32Z",
    "required_state_fresh_after": "2026-06-21T19:04:00Z",
    "correlation_id": "cmdcorr_sample_disable_001"
  }
}
```

```json
{
  "table": "cubesat_command_results",
  "row": {
    "command_id": "22222222-2222-2222-2222-222222222222",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_sample_disable_001",
    "execution_id": "cmdexec_sample_disable_001",
    "status": "succeeded",
    "result_class": "success_when_disabled",
    "send_outcome": "confirmed",
    "openc3_target": "SAMPLE_RADIO",
    "openc3_command": "SAMPLE_DISABLE_CC",
    "openc3_args": {},
    "payload": {
      "openc3": {
        "method": "cmd",
        "target": "SAMPLE_RADIO",
        "command": "SAMPLE_DISABLE_CC",
        "args": {},
        "sent_at": "2026-06-21T19:05:04Z",
        "response": {"result": ["SAMPLE_RADIO", "SAMPLE_DISABLE_CC", {}]}
      },
      "telemetry_verifier": {
        "target": "SAMPLE_RADIO",
        "packet": "SAMPLE_HK_TLM",
        "item": "DEVICE_ENABLED",
        "condition": "equals:DISABLED",
        "before": {"value": "ENABLED"},
        "after": {"value": "DISABLED"},
        "status": "satisfied"
      },
      "state_updates": [
        {
          "table": "cubesat_latest_state",
          "state_path": "sample.device_enabled",
          "before": true,
          "after": false
        }
      ]
    }
  }
}
```

### 3. Rejected Unresolved EPS Load Shed

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "33333333-3333-3333-3333-333333333333",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "eps_load_shed_policy",
    "args": {"load": "payload"},
    "canonical_args_hash": "sha256:example-eps-load-payload",
    "idempotency_key": "agent-evt-9001:load-shed",
    "source": "ai_agent",
    "requested_at": "2026-06-21T19:10:00Z",
    "expires_at": "2026-06-21T19:12:00Z",
    "status": "rejected",
    "last_error_class": "unresolved_catalog_entry",
    "correlation_id": "cmdcorr_eps_reject_001"
  }
}
```

```json
{
  "table": "cubesat_command_results",
  "row": {
    "command_id": "33333333-3333-3333-3333-333333333333",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_eps_reject_001",
    "execution_id": "cmdexec_eps_reject_001",
    "status": "rejected",
    "result_class": "unresolved_catalog_entry",
    "send_outcome": "not_sent",
    "openc3_target": null,
    "openc3_command": null,
    "openc3_args": {},
    "payload": {
      "catalog": {
        "catalog_command_id": "eps_load_shed_policy",
        "status": "unresolved",
        "result_classification": "blocked_unresolved_mapping"
      },
      "error": {
        "class": "unresolved_catalog_entry",
        "message": "Generic EPS load shed has no approved load-to-switch policy.",
        "retryable": false
      }
    }
  }
}
```

### 4. Expired ADCS Command

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "44444444-4444-4444-4444-444444444444",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "adcs_set_sunsafe",
    "args": {"GNC_MODE": "SUNSAFE_MODE"},
    "canonical_args_hash": "sha256:example-adcs-sunsafe",
    "idempotency_key": "operator-training:adcs-sunsafe-window-1",
    "source": "operator_ui",
    "requested_at": "2026-06-21T19:15:00Z",
    "expires_at": "2026-06-21T19:16:00Z",
    "status": "expired",
    "last_error_class": "expired_command",
    "approval_id": null,
    "correlation_id": "cmdcorr_adcs_expired_001"
  }
}
```

```json
{
  "table": "cubesat_command_results",
  "row": {
    "command_id": "44444444-4444-4444-4444-444444444444",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_adcs_expired_001",
    "execution_id": "cmdexec_adcs_expired_001",
    "status": "expired",
    "result_class": "expired_command",
    "send_outcome": "not_sent",
    "openc3_target": null,
    "openc3_command": null,
    "openc3_args": {},
    "payload": {
      "catalog": {
        "catalog_command_id": "adcs_set_sunsafe",
        "human_review_required": true,
        "target": "GENERIC_ADCS",
        "command": "GENERIC_ADCS_SET_MODE_CC"
      },
      "error": {
        "class": "expired_command",
        "message": "Command expired before approval and bridge send.",
        "retryable": false
      }
    }
  }
}
```

## Validation Walkthroughs

### Agent Request To Result Row

1. Agent asks for `cfs_noop` using an idempotency key and satellite id.
2. Supabase RPC validates only catalog id and args, computes
   `canonical_args_hash`, inserts `cubesat_commands.status = queued`, and
   returns the row. It does not accept OpenC3 target/command fields.
3. Bridge atomically claims the row as `accepted`.
4. Bridge resolves `cfs_noop` in
   `docs/cubesat-openc3-command-catalog.md`: target `CFS`, command
   `CFE_ES_NOOP`, verifier `CFS CFE_ES_HKPACKET CMDCOUNTER increments`.
5. Bridge reads baseline telemetry with OpenC3 `tlm`.
6. Bridge writes a send-intent result and transitions to `running`.
7. Bridge calls OpenC3 JSON API `cmd` with structured params
   `["CFS", "CFE_ES_NOOP", {}]`.
8. Bridge polls `tlm` until `CMDCOUNTER` increments or timeout.
9. On success, bridge writes a `succeeded` result payload, updates
   `cubesat_commands.status = succeeded`, and updates
   `cubesat_latest_state` with the counter, freshness, command id, result id,
   and correlation id.

### Bridge Restart During `running`

1. Worker claims `sample_disable`, records send intent, transitions the command
   to `running`, sends `SAMPLE_RADIO SAMPLE_DISABLE_CC`, and then crashes.
2. No worker may claim that row until `claim_expires_at` passes.
3. Recovery worker claims the expired `running` row with a new `claim_token`.
4. Recovery worker reads the existing result payload. Because send intent exists
   and the command may have reached OpenC3, it must not call `cmd` again.
5. Recovery worker resumes telemetry verification for
   `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == DISABLED`.
6. If verifier succeeds, status becomes `succeeded`; if it times out or state
   contradicts the expected condition, status becomes `failed` with
   `telemetry_verifier_timeout`, `postcondition_failed`, or `ambiguous_send`.

### OpenC3 Outage

1. Worker claims `cfs_noop` as `accepted`.
2. If OpenC3 is unavailable during auth or baseline telemetry before any
   send-intent/command request, the bridge records `openc3_unavailable`,
   clears the claim, sets `retry_after`, and returns the command to `queued`
   until max attempts or expiry.
3. If OpenC3 is unavailable after send-intent or after the command HTTP request
   may have been transmitted, the bridge treats the row as `running` and
   `ambiguous_send`; it may continue read-only telemetry verification after
   OpenC3 returns, but it must not resend.
4. If retry attempts are exhausted before any send, terminal status is `failed`
   with `openc3_unavailable`; if the command expired while waiting, terminal
   status is `expired`.

## Migration Notes

Future migrations should:

- create `cubesat_commands`, `cubesat_command_results`, and
  `cubesat_latest_state`;
- add check constraints or enums for lifecycle statuses, send outcomes, source
  values, and rejection/failure classes;
- add the idempotency unique index using `satellite_id`, `catalog_version`,
  `catalog_command_id`, `idempotency_key`, and `canonical_args_hash`;
- add claim indexes on `status`, `not_before`, `retry_after`, `expires_at`,
  `priority`, and `requested_at`;
- implement enqueue/approval/claim operations as database RPCs or tightly
  scoped service-role operations so public clients cannot update status,
  claims, results, or latest state directly;
- keep OpenC3 target/command fields out of `cubesat_commands`; store resolved
  target/command only in bridge-owned result rows;
- reference existing `satellites(id)` and optionally `command_runbooks(id)`;
- preserve RLS such that agents and authenticated users may request catalog
  commands but only the bridge service account may claim, execute, write
  results, or update latest state;
- add retention/export policy for append-only result payloads and log pointers.

## Remaining Risks

- The command catalog is currently a documentation artifact. A bridge
  implementation should load it from an immutable machine-readable table or
  signed file generated from `docs/cubesat-openc3-command-catalog.md`.
- Telemetry verifiers depend on OpenC3/NOS3 target freshness. T6 should define
  the canonical latest-state map and freshness thresholds.
- Human-review approval records are specified here by shape only. A future task
  should define the operator UI/RLS flow and audit requirements.
- Some simulator commands are semantically idempotent in a desired-state sense,
  but this contract treats every send as side-effecting unless the catalog
  explicitly defines a no-send success policy.
