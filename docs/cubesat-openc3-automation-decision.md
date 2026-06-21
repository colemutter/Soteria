# CubeSat OpenC3 Automation Decision

Generated: 2026-06-21

This decision is simulator-only. It applies to the stock NOS3/OpenC3 bench
described in the Soteria CubeSat command artifacts. It is not a flight command
procedure, flight rule, spacecraft command authority, RF uplink path, or claim
of flight qualification.

## Decision

Primary automation path: the Soteria OpenC3 bridge submits approved simulator
commands to the private OpenC3 JSON API with the standard `cmd` method.

Telemetry verification path: the bridge performs synchronous JSON API reads
before and after command execution, then bounded packet polling through
`tlm`, `tlm_raw`, or `tlm_formatted` until the catalog verifier succeeds or
times out. A Streaming API subscription may maintain a freshness cache and
support diagnostics, but command success must not depend only on logs.

Diagnostic fallback: bridge-owned, non-interactive OpenC3 Script Runner/CLI
procedures may be used in the private lab bench when the JSON client path is
under investigation. They are a diagnostic fallback, not the normal Soteria
command path.

Rejected production path: direct cFS/UDP or raw packet injection is not allowed
for Soteria production automation. It bypasses the OpenC3 dictionary, command
history, check behavior, and the Supabase result trail. A human operator may
use private, lab-only UDP diagnostics to prove a network path when OpenC3 is
unavailable, but that diagnostic must not be exposed as a public command
endpoint or as a bridge fallback.

The Soteria product interface remains Supabase: agents and UI write catalog
command requests to Supabase, the private bridge executes through OpenC3, and
the bridge writes `cubesat_command_results` plus telemetry/state updates back
to Supabase.

## Source Basis

| Source | Decision-relevant fact |
| --- | --- |
| [T1 bench runbook](./cubesat-nos3-openc3-bench-runbook.md) | The NOS3/OpenC3 bench keeps OpenC3 private through IAP/SSH/VPN-style access; OpenC3 should expose `CFS` and NOS3 subsystem targets, with telemetry verified through OpenC3. |
| [T2 command catalog](./cubesat-openc3-command-catalog.md) | The first executable commands are catalog IDs such as `cfs_noop`, `radio_enable_output`, `sample_enable`, and `sample_disable`; unresolved or manual-only rows must not execute automatically. |
| [Parent task plan](../agents/cubesat-nos3-openc3-commanding-subtasks.md) | Supabase is the product I/O layer; the bridge executes through OpenC3 and writes results/state back to Supabase. |
| [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api) | External applications can send commands and retrieve telemetry without knowing binary packet formats. The API uses a token in the `Authorization` header, JSON-RPC 2.0-style requests, scope in `keyword_params`, and the `/openc3-api/api` endpoint on port `2900`. |
| [OpenC3 Scripting API](https://docs.openc3.com/docs/guides/scripting-api) | Script Runner supports `cmd(...)`, `tlm(...)`, packet waits, and no-check command variants. Standard `cmd` preserves validation, while no-check APIs bypass range or hazardous-command protections. |
| [OpenC3 Streaming API](https://docs.openc3.com/docs/development/streaming-api) | The streaming interface uses WebSockets/ActionCable to stream raw or decommutated command and telemetry packets, including realtime and historical data. |
| [OpenC3 CLI](https://docs.openc3.com/docs/getting-started/cli) | CLI script methods can list, spawn, run, inspect, and stop Script Runner scripts; CLI auth uses OpenC3 credentials and may require an offline access token. |
| [OpenC3 cFS guide](https://docs.openc3.com/docs/guides/cfs) | cFS integration uses OpenC3 targets and UDP TM/TC interfaces under OpenC3 control. The UDP interface is an implementation detail of the simulator bench, not the Soteria automation API. |

## Path Evaluation

| Path | Auth | Command shape | Telemetry shape | Idempotency | Error handling | Deployment complexity | Safety impact | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OpenC3 JSON API from bridge | `Authorization: <token>` to private `/openc3-api/api`; token derived from OpenC3 auth and held by bridge only. | JSON-RPC `cmd` with either one command string or structured target, command, args. | JSON-RPC `tlm`, `tlm_raw`, `tlm_formatted` for verifier items; optional Streaming API cache. | OpenC3 commands are side-effecting and have no native Soteria idempotency key, so Supabase claim/result state must prevent duplicates. | HTTP/auth failures, JSON-RPC errors, OpenC3 command rejections, and verifier timeouts map directly into result rows. | Low. One HTTP client, private network path, no generated scripts required. | Best fit. Keeps OpenC3 dictionary validation and avoids binary packet construction. | Adopt as primary path. |
| Bridge-generated Script Runner or CLI script | OpenC3 script credentials through env vars; Enterprise also needs `OPENC3_API_USER`; CLI script access can require an offline token. | Ruby/Python script using `cmd(...)`, `tlm(...)`, `wait_check(...)`, run by Script Runner or `openc3.sh cli script run`. | Script APIs can poll `tlm(...)`, wait for packets, and emit script output. | Harder. A spawned script may keep running across bridge restarts, so the bridge must track script ID and status. | Parse script state/output; distinguish failed script, paused script, command failure, and verifier timeout. | Medium to high. Requires script packaging, upload/location control, CLI token bootstrap, log parsing, and process cleanup. | Acceptable only if scripts use standard `cmd` and do not prompt for human input. Risk rises if scripts can call no-check APIs or `validate=False`. | Diagnostic fallback only. |
| Streaming API | Token passed to the ActionCable subscription. | Not a command submission path for Soteria. | Streams raw or decommutated packets/items such as `DECOM__TLM__CFS__CFE_ES_HKPACKET__CMDCOUNTER__CONVERTED`. | Useful for freshness and history, but not enough to prove a unique command execution by itself. | Handle disconnects, rejected subscriptions, delayed batches, and stale cache. | Medium. Requires long-lived WebSocket and reconnect logic. | Good observer. Unsafe as the sole verifier if bridge loses exact before/after correlation. | Use only for telemetry observation/cache. |
| Direct cFS/UDP/raw packet injection | No OpenC3 application auth; relies on private UDP reachability. | Binary/raw cFS packets built or injected outside OpenC3. | Raw packet counters or simulator logs unless separately decoded. | Very poor. No OpenC3 command history or bridge-level send correlation. | Ambiguous send outcomes and simulator-side errors are hard to classify. | High. Requires binary packet knowledge, ports, checksums, and target-specific packet details. | Reject. Bypasses OpenC3 checks, catalog validation surface, history, and operator tooling. | Rejected for production; lab-only human diagnostic at most. |

## Recommended Command Call Shape

The bridge must accept catalog command IDs, not arbitrary target/command text
from an agent or public endpoint. It resolves `catalog_command_id`,
`catalog_version`, `satellite_id`, and typed args against the versioned command
catalog before any OpenC3 call.

HTTP target:

```text
POST http://127.0.0.1:2900/openc3-api/api
Content-Type: application/json
Authorization: <openc3-session-token>
```

Use one JSON-RPC request per command or telemetry read. The JSON-RPC `id` must
be non-null and should be the bridge `execution_id` or a stable derivative of
it. Always include `keyword_params.scope`; the bench default is `DEFAULT`.

Preferred structured command form:

```json
{
  "jsonrpc": "2.0",
  "method": "cmd",
  "params": [
    "CFS_RADIO",
    "TO_ENABLE_OUTPUT",
    {
      "DEST_IP": "radio-sim",
      "DEST_PORT": 5011
    }
  ],
  "id": "cmdexec_20260621_radio_enable_output_001",
  "keyword_params": {
    "scope": "DEFAULT"
  }
}
```

Expected successful response shape:

```json
{
  "jsonrpc": "2.0",
  "result": [
    "CFS_RADIO",
    "TO_ENABLE_OUTPUT",
    {
      "DEST_IP": "radio-sim",
      "DEST_PORT": 5011
    }
  ],
  "id": "cmdexec_20260621_radio_enable_output_001"
}
```

Supported string command form, useful for no-argument commands:

```json
{
  "jsonrpc": "2.0",
  "method": "cmd",
  "params": [
    "CFS CFE_ES_NOOP"
  ],
  "id": "cmdexec_20260621_cfs_noop_001",
  "keyword_params": {
    "scope": "DEFAULT"
  }
}
```

String form with arguments is supported by OpenC3, but Soteria should prefer
the structured form for typed catalog args:

```text
CFS_RADIO TO_ENABLE_OUTPUT with DEST_IP 'radio-sim', DEST_PORT 5011
```

Forbidden by default:

- Do not call `cmd_no_range_check`.
- Do not call `cmd_no_hazardous_check`.
- Do not call `cmd_no_checks`.
- Do not call raw no-check variants such as `cmd_raw_no_hazardous_check` or `cmd_raw_no_checks`.
- Do not set Script Runner `cmd(..., validate=False)`.

Any range-check, hazardous-check, or all-check bypass requires all of the
following before a bridge implementation may allow it: a named bench test case,
a human approval record, a simulator-only scope flag, an explicit catalog row
that permits the bypass, and a `cubesat_command_results` record that preserves
the bypass reason. No current first-slice command needs a bypass.

## Telemetry Verification Read Path

For every command that reaches OpenC3:

1. Read the verifier baseline by JSON API before the send when the verifier
   depends on a counter, state transition, or freshness timestamp.
2. Send exactly one JSON API `cmd` request after the Supabase row is claimed
   and a send-intent result record is durable.
3. Poll JSON API telemetry until the catalog verifier succeeds or the catalog
   timeout expires.
4. Optionally use the Streaming API to maintain a packet freshness cache or to
   collect richer diagnostics, but treat it as supporting evidence unless the
   bridge can correlate the streamed packet with the exact execution window.

Converted value read:

```json
{
  "jsonrpc": "2.0",
  "method": "tlm",
  "params": [
    "CFS",
    "CFE_ES_HKPACKET",
    "CMDCOUNTER"
  ],
  "id": "tlm_cmdexec_20260621_cfs_noop_001_before",
  "keyword_params": {
    "scope": "DEFAULT"
  }
}
```

Formatted or raw reads use the same parameter shape with `method` changed to
`tlm_formatted` or `tlm_raw`. Streaming observer names should follow the
OpenC3 documented topic shape, for example:

```text
DECOM__TLM__CFS__CFE_ES_HKPACKET__CMDCOUNTER__CONVERTED
DECOM__TLM__CFS_RADIO__TO_HKPACKET__ENABLEDROUTES__CONVERTED
```

## Auth, Credential Storage, And Rotation

OpenC3 API credentials must never be stored in repository files, Supabase
command rows, command result payloads, screenshots, or application logs.

For the GCE-hosted bridge, store OpenC3 automation credentials in GCP Secret
Manager under a bridge-specific service account. If a future Supabase-hosted
component needs the secret, store only the minimum required secret in Supabase
Vault and do not mirror it into database rows. Operators keep UI credentials in
their password manager.

The bridge startup flow is:

1. Read the current OpenC3 credential secret version.
2. Obtain or refresh an OpenC3 session token through the documented auth flow.
3. Cache the session token in memory only.
4. Send JSON API requests with `Authorization: <token>`.
5. On `401` or `403`, clear the cached token, retry auth once, then fail closed
   as `failed_openc3_auth` if auth still fails.

Rotation flow:

1. Create a new OpenC3 automation credential or token.
2. Add it as a new secret version.
3. Restart or signal the bridge to reload secrets.
4. Run a non-mutating telemetry read and, if approved, `cfs_noop`.
5. Disable the old secret version after the new one is proven.

Rotate credentials after bench rebuilds, staff or access changes, suspected
exposure, failed audit, or on the project cadence chosen by T7. CLI fallback
offline tokens are separate secrets and should stay disabled or absent unless
the diagnostic fallback is actively being used.

## Result Mapping

`cubesat_command_results` is the durable bridge audit trail. T5 will define the
schema, but T4 requires these mappings:

| Condition | Result status | Error/result class | Required result payload |
| --- | --- | --- | --- |
| Catalog ID unknown | `rejected` | `unknown_command` | Requested catalog ID, catalog version, requester, no OpenC3 call. |
| Catalog row unresolved or rejected | `rejected` | Catalog row result class, such as `blocked_no_nos3_target` or `blocked_unresolved_mapping` | Catalog row, reason, no OpenC3 call. |
| Manual review required and no approval | `manual_review_required` | `human_review_required` | Catalog row, missing approval reference, no OpenC3 call. |
| Command expired before claim/send | `expired` | `expired_command` | Expiry timestamp, no OpenC3 call. |
| Precondition fails | `rejected` | `precondition_failed` | Failed precondition, verifier baseline if read, no OpenC3 command call. |
| OpenC3 auth fails | `failed` | `failed_openc3_auth` | HTTP status, redacted auth context, no token. |
| OpenC3 unavailable before send certainty | `failed` | `openc3_unavailable` | Transport error, retry count, no token. |
| HTTP request may have reached OpenC3 but no response was recorded | `failed` or `running_verification_only` | `ambiguous_send` | Send-intent timestamp, execution ID, retry prohibited unless catalog and human approval allow it. |
| JSON-RPC error object returned | `failed` | `openc3_command_error` | JSON-RPC error code/message/data, target/command/args attempted. |
| JSON-RPC result returned but verifier times out | `failed` | `telemetry_verifier_timeout` | OpenC3 result, before/after telemetry samples, timeout. |
| Verifier returns wrong postcondition | `failed` | `postcondition_failed` | OpenC3 result, verifier samples, expected condition. |
| Command result and verifier both succeed | `succeeded` | Catalog result class, such as `success_when_counter_increments` | OpenC3 result, before/after telemetry, correlation ID. |

Sample success result:

```json
{
  "command_row_id": "cmdrow_123",
  "execution_id": "cmdexec_20260621_cfs_noop_001",
  "status": "succeeded",
  "result_class": "success_when_counter_increments",
  "openc3": {
    "method": "cmd",
    "target": "CFS",
    "command": "CFE_ES_NOOP",
    "args": {},
    "jsonrpc_id": "cmdexec_20260621_cfs_noop_001",
    "response": ["CFS", "CFE_ES_NOOP", {}]
  },
  "telemetry": {
    "before": {"target": "CFS", "packet": "CFE_ES_HKPACKET", "item": "CMDCOUNTER", "value": 14},
    "after": {"target": "CFS", "packet": "CFE_ES_HKPACKET", "item": "CMDCOUNTER", "value": 15}
  }
}
```

Sample rejected result:

```json
{
  "command_row_id": "cmdrow_999",
  "execution_id": "cmdexec_20260621_radiation_protect_001",
  "status": "rejected",
  "result_class": "blocked_no_nos3_target",
  "catalog_command_id": "radiation_protect_generic",
  "openc3": null,
  "telemetry": null,
  "message": "Catalog row has no source-backed NOS3/OpenC3 target or command."
}
```

## Duplicate Execution Avoidance

OpenC3 command calls are not idempotent. The bridge must make Supabase
claiming and result recording the idempotency boundary.

Required behavior:

- Claim one queued command row atomically before any OpenC3 call.
- Compute a deterministic `idempotency_key` from at least
  `catalog_version`, `satellite_id`, `catalog_command_id`, normalized args,
  requested execution window, and requester-supplied idempotency key.
- Enforce a unique active command constraint on that idempotency key for
  queued/running commands.
- Write a durable send-intent result with `execution_id`, `openc3_jsonrpc_id`,
  target, command, args, and verifier plan before issuing the HTTP request.
- If the bridge restarts before send intent is durable, the row can be claimed
  again normally.
- If the bridge restarts after send intent but before a response, do not blindly
  resend. Rehydrate the command and run verification only when the catalog
  verifier can prove the outcome; otherwise finish as `ambiguous_send`.
- If the bridge restarts after OpenC3 response but before verifier completion,
  resume telemetry polling using the same `execution_id`.
- Only commands explicitly marked retry-safe in the catalog may be retried
  after an ambiguous send, and state-changing commands should require human
  approval before retry.

## Conceptual Dry Run

No live NOS3/OpenC3 runtime was launched for this task. These are conceptual
walkthroughs against the T2 catalog and official OpenC3 API shapes.

### Accepted: `cfs_noop`

1. Bridge receives `catalog_command_id = cfs_noop`.
2. Catalog resolves to `CFS` / `CFE_ES_NOOP`, no args, automated allowed.
3. Bridge reads `tlm("CFS", "CFE_ES_HKPACKET", "CMDCOUNTER")`; example
   baseline value is `14`.
4. Bridge sends structured `cmd` or string `cmd("CFS CFE_ES_NOOP")`.
5. Bridge polls `CMDCOUNTER` until it is greater than `14` within 10 seconds.
6. Result row is `succeeded` with `success_when_counter_increments`.

### Accepted: `radio_enable_output`

1. Bridge receives `catalog_command_id = radio_enable_output` with
   `DEST_IP = radio-sim` and `DEST_PORT = 5011`.
2. Catalog validates the exact args and private radio path precondition.
3. Bridge reads `CFS_RADIO TO_HKPACKET ENABLEDROUTES` or a freshness baseline.
4. Bridge sends `cmd("CFS_RADIO", "TO_ENABLE_OUTPUT", {"DEST_IP": "radio-sim", "DEST_PORT": 5011})`.
5. Bridge polls until `ENABLEDROUTES` changes or radio telemetry becomes fresh
   within 10 seconds.
6. Result row is `succeeded` with `success_when_radio_tlm_fresh`, or `failed`
   with verifier detail if telemetry never changes.

### Rejected: `radiation_protect_generic`

1. Bridge receives `catalog_command_id = radiation_protect_generic`.
2. Catalog row is `unresolved_rejected` and has no OpenC3 target or command.
3. Bridge writes a `rejected` result with `blocked_no_nos3_target`.
4. Bridge makes no OpenC3 JSON API, Script Runner, CLI, UDP, or raw packet call.

## Implementation Notes For T5

- The bridge should expose no public raw command endpoint. Public or agent-side
  inputs are catalog IDs plus typed, allowlisted args only.
- `cmd` is the only command method allowed for the first slice.
- Telemetry verifier definitions should live with the command catalog records:
  target, packet, item, expected condition, timeout, and failure class.
- Streaming telemetry can improve freshness and UI state, but synchronous reads
  remain the verifier of record until the bridge can prove exact streaming
  correlation.
- Script Runner/CLI diagnostics must use non-interactive scripts. A script that
  prompts, pauses, waits for manual input, or calls no-check APIs is not a
  bridge fallback.
- Direct cFS/UDP testing belongs in bench notes, not `cubesat_command_results`,
  unless T5 deliberately adds a separate diagnostic evidence table.

## Remaining Risks

- The current OpenC3 docs are source-backed but should still be checked against
  the exact NOS3-bundled OpenC3/COSMOS version during the bench run.
- OpenC3 session-token lifetime and rotation mechanics need bench confirmation.
- Some verifier packet names may differ in the live target dictionary; T3/T5
  should confirm exact packet/item names from the running OpenC3 instance.
- Ambiguous network failure after HTTP dispatch cannot be made perfectly
  idempotent for state-changing commands. The safe default is verification-only
  recovery or human-reviewed retry.
